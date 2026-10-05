"""Transactional, same-host SQLite persistence for complete scoped sessions."""

from __future__ import annotations

import math
import os
import sqlite3
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ...course import Record
from .._io import _fsync_dir
from .._protocol import (
    ReconciliationRequired,
    RecoveryRequired,
    SessionCommit,
    SessionCommitResult,
    SessionRead,
    SessionReadKind,
    SessionSchemaError,
    SessionScope,
    StatePathError,
    StoreBusy,
    StoreError,
)
from .._protocol._boundary import validate_command, validate_scope
from ._aggregate import apply, decode, encode

_SCHEMA = (
    "CREATE TABLE skilling_schema (version INTEGER NOT NULL CHECK(version = 1))",
    "CREATE TABLE skilling_sessions ("
    "namespace TEXT NOT NULL, learner_id TEXT NOT NULL, course_id TEXT NOT NULL, "
    "generation TEXT NOT NULL, deleted INTEGER NOT NULL CHECK(deleted IN (0, 1)), "
    "payload BLOB, PRIMARY KEY(namespace, learner_id, course_id), "
    "CHECK((deleted = 0 AND payload IS NOT NULL) OR (deleted = 1 AND payload IS NULL)))",
)


class SQLiteSessionStore:
    """A synchronous store with one bounded connection per call.

    Producers must run these calls outside their asynchronous event loop. The path
    belongs to a stopped/local same-host deployment; network filesystem coordination
    and power-loss behavior are not implied by process-interruption tests.
    """

    def __init__(self, path: Path, timeout: float) -> None:
        self.path = path
        self.timeout = timeout
        self._closed = False

    @classmethod
    def open(cls, path: Path, *, timeout: float = 5.0) -> SQLiteSessionStore:
        if not isinstance(path, Path) or not path.is_absolute():
            raise StatePathError("SQLite requires an explicit absolute database path")
        if isinstance(timeout, bool) or not math.isfinite(timeout) or not 0 <= timeout <= 60:
            raise ValueError("SQLite timeout must be between zero and 60 seconds")
        if path.is_symlink() or not path.parent.is_dir() or (path.exists() and not path.is_file()):
            raise StatePathError("SQLite database path must be a local regular file")
        value = cls(path, timeout)
        with value._connection(create=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            names = connection.execute("SELECT name FROM sqlite_master").fetchall()
            if not names:
                if connection.execute("PRAGMA user_version").fetchone()[0] != 0:
                    raise SessionSchemaError("Unrecognized SQLite metadata version")
                for statement in _SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO skilling_schema VALUES (1)")
            value._schema(connection)
            connection.commit()
        return value

    def close(self) -> None:
        """Refuse future operations; per-call connections already close on return."""
        self._closed = True

    def __enter__(self) -> SQLiteSessionStore:
        if self._closed:
            raise StoreError("SQLite session store is closed")
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @contextmanager
    def _connection(self, *, create: bool = False) -> Iterator[sqlite3.Connection]:
        if self._closed:
            raise StoreError("SQLite session store is closed")
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self.path.as_uri() + ("?mode=rwc" if create else "?mode=rw"),
                uri=True,
                timeout=self.timeout,
                isolation_level=None,
            )
            if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                raise RecoveryRequired("SQLite requires DELETE journal mode")
            connection.execute("PRAGMA synchronous=EXTRA")
            yield connection
        except sqlite3.Error as exc:
            if exc.sqlite_errorcode in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                raise StoreBusy("SQLite transaction exceeded the configured busy wait") from None
            raise RecoveryRequired(
                "SQLite operation failed; inspect the configured database"
            ) from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _schema(connection: sqlite3.Connection) -> None:
        actual = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        if [row[0] for row in actual] != list(_SCHEMA):
            raise SessionSchemaError(
                "Unsupported SQLite layout; no automatic migration is available"
            )
        if connection.execute("SELECT version FROM skilling_schema").fetchall() != [(1,)]:
            raise SessionSchemaError("Unsupported SQLite schema version")
        extras = connection.execute(
            "SELECT name FROM sqlite_master WHERE type NOT IN ('table', 'index') "
            "OR (type='index' AND sql IS NOT NULL)"
        ).fetchall()
        if extras:
            raise SessionSchemaError("Unsupported SQLite schema objects")

    def read(self, scope: SessionScope) -> SessionRead:
        validate_scope(scope)
        with self._connection() as connection:
            self._schema(connection)
            return self._read(connection, scope)

    @staticmethod
    def _read(connection: sqlite3.Connection, scope: SessionScope) -> SessionRead:
        row = connection.execute(
            "SELECT generation, deleted, payload FROM skilling_sessions "
            "WHERE namespace=? AND learner_id=? AND course_id=?",
            (scope.namespace, scope.learner_id, scope.course_id),
        ).fetchone()
        if row is None:
            return SessionRead(SessionReadKind.ABSENT, scope, None)
        generation, deleted, payload = row
        if not isinstance(generation, str) or not generation or type(deleted) is not int:
            raise RecoveryRequired("Invalid SQLite session metadata")
        if deleted == 1 and payload is None:
            return SessionRead(SessionReadKind.DELETED, scope, generation)
        if deleted != 0 or not isinstance(payload, bytes):
            raise RecoveryRequired("Invalid SQLite session payload")
        value = decode(payload, scope)
        if value.session_revision != generation or value.kind != SessionReadKind.LIVE:
            raise RecoveryRequired("SQLite row metadata differs from complete aggregate")
        return value

    def commit(self, command: SessionCommit) -> SessionCommitResult:
        validate_command(command)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._schema(connection)
            current = self._read(connection, command.scope)
            result = apply(current, command)
            if result.replayed:
                connection.rollback()
                return result
            value = result.read
            payload = encode(value) if value.kind == SessionReadKind.LIVE else None
            deleted = int(value.kind == SessionReadKind.DELETED)
            if current.kind == SessionReadKind.ABSENT:
                connection.execute(
                    "INSERT INTO skilling_sessions "
                    "(namespace, learner_id, course_id, generation, deleted, payload) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        value.scope.namespace,
                        value.scope.learner_id,
                        value.scope.course_id,
                        value.session_revision,
                        deleted,
                        payload,
                    ),
                )
            else:
                connection.execute(
                    "UPDATE skilling_sessions SET generation=?, deleted=?, payload=? "
                    "WHERE namespace=? AND learner_id=? AND course_id=?",
                    (
                        value.session_revision,
                        deleted,
                        payload,
                        value.scope.namespace,
                        value.scope.learner_id,
                        value.scope.course_id,
                    ),
                )
            try:
                connection.commit()
            except sqlite3.Error:
                raise ReconciliationRequired(
                    "SQLite commit acknowledgement is uncertain; reconcile before retry"
                ) from None
            return result

    def list_records(self, namespace: str, course_id: str) -> tuple[Record, ...]:
        validate_scope(SessionScope(namespace, "administrative-enumeration", course_id))
        with self._connection() as connection:
            connection.execute("BEGIN")
            self._schema(connection)
            learners = connection.execute(
                "SELECT learner_id FROM skilling_sessions "
                "WHERE namespace=? AND course_id=? ORDER BY learner_id",
                (namespace, course_id),
            ).fetchall()
            records: list[Record] = []
            for row in learners:
                if not isinstance(row[0], str):
                    raise RecoveryRequired("Invalid SQLite learner identity")
                value = self._read(connection, SessionScope(namespace, row[0], course_id))
                if value.kind == SessionReadKind.DELETED:
                    continue
                if value.state is None:
                    raise RecoveryRequired("Missing live SQLite state")
                records.append(value.state.record)
            return tuple(records)

    def export_progress(self, scope: SessionScope) -> Record | None:
        """Inspection-only normalized progress; cannot restore the complete session."""
        value = self.read(scope)
        return value.state.record if value.state is not None else None

    def backup(self, destination: Path) -> None:
        """Write a native complete backup to a new path, never overwrite one."""
        self._copy_to(destination)

    @classmethod
    def restore(
        cls, source: Path, destination: Path, *, timeout: float = 5.0
    ) -> SQLiteSessionStore:
        """Validate a stopped backup, copy to a new path, and reopen it."""
        if not source.is_absolute() or not source.is_file() or source.is_symlink():
            raise StatePathError("Restore source must be an absolute regular database file")
        value = cls(source, timeout)
        value._copy_to(destination)
        return cls.open(destination, timeout=timeout)

    def _copy_to(self, destination: Path) -> None:
        if not destination.is_absolute() or not destination.parent.is_dir():
            raise StatePathError("Backup destination requires an absolute path and existing parent")
        if destination.exists() or destination.is_symlink():
            raise StatePathError("Backup destination must not exist")
        try:
            descriptor, staging_name = tempfile.mkstemp(
                prefix=".skilling-backup-", dir=destination.parent
            )
            os.close(descriptor)
        except OSError:
            raise StatePathError("Backup destination must have a writable parent") from None
        staging = Path(staging_name)
        deadline = time.monotonic() + max(self.timeout, 0.01)

        def progress(status: int, remaining: int, total: int) -> None:
            if status != sqlite3.SQLITE_DONE and time.monotonic() > deadline:
                raise StoreBusy("SQLite backup exceeded the configured busy wait")

        try:
            with self._connection() as source:
                self._validate_database(source)
                target = sqlite3.connect(staging, isolation_level=None)
                try:
                    source.backup(target, pages=128, progress=progress, sleep=0.01)
                    self._validate_database(target)
                finally:
                    target.close()
            with staging.open("rb") as stream:
                os.fsync(stream.fileno())
            # Link publishes a complete validated file atomically and refuses an existing target.
            os.link(staging, destination)
            _fsync_dir(destination.parent)
        except sqlite3.Error:
            raise RecoveryRequired("SQLite backup failed") from None
        except OSError:
            raise StatePathError(
                "Backup destination could not be published without overwrite"
            ) from None
        finally:
            staging.unlink(missing_ok=True)

    def _validate_database(self, connection: sqlite3.Connection) -> None:
        self._schema(connection)
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RecoveryRequired("SQLite integrity check failed")
        for row in connection.execute(
            "SELECT namespace, learner_id, course_id FROM skilling_sessions"
        ):
            if not all(isinstance(component, str) for component in row):
                raise RecoveryRequired("Invalid SQLite scope columns")
            scope = SessionScope(row[0], row[1], row[2])
            validate_scope(scope)
            self._read(connection, scope)
