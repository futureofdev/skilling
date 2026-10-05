"""Identical real endpoint cases for AWS and single-node SeaweedFS."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from skilling.store import (
    Conflict,
    ReconciliationRequired,
    RecoveryRequired,
    SessionCapacity,
    SessionRead,
    SessionStore,
)
from skilling.store._backends._s3 import S3SessionStore
from skilling.store._backends._s3._control import CONTROL
from skilling.store._backends._s3._objects import Objects, stream_key
from skilling.store._protocol import (
    DeleteSession,
    InitializeSession,
    SessionDeleted,
    SessionReadKind,
    SessionScope,
)

from ....test_store import a_record
from ..test_sqlite import SCOPE, answer, mutation
from ._support import S3Fixture, s3_fixture


def initialize(store: SessionStore, scope: SessionScope = SCOPE) -> SessionRead:
    return store.commit(InitializeSession(scope, None, a_record(learner_id=scope.learner_id))).read


@pytest.fixture
def endpoint(request: pytest.FixtureRequest) -> S3Fixture:
    if request.config.getoption("--store-profile", default=None) not in ("aws", "seaweed"):
        pytest.skip("Real S3 endpoint suite requires explicit --store-profile")
    return s3_fixture(request)


def test_replay_reopen_loss_and_tombstone(
    endpoint: S3Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = endpoint.store
    initial = initialize(store)
    command = answer(initial)
    original = Objects.put

    def lose(self: Objects, key: str, raw: bytes, etag: str | None = None) -> None:
        original(self, key, raw, etag)
        from skilling.store._backends._s3._objects import UncertainWrite

        raise UncertainWrite

    with monkeypatch.context() as patch:
        patch.setattr(Objects, "put", lose)
        accepted = store.commit(command)
    assert accepted.replayed and accepted.outcome == command.commit.outcome
    reopened = S3SessionStore.open(endpoint.client, endpoint.bucket, endpoint.prefix)
    changed = reopened.commit(mutation(accepted.read))
    assert reopened.commit(command).read == changed.read
    reopened.commit(DeleteSession(SCOPE, changed.read.session_revision))
    with pytest.raises(SessionDeleted):
        reopened.commit(command)
    assert initial.state is not None
    with pytest.raises(SessionDeleted):
        reopened.commit(InitializeSession(SCOPE, None, initial.state.record))
    assert reopened.list_records(SCOPE.namespace, SCOPE.course_id) == ()


def test_real_response_loss_and_failed_upload(
    endpoint: S3Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial = initialize(endpoint.store)
    from botocore.exceptions import ReadTimeoutError

    original = endpoint.client.put_object

    def lose(**kwargs):
        original(**kwargs)
        raise ReadTimeoutError(endpoint_url="redacted")

    with monkeypatch.context() as patch:
        patch.setattr(endpoint.client, "put_object", lose)
        assert endpoint.store.commit(answer(initial)).replayed
    current = endpoint.store.read(SCOPE)

    def fail(**kwargs):
        raise ReadTimeoutError(endpoint_url="redacted")

    with monkeypatch.context() as patch:
        patch.setattr(endpoint.client, "put_object", fail)
        with pytest.raises(ReconciliationRequired):
            endpoint.store.commit(mutation(current))
    assert endpoint.store.read(SCOPE) == current


def test_two_conditional_writers(endpoint: S3Fixture, monkeypatch: pytest.MonkeyPatch) -> None:
    initial = initialize(endpoint.store)
    barrier = Barrier(2)
    original = Objects.put

    def racing(self: Objects, key: str, raw: bytes, etag: str | None = None) -> None:
        barrier.wait(timeout=10)
        original(self, key, raw, etag)

    def worker() -> str:
        try:
            endpoint.store.commit(mutation(initial))
            return "accepted"
        except Conflict:
            return "conflict"

    with monkeypatch.context() as patch:
        patch.setattr(Objects, "put", racing)
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            assert sorted(future.result() for future in futures) == ["accepted", "conflict"]


def test_backup_restore_and_interruption(
    endpoint: S3Fixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial = initialize(endpoint.store)
    command = answer(initial)
    endpoint.store.commit(command)
    other = SessionScope(SCOPE.namespace, "deleted", SCOPE.course_id)
    deleted = initialize(endpoint.store, other)
    endpoint.store.commit(DeleteSession(other, deleted.session_revision))
    backup = tmp_path / "backup.json"
    endpoint.store.backup(backup)
    restored = S3SessionStore.restore(
        endpoint.client, endpoint.bucket, endpoint.prefix + "/restored", backup
    )
    assert restored.commit(command).replayed
    assert restored.read(other).kind == SessionReadKind.DELETED
    with pytest.raises(RecoveryRequired):
        S3SessionStore.restore(endpoint.client, endpoint.bucket, endpoint.prefix, backup)
    original = Objects.put
    target = endpoint.prefix + "/interrupted"

    def interrupt(self: Objects, key: str, raw: bytes, etag: str | None = None) -> None:
        original(self, key, raw, etag)
        if key != CONTROL:
            raise RuntimeError("stop after first complete body")

    with monkeypatch.context() as patch:
        patch.setattr(Objects, "put", interrupt)
        with pytest.raises(RuntimeError, match="stop after"):
            S3SessionStore.restore(endpoint.client, endpoint.bucket, target, backup)
    with pytest.raises(RecoveryRequired, match="not READY"):
        S3SessionStore.open(endpoint.client, endpoint.bucket, target)
    keys = Objects(endpoint.client, endpoint.bucket, target).keys()
    assert len(keys) == 2


def test_corruption_size_and_validation_before_access(
    endpoint: S3Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial = initialize(endpoint.store)
    from skilling.store._backends import _s3
    from skilling.store._backends._s3._objects import MAX_BYTES

    with monkeypatch.context() as patch:
        patch.setattr(_s3, "encode", lambda value: b"x" * (MAX_BYTES + 1))
        with pytest.raises(SessionCapacity):
            endpoint.store.commit(mutation(initial))
    assert endpoint.store.read(SCOPE) == initial
    objects = Objects(endpoint.client, endpoint.bucket, endpoint.prefix)
    value = objects.get(stream_key(SCOPE))
    assert value is not None
    raw = json.loads(value.body)
    raw["scope"]["namespace"] = "foreign"
    objects.put(stream_key(SCOPE), json.dumps(raw).encode(), value.etag)
    with pytest.raises(RecoveryRequired):
        endpoint.store.read(SCOPE)


def test_empty_prefix_initialize_restore_race(
    endpoint: S3Fixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initialize(endpoint.store)
    backup = tmp_path / "race-backup.json"
    endpoint.store.backup(backup)
    target = endpoint.prefix + "/contested"
    barrier = Barrier(2)
    original = Objects.put

    def rendezvous(self: Objects, key: str, raw: bytes, etag: str | None = None) -> None:
        if key == CONTROL and etag is None:
            barrier.wait(timeout=10)
        original(self, key, raw, etag)

    def initialize_target() -> str:
        try:
            S3SessionStore.open(endpoint.client, endpoint.bucket, target)
            return "initialized"
        except RecoveryRequired:
            return "refused"

    def restore_target() -> str:
        try:
            S3SessionStore.restore(endpoint.client, endpoint.bucket, target, backup)
            return "restored"
        except RecoveryRequired:
            return "refused"

    with monkeypatch.context() as patch:
        patch.setattr(Objects, "put", rendezvous)
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(initialize_target), pool.submit(restore_target)]
            outcomes = [future.result() for future in futures]
    assert outcomes.count("refused") == 1
    opened = S3SessionStore.open(endpoint.client, endpoint.bucket, target)
    expected = SessionReadKind.LIVE if "restored" in outcomes else SessionReadKind.ABSENT
    assert opened.read(SCOPE).kind == expected


def test_invalid_backup_no_reservation(endpoint: S3Fixture, tmp_path: Path) -> None:
    initialize(endpoint.store)
    backup = tmp_path / "invalid.json"
    endpoint.store.backup(backup)
    wire = json.loads(backup.read_text())
    wire["entries"][0]["sha256"] = "0" * 64
    backup.write_text(json.dumps(wire))
    target = endpoint.prefix + "/invalid"
    with pytest.raises(RecoveryRequired):
        S3SessionStore.restore(endpoint.client, endpoint.bucket, target, backup)
    assert Objects(endpoint.client, endpoint.bucket, target).keys() == ()


def test_independent_processes_keep_one_captured_winner(
    endpoint: S3Fixture, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    import subprocess
    import sys
    import time

    initialize(endpoint.store)
    config_path = request.config.getoption("--store-config")
    assert isinstance(config_path, str)
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "packages.skilling.tests.session_store.backends.s3.worker",
                config_path,
                endpoint.prefix,
                str(tmp_path),
                str(index),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for index in range(2)
    ]
    try:
        deadline = time.monotonic() + 30
        while not all((tmp_path / f"ready-{index}").exists() for index in range(2)):
            assert all(process.poll() is None for process in processes), (
                "Worker exited before barrier"
            )
            assert time.monotonic() < deadline, "Worker ready barrier timed out"
            time.sleep(0.01)
        (tmp_path / "release").touch()
        for process in processes:
            process.communicate(timeout=30)
            assert process.returncode == 0
        assert sorted((tmp_path / f"result-{index}").read_text() for index in range(2)) == [
            "accepted",
            "conflict",
        ]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()


def test_backup_preserves_original_homework_and_feedback(
    endpoint: S3Fixture, tmp_path: Path
) -> None:
    from skilling.store._protocol._boundary import pending_feedback

    from ..test_sqlite import completion, submission

    initial = initialize(endpoint.store)
    complete = completion(initial)
    completed = endpoint.store.commit(complete)
    submit = submission(completed.read)
    submitted = endpoint.store.commit(submit)
    answered = endpoint.store.commit(answer(submitted.read))
    backup = tmp_path / "full-backup.json"
    endpoint.store.backup(backup)
    restored = S3SessionStore.restore(
        endpoint.client, endpoint.bucket, endpoint.prefix + "/full-restored", backup
    )
    for command, original in ((complete, completed), (submit, submitted)):
        recovered = restored.commit(command)
        assert recovered.replayed and recovered.outcome == original.outcome
        assert recovered.read == answered.read
    assert pending_feedback(restored.read(SCOPE)) is not None


@pytest.mark.parametrize("operation", ["complete", "submit", "ack"])
def test_lost_commit_response_recovers_original_atomic_effects(
    endpoint: S3Fixture, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    from botocore.exceptions import ReadTimeoutError

    from skilling.store._protocol import AcknowledgeSession
    from skilling.store._protocol._boundary import pending_feedback

    from ..test_sqlite import completion, submission

    initial = initialize(endpoint.store)
    if operation == "submit":
        initial = endpoint.store.commit(completion(initial)).read
        command = submission(initial)
    elif operation == "ack":
        initial = endpoint.store.commit(answer(initial)).read
        feedback = pending_feedback(initial)
        assert feedback and initial.state and initial.session_revision
        command = AcknowledgeSession(
            SCOPE, initial.session_revision, feedback.feedback_id, initial.state.record_revision
        )
    else:
        command = completion(initial)
    original = endpoint.client.put_object

    def lose(**kwargs):
        original(**kwargs)
        raise ReadTimeoutError(endpoint_url="redacted")

    with monkeypatch.context() as patch:
        patch.setattr(endpoint.client, "put_object", lose)
        recovered = endpoint.store.commit(command)
    assert recovered.replayed
    assert endpoint.store.commit(command).read == recovered.read
    state = recovered.read.state
    assert state is not None
    if operation == "complete":
        assert len(state.log) == 1 and state.homework is not None
    elif operation == "submit":
        assert len(state.archive) == 1 and state.homework is None
    else:
        assert pending_feedback(recovered.read) is None


def test_response_loss_with_unavailable_reconciliation_preserves_uncertainty(
    endpoint: S3Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from botocore.exceptions import ReadTimeoutError

    command = answer(initialize(endpoint.store))
    original_put = endpoint.client.put_object
    original_get = endpoint.client.get_object
    lost = False

    def lose(**kwargs):
        nonlocal lost
        original_put(**kwargs)
        lost = True
        raise ReadTimeoutError(endpoint_url="redacted")

    def unavailable(**kwargs):
        if lost:
            raise ReadTimeoutError(endpoint_url="redacted")
        return original_get(**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(endpoint.client, "put_object", lose)
        patch.setattr(endpoint.client, "get_object", unavailable)
        with pytest.raises(ReconciliationRequired):
            endpoint.store.commit(command)
    recovered = endpoint.store.commit(command)
    assert recovered.replayed and recovered.outcome == command.commit.outcome
    assert recovered.read.state is not None
    assert len(recovered.read.state.action_receipts) == 1
