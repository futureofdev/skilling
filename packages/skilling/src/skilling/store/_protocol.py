"""The store interface.

A store is deliberately dumb: it persists what it is given and refuses stale writes. It
never interprets, enriches, or repairs a record — derivation is the runtime's job, and a
store that "helpfully" recomputes something becomes a second source of truth.

Absence is represented by absence throughout: a missing record, an empty homework slot,
and an unwritten log are all ``None`` rather than a special stored value.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal, NamedTuple, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..course import (
    CompletionEntry,
    HomeworkArchiveEntry,
    HomeworkSlot,
    Record,
    is_course_id,
    is_semver,
)

Revision = str
"""An opaque token the store issues with every read. Compare it, never parse it."""


class StoreError(Exception):
    pass


class StatePathError(StoreError):
    """Invalid state identifier, unsafe descendant path, or state identity mismatch."""


class StoreBusy(StoreError):
    """The course lock could not be acquired within the bounded wait."""


class RecoveryRequired(StoreError):
    """Recovery metadata needs inspection; no guessed repair is safe."""


class Conflict(StoreError):
    """A write whose ``expected_revision`` did not match the store's current revision.

    Distinguishable by type on purpose: the whole point of optimistic concurrency is that
    a caller can tell "someone else wrote" from "the write failed"."""

    def __init__(self, what: str, expected: Revision | None, actual: Revision | None) -> None:
        super().__init__(
            f"{what} has revision {actual!r}, not the expected {expected!r} — refusing to write"
        )
        self.expected = expected
        self.actual = actual


class NotSupported(StoreError):
    """An operation unsupported by this backend's implemented contract."""


@dataclass(frozen=True)
class CompletionReceipt:
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


@dataclass(frozen=True)
class HomeworkWrite:
    expected_revision: Revision | None
    slot: HomeworkSlot | None


@dataclass(frozen=True)
class CompletionCommit:
    receipt: CompletionReceipt
    expected_record_revision: Revision
    record: Record
    expected_log: tuple[CompletionEntry, ...]
    entry: CompletionEntry
    homework: HomeworkWrite | None


class CompletionCommitResult(NamedTuple):
    record: Record
    revision: Revision
    receipt: CompletionReceipt
    replayed: bool


class InvalidSubmissionToken(ValueError):
    """A malformed or noncanonical submission token; no state access is needed."""


