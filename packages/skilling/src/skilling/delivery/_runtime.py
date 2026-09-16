"""Record initialization, objective transforms, consent and homework submission.

Recoverable lesson completion is prepared in ``_completion``; all public runtime functions
remain re-exported by ``delivery``. This module keeps the other runtime-owned semantics.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import NamedTuple

from ..conformance import SPEC_MAJOR, SPEC_MINOR
from ..course import (
    Attestation,
    Capability,
    Course,
    HomeworkArchiveEntry,
    HomeworkSlot,
    Objective,
    ObjectiveMet,
    Record,
    ResolvedLesson,
    parse_lesson,
    today_in,
    utc_now,
)
from ..store import (
    Conflict,
    InvalidSubmissionToken,
    ProgressStore,
    SubmissionCommit,
    SubmissionReceipt,
    SubmissionToken,
    require_store,
)
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
    attestation: Attestation | None = None,
    now: datetime | None = None,
) -> ObjectivesMarked:
    """Record the objectives a runtime has genuinely established. Returns the new ids.

    The capability rule is enforced *here* rather than trusted to the caller, for the same
    reason telemetry consent lives in the dispatcher: a runtime that claims more than it can
    observe must not be *able* to write it. Evidence follows from the kind, so a caller cannot
    label an observation as an explanation either.

    ``attestation``, since 1.3, is applied to observed entries in this batch — an observed
    claim with no attestation is, like one beyond capability, unwritable rather than merely
    ignored, so it is silently excluded from what gets written. ``explained``/``homework``
    entries ignore it.

    A quiz is never grounds for any of this. It settles nothing.
    """
    permitted = {o.id: o for o in settleable(lesson, capabilities)}
    candidates = [oid for oid in met if oid in permitted and not record.has_met(oid)]
    if not candidates:
        return ObjectivesMarked(record, revision, [])

    today = today_in(record.timezone, now or utc_now())
    entries = []
    fresh = []
    for oid in candidates:
        settles = permitted[oid].settled_by()
        assert settles is not None
        _, evidence = settles
        if evidence == "observed" and attestation is None:
            continue
        entries.append(
            ObjectiveMet(
                id=oid,
                at=today,
                evidence=evidence,  # type: ignore[arg-type]
                provenance=attestation if evidence == "observed" else None,
            )
        )
        fresh.append(oid)

    if not fresh:
        return ObjectivesMarked(record, revision, [])

    updated = record.model_copy(update={"objectives_met": [*record.objectives_met, *entries]})
    return ObjectivesMarked(updated, store.put_record(updated, revision), fresh)


def settle_objective(
    store: ProgressStore,
    record: Record,
    revision: str | None,
    lesson: ResolvedLesson,
    objective_id: str,
    capabilities: Iterable[Capability],
    *,
    attestation: Attestation | None = None,
    now: datetime | None = None,
) -> ObjectivesMarked:
    """One objective, capability-enforced, provenance-required for observed evidence.

    Unlike ``mark_objectives_met``'s batch, best-effort marking, a caller settling one named
    objective deserves to know exactly why it was refused: raises ``ValueError`` naming the
    failed precondition rather than writing a weaker entry.
    """
    objective = next((o for o in objectives_of(lesson) if o.id == objective_id), None)
    if objective is None:
        raise ValueError(f"lesson {lesson.coordinate!r} has no objective {objective_id!r}")

    settles = objective.settled_by()
    if settles is None:
        raise ValueError(f"objective {objective_id!r} (kind {objective.kind!r}) settles nothing")
    capability, evidence = settles

    if capability not in set(capabilities):
        raise ValueError(
            f"objective {objective_id!r} needs the {capability.value!r} capability to "
            "settle, which this runtime does not hold"
        )

    if objective.kind == "practice" and not objective.verify:
        raise ValueError(
            f"objective {objective_id!r} has no verify clause, so it cannot be settled"
        )

    if evidence == "observed" and attestation is None:
        raise ValueError(
            "observed evidence requires provenance: what was checked, which verify sentence, "
            "which host — recorded because the attestation cannot be verified"
        )

    if record.has_met(objective_id):
        return ObjectivesMarked(record, revision, [])

    today = today_in(record.timezone, now or utc_now())
    entry = ObjectiveMet(
        id=objective_id,
        at=today,
        evidence=evidence,  # type: ignore[arg-type]
        provenance=attestation if evidence == "observed" else None,
    )
    updated = record.model_copy(update={"objectives_met": [*record.objectives_met, entry]})
    return ObjectivesMarked(updated, store.put_record(updated, revision), [objective_id])


def submit_homework(
    store: ProgressStore,
    learner_id: str,
    course_id: str,
    coordinate: str,
    *,
    token: str,
    now: datetime | None = None,
    hooks: Dispatcher = NO_HOOKS,
    record: Record | None = None,
) -> HomeworkArchiveEntry:
    """Commit only the separately confirmed checked instance; replay its original archive.

    Tokens bind a checked slot, not consent. Recovery/replay emits no hooks; a crash after
    durability can omit the new commit's best-effort notification.
    """
    identity = SubmissionToken.parse(token)
    if (identity.learner_id, identity.course_id, identity.coordinate) != (
        learner_id,
        course_id,
        coordinate,
    ):
        raise InvalidSubmissionToken("Token belongs to a different checked assignment")
    require_store(store)
    accepted = store.get_submission_receipt(learner_id, course_id, token)
    if accepted is not None:
        return SubmissionReceipt.checked(accepted, token).archive
    current = store.get_record(learner_id, course_id)
    if current is None:
        raise Conflict("submission record stream", identity.course_version, None)
    if current[0].course_version != identity.course_version:
        raise InvalidSubmissionToken("Token belongs to a different course version")
    active, revision = store.get_homework(learner_id, course_id)
    if active is None or revision != identity.slot_revision:
        raise Conflict("homework/active.yaml", identity.slot_revision, revision)
    assert revision is not None
    checked = SubmissionToken.for_slot(
        learner_id, course_id, identity.course_version, active, revision
    )
    if checked != identity:
        raise Conflict("homework assignment instance", identity.instance_id, checked.instance_id)

    entry = HomeworkArchiveEntry(
        coordinate=active.coordinate,
        title=active.title,
        requirements=active.requirements,
        stretch_goals=active.stretch_goals,
        submitted_at=now or utc_now(),
    )
    if active.queued:
        head, *rest = active.queued
        following = HomeworkSlot(**head.model_dump(), queued=rest)
    else:
        following = None
    receipt = SubmissionReceipt(
        token,
        learner_id,
        course_id,
        identity.course_version,
        coordinate,
        identity.instance_id,
        entry,
    )
    result = store.commit_submission(SubmissionCommit(receipt, revision, following))
    entry = SubmissionReceipt.checked(result.receipt, token).archive

    if not result.replayed and record is not None:
        hooks.emit(
            EventName.HOMEWORK_SUBMITTED,
            current[0],
            occurred_at=entry.submitted_at,
            coordinate=entry.coordinate,
            verdicts=[r.verdict for r in entry.requirements],
        )

    return entry
