"""Runtime-owned deterministic preparation of recoverable lesson completion."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

from ..course import (
    Assignment,
    CompletionEntry,
    Course,
    HomeworkSlot,
    Position,
    Record,
    Requirement,
    ResolvedLesson,
    next_streak,
    parse_homework,
    parse_lesson,
    utc_now,
)
from ..course import (
    today_in as today_in,
)
from ..store import (
    CompletionCommit,
    CompletionReceipt,
    Conflict,
    HomeworkWrite,
    ProgressStore,
    RecoveryRequired,
    require_store,
)
from ._hooks import NO_HOOKS, Dispatcher, EventName


@dataclass(frozen=True)
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
    """Prepare all semantic effects before handing one write set to the store.

    Recovery and retries emit no hooks. An uninterrupted new commit emits best-effort
    events after its receipt is durable; a process exit in between can omit those events.
    """
    require_store(store)
    before = store.get_record(record.learner_id, course.id)
    if before is None:
        raise Conflict("record.yaml", revision, None)
    if before[0].has_completed(lesson.coordinate):
        return CompletionOutcome(*before, already_completed=True)
    if before[1] != revision:
        raise Conflict("record.yaml", revision, before[1])
    log = store.get_log(record.learner_id, course.id)
    slot, slot_revision = store.get_homework(record.learner_id, course.id)
    store.get_completion_receipt(record.learner_id, course.id)
    after = store.get_record(record.learner_id, course.id)
    if after is None:
        raise Conflict("record.yaml", revision, None)
    record, current_revision = after
    if record.has_completed(lesson.coordinate):
        return CompletionOutcome(record, current_revision, already_completed=True)
    if current_revision != before[1] or current_revision != revision:
        raise Conflict("record.yaml", revision, current_revision)
    if any(e.coordinate == lesson.coordinate and e.course_version == course.version for e in log):
        raise RecoveryRequired(
            "A legacy completion log disagrees with the record and has no recoverable intent; "
            "preserve state for inspection instead of appending another entry."
        )
    moment = now or utc_now()
    today = today_in(record.timezone, moment)
    completed = [*record.completed, lesson.coordinate]
    awarded = [b for b in skills_for(lesson) if b not in record.skills_unlocked]
    phase_completed = lesson.phase if course.is_last_in_phase(lesson.coordinate) else None
    if phase_completed is not None:
        phase = course.phase_at(lesson.phase)
        if phase:
            for entry in phase.lessons:
                if entry.coordinate in completed and entry.path.is_file():
                    for badge in skills_for(entry):
                        if badge not in record.skills_unlocked and badge not in awarded:
                            awarded.append(badge)
    homework = None
    placed, queued = False, False
    if phase_completed is not None and lesson.homework:
        assignment = assignment_from_lesson(lesson, now=moment)
        if assignment is not None:
            if slot is None:
                homework = HomeworkWrite(slot_revision, HomeworkSlot(**assignment.model_dump()))
                placed = True
            elif slot.coordinate != assignment.coordinate and not any(
                q.coordinate == assignment.coordinate for q in slot.queued
            ):
                homework = HomeworkWrite(
                    slot_revision, slot.model_copy(update={"queued": [*slot.queued, assignment]})
                )
                queued = True
    following = course.next_lesson(lesson.coordinate)
    position = Position(
        phase=following.phase if following else lesson.phase,
        lesson=following.number if following else lesson.number,
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
    identity = json.dumps(
        [record.learner_id, record.course_id, course.version, lesson.coordinate],
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    receipt = CompletionReceipt(
        hashlib.sha256(identity).hexdigest(),
        record.learner_id,
        record.course_id,
        course.version,
        lesson.coordinate,
        moment,
        tuple(awarded),
        phase_completed,
        placed,
        queued,
    )
    result = store.commit_completion(
        CompletionCommit(
            receipt,
            current_revision,
            updated,
            tuple(log),
            CompletionEntry(
                coordinate=lesson.coordinate,
                title=lesson.title,
                completed_at=moment,
                course_version=course.version,
            ),
            homework,
        )
    )
    if result.receipt.coordinate not in result.record.completed:
        raise RecoveryRequired(
            "Completion receipt is not reflected in its returned record snapshot"
        )
    if result.replayed:
        return CompletionOutcome(result.record, result.revision, already_completed=True)
    outcome = CompletionOutcome(
        result.record,
        result.revision,
        badges_awarded=list(result.receipt.badges_awarded),
        phase_completed=result.receipt.phase_completed,
        homework_placed=result.receipt.homework_placed,
        homework_queued=result.receipt.homework_queued,
    )
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
