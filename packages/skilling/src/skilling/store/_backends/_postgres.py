"""Complete session aggregates in a producer-owned synchronous PostgreSQL pool."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Generic, NamedTuple, TypeVar

from ...course import Record
from .._protocol import (
    ReconciliationRequired,
    RecoveryRequired,
    SessionCommit,
    SessionCommitResult,
    SessionRead,
    SessionReadKind,
    SessionSchemaError,
    SessionScope,
    StoreBusy,
    StoreError,
)
from .._protocol._boundary import validate_command, validate_scope
from ._aggregate import apply, decode, encode

if TYPE_CHECKING:
    from psycopg import Connection
    from psycopg_pool import ConnectionPool


ConnectionT = TypeVar("ConnectionT", bound="Connection[tuple[object, ...]]")


class _Values(NamedTuple):
    namespace: str
    learner_id: str
    course_id: str
    generation: str | None
    deleted: bool
    payload: bytes | None


class PostgresSessionStore(Generic[ConnectionT]):
    """One bounded transaction per operation; the producer retains pool ownership."""

    def __init__(
        self,
        pool: ConnectionPool[ConnectionT],
        schema: str,
        timeout: float,
        statement_timeout: float,
    ) -> None:
        self.pool = pool
        self.schema = schema
        self.timeout = timeout
        self.statement_timeout = statement_timeout
        self._closed = False

    @classmethod
    def open(
        cls,
        pool: ConnectionPool[ConnectionT],
        *,
        schema: str = "skilling",
        timeout: float = 5.0,
        statement_timeout: float = 10.0,
    ) -> PostgresSessionStore[ConnectionT]:
        try:
            from psycopg_pool import ConnectionPool
        except ImportError:
            raise StoreError("PostgreSQL requires the skilling[postgres] extra") from None
        if not isinstance(pool, ConnectionPool) or pool.closed:
            raise StoreError("PostgreSQL requires an open producer-owned synchronous pool")
        if (
            not isinstance(schema, str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema) is None
            or schema in {"public", "information_schema"}
            or schema.startswith("pg_")
        ):
            raise ValueError("PostgreSQL requires a lowercase dedicated schema identifier")
        for value in (timeout, statement_timeout):
            if isinstance(value, bool) or not math.isfinite(value) or not 0 < value <= 60:
                raise ValueError("PostgreSQL waits must be positive and at most 60 seconds")
        store = cls(pool, schema, timeout, statement_timeout)
        with store._transaction() as connection:
            store._initialize(connection)
        return store

    def close(self) -> None:
        """Disable this adapter without closing the producer's pool."""
        self._closed = True

    def __enter__(self) -> PostgresSessionStore[ConnectionT]:
        if self._closed:
            raise StoreError("PostgreSQL session store is closed")
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[ConnectionT]:
        from psycopg import Error, OperationalError
        from psycopg.errors import DeadlockDetected, LockNotAvailable, QueryCanceled
        from psycopg_pool import PoolClosed, PoolTimeout

        if self._closed:
            raise StoreError("PostgreSQL session store is closed")
        try:
            with self.pool.connection(timeout=self.timeout) as connection, connection.transaction():
                connection.execute(
                    "SELECT set_config('lock_timeout', %s, true), "
                    "set_config('statement_timeout', %s, true)",
                    (
                        str(math.ceil(self.timeout * 1000)),
                        str(math.ceil(self.statement_timeout * 1000)),
                    ),
                )
                yield connection
        except (PoolTimeout, LockNotAvailable, QueryCanceled, DeadlockDetected):
            raise StoreBusy("PostgreSQL operation exceeded its bounded wait") from None
        except PoolClosed:
            raise StoreError("PostgreSQL producer pool is closed") from None
        except OperationalError:
            if write:
                raise ReconciliationRequired(
                    "PostgreSQL commit outcome is uncertain; reconcile the original operation"
                ) from None
            raise RecoveryRequired("PostgreSQL connection failed") from None
        except Error:
            raise RecoveryRequired(
                "PostgreSQL operation failed; inspect the selected store"
            ) from None

    def _initialize(self, connection: Connection[tuple[object, ...]]) -> None:
        from psycopg import sql

        lock = int.from_bytes(
            hashlib.sha256(("skilling-schema:" + self.schema).encode()).digest()[:8],
            "big",
            signed=True,
        )
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
        exists = connection.execute(
            "SELECT 1 FROM pg_namespace WHERE nspname=%s", (self.schema,)
        ).fetchone()
        if exists is None:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        tables = connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema=%s",
            (self.schema,),
        ).fetchall()
        if not tables:
            connection.execute(
                sql.SQL(
                    "CREATE TABLE {}.schema_version (version INTEGER NOT NULL CHECK (version=1))"
                ).format(sql.Identifier(self.schema))
            )
            connection.execute(
                sql.SQL(
                    "CREATE TABLE {}.sessions (namespace TEXT NOT NULL, learner_id TEXT NOT NULL, "
                    "course_id TEXT NOT NULL, generation TEXT NOT NULL, deleted BOOLEAN NOT NULL, "
                    "payload BYTEA, PRIMARY KEY(namespace, learner_id, course_id), "
                    "CHECK ((deleted AND payload IS NULL) "
                    "OR (NOT deleted AND payload IS NOT NULL)))"
                ).format(sql.Identifier(self.schema))
            )
            connection.execute(
                sql.SQL("INSERT INTO {}.schema_version VALUES (1)").format(
                    sql.Identifier(self.schema)
                )
            )
        self._schema(connection)

    def _schema(self, connection: Connection[tuple[object, ...]]) -> None:
        from psycopg import sql

        names = connection.execute(
            "SELECT table_name, table_type FROM information_schema.tables "
            "WHERE table_schema=%s ORDER BY table_name",
            (self.schema,),
        ).fetchall()
        if names != [("schema_version", "BASE TABLE"), ("sessions", "BASE TABLE")]:
            raise SessionSchemaError("Unsupported PostgreSQL store layout")
        relations = connection.execute(
            "SELECT c.relname,c.relkind,c.relrowsecurity,c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=%s ORDER BY c.relname",
            (self.schema,),
        ).fetchall()
        if relations != [
            ("schema_version", "r", False, False),
            ("sessions", "r", False, False),
            ("sessions_pkey", "i", False, False),
        ]:
            raise SessionSchemaError("Unsupported PostgreSQL store relations or row policies")
        effects = connection.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=%s AND NOT t.tgisinternal), "
            "EXISTS(SELECT 1 FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s)",
            (self.schema, self.schema),
        ).fetchone()
        if effects != (False, False):
            raise SessionSchemaError("Unsupported PostgreSQL store triggers or rewrite rules")
        rows = connection.execute(
            sql.SQL("SELECT version FROM {}.schema_version").format(sql.Identifier(self.schema))
        ).fetchall()
        if rows != [(1,)]:
            raise SessionSchemaError("Unsupported PostgreSQL storage schema version")
        columns = connection.execute(
            "SELECT table_name,column_name,data_type,is_nullable FROM information_schema.columns "
            "WHERE table_schema=%s ORDER BY table_name,ordinal_position",
            (self.schema,),
        ).fetchall()
        expected = [
            ("schema_version", "version", "integer", "NO"),
            ("sessions", "namespace", "text", "NO"),
            ("sessions", "learner_id", "text", "NO"),
            ("sessions", "course_id", "text", "NO"),
            ("sessions", "generation", "text", "NO"),
            ("sessions", "deleted", "boolean", "NO"),
            ("sessions", "payload", "bytea", "YES"),
        ]
        if columns != expected:
            raise SessionSchemaError("Unsupported PostgreSQL storage columns")
        primary = connection.execute(
            "SELECT a.attname FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum,ord) ON true "
            "JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum "
            "WHERE n.nspname=%s AND c.relname='sessions' AND i.indisprimary ORDER BY k.ord",
            (self.schema,),
        ).fetchall()
        if primary != [("namespace",), ("learner_id",), ("course_id",)]:
            raise SessionSchemaError("PostgreSQL session identity constraint is missing")

    def _read(
        self,
        connection: Connection[tuple[object, ...]],
        scope: SessionScope,
        *,
        lock: bool = False,
    ) -> SessionRead:
        from psycopg import sql

        query = sql.SQL(
            "SELECT generation,deleted,payload FROM {}.sessions "
            "WHERE namespace=%s AND learner_id=%s AND course_id=%s"
        ).format(sql.Identifier(self.schema))
        if lock:
            query += sql.SQL(" FOR UPDATE")
        row = connection.execute(
            query, (scope.namespace, scope.learner_id, scope.course_id)
        ).fetchone()
        if row is None:
            return SessionRead(SessionReadKind.ABSENT, scope, None)
        generation, deleted, payload = row
        if not isinstance(generation, str) or not generation or type(deleted) is not bool:
            raise RecoveryRequired("Invalid PostgreSQL session metadata")
        if deleted and payload is None:
            return SessionRead(SessionReadKind.DELETED, scope, generation)
        if deleted or not isinstance(payload, bytes):
            raise RecoveryRequired("Invalid PostgreSQL session payload")
        value = decode(payload, scope)
        if value.kind is not SessionReadKind.LIVE or value.session_revision != generation:
            raise RecoveryRequired("PostgreSQL metadata differs from complete aggregate")
        return value

    def read(self, scope: SessionScope) -> SessionRead:
        validate_scope(scope)
        with self._transaction() as connection:
            self._schema(connection)
            return self._read(connection, scope)

    def commit(self, command: SessionCommit) -> SessionCommitResult:
        from psycopg import sql

        validate_command(command)
        with self._transaction(write=True) as connection:
            self._schema(connection)
            current = self._read(connection, command.scope, lock=True)
            result = apply(current, command)
            if result.replayed:
                return result
            if current.kind is SessionReadKind.ABSENT:
                inserted = connection.execute(
                    sql.SQL(
                        "INSERT INTO {}.sessions "
                        "(namespace,learner_id,course_id,generation,deleted,payload) "
                        "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING generation"
                    ).format(sql.Identifier(self.schema)),
                    self._values(result.read),
                ).fetchone()
                if inserted is not None:
                    if inserted != (result.read.session_revision,):
                        raise RecoveryRequired(
                            "PostgreSQL initialization was not stored as prepared"
                        )
                    return result
                current = self._read(connection, command.scope, lock=True)
                if current.kind is SessionReadKind.ABSENT:
                    raise RecoveryRequired("PostgreSQL initialization did not create a stream")
                result = apply(current, command)
                if result.replayed:
                    return result
            value = result.read
            updated = connection.execute(
                sql.SQL(
                    "UPDATE {}.sessions SET generation=%s,deleted=%s,payload=%s "
                    "WHERE namespace=%s AND learner_id=%s AND course_id=%s RETURNING generation"
                ).format(sql.Identifier(self.schema)),
                (
                    value.session_revision,
                    value.kind is SessionReadKind.DELETED,
                    encode(value) if value.kind is SessionReadKind.LIVE else None,
                    value.scope.namespace,
                    value.scope.learner_id,
                    value.scope.course_id,
                ),
            ).fetchone()
            if updated != (value.session_revision,):
                raise RecoveryRequired("PostgreSQL mutation was not stored as prepared")
            return result

    @staticmethod
    def _values(value: SessionRead) -> _Values:
        return _Values(
            value.scope.namespace,
            value.scope.learner_id,
            value.scope.course_id,
            value.session_revision,
            value.kind is SessionReadKind.DELETED,
            encode(value) if value.kind is SessionReadKind.LIVE else None,
        )

    def list_records(self, namespace: str, course_id: str) -> tuple[Record, ...]:
        from psycopg import sql

        validate_scope(SessionScope(namespace, "enumeration", course_id))
        with self._transaction() as connection:
            self._schema(connection)
            rows = connection.execute(
                sql.SQL(
                    "SELECT learner_id FROM {}.sessions WHERE namespace=%s AND course_id=%s "
                    "AND NOT deleted ORDER BY learner_id"
                ).format(sql.Identifier(self.schema)),
                (namespace, course_id),
            ).fetchall()
            result: list[Record] = []
            for row in rows:
                if not isinstance(row[0], str):
                    raise RecoveryRequired("Invalid PostgreSQL learner identity")
                value = self._read(connection, SessionScope(namespace, row[0], course_id))
                if value.state is not None:
                    result.append(value.state.record.model_copy(deep=True))
            return tuple(result)

    def export_progress(self, scope: SessionScope) -> Record | None:
        value = self.read(scope)
        return value.state.record.model_copy(deep=True) if value.state is not None else None
