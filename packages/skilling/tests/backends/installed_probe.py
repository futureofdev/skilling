"""Outside-checkout public session probe; explicit remote targets must be disposable."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path

from skilling.course import parse_lesson, parse_quiz
from skilling.session import ActionOperation, Session, load_course
from skilling.store import (
    Conflict,
    DeleteSession,
    FileSessionStore,
    PostgresSessionStore,
    S3SessionStore,
    SessionDeleted,
    SessionReadKind,
    SessionScope,
    SQLiteSessionStore,
)


def native(
    prefix: list[str], executable: str, args: list[str], *, data: bytes | None = None
) -> bytes:
    try:
        result = subprocess.run(
            [*prefix, executable, *args], input=data, capture_output=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Native {executable} exceeded the 60-second limit") from None
    if result.returncode:
        raise RuntimeError(f"Native {executable} failed; inspect private service logs")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store-profile", choices=("file", "sqlite", "postgres", "s3"), required=True
    )
    parser.add_argument("--store-config", type=Path)
    parser.add_argument("--course-source", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.store_config.read_text()) if args.store_config else {}
    if not isinstance(config, dict):
        raise ValueError("store configuration must be a JSON object")
    if args.store_profile in ("postgres", "s3") and config.get("disposable") is not True:
        raise ValueError("remote installed probes require explicit disposable=true")
    root = args.workspace.resolve()
    root.mkdir(parents=True, exist_ok=False)
    work = root / "work"
    work.mkdir()
    scope = SessionScope("installed-probe", "synthetic-learner", "welcome-skilling")
    restored_pool = None
    client = None
    schema = ""
    restored_prefix = ""
    with ExitStack() as resources:
        if args.store_profile == "sqlite":
            store = SQLiteSessionStore.open(root / "state.sqlite3")
            resources.callback(store.close)
        elif args.store_profile == "file":
            store = FileSessionStore.open(
                root / "state", namespace=scope.namespace, learner_id=scope.learner_id
            )
        elif args.store_profile == "postgres":
            from psycopg_pool import ConnectionPool

            dsn = os.environ[config["dsn_env"]]
            restore_dsn = os.environ[config["restore_dsn_env"]]
            if dsn == restore_dsn:
                raise ValueError("restore database must differ from source")
            schema = "installed_" + secrets.token_hex(12)
            pool = resources.enter_context(
                ConnectionPool(
                    dsn, min_size=1, max_size=4, timeout=5, kwargs={"connect_timeout": 5}
                )
            )
            restored_pool = resources.enter_context(
                ConnectionPool(
                    restore_dsn, min_size=1, max_size=4, timeout=5, kwargs={"connect_timeout": 5}
                )
            )
            store = PostgresSessionStore.open(pool, schema=schema)
        else:
            from boto3.session import Session as BotoSession
            from botocore.config import Config

            prefix = config["prefix"]
            if not isinstance(prefix, str) or not prefix.strip("/"):
                raise ValueError("explicit nonempty disposable prefix required")
            client = BotoSession().client(
                "s3",
                region_name=config["region"],
                endpoint_url=config.get("endpoint_url"),
                config=Config(
                    retries={"total_max_attempts": 1},
                    connect_timeout=5,
                    read_timeout=10,
                    s3={"addressing_style": "path"},
                ),
            )
            resources.callback(client.close)
            identity = secrets.token_hex(12)
            source_prefix = prefix.rstrip("/") + "/" + identity + "-source/"
            restored_prefix = prefix.rstrip("/") + "/" + identity + "-restored/"
            store = S3SessionStore.open(client, config["bucket"], source_prefix)
        session = Session.open(
            args.course_source.resolve(), store=store, scope=scope, work_root=work
        )
        action = None
        for index in range(40):
            snapshot = session.snapshot()
            if snapshot.pending_feedback is not None:
                break
            if snapshot.beat.question is not None:
                lesson = load_course(args.course_source).lesson_at(snapshot.position.coordinate)
                assert lesson is not None
                quiz = parse_lesson(lesson.path).section("quiz")
                assert quiz is not None
                answer = parse_quiz(quiz.body, quiz.line)[
                    snapshot.beat.question.number - 1
                ].answer_label
                payload = next(
                    option.label
                    for option in snapshot.beat.question.options
                    if option.label != answer
                )
                operation = ActionOperation.ANSWER
            else:
                choices = tuple(str(value) for value in snapshot.legal_inputs)
                payload = next(
                    (
                        value
                        for value in ("proceed", "attempted", "continue", "next")
                        if value in choices
                    ),
                    choices[0],
                )
                operation = ActionOperation.ADVANCE
            action = session.capture_action(
                snapshot, event_id=f"fixture-{index}", operation=operation, payload=payload
            )
            session.act(action)
        else:
            raise AssertionError("pending canonical feedback not reached")
        before = store.read(scope)
        assert before.state is not None and before.state.action_receipts
        assert action is not None
        backup = root / "backup"
        if isinstance(store, SQLiteSessionStore):
            store.backup(backup)
            restored = SQLiteSessionStore.restore(backup, root / "restored.sqlite3")
            resources.callback(restored.close)
        elif isinstance(store, FileSessionStore):
            shutil.copytree(root / "state", backup)
            restored = FileSessionStore.open(
                backup, namespace=scope.namespace, learner_id=scope.learner_id
            )
        elif isinstance(store, PostgresSessionStore):
            assert restored_pool is not None
            prefix = config.get("native_command", [])
            if not isinstance(prefix, list) or any(
                not isinstance(value, str) or not value or "\x00" in value for value in prefix
            ):
                raise ValueError("native_command must be an argv prefix")
            # Service names carry no passwords; libpq environment handles credentials.
            source_database, restore_database = (
                config["native_database"],
                config["native_restore_database"],
            )
            if not all(
                isinstance(value, str)
                and value
                and not value.startswith("-")
                and "://" not in value
                and "=" not in value
                for value in (source_database, restore_database)
            ):
                raise ValueError("native databases must be plain database names")
            with restored_pool.connection() as connection:
                assert (
                    connection.execute(
                        "SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,)
                    ).fetchone()
                    is None
                )
            backup.write_bytes(
                native(
                    prefix,
                    "pg_dump",
                    [
                        "--format=custom",
                        "--no-owner",
                        "--no-privileges",
                        "--schema=" + schema,
                        "--dbname=" + source_database,
                    ],
                )
            )
            native(
                prefix,
                "pg_restore",
                [
                    "--single-transaction",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "--dbname=" + restore_database,
                ],
                data=backup.read_bytes(),
            )
            restored = PostgresSessionStore.open(restored_pool, schema=schema)
        else:
            assert isinstance(store, S3SessionStore) and client is not None
            store.backup(backup)
            restored = S3SessionStore.restore(client, config["bucket"], restored_prefix, backup)
        assert restored.read(scope) == before
        resumed = Session.open(
            args.course_source.resolve(), store=restored, scope=scope, work_root=work
        )
        assert resumed.pending_feedback() == session.pending_feedback()
        assert resumed.act(action).replayed
        assert before.session_revision is not None
        command = DeleteSession(scope, before.session_revision)

        def delete() -> str:
            try:
                store.commit(command)
                return "deleted"
            except (Conflict, SessionDeleted):
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = sorted(executor.map(lambda _: delete(), range(2)))
        assert outcomes == ["conflict", "deleted"]
        assert store.read(scope).kind is SessionReadKind.DELETED
        assert restored.read(scope).state == before.state
        print(
            json.dumps(
                {
                    "profile": args.store_profile,
                    "pending_feedback": True,
                    "backup_restore": True,
                    "delete_race": outcomes,
                    "synthetic": True,
                }
            )
        )


if __name__ == "__main__":
    main()
