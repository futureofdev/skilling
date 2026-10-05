"""Copied application values and bounded, ephemeral presentation receipts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from skilling.session import PendingFeedback, ScopedPendingFeedback, SessionSnapshot


class RuntimeErrorCode(StrEnum):
    INVALID = "invalid-request"
    CAPACITY = "capacity"
    BUSY = "session-busy"
    STALE = "stale-display"
    CONFLICT = "request-conflict"
    MODEL = "model-unavailable"
    EVIDENCE = "evidence-required"
    REVIEW = "review-required"


class TutorSessionError(Exception):
    def __init__(self, code: RuntimeErrorCode, message: str, status: int = 409):
        super().__init__(message)
        self.code = str(code)
        self.status = status


class TutorEventType(StrEnum):
    TEXT_DELTA = "text-delta"
    TEXT_RESET = "text-reset"
    STATE = "state"
    ERROR = "error"


@dataclass(frozen=True)
class TutorEvent:
    type: TutorEventType
    text: str | None = None
    state: dict[str, object] | None = None
    code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class Evidence:
    """Actual application-observed evidence; revision binds confirmation to unchanged work.

    The hook reads trusted application storage. Browser assertions must never populate
    ``checked`` or ``attested_by``; these are the producer's practice provenance.
    """

    text: str
    revision: str
    checked: str | None = None
    attested_by: str | None = None


@dataclass
class Display:
    snapshot: SessionSnapshot
    feedback: PendingFeedback | ScopedPendingFeedback | None
    presented: bool = False
    acknowledged: bool = False


@dataclass
class Turn:
    fingerprint: str
    applied: bool = False
    finished: bool = False


@dataclass(frozen=True)
class Continuation:
    id: str
    display_id: str
    control: str | None
    remaining: int
