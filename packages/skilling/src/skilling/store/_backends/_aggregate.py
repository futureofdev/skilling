"""Schema-v1 complete aggregates, shared by SQL and conditional-object backends."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...course import CompletionEntry, HomeworkArchiveEntry, HomeworkSlot, Record
from .._journal import (
    AcknowledgementStatus,
    ActionIdentity,
    ActionOperation,
    AdvanceOutcome,
    FeedbackAcknowledgement,
    FeedbackPointer,
    FeedbackRef,
    IdempotencyKeyConflict,
    LegacyOutcomeUnavailable,
    QuizAnswerOutcome,
    TransitionCommit,
    UpgradeIdentity,
    key_digest,
)
from .._journal._actions import ActionBoundary, AdvanceBoundary, AnswerBoundary, outcome_boundary
from .._journal._transition import dump
from .._journal._transition_types import Identity
from .._protocol import (
    AcknowledgeSession,
    BindSourceSession,
    CompleteSession,
    CompletionReceipt,
    Conflict,
    DeleteSession,
    HomeworkWrite,
    InitializeSession,
    MutateSession,
    RecoveryRequired,
    SessionActionReceipt,
    SessionCommit,
    SessionCommitResult,
    SessionDeleted,
    SessionKeyReservation,
    SessionRead,
    SessionReadKind,
    SessionScope,
    SessionState,
    SessionUpgradeReceipt,
    SubmissionReceipt,
    SubmissionToken,
    SubmitSession,
    TransitionSession,
    UpgradeSession,
    neutral_pending_pointer,
)
from .._protocol._boundary import validate_scratch as scratch_value


class _Boundary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Scope(_Boundary):
    namespace: str = Field(min_length=1)
    learner_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)

    def value(self) -> SessionScope:
        return SessionScope(self.namespace, self.learner_id, self.course_id)


class _Action(ActionBoundary):
    expected_revision: str = Field(min_length=1)


class _ActionReceipt(_Boundary):
    identity: _Action | Identity
    outcome: AdvanceBoundary | AnswerBoundary | None

    def value(self) -> SessionActionReceipt:
        return SessionActionReceipt(
            self.identity.value(),
            self.outcome.value() if self.outcome is not None else LegacyOutcomeUnavailable(),
        )


class _Completion(_Boundary):
    operation_id: str
    learner_id: str
    course_id: str
    course_version: str
    coordinate: str
    completed_at: datetime
    badges_awarded: tuple[str, ...]
    phase_completed: int | None
    homework_placed: bool
    homework_queued: bool

    def value(self) -> CompletionReceipt:
        return CompletionReceipt(**self.model_dump())


class _Submission(_Boundary):
    token: str
    learner_id: str
    course_id: str
    course_version: str
    coordinate: str
    instance_id: str
    archive: HomeworkArchiveEntry

    def value(self) -> SubmissionReceipt:
        return SubmissionReceipt.checked(
            SubmissionReceipt(
                self.token,
                self.learner_id,
                self.course_id,
                self.course_version,
                self.coordinate,
                self.instance_id,
                self.archive,
            ),
            self.token,
        )


class _Reservation(_Boundary):
    course_version: str
    key: str


class _Upgrade(_Boundary):
    learner_id: str
    course_id: str
    from_version: str
    to_version: str


class _State(_Boundary):
    record: Record
    record_revision: str = Field(min_length=1)
    scratch: str
    log: tuple[CompletionEntry, ...]
    homework: HomeworkSlot | None
    homework_revision: str | None
    archive: tuple[HomeworkArchiveEntry, ...]
    completion_receipts: tuple[_Completion, ...]
    action_receipts: tuple[_ActionReceipt, ...]
    reservations: tuple[_Reservation, ...]
    submission_receipts: tuple[_Submission, ...]
    upgrades: tuple[_Upgrade, ...]
    source_digest: str | None

    def value(self) -> SessionState:
        return SessionState(
            self.record,
            self.record_revision,
            bytes.fromhex(self.scratch),
            self.log,
            self.homework,
            self.homework_revision,
            self.archive,
            tuple(r.value() for r in self.completion_receipts),
            tuple(r.value() for r in self.action_receipts),
            tuple(SessionKeyReservation(r.course_version, r.key) for r in self.reservations),
            tuple(r.value() for r in self.submission_receipts),
            tuple(SessionUpgradeReceipt(UpgradeIdentity(**r.model_dump())) for r in self.upgrades),
            self.source_digest,
        )


class _Aggregate(_Boundary):
    schema_version: Literal[1]
    kind: SessionReadKind
    scope: _Scope
    session_revision: str = Field(min_length=1)
    state: _State | None

    @field_validator("schema_version", mode="before")
    @classmethod
    def schema_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Aggregate schema version must be an integer")
        return value


def encode(value: SessionRead) -> bytes:
    """Serialize every durable field after mechanical validation."""
    from .._protocol._boundary import validate_read

    validate_read(value)
    state = value.state
    body = None
    if state is not None:
        body = _State(
            record=state.record,
            record_revision=state.record_revision,
            scratch=state.scratch.hex(),
            log=state.log,
            homework=state.homework,
            homework_revision=state.homework_revision,
            archive=state.archive,
            completion_receipts=tuple(_Completion(**asdict(r)) for r in state.completion_receipts),
            action_receipts=tuple(
                _ActionReceipt(
                    identity=(
                        _Action.model_validate(asdict(r.identity))
                        if isinstance(r.identity, ActionIdentity)
                        else Identity.model_validate(asdict(r.identity))
                    ),
                    outcome=(
                        outcome_boundary(r.outcome)
                        if isinstance(r.outcome, (AdvanceOutcome, QuizAnswerOutcome))
                        else None
                    ),
                )
                for r in state.action_receipts
            ),
            reservations=tuple(_Reservation(**asdict(r)) for r in state.reservations),
            submission_receipts=tuple(
                _Submission(**{**asdict(r), "archive": r.archive})
                for r in state.submission_receipts
            ),
            upgrades=tuple(_Upgrade(**asdict(r.identity)) for r in state.upgrades),
            source_digest=state.source_digest,
        )
    return (
        _Aggregate(
            schema_version=1,
            kind=value.kind,
            scope=_Scope(**asdict(value.scope)),
            session_revision=value.session_revision or "",
            state=body,
        )
        .model_dump_json()
        .encode("utf-8")
    )


def decode(raw: bytes, scope: SessionScope) -> SessionRead:
    """Refuse unknown fields/schema, malformed values, or cross-scope payloads."""
    from .._protocol._boundary import validate_read

    try:
        wire = _Aggregate.model_validate_json(raw)
        value = SessionRead(
            wire.kind,
            wire.scope.value(),
            wire.session_revision,
            wire.state.value() if wire.state is not None else None,
        )
        if value.scope != scope:
            raise ValueError("aggregate identity differs from selected scope")
        validate_read(value)
        return value
    except (ValueError, TypeError, AttributeError) as exc:
        raise RecoveryRequired("Invalid complete session aggregate") from exc


def revision(scope: SessionScope, component: str) -> str:
    """Opaque scoped revision with a fresh incarnation on every mutation."""
    import hashlib
    import json

    identity = json.dumps(asdict(scope), sort_keys=True).encode()
    return f"{component}:{hashlib.sha256(identity).hexdigest()}:{uuid4().hex}"


def replay(current: SessionRead, command: SessionCommit) -> SessionCommitResult | None:
    """Recover exact original outcomes before comparing today's aggregate revision."""
    from .._protocol._boundary import validate_command, validate_read

    validate_read(current)
    validate_command(command)
    if current.scope != command.scope:
        raise RecoveryRequired("Command scope differs from selected aggregate")
    if current.kind == SessionReadKind.DELETED:
        raise SessionDeleted("Deleted session cannot be recreated or replayed")
    state = current.state
    if state is None:
        return None
    if isinstance(command, TransitionSession):
        identity = command.commit.identity
        if identity.key is not None:
            requested_key = (
                identity.key if isinstance(identity, ActionIdentity) else key_digest(identity.key)
            )
            for receipt in state.action_receipts:
                saved_key = receipt.identity.key
                if saved_key is not None and not isinstance(receipt.identity, ActionIdentity):
                    saved_key = key_digest(saved_key)
                if saved_key == requested_key:
                    if receipt.identity != identity:
                        raise IdempotencyKeyConflict("Action key has a different original identity")
                    return SessionCommitResult(current, True, receipt.outcome)
            legacy_key = scratch_value(state.scratch).last_key
            if legacy_key and key_digest(legacy_key) == requested_key:
                raise IdempotencyKeyConflict("Action key is reserved by legacy scratch")
            if any(r.key == requested_key for r in state.reservations):
                raise IdempotencyKeyConflict("Action key is permanently reserved")
    elif isinstance(command, CompleteSession):
        receipt = command.commit.receipt
        for saved in state.completion_receipts:
            if saved.operation_id == receipt.operation_id:
                if (saved.learner_id, saved.course_id, saved.course_version, saved.coordinate) != (
                    receipt.learner_id,
                    receipt.course_id,
                    receipt.course_version,
                    receipt.coordinate,
                ):
                    raise IdempotencyKeyConflict("Completion identity changed on retry")
                return SessionCommitResult(current, True, saved)
    elif isinstance(command, SubmitSession):
        receipt = command.commit.receipt
        for saved in state.submission_receipts:
            if saved.token == receipt.token:
                if (
                    saved.learner_id,
                    saved.course_id,
                    saved.course_version,
                    saved.coordinate,
                    saved.instance_id,
                ) != (
                    receipt.learner_id,
                    receipt.course_id,
                    receipt.course_version,
                    receipt.coordinate,
                    receipt.instance_id,
                ):
                    raise IdempotencyKeyConflict("Submission identity changed on retry")
                return SessionCommitResult(current, True, saved)
    elif isinstance(command, UpgradeSession):
        for saved in state.upgrades:
            if saved.identity == command.commit.identity:
                return SessionCommitResult(current, True, saved.identity)
    elif isinstance(command, AcknowledgeSession):
        scratch = scratch_value(state.scratch)
        pointer = scratch.presented_feedback
        if pointer is not None and _feedback_matches(
            command.feedback, pointer.value(), current.scope
        ):
            return SessionCommitResult(
                current,
                True,
                FeedbackAcknowledgement(
                    AcknowledgementStatus.ALREADY_PRESENTED, state.record_revision
                ),
            )
    return None


