"""PostgreSQL 17 service concurrency, schema, lifecycle and commit uncertainty."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier
from typing import TYPE_CHECKING

import pytest

from skilling.course import Course, Record
from skilling.store import (
    Conflict,
    DeleteSession,
    InitializeSession,
    MutateSession,
    ReconciliationRequired,
    RecordMutationKind,
    RecoveryRequired,
    SessionDeleted,
    SessionReadKind,
    SessionSchemaError,
    SessionScope,
    StoreBusy,
    StoreError,
)
from skilling.store._backends._postgres import PostgresSessionStore

from ._support import PostgresFixture, postgres_fixture

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def postgres(request: pytest.FixtureRequest) -> PostgresFixture:
    return postgres_fixture(request)


def initialize(postgres: PostgresFixture, path: Path, learner: str = "learner") -> SessionScope:
    course = Course.load(path)
    scope = SessionScope("producer", learner, course.id)
    postgres.store.commit(InitializeSession(scope, None, Record.new(course, learner)))
    return scope


def test_create_race_delete_restart_and_pool_ownership(
    postgres: PostgresFixture, clean_dir: Path
) -> None:
    course = Course.load(clean_dir)
    scope = SessionScope("producer", "learner", course.id)
    command = InitializeSession(scope, None, Record.new(course, "learner"))
    barrier = Barrier(2)

    def create() -> str:
        barrier.wait(timeout=5)
        try:
            postgres.store.commit(command)
            return "created"
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(lambda _: create(), range(2))) == ["conflict", "created"]
    read = postgres.store.read(scope)
    assert read.state is not None
    postgres.store.commit(DeleteSession(scope, read.session_revision))
    reopened = PostgresSessionStore.open(postgres.pool, schema=postgres.store.schema)
    assert reopened.read(scope).kind is SessionReadKind.DELETED
    with pytest.raises(SessionDeleted):
        reopened.commit(command)
    reopened.close()
    assert not postgres.pool.closed
    with pytest.raises(StoreError, match="closed"):
        reopened.read(scope)


def test_distinct_streams_do_not_share_row_locks(
    postgres: PostgresFixture, clean_dir: Path
) -> None:
    from psycopg import sql

    a = initialize(postgres, clean_dir, "a")
    b = initialize(postgres, clean_dir, "b")
    store = PostgresSessionStore.open(postgres.pool, schema=postgres.store.schema, timeout=0.1)
    with postgres.pool.connection() as locker:
        locker.execute(
            sql.SQL("SELECT * FROM {}.sessions WHERE learner_id=%s FOR UPDATE").format(
                sql.Identifier(store.schema)
            ),
            ("a",),
        )
        current_b = store.read(b)
        assert current_b.state is not None and current_b.session_revision is not None
        changed = current_b.state.record.model_copy(update={"streak_days": 4})
        store.commit(
            MutateSession(
                b,
                current_b.session_revision,
                changed,
                current_b.state.record_revision,
                RecordMutationKind.RECORD,
            )
        )
        current_a = store.read(a)
        assert current_a.session_revision is not None
        with pytest.raises(StoreBusy):
            store.commit(DeleteSession(a, current_a.session_revision))
    assert store.read(b).state is not None


def test_corruption_and_schema_refuse_without_secret_diagnostics(
    postgres: PostgresFixture, clean_dir: Path
) -> None:
    from psycopg import sql

    scope = initialize(postgres, clean_dir)
    with postgres.pool.connection() as connection:
        connection.execute(
            sql.SQL("UPDATE {}.sessions SET payload=%s").format(
                sql.Identifier(postgres.store.schema)
            ),
            (b"broken",),
        )
    with pytest.raises(RecoveryRequired) as error:
        postgres.store.read(scope)
    assert postgres.config.password not in str(error.value)
    with postgres.pool.connection() as connection:
        connection.execute(
            sql.SQL(
                "ALTER TABLE {}.schema_version DROP CONSTRAINT schema_version_version_check"
            ).format(sql.Identifier(postgres.store.schema))
        )
        connection.execute(
            sql.SQL("UPDATE {}.schema_version SET version=2").format(
                sql.Identifier(postgres.store.schema)
            )
        )
    with pytest.raises(SessionSchemaError):
        PostgresSessionStore.open(postgres.pool, schema=postgres.store.schema)


def test_concurrent_schema_creation(postgres: PostgresFixture) -> None:
    from uuid import uuid4

    from psycopg import sql

    schema = "race_" + uuid4().hex
    barrier = Barrier(2)

    def open_schema() -> str:
        barrier.wait(timeout=5)
        return PostgresSessionStore.open(postgres.pool, schema=schema).schema

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            assert list(workers.map(lambda _: open_schema(), range(2))) == [schema, schema]
    finally:
        with postgres.pool.connection() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_commit_response_loss_requires_reconcile(
    postgres: PostgresFixture, clean_dir: Path
) -> None:
    from psycopg import Connection, OperationalError, Transaction
    from psycopg_pool import ConnectionPool

    class LostAcknowledgement(Connection[tuple[object, ...]]):
        lose_response = False

        @contextmanager
        def transaction(
            self, savepoint_name: str | None = None, force_rollback: bool = False
        ) -> Iterator[Transaction]:
            with super().transaction(
                savepoint_name=savepoint_name, force_rollback=force_rollback
            ) as transaction:
                yield transaction
            if self.lose_response:
                self.lose_response = False
                self.close()
                raise OperationalError("injected loss after server commit")

    with ConnectionPool(
        kwargs={
            "host": "127.0.0.1",
            "port": postgres.config.port,
            "user": "skilling_test",
            "dbname": "skilling_test",
            "password": postgres.config.password,
            "connect_timeout": 5,
        },
        connection_class=LostAcknowledgement,
        min_size=1,
        max_size=1,
        timeout=5,
    ) as pool:
        store = PostgresSessionStore.open(pool, schema=postgres.store.schema)
        course = Course.load(clean_dir)
        scope = SessionScope("producer", "learner", course.id)
        with pool.connection() as connection:
            connection.lose_response = True
        with pytest.raises(ReconciliationRequired):
            store.commit(InitializeSession(scope, None, Record.new(course, "learner")))
        assert postgres.store.read(scope).kind is SessionReadKind.LIVE
        with pytest.raises(Conflict):
            store.commit(InitializeSession(scope, None, Record.new(course, "learner")))


def test_unexpected_trigger_refuses_before_acknowledging_a_write(
    postgres: PostgresFixture, clean_dir: Path
) -> None:
    from psycopg import sql

    course = Course.load(clean_dir)
    scope = SessionScope("producer", "learner", course.id)
    with postgres.pool.connection() as connection:
        connection.execute(
            sql.SQL(
                "CREATE FUNCTION {}.suppress_write() RETURNS trigger "
                "LANGUAGE plpgsql AS 'BEGIN RETURN NULL; END'"
            ).format(sql.Identifier(postgres.store.schema))
        )
        connection.execute(
            sql.SQL(
                "CREATE TRIGGER suppress_write BEFORE INSERT OR UPDATE ON {}.sessions "
                "FOR EACH ROW EXECUTE FUNCTION {}.suppress_write()"
            ).format(sql.Identifier(postgres.store.schema), sql.Identifier(postgres.store.schema))
        )
    with pytest.raises(SessionSchemaError, match="triggers"):
        PostgresSessionStore.open(postgres.pool, schema=postgres.store.schema)
    with pytest.raises(SessionSchemaError, match="triggers"):
        postgres.store.commit(InitializeSession(scope, None, Record.new(course, "learner")))
    with postgres.pool.connection() as connection:
        assert connection.execute(
            sql.SQL("SELECT count(*) FROM {}.sessions").format(
                sql.Identifier(postgres.store.schema)
            )
        ).fetchone() == (0,)
