"""Independent process and kill/reopen checks at real PostgreSQL commit boundaries."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from psycopg import Connection, Transaction
from psycopg_pool import ConnectionPool

from skilling.store import AcknowledgeSession, Conflict, InitializeSession
from skilling.store._backends._postgres import PostgresSessionStore
from skilling.store._protocol._boundary import pending_feedback

from ....test_store import a_record
from ..test_sqlite import SCOPE, answer, completion, submission
from ._support import ServiceConfig


class InterruptedConnection(Connection[tuple[object, ...]]):
    interruption: str | None = None

    @contextmanager
    def transaction(
        self, savepoint_name: str | None = None, force_rollback: bool = False
    ) -> Iterator[Transaction]:
        with super().transaction(
            savepoint_name=savepoint_name, force_rollback=force_rollback
        ) as value:
            yield value
            if self.interruption == "before":
                os._exit(73)
        if self.interruption == "after":
            os._exit(73)


def main() -> None:
    config = ServiceConfig.model_validate_json(Path(sys.argv[1]).read_bytes())
    schema, operation, interruption = sys.argv[2:5]
    with ConnectionPool(
        kwargs={
            "host": "127.0.0.1",
            "port": config.port,
            "user": "skilling_test",
            "dbname": "skilling_test",
            "password": config.password,
            "connect_timeout": 5,
        },
        connection_class=InterruptedConnection,
        min_size=1,
        max_size=1,
    ) as pool:
        store = PostgresSessionStore.open(pool, schema=schema)
        state = store.read(SCOPE)
        if operation == "create":
            command = InitializeSession(SCOPE, None, a_record())
        elif operation == "complete":
            command = completion(state)
        elif operation == "submit":
            command = submission(state)
        elif operation == "answer":
            command = answer(state)
        elif operation == "ack":
            feedback = pending_feedback(state)
            assert feedback is not None and state.session_revision is not None
            command = AcknowledgeSession(
                SCOPE, state.session_revision, feedback.feedback_id, feedback.revision
            )
        else:
            raise ValueError("unknown process operation")
        with pool.connection() as connection:
            connection.interruption = interruption
        print("ready", flush=True)
        if sys.stdin.readline().strip() != "go":
            raise RuntimeError("Missing parent release")
        try:
            store.commit(command)
            print("created", flush=True)
        except Conflict:
            print("conflict", flush=True)


if __name__ == "__main__":
    main()
