"""Runtime machinery every conforming tutor needs, with no language model in it.

The delivery loop lives in ``machine``; persistence lives in ``store``. This module is the
part between them: what a completion actually writes, in what order, and what it must
refuse to write twice. A model-backed tutor and a text walker should both call these
functions rather than reimplementing the write set — reimplementing it is how badges stop
reaching records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import lesson as md
from .errors import SPEC_MAJOR, SPEC_MINOR
from .loader import Course, ResolvedLesson
from .models import (
    Assignment,
    CompletionEntry,
    HomeworkArchiveEntry,
    HomeworkSlot,
    Position,
    Record,
    Requirement,
)
from .store.protocol import ProgressStore

SPEC_VERSION = f"{SPEC_MAJOR}.{SPEC_MINOR}"


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def today_in(zone: str, now: datetime | None = None) -> date:
    """Today's date in the record's timezone — the streak is defined in local days."""
    moment = now or utc_now()
    try:
        return moment.astimezone(ZoneInfo(zone)).date()
    except (ZoneInfoNotFoundError, ValueError):
        return moment.astimezone(ZoneInfo("UTC")).date()


def next_streak(last_activity: date | None, today: date, current: int) -> int:
    """Yesterday → increment. Today → unchanged. Older or unset → 1."""
    if last_activity is None:
        return 1
    if last_activity == today:
        return max(current, 1)
    if last_activity == today - timedelta(days=1):
        return current + 1
    return 1


def new_record(
    course: Course,
    learner_id: str,
    *,
    zone: str = "UTC",
    now: datetime | None = None,
) -> Record:
    today = today_in(zone, now)
    first = course.first_lesson
    return Record(
        learner_id=learner_id,
        course_id=course.id,
        course_version=course.version,
        spec_version=SPEC_VERSION,
        position=Position(phase=first.phase, lesson=first.number),
        completed=[],
        skills_unlocked=[],
        started_at=today,
        last_activity=today,
        timezone=zone,
        streak_days=0,
    )


def load_or_create(
    store: ProgressStore,
    course: Course,
    learner_id: str,
    *,
    zone: str = "UTC",
    now: datetime | None = None,
) -> tuple[Record, str | None]:
    found = store.get_record(learner_id, course.id)
    if found:
        return found
    record = new_record(course, learner_id, zone=zone, now=now)
    revision = store.put_record(record, None)
    return record, revision


@dataclass
class CompletionOutcome:
    record: Record
    revision: str | None
    already_completed: bool = False
    badges_awarded: list[str] = field(default_factory=list)
    phase_completed: int | None = None
    homework_placed: bool = False
    homework_queued: bool = False


def skills_for(lesson: ResolvedLesson) -> list[str]:
    parsed = md.parse_lesson(lesson.path)
    return list(parsed.frontmatter.skills_unlocked) if parsed.frontmatter else []


def assignment_from_lesson(
    lesson: ResolvedLesson, *, now: datetime | None = None
) -> Assignment | None:
    parsed = md.parse_lesson(lesson.path)
    section = parsed.section("homework")
    if section is None:
        return None
    hw = md.parse_homework(section.body)
    if not hw.complete:
        return None
    assert hw.title and hw.objective and hw.submission
    return Assignment(
        coordinate=lesson.coordinate,
        title=hw.title,
        objective=hw.objective,
        requirements=[Requirement(text=t) for t in hw.requirements],
        stretch_goals=[Requirement(text=t) for t in hw.stretch_goals],
        submission=hw.submission,
        unlocked_at=now or utc_now(),
    )


def complete_lesson(
    store: ProgressStore,
    course: Course,
    record: Record,
    revision: str | None,
    lesson: ResolvedLesson,
    *,
    now: datetime | None = None,
) -> CompletionOutcome:
    """The completion write set.

    Idempotent by contract: completing an already-completed coordinate changes nothing —
    not the completed set, not the log, not the streak, not the badges. A learner may
    revisit any lesson; revisiting is not completing.

    The log is appended *before* the record is written, so no observable state can ever
    show a completion without its log entry.
    """
    if record.has_completed(lesson.coordinate):
        return CompletionOutcome(record=record, revision=revision, already_completed=True)

    moment = now or utc_now()
    today = today_in(record.timezone, moment)

    store.append_completion(
        record.learner_id,
        record.course_id,
        CompletionEntry(
            coordinate=lesson.coordinate,
            title=lesson.title,
            completed_at=moment,
            course_version=course.version,
        ),
    )

    completed = [*record.completed, lesson.coordinate]
    declared = skills_for(lesson)
    awarded = [b for b in declared if b not in record.skills_unlocked]

    following = course.next_lesson(lesson.coordinate)
    position = (
        Position(phase=following.phase, lesson=following.number)
        if following
        else Position(phase=lesson.phase, lesson=lesson.number)
    )

    updated = record.model_copy(
        update={
            "completed": completed,
            "position": position,
            "skills_unlocked": [*record.skills_unlocked, *awarded],
            "last_activity": today,
            "streak_days": next_streak(record.last_activity, today, record.streak_days),
        }
    )
    new_revision = store.put_record(updated, revision)

    outcome = CompletionOutcome(
        record=updated,
        revision=new_revision,
        badges_awarded=awarded,
    )

    if course.is_last_in_phase(lesson.coordinate):
        outcome.phase_completed = lesson.phase
        outcome = _run_ceremony(store, course, updated, lesson, outcome, moment)

    return outcome


def _run_ceremony(
    store: ProgressStore,
    course: Course,
    record: Record,
    lesson: ResolvedLesson,
    outcome: CompletionOutcome,
    moment: datetime,
) -> CompletionOutcome:
    """Award any outstanding badges for the phase, then fill the homework slot.

    Phase completion itself is not stored: it is derived from the phase's lessons and the
    record's completed set, like every other count in this format.
    """
    phase = course.phase_at(lesson.phase)
    if phase:
        outstanding: list[str] = []
        for entry in phase.lessons:
            if entry.coordinate not in record.completed or not entry.path.is_file():
                continue
            for badge in skills_for(entry):
                if badge not in record.skills_unlocked and badge not in outstanding:
                    outstanding.append(badge)
        if outstanding:
            updated = record.model_copy(
                update={"skills_unlocked": [*record.skills_unlocked, *outstanding]}
            )
            outcome.revision = store.put_record(updated, outcome.revision)
            outcome.record = updated
            outcome.badges_awarded = [*outcome.badges_awarded, *outstanding]

    if not lesson.homework:
        return outcome

    assignment = assignment_from_lesson(lesson, now=moment)
    if assignment is None:
        return outcome

    active, slot_revision = store.get_homework(record.learner_id, record.course_id)
    if active is None:
        store.put_homework(
            record.learner_id,
            record.course_id,
            HomeworkSlot(**assignment.model_dump()),
            slot_revision,
        )
        outcome.homework_placed = True
    elif active.coordinate != assignment.coordinate and not any(
        q.coordinate == assignment.coordinate for q in active.queued
    ):
        # One slot per learner: a second assignment queues rather than overwriting.
        store.put_homework(
            record.learner_id,
            record.course_id,
            active.model_copy(update={"queued": [*active.queued, assignment]}),
            slot_revision,
        )
        outcome.homework_queued = True

    return outcome


def submit_homework(
    store: ProgressStore,
    learner_id: str,
    course_id: str,
    coordinate: str,
    *,
    now: datetime | None = None,
) -> HomeworkArchiveEntry | None:
    """Archive the active assignment and reset the slot, loading any queued assignment.

    Idempotent per assignment instance: a retried submit of something already archived is a
    no-op that returns the archived result rather than archiving it twice.
    """
    active, revision = store.get_homework(learner_id, course_id)

    if active is None or active.coordinate != coordinate:
        for entry in reversed(store.get_homework_archive(learner_id, course_id)):
            if entry.coordinate == coordinate:
                return entry
        return None

    entry = HomeworkArchiveEntry(
        coordinate=active.coordinate,
        title=active.title,
        requirements=active.requirements,
        stretch_goals=active.stretch_goals,
        submitted_at=now or utc_now(),
    )
    store.append_homework_archive(learner_id, course_id, entry)

    if active.queued:
        head, *rest = active.queued
        store.put_homework(
            learner_id,
            course_id,
            HomeworkSlot(**head.model_dump(), queued=rest),
            revision,
        )
    else:
        store.put_homework(learner_id, course_id, None, revision)

    return entry
