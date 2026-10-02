"""Rolling a learner's record forward when the course on disk is a newer version.

spec/course-format.md#course-versions makes a promise per version level: patch and minor
bumps keep every existing coordinate, a major bump may move or remove them. spec/runtime.md
#course-version-changes turns that into the runtime rule implemented here. ``plan_upgrade`` is
pure — it decides from the record, its log and homework slot, and a snapshot of the new course
whether progress carries over, and builds the upgraded record. ``roll_forward`` is the one
I/O path: it reads, plans, and commits through the file store's recoverable upgrade journal.

Coordinates pass through a ``CoordinateMap`` on the way. Patch and minor bumps always use the
identity map. A major bump is refused unless a map is supplied — the seam an author-declared
migration map can later plug into without a second upgrade path.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NamedTuple

from ..course import (
    CompletionEntry,
    Course,
    HomeworkSlot,
    Position,
    Record,
    declared_level,
    parse_lesson,
)
from ..store import (
    Conflict,
    FileProgressStore,
    HomeworkWrite,
    RuntimeSnapshot,
    UpgradeCommit,
    UpgradeIdentity,
)
from ._machine import Beat, LessonShape
from ._runtime import objectives_of


class UpgradeRefusal(StrEnum):
    """Why progress cannot carry over automatically."""

    UNORDERED = "unordered"
    """Versions that cannot be ordered: unparseable, or differing only in pre-release/build."""

    DOWNGRADE = "downgrade"
    MAJOR = "major"
    MISSING = "missing-coordinates"
    PENDING_FEEDBACK = "pending-feedback"


@dataclass(frozen=True)
class CoordinateMap:
    """Old → new coordinate translation applied while upgrading. Unlisted coordinates keep
    their value, so the empty map is the identity every patch and minor bump uses."""

    moves: tuple[tuple[str, str], ...] = ()

    def __call__(self, coordinate: str) -> str:
        return dict(self.moves).get(coordinate, coordinate)


@dataclass(frozen=True)
class UpgradeTarget:
    """What the new course version offers, read once from disk so planning stays pure."""

    course_id: str
    version: str
    coordinates: frozenset[str]
    objective_ids: frozenset[str]
    shapes: dict[str, LessonShape] = field(default_factory=dict)

    @classmethod
    def of(cls, course: Course) -> UpgradeTarget:
        shapes: dict[str, LessonShape] = {}
        objectives: set[str] = set()
        for lesson in course.lessons():
            parsed = parse_lesson(lesson.path)
            shapes[lesson.coordinate] = LessonShape(
                has_exercise=parsed.section("exercise") is not None,
                is_phase_end=course.is_last_in_phase(lesson.coordinate),
            )
            objectives.update(o.id for o in objectives_of(lesson))
        return cls(course.id, course.version, frozenset(shapes), frozenset(objectives), shapes)


@dataclass(frozen=True)
class UpgradePlan:
    course_id: str
    from_version: str
    to_version: str
    level: str
    refusal: UpgradeRefusal | None = None
    missing: tuple[str, ...] = ()
    record: Record | None = None
    homework: HomeworkSlot | None = None
    homework_changed: bool = False
    lesson_restarted: bool = False
    dropped_objectives: tuple[str, ...] = ()
    """Met objectives the new version no longer declares: removed from the record."""

    @property
    def ok(self) -> bool:
        return self.refusal is None

    def summary(self) -> str:
        """One plain sentence about what happens to existing progress."""
        name = f"{self.course_id} {self.from_version} -> {self.to_version}"
        if self.ok:
            restart = (
                " The current lesson restarts at its first beat because its shape changed."
                if self.lesson_restarted
                else ""
            )
            dropped = (
                f" Objective(s) {', '.join(self.dropped_objectives)} no longer exist in "
                f"{self.to_version}, so they are no longer recorded as met."
                if self.dropped_objectives
                else ""
            )
            return (
                f"Progress carries over ({name}, {self.level}): position, completed "
                f"lessons, objectives and homework are kept.{restart}{dropped}"
            )
        return f"Progress is not resumable ({name}): {self.reason()}"

    def reason(self) -> str:
        if self.refusal is UpgradeRefusal.PENDING_FEEDBACK:
            return (
                "quiz feedback must be presented and acknowledged before changing course version."
            )
        if self.refusal is UpgradeRefusal.DOWNGRADE:
            return (
                f"{self.to_version} is older than the {self.from_version} this record was "
                "started on, and progress never carries backwards automatically."
            )
        if self.refusal is UpgradeRefusal.MAJOR:
            return (
                "this is a major version change, which may move or remove lessons, so "
                "progress cannot carry over automatically."
            )
        if self.refusal is UpgradeRefusal.MISSING:
            return (
                f"{self.to_version} no longer has {', '.join(self.missing)}, which this "
                "record refers to, so progress cannot carry over automatically."
            )
        return (
            f"{self.from_version} and {self.to_version} cannot be ordered as an upgrade, so "
            "progress cannot carry over automatically."
        )

    def refusal_message(self) -> str:
        return (
            f"the record was started against {self.course_id} {self.from_version}, but "
            f"{self.course_id} on disk is {self.to_version}: {self.reason()} The record is "
            f"unchanged and still resumes on {self.from_version}."
        )


def plan_upgrade(
    record: Record,
    log: Sequence[CompletionEntry],
    slot: HomeworkSlot | None,
    target: UpgradeTarget,
    mapping: CoordinateMap | None = None,
) -> UpgradePlan:
    """Decide whether ``record`` rolls forward to ``target``, and build the upgraded record.

    Everything except ``course_version`` (and coordinates the map moves) is preserved, except
    that a met objective the new version no longer declares is dropped and reported. Log
    entries are never rewritten: they keep their historical ``course_version`` and are only
    checked to name coordinates the new version still has. An in-lesson beat the new lesson
    no longer has (an exercise beat with no exercise, a ceremony off a phase end) restarts that
    lesson at its first beat rather than resuming somewhere that does not exist.
    """
    base = UpgradePlan(
        record.course_id,
        record.course_version,
        target.version,
        declared_level(record.course_version, target.version),
    )
    if base.level in ("unparseable", "none"):
        return _refused(base, UpgradeRefusal.UNORDERED)
    if base.level == "downgrade":
        return _refused(base, UpgradeRefusal.DOWNGRADE)
    if base.level == "major" and mapping is None:
        return _refused(base, UpgradeRefusal.MAJOR)
    move = mapping or CoordinateMap()

    referenced: list[tuple[str, str]] = [("position", record.position.coordinate)]
    referenced += [("completed", c) for c in record.completed]
    referenced += [("artifact", a.coordinate) for a in record.artifacts]
    if slot is not None:
        referenced += [("homework", slot.coordinate)]
        referenced += [("queued homework", q.coordinate) for q in slot.queued]
    referenced += [("completion log", e.coordinate) for e in log]
    missing = [f"{what} {c}" for what, c in referenced if move(c) not in target.coordinates]
    dropped = tuple(
        dict.fromkeys(o.id for o in record.objectives_met if o.id not in target.objective_ids)
    )
    if missing:
        return _refused(base, UpgradeRefusal.MISSING, tuple(dict.fromkeys(missing)))

    phase, lesson = move(record.position.coordinate).split(".")
    position = Position(
        phase=int(phase),
        lesson=int(lesson),
        beat=record.position.beat,
        question_index=record.position.question_index,
    )
    restarted = not _beat_fits(position.beat, target.shapes.get(position.coordinate))
    if restarted:
        position = position.model_copy(update={"beat": None, "question_index": None})
    upgraded = record.model_copy(
        update={
            "course_version": target.version,
            "position": position,
            "completed": [move(c) for c in record.completed],
            "objectives_met": [o for o in record.objectives_met if o.id not in dropped],
            "artifacts": [
                a.model_copy(update={"coordinate": move(a.coordinate)}) for a in record.artifacts
            ],
        }
    )
    remapped = (
        slot.model_copy(
            update={
                "coordinate": move(slot.coordinate),
                "queued": [
                    q.model_copy(update={"coordinate": move(q.coordinate)}) for q in slot.queued
                ],
            }
        )
        if slot is not None
        else None
    )
    return UpgradePlan(
        base.course_id,
        base.from_version,
        base.to_version,
        base.level,
        record=upgraded,
        homework=remapped,
        homework_changed=remapped != slot,
        lesson_restarted=restarted,
        dropped_objectives=dropped,
    )


def _refused(
    base: UpgradePlan, refusal: UpgradeRefusal, missing: tuple[str, ...] = ()
) -> UpgradePlan:
    return UpgradePlan(
        base.course_id, base.from_version, base.to_version, base.level, refusal, missing
    )


def _beat_fits(beat: str | None, shape: LessonShape | None) -> bool:
    if beat is None or shape is None or beat not in set(Beat):
        return True
    if Beat(beat) in (Beat.EXERCISE, Beat.GATE_EXERCISE):
        return shape.has_exercise
    if Beat(beat) is Beat.CEREMONY:
        return shape.is_phase_end
    return True


class RollForward(NamedTuple):
    plan: UpgradePlan | None
    """``None`` when no record exists or it already names the course's version."""

    snapshot: RuntimeSnapshot | None
    """The current coherent snapshot: upgraded on success, untouched on refusal."""


