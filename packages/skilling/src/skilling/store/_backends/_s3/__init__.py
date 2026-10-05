"""Conditional S3-compatible complete-session persistence (optional caller-owned SDK)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ....course import Record
from ..._protocol import (
    Conflict,
    ReconciliationRequired,
    RecoveryRequired,
    SessionCommit,
    SessionCommitResult,
    SessionRead,
    SessionReadKind,
    SessionScope,
)
from ..._protocol._boundary import validate_command, validate_scope
from .._aggregate import apply, decode, encode, replay
from ._control import Mode, read_control, ready, reserve
from ._objects import (
    ConditionalFailure,
    Objects,
    ReadUnavailable,
    UncertainWrite,
    digest,
    stream_key,
)

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class S3SessionStore:
    """One conditional aggregate Put per mutation; SDK retries must be disabled.

    The client is caller-owned and never closed. Calls are synchronous and must be
    offloaded by async hosts. Logical deletion retains an authoritative tombstone.
    """

    def __init__(self, objects: Objects) -> None:
        self._objects = objects

    @classmethod
    def open(cls, client: S3Client, bucket: str, prefix: str) -> S3SessionStore:
        objects = Objects(client, bucket, prefix)
        if read_control(objects) is None:
            reserve(objects, Mode.READY)
        ready(objects)
        return cls(objects)

    def read(self, scope: SessionScope) -> SessionRead:
        validate_scope(scope)
        ready(self._objects)
        value = self._objects.get(stream_key(scope))
        return (
            decode(value.body, scope) if value else SessionRead(SessionReadKind.ABSENT, scope, None)
        )

    def commit(self, command: SessionCommit) -> SessionCommitResult:
        validate_command(command)
        objects = self._objects
        ready(objects)
        key = stream_key(command.scope)
        original = objects.get(key)
        current = (
            decode(original.body, command.scope)
            if original
            else SessionRead(SessionReadKind.ABSENT, command.scope, None)
        )
        result = apply(current, command)
        if result.replayed:
            return result
        raw = encode(result.read)
        try:
            objects.put(key, raw, original.etag if original else None)
        except (ConditionalFailure, UncertainWrite) as exc:
            try:
                latest = self.read(command.scope)
            except ReadUnavailable:
                raise ReconciliationRequired(
                    "S3 commit outcome could not be observed; reconcile the original operation"
                ) from None
            recovered = replay(latest, command)
            if recovered is not None:
                return recovered
            if isinstance(exc, ConditionalFailure):
                raise Conflict(
                    "session", command.expected_revision, latest.session_revision
                ) from None
            raise ReconciliationRequired(
                "S3 commit acknowledgement uncertain; inspect current state before new consent"
            ) from None
        return result

    def list_records(self, namespace: str, course_id: str) -> tuple[Record, ...]:
        from ._backup import decode_entry

        validate_scope(SessionScope(namespace, "administrative-enumeration", course_id))
        ready(self._objects)
        prefix = f"streams/{digest(namespace)}/{digest(course_id)}/"
        records: list[Record] = []
        for key in self._objects.keys(prefix):
            value = self._objects.get(key)
            if value is None:
                raise RecoveryRequired("S3 inventory changed during enumeration")
            read = decode_entry(key, value.body)
            if read.scope.namespace != namespace or read.scope.course_id != course_id:
                raise RecoveryRequired("S3 enumeration scope mismatch")
            if read.state is not None:
                records.append(read.state.record)
        return tuple(sorted(records, key=lambda record: record.learner_id))

    def export_progress(self, scope: SessionScope) -> Record | None:
        """Inspection-only progress; excludes recovery state and cannot restore a session."""
        value = self.read(scope)
        return value.state.record if value.state is not None else None

    def backup(self, destination: Path) -> None:
        """Full prefix backup; the producer must quiesce all writers first."""
        from ._backup import backup

        backup(self._objects, destination)

    @classmethod
    def restore(cls, client: S3Client, bucket: str, prefix: str, source: Path) -> S3SessionStore:
        """Validate all bodies, reserve an empty prefix, verify, then publish READY."""
        from ._backup import restore

        objects = Objects(client, bucket, prefix)
        restore(objects, source)
        return cls(objects)
