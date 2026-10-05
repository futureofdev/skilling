"""Copied complete-session values; no backend or teaching behavior."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from ...course import CompletionEntry, HomeworkArchiveEntry, HomeworkSlot, Record
from ._progress import CompletionReceipt, StoreError, SubmissionReceipt

if TYPE_CHECKING:
    from .._journal import (
        ActionIdentity,
        AdvanceOutcome,
        FeedbackRef,
        LegacyOutcomeUnavailable,
        QuizAnswerOutcome,
        TransitionIdentity,
        UpgradeIdentity,
    )


@dataclass(frozen=True)
class SessionScope:
    namespace: str
    learner_id: str
    course_id: str


class SessionReadKind(StrEnum):
    ABSENT = "absent"
    LIVE = "live"
    DELETED = "deleted"


@dataclass(frozen=True)
class SessionActionReceipt:
    identity: ActionIdentity | TransitionIdentity
    outcome: AdvanceOutcome | QuizAnswerOutcome | LegacyOutcomeUnavailable


@dataclass(frozen=True)
class SessionKeyReservation:
    course_version: str
    key: str


@dataclass(frozen=True)
class SessionUpgradeReceipt:
    identity: UpgradeIdentity


@dataclass(frozen=True)
class SessionState:
    record: Record
    record_revision: str
    scratch: bytes = b""
    log: tuple[CompletionEntry, ...] = ()
    homework: HomeworkSlot | None = None
    homework_revision: str | None = None
    archive: tuple[HomeworkArchiveEntry, ...] = ()
    completion_receipts: tuple[CompletionReceipt, ...] = ()
    action_receipts: tuple[SessionActionReceipt, ...] = ()
    reservations: tuple[SessionKeyReservation, ...] = ()
    submission_receipts: tuple[SubmissionReceipt, ...] = ()
    upgrades: tuple[SessionUpgradeReceipt, ...] = ()
    source_digest: str | None = None


@dataclass(frozen=True)
class SessionRead:
    kind: SessionReadKind
    scope: SessionScope
    session_revision: str | None
    state: SessionState | None = None


@dataclass(frozen=True)
class ScopedAction:
    scope: SessionScope
    identity: ActionIdentity
    session_revision: str


@dataclass(frozen=True)
class ScopedFeedback:
    scope: SessionScope
    feedback: FeedbackRef
    session_revision: str
    record_revision: str


@dataclass(frozen=True)
class ScopedSubmission:
    scope: SessionScope
    token: str
    session_revision: str


class SessionDeleted(StoreError):
    """A tombstoned stream cannot be recreated or replayed."""


class SessionCapacity(StoreError):
    """A complete durable aggregate exceeds its backend capacity."""


class SessionSchemaError(StoreError):
    """The selected store has an unsupported storage schema."""


class ReconciliationRequired(StoreError):
    """Commit acknowledgement is uncertain; read before another mutation."""
