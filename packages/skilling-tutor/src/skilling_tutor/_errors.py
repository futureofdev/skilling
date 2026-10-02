"""Adapter failures have no learning-state or rollback meaning."""

from enum import StrEnum


class TutorErrorKind(StrEnum):
    CONTEXT = "invalid-context"
    CONFIGURATION = "configuration"
    USAGE = "usage-limit"
    MODEL = "model-failure"
    ADVICE = "invalid-advice"


class TutorError(Exception):
    def __init__(self, kind: TutorErrorKind, message: str) -> None:
        self.kind = kind
        super().__init__(message)