def apply(current: SessionRead, command: SessionCommit) -> SessionCommitResult:
    """Evaluate a closed prepared mutation; never parse a lesson or derive teaching policy."""
    saved = replay(current, command)
    if saved is not None:
        return saved
    if current.session_revision != command.expected_revision:
        raise Conflict("session", command.expected_revision, current.session_revision)
    scope = current.scope
    if isinstance(command, DeleteSession):
        return SessionCommitResult(
            SessionRead(SessionReadKind.DELETED, scope, revision(scope, "s"))
        )
    if isinstance(command, InitializeSession):
        if current.kind != SessionReadKind.ABSENT:
            raise Conflict("initialize session", None, current.session_revision)
        return _result(
            current,
            SessionState(command.record, revision(scope, "r"), source_digest=command.source_digest),
        )
    state = current.state
    if state is None:
        raise Conflict("missing session", command.expected_revision, None)
    if (
        isinstance(command, (TransitionSession, CompleteSession, SubmitSession))
        and scratch_value(state.scratch).pending_feedback is not None
    ):
        raise RecoveryRequired("Pending feedback must be acknowledged before continuation")
    state = _reserve_legacy(state)
    outcome = None
    if isinstance(command, TransitionSession):
        commit = command.commit
        _expect("record", commit.expected_record_revision, state.record_revision)
        if commit.expected_scratch != state.scratch:
            raise Conflict("scratch", "captured scratch", "changed scratch")
        _same_stream(state.record, commit.record)
        if commit.identity.course_version != state.record.course_version:
            raise RecoveryRequired("Transition identity differs from current course version")
        if isinstance(commit.identity, ActionIdentity):
            _expect("action record", commit.identity.expected_revision, state.record_revision)
        _transition_effects(state, commit)
        receipt = SessionActionReceipt(
            commit.identity, commit.outcome or LegacyOutcomeUnavailable()
        )
        state = replace(
            state,
            record=commit.record,
            scratch=commit.scratch,
            action_receipts=state.action_receipts + ((receipt,) if commit.identity.key else ()),
        )
        outcome = receipt.outcome
    elif isinstance(command, AcknowledgeSession):
        _expect("record", command.expected_record_revision, state.record_revision)
        scratch = scratch_value(state.scratch)
        pointer = scratch.pending_feedback
        if pointer is None:
            raise Conflict("feedback", "pending feedback", None)
        if not _feedback_matches(command.feedback, pointer.value(), scope):
            raise Conflict("feedback", "captured feedback", "different feedback")
        scratch.presented_feedback, scratch.pending_feedback = pointer, None
        state = replace(state, scratch=dump(scratch.model_dump(exclude_none=True)))
        outcome = FeedbackAcknowledgement(AcknowledgementStatus.PRESENTED, state.record_revision)
    elif isinstance(command, CompleteSession):
        commit = command.commit
        _expect("record", commit.expected_record_revision, state.record_revision)
        _same_stream(state.record, commit.record)
        if state.log != commit.expected_log:
            raise Conflict("completion log", "captured log", "changed log")
        if (commit.entry.coordinate, commit.entry.course_version, commit.entry.completed_at) != (
            commit.receipt.coordinate,
            commit.receipt.course_version,
            commit.receipt.completed_at,
        ):
            raise RecoveryRequired("Completion entry differs from receipt")
        if commit.receipt.course_version != state.record.course_version:
            raise RecoveryRequired("Completion receipt differs from current course version")
        state = _homework(state, commit.homework)
        state = replace(
            state,
            record=commit.record,
            log=state.log + (commit.entry,),
            scratch=b"",
            completion_receipts=state.completion_receipts + (commit.receipt,),
        )
        outcome = commit.receipt
    elif isinstance(command, SubmitSession):
        commit = command.commit
        token = SubmissionToken.parse(commit.receipt.token)
        _expect("homework", commit.expected_slot_revision, state.homework_revision)
        if state.homework is None or state.homework_revision is None:
            raise Conflict("homework", commit.expected_slot_revision, None)
        if (
            SubmissionToken.for_slot(
                scope.learner_id,
                scope.course_id,
                state.record.course_version,
                state.homework,
                state.homework_revision,
            )
            != token
        ):
            raise RecoveryRequired("Submission token differs from the captured assignment")
        archive, slot = commit.receipt.archive, state.homework
        if (archive.coordinate, archive.title, archive.requirements, archive.stretch_goals) != (
            slot.coordinate,
            slot.title,
            slot.requirements,
            slot.stretch_goals,
        ):
            raise RecoveryRequired("Submission archive differs from the captured assignment")
        successor = (
            HomeworkSlot(**slot.queued[0].model_dump(), queued=slot.queued[1:])
            if slot.queued
            else None
        )
        if commit.slot != successor:
            raise RecoveryRequired("Submission must preserve and advance the captured queue once")
        state = replace(
            state,
            homework=commit.slot,
            archive=state.archive + (commit.receipt.archive,),
            submission_receipts=state.submission_receipts + (commit.receipt,),
        )
        outcome = commit.receipt
    elif isinstance(command, BindSourceSession):
        if state.source_digest is not None:
            raise Conflict("source attachment", None, state.source_digest)
        state = replace(state, source_digest=command.source_digest)
    elif isinstance(command, MutateSession):
        from .._protocol._boundary import validate_mutation

        validate_mutation(current, command)
        _expect("record", command.expected_record_revision, state.record_revision)
        _same_stream(state.record, command.record)
        state = replace(state, record=command.record)
    elif isinstance(command, UpgradeSession):
        commit = command.commit
        _expect("record", commit.expected_record_revision, state.record_revision)
        if state.scratch != commit.expected_scratch:
            raise Conflict("scratch", "captured scratch", "changed scratch")
        if scratch_value(state.scratch).pending_feedback is not None:
            raise RecoveryRequired("Pending feedback must be acknowledged before upgrade")
        if (state.record.course_version, commit.record.course_version) != (
            commit.identity.from_version,
            commit.identity.to_version,
        ):
            raise RecoveryRequired("Upgrade versions differ from prepared records")
        state = _homework(state, commit.homework)
        reservations = list(state.reservations)
        raw_legacy_key = scratch_value(state.scratch).last_key
        legacy_key = key_digest(raw_legacy_key) if raw_legacy_key else None
        if legacy_key and not any(r.key == legacy_key for r in reservations):
            reservations.append(SessionKeyReservation(state.record.course_version, legacy_key))
        for receipt in state.action_receipts:
            if receipt.identity.key is not None:
                reservation = SessionKeyReservation(
                    receipt.identity.course_version,
                    receipt.identity.key
                    if isinstance(receipt.identity, ActionIdentity)
                    else key_digest(receipt.identity.key),
                )
                if reservation not in reservations:
                    reservations.append(reservation)
        state = replace(
            state,
            record=commit.record,
            scratch=commit.scratch,
            reservations=tuple(reservations),
            upgrades=state.upgrades + (SessionUpgradeReceipt(commit.identity),),
            source_digest=command.source_digest,
        )
        outcome = commit.identity
    else:
        raise RecoveryRequired("Unsupported complete-session operation")
    old = current.state
    assert old is not None
    if state.record != old.record:
        state = replace(state, record_revision=revision(scope, "r"))
    if state.homework != old.homework:
        state = replace(
            state,
            homework_revision=revision(scope, "h") if state.homework is not None else None,
        )
    return _result(current, state, outcome)


