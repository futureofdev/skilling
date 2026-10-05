"""Framework-independent session refusals."""

from enum import StrEnum

from ..delivery import UpgradeRefusal


class RefusalKind(StrEnum):
    INVALID = "invalid"
    CONFLICT = "conflict"
    ILLEGAL = "illegal"


class SessionRefusal(Exception):
    def __init__(self, kind: RefusalKind, code: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.code = code


class VersionMismatch(SessionRefusal):
    def __init__(
        self,
        course_id: str,
        from_version: str,
        to_version: str,
        resumable: bool,
        reason: UpgradeRefusal | None,
        refusal_message: str | None,
    ) -> None:
        super().__init__(
            RefusalKind.INVALID, "version-mismatch", "course version differs from record"
        )
        self.course_id = course_id
        self.from_version = from_version
        self.to_version = to_version
        self.resumable = resumable
        self.reason = reason
        self.refusal_message = refusal_message
