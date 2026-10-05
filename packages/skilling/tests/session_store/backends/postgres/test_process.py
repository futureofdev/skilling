"""Independent-process races and abrupt process exits, without timing sleeps."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from skilling.store import InitializeSession
from skilling.store._protocol._boundary import pending_feedback

from ....test_store import a_record
from ..test_sqlite import SCOPE, answer, completion
from ._support import PostgresFixture, postgres_fixture


def start_worker(
    request: pytest.FixtureRequest, fixture: PostgresFixture, operation: str, boundary: str
) -> subprocess.Popen[str]:
    config_path = request.config.getoption("--store-config")
    if not isinstance(config_path, str):
        raise ValueError("PostgreSQL worker requires a private configuration path")
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "packages.skilling.tests.session_store.backends.postgres.worker",
            str(Path(config_path).resolve()),
            fixture.store.schema,
            operation,
            boundary,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_independent_process_creation_has_one_winner(request: pytest.FixtureRequest) -> None:
    fixture = postgres_fixture(request)
    workers = [start_worker(request, fixture, "create", "none") for _ in range(2)]
    try:
        for process in workers:
            assert process.stdout and process.stdout.readline().strip() == "ready"
        for process in workers:
            assert process.stdin
            process.stdin.write("go\n")
            process.stdin.flush()
        results = [process.communicate(timeout=15)[0].strip() for process in workers]
        assert sorted(results) == ["conflict", "created"]
        assert all(process.returncode == 0 for process in workers)
    finally:
        for process in workers:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)


@pytest.mark.parametrize("operation", ["complete", "submit", "answer", "ack"])
@pytest.mark.parametrize("boundary", ["before", "after"])
def test_kill_at_real_commit_boundary(
    request: pytest.FixtureRequest, operation: str, boundary: str
) -> None:
    fixture = postgres_fixture(request)
    store = fixture.store
    before = store.commit(InitializeSession(SCOPE, None, a_record())).read
    if operation == "submit":
        before = store.commit(completion(before)).read
    elif operation == "ack":
        before = store.commit(answer(before)).read
    process = start_worker(request, fixture, operation, boundary)
    try:
        assert process.stdout and process.stdout.readline().strip() == "ready"
        process.communicate(input="go\n", timeout=15)
        assert process.returncode == 73
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
    after = store.read(SCOPE)
    if boundary == "before":
        assert after == before
    else:
        assert after.session_revision != before.session_revision and after.state is not None
        if operation == "complete":
            assert len(after.state.log) == 1 and after.state.homework is not None
            assert store.commit(completion(before)).replayed
        elif operation == "submit":
            assert len(after.state.archive) == 1 and after.state.homework is None
        elif operation == "answer":
            assert pending_feedback(after) is not None and store.commit(answer(before)).replayed
        else:
            assert pending_feedback(after) is None
            assert before.state is not None
            assert after.state.record_revision == before.state.record_revision
