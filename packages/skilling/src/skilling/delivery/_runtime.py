"""Runtime machinery every conforming tutor needs, with no language model in it.

The delivery loop lives in ``machine``; persistence lives in ``store``. This module is the
part between them: what a completion actually writes, in what order, and what it must
refuse to write twice. A model-backed tutor and a text walker should both call these
functions rather than reimplementing the write set — reimplementing it is how badges stop
reaching records.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import NamedTuple

from ..conformance import SPEC_MAJOR, SPEC_MINOR
from ..course import (
    Assignment,
    Capability,
    CompletionEntry,
    Course,
    HomeworkArchiveEntry,
    HomeworkSlot,
    Objective,
    ObjectiveMet,
    Position,
    Record,
    Requirement,
    ResolvedLesson,
    next_streak,
    parse_homework,
    parse_lesson,
    today_in,
    utc_now,
)
from ..store import ProgressStore
from ._hooks import NO_HOOKS, Dispatcher, EventName, new_anonymous_id

SPEC_VERSION = f"{SPEC_MAJOR}.{SPEC_MINOR}"


class StoredRecord(NamedTuple):
    record: Record
    revision: str | None


class ObjectivesMarked(NamedTuple):
    record: Record
    revision: str | None
    newly_met: list[str]


def load_or_create(
    store: ProgressStore,
    course: Course,
    learner_id: str,
    *,
    zone: str = "UTC",
    now: datetime | None = None,
) -> StoredRecord:
    found = store.get_record(learner_id, course.id)
    if found:
        return StoredRecord(*found)
    record = Record.new(course, learner_id, zone=zone, now=now)
    revision = store.put_record(record, None)
    return StoredRecord(record, revision)


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
    parsed = parse_lesson(lesson.path)
    return list(parsed.frontmatter.skills_unlocked) if parsed.frontmatter else []


def assignment_from_lesson(
    lesson: ResolvedLesson, *, now: datetime | None = None
) -> Assignment | None:
    parsed = parse_lesson(lesson.path)
    section = parsed.section("homework")
    if section is None:
        return None
    hw = parse_homework(section.body)
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
    hooks: Dispatcher = NO_HOOKS,
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
        outcome = _run_ceremony(store, course, updated, lesson, outcome, moment, hooks=hooks)

    # Events fire after the writes, so a sink can never observe a completion the record does
    # not yet show.
    for badge in outcome.badges_awarded:
        hooks.emit(EventName.BADGE_AWARDED, outcome.record, occurred_at=moment, badge_id=badge)
    hooks.emit(
        EventName.LESSON_COMPLETED,
        outcome.record,
        occurred_at=moment,
        coordinate=lesson.coordinate,
        title=lesson.title,
    )
    if outcome.phase_completed is not None:
        hooks.emit(
            EventName.PHASE_COMPLETED,
            outcome.record,
            occurred_at=moment,
            phase=outcome.phase_completed,
            badges_awarded=outcome.badges_awarded,
        )
    if course.completed_count(outcome.record.completed) >= course.lesson_count:
        hooks.emit(EventName.COURSE_COMPLETED, outcome.record, occurred_at=moment)

    return outcome


def _run_ceremony(
    store: ProgressStore,
    course: Course,
    record: Record,
    lesson: ResolvedLesson,
    outcome: CompletionOutcome,
    moment: datetime,
    *,
    hooks: Dispatcher = NO_HOOKS,
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


def set_telemetry_consent(
    store: ProgressStore,
    record: Record,
    revision: str | None,
    opt_in: bool,
) -> StoredRecord:
    """Record the learner's answer, and assign an anonymous id on the first yes.

    The id is write-once and never derived from ``learner_id``: a learner who says yes gets a
    fresh pseudonym, and a learner who later says no keeps it rather than having it recycled.
    """
    telemetry = record.telemetry.model_copy(update={"opt_in": opt_in})
    if opt_in and not telemetry.anonymous_id:
        telemetry = telemetry.model_copy(update={"anonymous_id": new_anonymous_id()})

    updated = record.model_copy(update={"telemetry": telemetry})
    return StoredRecord(updated, store.put_record(updated, revision))


def objectives_of(lesson: ResolvedLesson) -> list[Objective]:
    parsed = parse_lesson(lesson.path)
    return list(parsed.frontmatter.objectives) if parsed.frontmatter else []


def settleable(lesson: ResolvedLesson, capabilities: Iterable[Capability]) -> list[Objective]:
    """The objectives this runtime is *permitted* to settle, given what it can observe.

    A ``practice`` objective additionally needs a ``verify`` clause: without one there is
    nothing saying what to look for, so even a runtime that can look cannot honestly settle it.
    """
    held = set(capabilities)
    out: list[Objective] = []
    for objective in objectives_of(lesson):
        settles = objective.settled_by()
        if settles is None or settles[0] not in held:
            continue
        if objective.kind == "practice" and not objective.verify:
            continue
        out.append(objective)
    return out


def mark_objectives_met(
    store: ProgressStore,
    record: Record,
    revision: str | None,
    lesson: ResolvedLesson,
    met: Iterable[str],
    capabilities: Iterable[Capability] = (),
    *,
    now: datetime | None = None,
) -> ObjectivesMarked:
    """Record the objectives a runtime has genuinely established. Returns the new ids.

    The capability rule is enforced *here* rather than trusted to the caller, for the same
    reason telemetry consent lives in the dispatcher: a runtime that claims more than it can
    observe must not be *able* to write it. Evidence follows from the kind, so a caller cannot
    label an observation as an explanation either.

    A quiz is never grounds for any of this. It settles nothing.
    """
    permitted = {o.id: o for o in settleable(lesson, capabilities)}
    fresh = [oid for oid in met if oid in permitted and not record.has_met(oid)]
    if not fresh:
        return ObjectivesMarked(record, revision, [])

    today = today_in(record.timezone, now or utc_now())
    entries = []
    for oid in fresh:
        settles = permitted[oid].settled_by()
        assert settles is not None
        entries.append(ObjectiveMet(id=oid, at=today, evidence=settles[1]))  # type: ignore[arg-type]

    updated = record.model_copy(update={"objectives_met": [*record.objectives_met, *entries]})
    return ObjectivesMarked(updated, store.put_record(updated, revision), fresh)


def submit_homework(
    store: ProgressStore,
    learner_id: str,
    course_id: str,
    coordinate: str,
    *,
    now: datetime | None = None,
    hooks: Dispatcher = NO_HOOKS,
    record: Record | None = None,
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

    if record is not None:
        hooks.emit(
            EventName.HOMEWORK_SUBMITTED,
            record,
            occurred_at=entry.submitted_at,
            coordinate=entry.coordinate,
            verdicts=[r.verdict for r in entry.requirements],
        )

    return entry