def preview_upgrade(
    store: FileProgressStore,
    course: Course,
    learner_id: str,
    mapping: CoordinateMap | None = None,
) -> RollForward:
    """Plan without writing — what ``skilling start`` reports before switching versions."""
    snapshot = store.read_runtime_snapshot(learner_id, course.id)
    if snapshot is None or snapshot.record.course_version == course.version:
        return RollForward(None, snapshot)
    if snapshot.feedback is not None:
        base = UpgradePlan(
            course.id,
            snapshot.record.course_version,
            course.version,
            declared_level(snapshot.record.course_version, course.version),
        )
        return RollForward(_refused(base, UpgradeRefusal.PENDING_FEEDBACK), snapshot)
    log = store.get_log(learner_id, course.id)
    slot, _ = store.get_homework(learner_id, course.id)
    return RollForward(
        plan_upgrade(snapshot.record, log, slot, UpgradeTarget.of(course), mapping), snapshot
    )


def roll_forward(
    store: FileProgressStore,
    course: Course,
    learner_id: str,
    mapping: CoordinateMap | None = None,
) -> RollForward:
    """Upgrade the stored record in place when ``plan_upgrade`` allows it.

    Compare-and-swap on the record revision and scratch bytes; an identical committed upgrade
    replays. When a concurrent writer wins, the record already naming this version counts as
    success; anything else re-raises the ``Conflict``. A refusal writes nothing.
    """
    snapshot = store.read_runtime_snapshot(learner_id, course.id)
    if snapshot is None or snapshot.record.course_version == course.version:
        return RollForward(None, snapshot)
    if snapshot.feedback is not None:
        base = UpgradePlan(
            course.id,
            snapshot.record.course_version,
            course.version,
            declared_level(snapshot.record.course_version, course.version),
        )
        return RollForward(_refused(base, UpgradeRefusal.PENDING_FEEDBACK), snapshot)
    log = store.get_log(learner_id, course.id)
    slot, slot_revision = store.get_homework(learner_id, course.id)
    plan = plan_upgrade(snapshot.record, log, slot, UpgradeTarget.of(course), mapping)
    if plan.record is None:
        return RollForward(plan, snapshot)
    commit = UpgradeCommit(
        UpgradeIdentity(learner_id, course.id, plan.from_version, plan.to_version),
        snapshot.revision,
        snapshot.scratch,
        plan.record,
        b"" if plan.lesson_restarted else snapshot.scratch,
        HomeworkWrite(slot_revision, plan.homework) if plan.homework_changed else None,
    )
    try:
        return RollForward(plan, store.commit_upgrade(commit).snapshot)
    except Conflict:
        current = store.read_runtime_snapshot(learner_id, course.id)
        if current is not None and current.record.course_version == course.version:
            return RollForward(plan, current)
        raise
