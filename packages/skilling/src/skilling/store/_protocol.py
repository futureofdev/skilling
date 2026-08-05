"""The store interface.

A store is deliberately dumb: it persists what it is given and refuses stale writes. It
never interprets, enriches, or repairs a record — derivation is the runtime's job, and a
store that "helpfully" recomputes something becomes a second source of truth.

Absence is represented by absence throughout: a missing record, an empty homework slot,
and an unwritten log are all ``None`` rather than a special stored value.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..course import CompletionEntry, HomeworkArchiveEntry, HomeworkSlot, Record

Revision = str
"""An opaque token the store issues with every read. Compare it, never parse it."""


class StoreError(Exception):
    pass


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
    """An optional operation this backend does not implement."""


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
