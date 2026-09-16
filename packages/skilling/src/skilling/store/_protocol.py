"""The store interface.

A store is deliberately dumb: it persists what it is given and refuses stale writes. It
never interprets, enriches, or repairs a record — derivation is the runtime's job, and a
store that "helpfully" recomputes something becomes a second source of truth.

Absence is represented by absence throughout: a missing record, an empty homework slot,
and an unwritten log are all ``None`` rather than a special stored value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple, Protocol, runtime_checkable

from ..course import CompletionEntry, HomeworkArchiveEntry, HomeworkSlot, Record

Revision = str
"""An opaque token the store issues with every read. Compare it, never parse it."""


class StoreError(Exception):
    pass


class StatePathError(StoreError):
    """Invalid state identifier, unsafe descendant path, or state identity mismatch."""


class StoreBusy(StoreError):
    """The course lock could not be acquired within the bounded wait."""


class RecoveryRequired(StoreError):
    """Completion metadata needs inspection; no guessed repair is safe."""


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