def _result(
    current: SessionRead,
    state: SessionState,
    outcome: AdvanceOutcome
    | QuizAnswerOutcome
    | LegacyOutcomeUnavailable
    | CompletionReceipt
    | SubmissionReceipt
    | FeedbackAcknowledgement
    | UpgradeIdentity
    | None = None,
) -> SessionCommitResult:
    value = SessionRead(SessionReadKind.LIVE, current.scope, revision(current.scope, "s"), state)
    # Round-tripping validates all cross-references and detaches mutable boundary models.
    value = decode(encode(value), current.scope)
    return SessionCommitResult(value, False, outcome)


def _expect(what: str, expected: str | None, actual: str | None) -> None:
    if expected != actual:
        raise Conflict(what, expected, actual)


def _same_stream(before: Record, after: Record) -> None:
    if (before.learner_id, before.course_id, before.course_version) != (
        after.learner_id,
        after.course_id,
        after.course_version,
    ):
        raise RecoveryRequired("Only an explicit upgrade may change the record stream")


def _homework(state: SessionState, write: HomeworkWrite | None) -> SessionState:
    if write is None:
        return state
    _expect("homework", write.expected_revision, state.homework_revision)
    return replace(state, homework=write.slot)


def _feedback_matches(ref: FeedbackRef, pointer: FeedbackPointer, scope: SessionScope) -> bool:
    return (
        ref._learner_id,
        ref._course_id,
        ref._course_version,
        ref._answer_key,
        ref._receipt_digest,
    ) == (
        scope.learner_id,
        scope.course_id,
        pointer.origin_course_version,
        pointer.answer_key,
        pointer.receipt_digest,
    )


