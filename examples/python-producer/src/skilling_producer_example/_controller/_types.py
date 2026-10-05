"""Private controller custody values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from skilling.session import (
    PendingFeedback,
    ScopedPendingFeedback,
    SessionSnapshot,
)
from skilling.store import ScopedSubmission
from skilling_tutor import HomeworkAdvice, ObjectiveAdvice

from ._note import NoteObservation


class ControllerError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status


class ReviewKind(StrEnum):
    OBJECTIVES = "objectives"
    HOMEWORK = "homework"


@dataclass
class Review:
    id: str
    kind: ReviewKind
    advice: ObjectiveAdvice | HomeworkAdvice
    record_revision: str
    note: NoteObservation | None
    explanation: str
    submission_token: str | None = None
    displayed: bool = False
    snapshot: SessionSnapshot | None = None
    submission: ScopedSubmission | None = None


@dataclass(frozen=True)
class Display:
    snapshot: SessionSnapshot | None
    feedback: PendingFeedback | ScopedPendingFeedback | None


@dataclass(frozen=True)
class Continuation:
    id: str
    control: str
    display_id: str
    remaining: int
