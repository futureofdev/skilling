"""Full native pg_dump/pg_restore proof into an empty stopped database."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from skilling.store import DeleteSession, InitializeSession, RecoveryRequired, SessionReadKind
from skilling.store._backends._postgres import PostgresSessionStore
from skilling.store._protocol._boundary import pending_feedback

from ....test_store import a_record
from ..test_sqlite import SCOPE, answer, completion, submission
from ._support import PostgresFixture, postgres_fixture


def docker_native(fixture: PostgresFixture, *args: str, data: bytes | None = None) -> bytes:
    compose = Path(__file__).parents[3] / "backends" / "compose.yaml"
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose),
            "-p",
            fixture.config.project,
            "exec",
            "-T",
            "postgres",
            *args,
        ],
        input=data,
        capture_output=True,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Native PostgreSQL backup tool failed")
    return result.stdout


def checked_restore(fixture: PostgresFixture, target: str, data: bytes, digest: str) -> None:
    from psycopg import connect

    if hashlib.sha256(data).hexdigest() != digest:
        raise RecoveryRequired("Backup checksum differs")
    with connect(
        host="127.0.0.1",
        port=fixture.config.port,
        user="skilling_test",
        dbname=target,
        password=fixture.config.password,
    ) as connection:
        existing = connection.execute(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname NOT IN ('pg_catalog','information_schema') "
            "AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','v','m','S') LIMIT 1"
        ).fetchone()
        if existing is not None:
            raise RecoveryRequired("Restore requires an empty stopped database")
    docker_native(
        fixture,
        "pg_restore",
        "-U",
        "skilling_test",
        "-d",
        target,
        "--single-transaction",
        "--exit-on-error",
        "--no-owner",
        "--no-privileges",
        data=data,
    )


def test_native_backup_keeps_pending_feedback_submissions_and_tombstones(
    request: pytest.FixtureRequest,
) -> None:
    from psycopg import connect, sql
    from psycopg_pool import ConnectionPool

    fixture = postgres_fixture(request)
    store = fixture.store
    initial = store.commit(InitializeSession(SCOPE, None, a_record())).read
    completed = store.commit(completion(initial)).read
    submit = submission(completed)
    submitted = store.commit(submit).read
    action = answer(submitted)
    pending = store.commit(action).read
    dead_scope = type(SCOPE)(SCOPE.namespace, "deleted-learner", SCOPE.course_id)
    live = store.commit(
        InitializeSession(dead_scope, None, a_record(learner_id="deleted-learner"))
    ).read
    store.commit(DeleteSession(dead_scope, live.session_revision))
    archive = docker_native(
        fixture,
        "pg_dump",
        "-U",
        "skilling_test",
        "-d",
        "skilling_test",
        "--format=custom",
        "--schema=" + store.schema,
    )
    digest = hashlib.sha256(archive).hexdigest()
    target = "restore_" + uuid4().hex
    with connect(
        host="127.0.0.1",
        port=fixture.config.port,
        user="skilling_test",
        dbname="skilling_test",
        password=fixture.config.password,
        autocommit=True,
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
        try:
            with pytest.raises(RecoveryRequired, match="checksum"):
                checked_restore(fixture, target, archive + b"damaged", digest)
            checked_restore(fixture, target, archive, digest)
            with ConnectionPool(
                kwargs={
                    "host": "127.0.0.1",
                    "port": fixture.config.port,
                    "user": "skilling_test",
                    "dbname": target,
                    "password": fixture.config.password,
                },
                min_size=1,
                max_size=2,
            ) as pool:
                restored = PostgresSessionStore.open(pool, schema=store.schema)
                assert restored.read(SCOPE) == pending
                assert pending_feedback(restored.read(SCOPE)) is not None
                assert restored.commit(action).replayed
                assert restored.commit(submit).replayed
                assert restored.read(dead_scope).kind is SessionReadKind.DELETED
                assert (
                    restored.export_progress(SCOPE) == pending.state.record
                    if pending.state
                    else None
                )
            with pytest.raises(RecoveryRequired, match="empty"):
                checked_restore(fixture, target, archive, digest)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(target)))