def _reserve_legacy(state: SessionState) -> SessionState:
    raw = scratch_value(state.scratch).last_key
    if raw is None:
        return state
    key = key_digest(raw)
    if any(reservation.key == key for reservation in state.reservations):
        return state
    return replace(
        state,
        reservations=state.reservations
        + (SessionKeyReservation(state.record.course_version, key),),
    )


def _transition_effects(state: SessionState, commit: TransitionCommit) -> None:
    """The file journal's before/after invariants, without path or hash-revision policy."""
    if state.record.position.coordinate != commit.identity.coordinate:
        raise RecoveryRequired("Transition before coordinate differs from captured record")
    identity, outcome = commit.identity, commit.outcome
    after = scratch_value(commit.scratch)
    if isinstance(identity, ActionIdentity):
        if identity.verb == ActionOperation.ACKNOWLEDGE:
            raise RecoveryRequired("Feedback acknowledgement requires its closed command")
        if isinstance(outcome, AdvanceOutcome):
            if asdict(outcome.position) != commit.record.position.model_dump():
                raise RecoveryRequired("Advance outcome position differs from prepared record")
            if after.pending_feedback is not None:
                raise RecoveryRequired("An advance cannot invent pending feedback")
        elif isinstance(outcome, QuizAnswerOutcome):
            if (
                after.pending_feedback is None
                or after.pending_feedback.value() != neutral_pending_pointer(identity, outcome)
            ):
                raise RecoveryRequired("An answer must retain its exact outcome feedback pointer")
        else:
            raise RecoveryRequired("Trusted transition requires its original outcome")
