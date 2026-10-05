"""Strict neutral identity and complete-state validation, independent of file paths."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict
from typing import Literal

import yaml
from pydantic import Field, model_validator

from ...course import (
    CompletionEntry,
    HomeworkArchiveEntry,
    HomeworkSlot,
    Record,
    is_course_id,
    is_semver,
)
from .._journal._actions import (
    ActionBoundary,
    ActionIdentity,
    AdvanceBoundary,
    AdvanceOutcome,
    AnswerBoundary,
    FeedbackPointer,
    FeedbackRef,
    LegacyOutcomeUnavailable,
    PendingFeedback,
    PendingReference,
    QuizAnswerOutcome,
    Scratch,
    key_digest,
    outcome_boundary,
)
from .._journal._transition_types import Boundary, Identity, TransitionIdentity
from ._progress import HomeworkWrite, RecoveryRequired, SubmissionReceipt, SubmissionToken
from ._session import (
    AcknowledgeSession,
    BindSourceSession,
    CompleteSession,
    DeleteSession,
    InitializeSession,
    MutateSession,
    RecordMutationKind,
    SessionCommit,
    SubmitSession,
    TransitionSession,
    UpgradeSession,
)
from ._types import SessionActionReceipt, SessionRead, SessionReadKind, SessionScope


class NeutralActionBoundary(ActionBoundary):
    expected_revision: str = Field(min_length=1)


class NeutralActionReceipt(Boundary):
    version: Literal[2]
    kind: Literal["receipt"]
    identity: NeutralActionBoundary
    outcome: AdvanceBoundary | AnswerBoundary = Field(discriminator="kind")

    @model_validator(mode="after")
    def binding(self) -> NeutralActionReceipt:
        identity, outcome = self.identity, self.outcome
        if identity.verb != outcome.kind:
            raise ValueError("outcome operation mismatch")
        if isinstance(outcome, AdvanceBoundary):
            if outcome.input != identity.input:
                raise ValueError("advance outcome input mismatch")
        elif (outcome.question_number, outcome.label) != (
            identity.question_number,
            identity.input,
        ):
            raise ValueError("answer outcome question/label mismatch")
        return self


def validate_scope(scope: SessionScope) -> SessionScope:
    if (
        not isinstance(scope, SessionScope)
        or any(
            not isinstance(value, str) or not value or "\x00" in value
            for value in (scope.namespace, scope.learner_id, scope.course_id)
        )
        or not is_course_id(scope.course_id)
    ):
        raise RecoveryRequired("Invalid session scope")
    return scope


def validate_source_digest(value: str | None) -> None:
    if value is not None and (
        not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None
    ):
        raise RecoveryRequired("Invalid course source digest")


def revision(value: str | None, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or not value:
        raise RecoveryRequired("Expected a nonempty opaque revision")


def neutral_action_identity(identity: ActionIdentity) -> ActionIdentity:
    try:
        return NeutralActionBoundary.model_validate(asdict(identity)).value()
    except (ValueError, TypeError) as exc:
        raise RecoveryRequired("Invalid neutral action identity") from exc


def neutral_pending_pointer(
    identity: ActionIdentity, outcome: QuizAnswerOutcome
) -> FeedbackPointer:
    receipt = NeutralActionReceipt(
        version=2,
        kind="receipt",
        identity=NeutralActionBoundary.model_validate(asdict(identity)),
        outcome=outcome_boundary(outcome),
    )
    raw = yaml.safe_dump(
        receipt.model_dump(), sort_keys=False, allow_unicode=True, width=100
    ).encode("utf-8")
    return FeedbackPointer(
        identity.course_version, identity.key or "", hashlib.sha256(raw).hexdigest()
    )


def validate_scratch(raw: bytes) -> Scratch:
    try:
        if not isinstance(raw, bytes):
            raise ValueError("scratch must be bytes")
        value = yaml.safe_load(raw) if raw else {}
        return Scratch.model_validate({} if value is None else value)
    except (ValueError, TypeError, UnicodeError, yaml.YAMLError) as exc:
        raise RecoveryRequired("Invalid complete-session scratch") from exc


def _stream(scope: SessionScope, learner_id: str, course_id: str) -> None:
    if (learner_id, course_id) != (scope.learner_id, scope.course_id):
        raise RecoveryRequired("Stored or prepared identity differs from session scope")


def _record(record: Record, scope: SessionScope) -> None:
    Record.model_validate(record.model_dump(mode="json"))
    _stream(scope, record.learner_id, record.course_id)


def _homework_write(homework: HomeworkWrite | None) -> None:
    if homework is None:
        return
    revision(homework.expected_revision, optional=True)
    if homework.slot is not None:
        HomeworkSlot.model_validate(homework.slot.model_dump(mode="json"))


def action_key(identity: ActionIdentity | TransitionIdentity) -> str | None:
    """Normalize the legacy raw event name without rewriting its original receipt."""
    if identity.key is None:
        return None
    return identity.key if isinstance(identity, ActionIdentity) else key_digest(identity.key)


def validate_action_receipt(receipt: SessionActionReceipt, scope: SessionScope) -> None:
    identity = receipt.identity
    _stream(scope, identity.learner_id, identity.course_id)
    if isinstance(identity, ActionIdentity):
        if not isinstance(receipt.outcome, (AdvanceOutcome, QuizAnswerOutcome)):
            raise RecoveryRequired("Version-two action requires its original outcome")
        NeutralActionReceipt(
            version=2,
            kind="receipt",
            identity=NeutralActionBoundary.model_validate(asdict(identity)),
            outcome=outcome_boundary(receipt.outcome),
        )
    else:
        Identity.model_validate(asdict(identity))
        if not isinstance(receipt.outcome, LegacyOutcomeUnavailable):
            raise RecoveryRequired("Legacy receipt cannot invent an original outcome")


def validate_read(read: SessionRead, scope: SessionScope | None = None) -> SessionRead:
    """Refuse corruption before replay, CAS, or semantic preparation."""
    try:
        validate_scope(read.scope)
        if scope is not None and read.scope != scope:
            raise RecoveryRequired("Stored session scope differs from requested scope")
        if read.kind is SessionReadKind.ABSENT:
            if read.state is not None or read.session_revision is not None:
                raise RecoveryRequired("Absent session contains durable state")
            return read
        revision(read.session_revision)
        if read.kind is SessionReadKind.DELETED:
            if read.state is not None:
                raise RecoveryRequired("Deleted session retains a live payload")
            return read
        if read.kind is not SessionReadKind.LIVE or read.state is None:
            raise RecoveryRequired("Invalid live session shape")
        state = read.state
        _record(state.record, read.scope)
        validate_source_digest(state.source_digest)
        revision(state.record_revision)
        validate_scratch(state.scratch)
        revision(state.homework_revision, optional=state.homework is None)
        if state.homework is None and state.homework_revision is not None:
            raise RecoveryRequired("Empty homework slot has a revision")
        if state.homework is not None:
            HomeworkSlot.model_validate(state.homework.model_dump(mode="json"))
        for entry in state.log:
            CompletionEntry.model_validate(entry.model_dump(mode="json"))
        for entry in state.archive:
            HomeworkArchiveEntry.model_validate(entry.model_dump(mode="json"))
        keys: set[str] = set()
        for receipt in state.action_receipts:
            validate_action_receipt(receipt, read.scope)
            key = action_key(receipt.identity)
            if key is not None:
                if key in keys:
                    raise RecoveryRequired("Duplicate action receipt identity")
                keys.add(key)
        reserved: set[str] = set()
        for reservation in state.reservations:
            if not reservation.key or not is_semver(reservation.course_version):
                raise RecoveryRequired("Invalid lifetime key reservation")
            if reservation.key in reserved:
                raise RecoveryRequired("Duplicate lifetime key reservation")
            reserved.add(reservation.key)
        operations: set[str] = set()
        from .._journal import Receipt as CompletionBoundary

        for receipt in state.completion_receipts:
            CompletionBoundary.model_validate(asdict(receipt))
            _stream(read.scope, receipt.learner_id, receipt.course_id)
            if (
                not receipt.operation_id
                or receipt.operation_id in operations
                or not is_semver(receipt.course_version)
            ):
                raise RecoveryRequired("Invalid completion receipt identity")
            if (
                receipt.completed_at.utcoffset() is None
                or receipt.coordinate not in state.record.completed
            ):
                raise RecoveryRequired("Completion receipt has no completed record entry")
            if not any(
                (entry.coordinate, entry.course_version, entry.completed_at)
                == (receipt.coordinate, receipt.course_version, receipt.completed_at)
                for entry in state.log
            ):
                raise RecoveryRequired("Completion receipt has no matching log entry")
            operations.add(receipt.operation_id)
        tokens: set[str] = set()
        for receipt in state.submission_receipts:
            _stream(read.scope, receipt.learner_id, receipt.course_id)
            SubmissionReceipt.checked(receipt, receipt.token)
            if receipt.token in tokens or receipt.archive not in state.archive:
                raise RecoveryRequired("Invalid submission receipt archive or duplicate token")
            tokens.add(receipt.token)
        for receipt in state.upgrades:
            identity = receipt.identity
            _stream(read.scope, identity.learner_id, identity.course_id)
            if (
                not is_semver(identity.from_version)
                or not is_semver(identity.to_version)
                or identity.from_version == identity.to_version
            ):
                raise RecoveryRequired("Invalid upgrade receipt")
        pending_feedback(read)
        return read
    except (ValueError, TypeError, AttributeError) as exc:
        raise RecoveryRequired("Invalid complete-session state") from exc


def pending_feedback(read: SessionRead) -> PendingFeedback | None:
    if read.state is None:
        return None
    scratch = validate_scratch(read.state.scratch)
    for pointer in (scratch.pending_feedback, scratch.presented_feedback):
        if pointer is None:
            continue
        matches = [r for r in read.state.action_receipts if r.identity.key == pointer.answer_key]
        if len(matches) != 1:
            raise RecoveryRequired("Feedback reference has no unique original receipt")
        receipt = matches[0]
        if not isinstance(receipt.identity, ActionIdentity) or not isinstance(
            receipt.outcome, QuizAnswerOutcome
        ):
            raise RecoveryRequired("Feedback references a non-answer receipt")
        if pointer is scratch.pending_feedback and (
            receipt.identity.course_version != read.state.record.course_version
            or receipt.identity.coordinate != read.state.record.position.coordinate
        ):
            raise RecoveryRequired(
                "Pending feedback differs from current record version or coordinate"
            )
        expected = neutral_pending_pointer(receipt.identity, receipt.outcome)
        if expected != pointer.value():
            raise RecoveryRequired("Feedback reference differs from original receipt")
    pointer = scratch.pending_feedback
    if pointer is None:
        return None
    receipt = next(r for r in read.state.action_receipts if r.identity.key == pointer.answer_key)
    if not isinstance(receipt.outcome, QuizAnswerOutcome):
        raise RecoveryRequired("Feedback has no answer outcome")
    return PendingFeedback(
        FeedbackRef(
            read.scope.learner_id,
            read.scope.course_id,
            pointer.origin_course_version,
            pointer.answer_key,
            pointer.receipt_digest,
        ),
        receipt.outcome,
        read.state.record_revision,
    )


def replay_action(read: SessionRead, identity: ActionIdentity) -> SessionActionReceipt | None:
    from .._journal import IdempotencyKeyConflict
    from ._types import SessionDeleted

    validate_read(read)
    neutral_action_identity(identity)
    _stream(read.scope, identity.learner_id, identity.course_id)
    if read.kind is SessionReadKind.DELETED:
        raise SessionDeleted("Session was deleted")
    if read.state is None:
        return None
    for receipt in read.state.action_receipts:
        if action_key(receipt.identity) == identity.key:
            if receipt.identity != identity:
                raise IdempotencyKeyConflict("Action key is bound to another identity")
            return receipt
    if any(r.key == identity.key for r in read.state.reservations):
        raise IdempotencyKeyConflict("Action key is reserved by an earlier course version")
    return None


def validate_command(command: SessionCommit) -> SessionCommit:
    """Check foreign input before a backend acquires or mutates stream state."""
    try:
        validate_scope(command.scope)
        revision(
            command.expected_revision,
            optional=isinstance(command, (InitializeSession, DeleteSession)),
        )
        if isinstance(command, (InitializeSession, UpgradeSession, BindSourceSession)):
            validate_source_digest(command.source_digest)
        if isinstance(command, BindSourceSession):
            if command.source_digest is None:
                raise RecoveryRequired("Source attachment requires a digest")
        elif isinstance(command, (InitializeSession, MutateSession)):
            _record(command.record, command.scope)
            if isinstance(command, MutateSession):
                revision(command.expected_record_revision)
                if not isinstance(command.kind, RecordMutationKind):
                    raise RecoveryRequired("Invalid record mutation kind")
        elif isinstance(command, TransitionSession):
            commit = command.commit
            _record(commit.record, command.scope)
            _stream(command.scope, commit.identity.learner_id, commit.identity.course_id)
            if commit.identity.course_version != commit.record.course_version:
                raise RecoveryRequired("Transition changes course version")
            revision(commit.expected_record_revision)
            validate_scratch(commit.expected_scratch)
            validate_scratch(commit.scratch)
            if isinstance(commit.identity, ActionIdentity):
                neutral_action_identity(commit.identity)
                if commit.identity.expected_revision != commit.expected_record_revision:
                    raise RecoveryRequired("Action and prepared record revisions differ")
                if commit.outcome is None:
                    raise RecoveryRequired("Trusted action requires an original outcome")
                validate_action_receipt(
                    SessionActionReceipt(commit.identity, commit.outcome), command.scope
                )
            else:
                Identity.model_validate(asdict(commit.identity))
        elif isinstance(command, CompleteSession):
            from .._journal import Receipt as CompletionBoundary

            completion = command.commit
            CompletionBoundary.model_validate(asdict(completion.receipt))
            _homework_write(completion.homework)
            if (
                completion.entry.coordinate,
                completion.entry.course_version,
                completion.entry.completed_at,
            ) != (
                completion.receipt.coordinate,
                completion.receipt.course_version,
                completion.receipt.completed_at,
            ) or completion.record.course_version != completion.receipt.course_version:
                raise RecoveryRequired("Completion receipt, log and record differ")
            _record(completion.record, command.scope)
            _stream(command.scope, completion.receipt.learner_id, completion.receipt.course_id)
            revision(completion.expected_record_revision)
            CompletionEntry.model_validate(completion.entry.model_dump(mode="json"))
            for entry in completion.expected_log:
                CompletionEntry.model_validate(entry.model_dump(mode="json"))
            if completion.receipt.completed_at.utcoffset() is None:
                raise RecoveryRequired("Completion timestamp must be offset-aware")
        elif isinstance(command, SubmitSession):
            submission = command.commit
            identity = SubmissionToken.parse(submission.receipt.token)
            _stream(command.scope, identity.learner_id, identity.course_id)
            SubmissionReceipt.checked(submission.receipt, submission.receipt.token)
            revision(submission.expected_slot_revision)
            if submission.slot is not None:
                HomeworkSlot.model_validate(submission.slot.model_dump(mode="json"))
        elif isinstance(command, AcknowledgeSession):
            feedback = command.feedback
            _stream(command.scope, feedback._learner_id, feedback._course_id)
            PendingReference(
                version=1,
                origin_course_version=feedback._course_version,
                answer_key=feedback._answer_key,
                receipt_digest=feedback._receipt_digest,
            )
            revision(command.expected_record_revision)
        elif isinstance(command, UpgradeSession):
            from .._journal._upgrade import Identity as UpgradeBoundary

            upgrade = command.commit
            UpgradeBoundary.model_validate(asdict(upgrade.identity))
            _homework_write(upgrade.homework)
            _record(upgrade.record, command.scope)
            _stream(command.scope, upgrade.identity.learner_id, upgrade.identity.course_id)
            revision(upgrade.expected_record_revision)
            validate_scratch(upgrade.expected_scratch)
            validate_scratch(upgrade.scratch)
            if upgrade.record.course_version != upgrade.identity.to_version:
                raise RecoveryRequired("Upgrade record differs from target version")
        elif not isinstance(command, DeleteSession):
            raise RecoveryRequired("Unsupported session command")
        return command
    except (ValueError, TypeError, AttributeError) as exc:
        raise RecoveryRequired("Invalid prepared session command") from exc


def validate_mutation(read: SessionRead, command: MutateSession) -> None:
    """Record edits cannot replace enrollment or manufacture durable completion effects."""
    state = read.state
    if state is None:
        raise RecoveryRequired("Record mutation requires a live session")
    before, after = state.record, command.record
    if (before.learner_id, before.course_id, before.course_version) != (
        after.learner_id,
        after.course_id,
        after.course_version,
    ):
        raise RecoveryRequired("Record mutation cannot change stream or course version")
    changed = {
        key for key, value in before.model_dump().items() if after.model_dump()[key] != value
    }
    permitted = {
        RecordMutationKind.CONSENT: {"telemetry"},
        RecordMutationKind.OBJECTIVE: {"objectives_met"},
        RecordMutationKind.ARTIFACT: {"artifacts"},
    }
    if command.kind in permitted and not changed <= permitted[command.kind]:
        raise RecoveryRequired("Record mutation changes fields outside its operation")
    if changed & {"position", "completed", "skills_unlocked"}:
        raise RecoveryRequired("Teaching and completion state require their prepared operation")
    if after.objectives_met[: len(before.objectives_met)] != before.objectives_met:
        raise RecoveryRequired("Objective evidence must remain append-only")
