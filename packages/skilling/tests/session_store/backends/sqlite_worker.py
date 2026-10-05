"""Spawned worker: deterministic barriers surround actual SQLite commit boundaries."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

from skilling.store._backends._sqlite import SQLiteSessionStore
from skilling.store._protocol import AcknowledgeSession, Conflict, StoreError
from skilling.store._protocol._boundary import pending_feedback

from .test_sqlite import SCOPE, answer, completion, initialize, mutation, submission


def main() -> None:
    path, mode, phase = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    if mode == "create":
        print("READY", flush=True)
        sys.stdin.readline()
        try:
            store = SQLiteSessionStore.open(path, timeout=2)
            initialize(store)
            print("CREATED", flush=True)
        except Conflict:
            print("CONFLICT", flush=True)
        return
    store = SQLiteSessionStore.open(path, timeout=2)
    current = store.read(SCOPE)
    if mode == "ack":
        feedback = pending_feedback(current)
        assert feedback and current.session_revision
        command = AcknowledgeSession(
            SCOPE, current.session_revision, feedback.feedback_id, feedback.revision
        )
    else:
        operation = {
            "answer": answer,
            "mutation": mutation,
            "complete": completion,
            "submit": submission,
        }[mode]
        command = operation(current)
    original = sqlite3.connect

    class InterruptibleConnection(sqlite3.Connection):
        def commit(self) -> None:
            if phase == "before":
                print("BOUNDARY", flush=True)
                sys.stdin.readline()
                os._exit(71)
            super().commit()
            if phase == "after":
                print("BOUNDARY", flush=True)
                sys.stdin.readline()
                os._exit(72)

    def connect(*args, **kwargs):
        return original(*args, **kwargs, factory=InterruptibleConnection)

    sqlite3.connect = connect
    print("READY", flush=True)
    sys.stdin.readline()
    try:
        result = store.commit(command)
        print(json.dumps({"replayed": result.replayed}), flush=True)
    except StoreError as exc:
        print(type(exc).__name__, flush=True)


if __name__ == "__main__":
    main()
