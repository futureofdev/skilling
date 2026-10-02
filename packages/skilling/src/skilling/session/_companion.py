"""Shared companion transforms and copied results, independent of CLI and model code."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import yaml

from ..course import Assignment, Attestation, Capability, Course, Requirement, parse_lesson
from ..delivery import (
    Beat,
    CompletionOutcome,
    CoordinateRequired,
    ObjectiveRefusal,
    ObjectiveSettlementError,
    complete_lesson,
    completed_coordinate,
    objectives_of,
    set_telemetry_consent,
    settle_objective,
    settleable,
    submit_homework,
)
from ..store import Conflict, InvalidSubmissionToken, RecoveryRequired, SubmissionToken
from ._errors import RefusalKind, SessionRefusal
from ._loading import RuntimeSession, parse_scratch
from ._teaching import _lesson_state, _shape, snapshot_view
from ._types import (
    AssignmentView,
    CompletionResult,
    CourseView,
    EvidenceKind,
    HomeworkArchiveView,
    HomeworkCheck,
    ObjectiveResult,
    ObjectiveType,
    ObjectiveView,
    PositionView,
    ProgressView,
    ProvenanceView,
    RequirementVerdict,
    RequirementView,
    TelemetryView,
)


def course_view(course: Course) -> CourseView:
    return CourseView(course.id, course.version, course.manifest.title)


def require_record(session: RuntimeSession) -> None:
    if session.revision is None:
        raise SessionRefusal(
            RefusalKind.ILLEGAL, "record-missing", "initialize the session before writing"
        )


def check_revision(session: RuntimeSession, expected: str | None) -> None:
    if expected != session.revision:
        raise Conflict("record.yaml", expected, session.revision)


def complete(
    session: RuntimeSession, expected_revision: str | None, now: datetime | None
) -> CompletionResult:
    check_revision(session, expected_revision)
    lesson = session.lesson
    parsed = parse_lesson(lesson.path)
    current = _lesson_state(session.record, session.scratch, _shape(session.course, lesson, parsed))
    legacy_noop = False
    if current.beat is not Beat.COMPLETE:
        replay = None
        if session.record.position.beat is None:
            receipt = session.store.get_completion_receipt(
                session.record.learner_id, session.course.id
            )
            if receipt is not None:
                if (receipt.learner_id, receipt.course_id, receipt.course_version) != (
                    session.record.learner_id,
                    session.course.id,
                    session.course.version,
                ) or receipt.coordinate not in session.record.completed:
                    raise RecoveryRequired(
                        "Completion receipt does not match this session snapshot"
                    )
                finished = session.course.lesson_at(receipt.coordinate)
                if finished is not None:
                    following = session.course.next_lesson(receipt.coordinate) or finished
                    if following.coordinate == session.record.position.coordinate:
                        replay = finished
            else:
                coordinates = session.course.coordinates
                index = coordinates.index(session.record.position.coordinate)
                legacy_noop = (
                    index > 0 and coordinates[index - 1] in session.record.completed
                ) or (
                    index == len(coordinates) - 1 and coordinates[index] in session.record.completed
                )
        if replay is None and not legacy_noop:
            raise SessionRefusal(
                RefusalKind.ILLEGAL,
                "illegal-transition",
                f"the lesson is at {current.beat!s}, not the completion beat",
            )
        if replay is not None:
            lesson = replay
    outcome = (
        CompletionOutcome(session.record, session.revision, already_completed=True)
        if legacy_noop
        else complete_lesson(
            session.store, session.course, session.record, session.revision, lesson, now=now
        )
    )
    snapshot = session.store.read_runtime_snapshot(session.record.learner_id, session.course.id)
    assert snapshot is not None
    return CompletionResult(
        snapshot_view(
            session.course,
            snapshot.record,
            snapshot.revision,
            parse_scratch(snapshot.scratch),
            snapshot.feedback,
        ),
        outcome.already_completed,
        tuple(outcome.badges_awarded),
        outcome.phase_completed,
        outcome.homework_placed,
        outcome.homework_queued,
    )


def select_coordinate(session: RuntimeSession, coordinate: str | None) -> str:
    try:
        log = session.store.get_log(session.record.learner_id, session.course.id)
        return completed_coordinate(session.course, session.record, log, coordinate=coordinate)
    except CoordinateRequired as exc:
        raise SessionRefusal(RefusalKind.INVALID, "coordinate-required", str(exc)) from exc
    except (RecoveryRequired, ValueError, TypeError, OSError, yaml.YAMLError) as exc:
        raise SessionRefusal(
            RefusalKind.INVALID, "chronology-invalid", f"cannot select completed lesson: {exc}"
        ) from exc


def requirements(items: list[Requirement]) -> tuple[RequirementView, ...]:
    return tuple(
        RequirementView(r.text, RequirementVerdict(r.verdict) if r.verdict else None, r.reason)
        for r in items
    )


def assignment_view(
    assignment: Assignment, queued: tuple[AssignmentView, ...] = ()
) -> AssignmentView:
    return AssignmentView(
        assignment.coordinate,
        assignment.title,
        assignment.objective,
        requirements(assignment.requirements),
        requirements(assignment.stretch_goals),
        assignment.submission,
        assignment.unlocked_at,
        queued,
    )


def homework_check(session: RuntimeSession) -> HomeworkCheck:
    active, revision = session.store.get_homework(session.record.learner_id, session.course.id)
    token = None
    view = None
    if active is not None:
        assert revision is not None
        token = SubmissionToken.for_slot(
            session.record.learner_id, session.course.id, session.course.version, active, revision
        ).encode()
        view = assignment_view(active, tuple(assignment_view(a) for a in active.queued))
    return HomeworkCheck(course_view(session.course), view, revision, token)


def homework_submit(
    session: RuntimeSession, token: str, now: datetime | None
) -> HomeworkArchiveView:
    identity = SubmissionToken.parse(token)
    if (identity.learner_id, identity.course_id, identity.course_version) != (
        session.record.learner_id,
        session.course.id,
        session.course.version,
    ):
        raise InvalidSubmissionToken("Token belongs to a different record stream")
    entry = submit_homework(
        session.store,
        session.record.learner_id,
        session.course.id,
        identity.coordinate,
        token=token,
        now=now,
    )
    return HomeworkArchiveView(
        course_view(session.course),
        entry.coordinate,
        entry.title,
        requirements(entry.requirements),
        requirements(entry.stretch_goals),
        entry.submitted_at,
    )


def objective_views(
    session: RuntimeSession, capabilities: Iterable[Capability]
) -> tuple[ObjectiveView, ...]:
    permitted = {o.id for o in settleable(session.lesson, capabilities)}
    return tuple(
        ObjectiveView(o.id, ObjectiveType(o.kind), o.text, o.verify, o.check, o.id in permitted)
        for o in objectives_of(session.lesson)
    )


def settle(
    session: RuntimeSession,
    objective_id: str,
    capabilities: Iterable[Capability],
    checked: str | None,
    attested_by: str | None,
    expected_revision: str | None,
    now: datetime | None,
) -> ObjectiveResult:
    require_record(session)
    if expected_revision is not None:
        check_revision(session, expected_revision)
    objective = next((o for o in objectives_of(session.lesson) if o.id == objective_id), None)
    attestation = (
        Attestation(checked=checked, verify=objective.verify, attested_by=attested_by)
        if objective and objective.verify and checked and attested_by
        else None
    )
    try:
        outcome = settle_objective(
            session.store,
            session.record,
            session.revision,
            session.lesson,
            objective_id,
            capabilities,
            attestation=attestation,
            now=now,
        )
    except ObjectiveSettlementError as exc:
        kind = (
            RefusalKind.INVALID
            if exc.reason in (ObjectiveRefusal.UNKNOWN, ObjectiveRefusal.PROVENANCE)
            else RefusalKind.ILLEGAL
        )
        raise SessionRefusal(kind, exc.reason.value, str(exc)) from exc
    entry = next(o for o in outcome.record.objectives_met if o.id == objective_id)
    provenance = entry.provenance
    return ObjectiveResult(
        course_view(session.course),
        entry.id,
        EvidenceKind(entry.evidence),
        entry.at,
        ProvenanceView(provenance.checked, provenance.verify, provenance.attested_by)
        if provenance
        else None,
        objective_id in outcome.newly_met,
        outcome.revision,
    )


def progress(session: RuntimeSession) -> ProgressView:
    record, course = session.record, session.course
    position = record.position
    return ProgressView(
        course_view(course),
        PositionView(position.phase, position.lesson, position.beat, position.question_index),
        tuple(record.completed),
        course.completed_count(record.completed),
        course.lesson_count,
        course.percent_complete(record.completed),
        tuple(record.skills_unlocked),
        record.streak_days,
        record.started_at,
        record.last_activity,
        session.revision,
    )


def telemetry(session: RuntimeSession, opt_in: bool | None) -> TelemetryView:
    if opt_in is None:
        return TelemetryView(
            course_view(session.course), session.record.telemetry.opt_in, session.revision
        )
    require_record(session)
    record, revision = set_telemetry_consent(
        session.store, session.record, session.revision, opt_in
    )
    return TelemetryView(
        course_view(session.course),
        record.telemetry.opt_in,
        revision,
        record.telemetry.anonymous_id or None,
    )