class _TokenFields(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    version: Literal[1]
    learner_id: str = Field(min_length=1)
    course_id: str
    course_version: str
    coordinate: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    instance_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    slot_revision: str = Field(min_length=1)

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("token version must be an integer")
        return value

    @field_validator("course_id")
    @classmethod
    def valid_course(cls, value: str) -> str:
        if not is_course_id(value):
            raise ValueError("invalid submission course id")
        return value

    @field_validator("course_version")
    @classmethod
    def valid_version(cls, value: str) -> str:
        if not is_semver(value):
            raise ValueError("invalid submission course version")
        return value


@dataclass(frozen=True)
class SubmissionToken:
    """Portable checked-assignment identity, not authorization or proof of consent."""

    learner_id: str
    course_id: str
    course_version: str
    coordinate: str
    instance_id: str
    slot_revision: Revision

    @classmethod
    def for_slot(
        cls,
        learner_id: str,
        course_id: str,
        course_version: str,
        slot: HomeworkSlot,
        revision: Revision,
    ) -> SubmissionToken:
        payload = slot.model_dump(mode="json", exclude={"queued"})
        payload["requirements"] = [r.text for r in slot.requirements]
        payload["stretch_goals"] = [r.text for r in slot.stretch_goals]
        instance = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        value = cls(learner_id, course_id, course_version, slot.coordinate, instance, revision)
        return cls.parse(value.encode())

    def encode(self) -> str:
        data = _TokenFields.model_validate({"version": 1, **asdict(self)})
        raw = json.dumps(data.model_dump(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "s1." + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @classmethod
    def parse(cls, token: str) -> SubmissionToken:
        try:
            if not isinstance(token, str) or not token.startswith("s1."):
                raise ValueError("expected a version-1 submission token")
            payload = token[3:]
            raw = base64.b64decode(
                payload + "=" * (-len(payload) % 4), altchars=b"-_", validate=True
            )
            data = _TokenFields.model_validate(json.loads(raw))
            value = cls(**data.model_dump(exclude={"version"}))
            if value.encode() != token:
                raise ValueError("submission token is not canonical")
            return value
        except (ValueError, TypeError, UnicodeError) as exc:
            raise InvalidSubmissionToken(f"Invalid submission token: {exc}") from exc


@dataclass(frozen=True)
class SubmissionReceipt:
    token: str
    learner_id: str
    course_id: str
    course_version: str
    coordinate: str
    instance_id: str
    archive: HomeworkArchiveEntry

    @classmethod
    def checked(cls, receipt: SubmissionReceipt, token: str) -> SubmissionReceipt:
        """Validate copies even when a backend returns a preconstructed model."""
        identity = SubmissionToken.parse(token)
        if receipt.token != token or (
            receipt.learner_id,
            receipt.course_id,
            receipt.course_version,
            receipt.coordinate,
            receipt.instance_id,
        ) != (
            identity.learner_id,
            identity.course_id,
            identity.course_version,
            identity.coordinate,
            identity.instance_id,
        ):
            raise RecoveryRequired("Submission receipt differs from the checked assignment")
        try:
            archive = HomeworkArchiveEntry.model_validate(receipt.archive.model_dump(mode="json"))
        except (ValueError, TypeError, AttributeError) as exc:
            raise RecoveryRequired(f"Invalid submission archive: {exc}") from exc
        if archive.coordinate != identity.coordinate or archive.submitted_at.utcoffset() is None:
            raise RecoveryRequired("Submission archive has invalid coordinate or timestamp")
        return cls(
            token,
            receipt.learner_id,
            receipt.course_id,
            receipt.course_version,
            receipt.coordinate,
            receipt.instance_id,
            archive,
        )


@dataclass(frozen=True)
class SubmissionCommit:
    receipt: SubmissionReceipt
    expected_slot_revision: Revision
    slot: HomeworkSlot | None


@dataclass(frozen=True)
class SubmissionCommitResult:
    receipt: SubmissionReceipt
    replayed: bool


@runtime_checkable
class ProgressStore(Protocol):
    """Every operation in spec/runtime.md#the-store-interface.

    ``expected_revision`` of ``None`` means "I expect this not to exist yet". A returned
    revision of ``None`` means the artifact is now absent.
    """

    def get_record(self, learner_id: str, course_id: str) -> tuple[Record, Revision] | None: ...

    def put_record(self, record: Record, expected_revision: Revision | None) -> Revision: ...

    def append_completion(
        self, learner_id: str, course_id: str, entry: CompletionEntry
    ) -> None: ...

    def get_log(self, learner_id: str, course_id: str) -> list[CompletionEntry]: ...

    def get_homework(
        self, learner_id: str, course_id: str
    ) -> tuple[HomeworkSlot | None, Revision | None]: ...

    def put_homework(
        self,
        learner_id: str,
        course_id: str,
        slot: HomeworkSlot | None,
        expected_revision: Revision | None,
    ) -> Revision | None: ...

    def append_homework_archive(
        self, learner_id: str, course_id: str, entry: HomeworkArchiveEntry
    ) -> None: ...

    def get_homework_archive(
        self, learner_id: str, course_id: str
    ) -> list[HomeworkArchiveEntry]: ...

    def list_records(self, course_id: str) -> list[tuple[str, Record]]: ...

    def get_completion_receipt(
        self, learner_id: str, course_id: str
    ) -> CompletionReceipt | None: ...

    def commit_completion(self, commit: CompletionCommit) -> CompletionCommitResult: ...

    def get_submission_receipt(
        self, learner_id: str, course_id: str, token: str
    ) -> SubmissionReceipt | None: ...

    def commit_submission(self, commit: SubmissionCommit) -> SubmissionCommitResult: ...


def require_store(store: object) -> None:
    """Name missing public capabilities on an older external backend before effects."""
    if isinstance(store, ProgressStore):
        return
    methods = (
        "get_completion_receipt",
        "commit_completion",
        "get_submission_receipt",
        "commit_submission",
    )
    missing = [name for name in methods if not callable(getattr(store, name, None))]
    detail = ", ".join(missing) if missing else "the full ProgressStore contract"
    raise NotSupported(f"Store backend requires {detail}; upgrade the store backend.")
