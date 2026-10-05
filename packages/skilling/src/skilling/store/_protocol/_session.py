"""Closed runtime-prepared mutations and synchronous persistence seams."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, TypeAlias, runtime_checkable

from ...course import Record
from ._progress import (
    CompletionCommit,
    CompletionReceipt,
    ProgressStore,
    SubmissionCommit,
    SubmissionReceipt,
)
from ._types import SessionRead, SessionScope

if TYPE_CHECKING:
    from .._journal import (
        ActionIdentity,
        AdvanceOutcome,
        FeedbackAcknowledgement,
        FeedbackRef,
        LegacyOutcomeUnavailable,
        PendingFeedback,
        QuizAnswerOutcome,
        RuntimeSnapshot,
        TransitionCommit,
        TransitionIdentity,
        TransitionResult,
        UpgradeCommit,
        UpgradeIdentity,
        UpgradeResult,
    )


@dataclass(frozen=True)
class InitializeSession:
    scope: SessionScope
    expected_revision: str | None
    record: Record
    source_digest: str | None = None


@dataclass(frozen=True)
class TransitionSession:
    scope: SessionScope
    expected_revision: str
    commit: TransitionCommit


@dataclass(frozen=True)
class AcknowledgeSession:
    scope: SessionScope
    expected_revision: str
    feedback: FeedbackRef
    expected_record_revision: str


@dataclass(frozen=True)
class CompleteSession:
    scope: SessionScope
    expected_revision: str
    commit: CompletionCommit


@dataclass(frozen=True)
class SubmitSession:
    scope: SessionScope
    expected_revision: str
    commit: SubmissionCommit


class RecordMutationKind(StrEnum):
    RECORD = "record"
    OBJECTIVE = "objective"
    ARTIFACT = "artifact"
    CONSENT = "consent"


@dataclass(frozen=True)
class MutateSession:
    scope: SessionScope
    expected_revision: str
    record: Record
    expected_record_revision: str
    kind: RecordMutationKind


@dataclass(frozen=True)
class UpgradeSession:
    scope: SessionScope
    expected_revision: str
    commit: UpgradeCommit
    source_digest: str | None = None


@dataclass(frozen=True)
class BindSourceSession:
    """Attach current content to unknown legacy provenance without resetting any state."""

    scope: SessionScope
    expected_revision: str
    source_digest: str


@dataclass(frozen=True)
class DeleteSession:
    scope: SessionScope
    expected_revision: str | None


SessionCommit: TypeAlias = (
    InitializeSession
    | TransitionSession
    | AcknowledgeSession
    | CompleteSession
    | SubmitSession
    | MutateSession
    | UpgradeSession
    | DeleteSession
    | BindSourceSession
)


@dataclass(frozen=True)
class SessionCommitResult:
    read: SessionRead
    replayed: bool = False
    outcome: (
        AdvanceOutcome
        | QuizAnswerOutcome
        | LegacyOutcomeUnavailable
        | CompletionReceipt
        | SubmissionReceipt
        | FeedbackAcknowledgement
        | UpgradeIdentity
        | None
    ) = None


@runtime_checkable
class SessionStore(Protocol):
    def read(self, scope: SessionScope) -> SessionRead: ...
    def commit(self, command: SessionCommit) -> SessionCommitResult: ...
    def list_records(self, namespace: str, course_id: str) -> tuple[Record, ...]: ...
    def export_progress(self, scope: SessionScope) -> Record | None: ...


class RuntimeStore(ProgressStore, Protocol):
    """Internal calculation seam, implemented by file and captured-snapshot adapters."""

    def read_runtime_snapshot(self, learner_id: str, course_id: str) -> RuntimeSnapshot | None: ...
    def get_transition_identity(
        self, learner_id: str, course_id: str, key: str
    ) -> TransitionIdentity | None: ...
    def get_action_result(self, identity: ActionIdentity) -> TransitionResult | None: ...
    def commit_transition(self, commit: TransitionCommit) -> TransitionResult: ...
    def pending_feedback(self, learner_id: str, course_id: str) -> PendingFeedback | None: ...
    def acknowledge_feedback(
        self, ref: FeedbackRef, expected_revision: str
    ) -> FeedbackAcknowledgement: ...
    def commit_upgrade(self, commit: UpgradeCommit) -> UpgradeResult: ...
