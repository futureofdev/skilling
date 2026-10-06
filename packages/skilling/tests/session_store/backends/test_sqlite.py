"""Actual SQLite persistence, interruption, isolation, and administrative recovery."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path

import pytest
import yaml

from skilling.store import (
    ActionIdentity,
    ActionOperation,
    ActionOrigin,
    Conflict,
    QuizAnswerOutcome,
    RecoveryRequired,
    TransitionCommit,
    key_digest,
)
from skilling.store._backends._aggregate import decode, encode
from skilling.store._backends._sqlite import SQLiteSessionStore
from skilling.store._protocol import (
    AcknowledgeSession,
    DeleteSession,
    InitializeSession,
    MutateSession,
    RecordMutationKind,
    SessionDeleted,
    SessionRead,
    SessionReadKind,
    SessionScope,
    StoreBusy,
    StoreError,
    TransitionSession,
)
from skilling.store._protocol._boundary import neutral_pending_pointer, pending_feedback

from ...test_store import a_record

SCOPE = SessionScope("producer", "local", "clean-course")


def initialize(store: SQLiteSessionStore, scope: SessionScope = SCOPE) -> SessionRead:
    return store.commit(InitializeSession(scope, None, a_record(learner_id=scope.learner_id))).read


def answer(read: SessionRead, key: str = "same-event") -> TransitionSession:
    assert read.state is not None and read.session_revision is not None
    state = read.state
    identity = ActionIdentity(
        read.scope.learner_id,
        read.scope.course_id,
        state.record.course_version,
        "0.1",
        ActionOperation.ANSWER,
        "b",
        key_digest(key),
        ActionOrigin.LEARNER,
        state.record_revision,
        1,
    )
    outcome = QuizAnswerOutcome(1, "b", False, "Canonical reason", True, ("Review this",))
    scratch = yaml.safe_dump(
        {"pending_feedback": asdict(neutral_pending_pointer(identity, outcome))}
    ).encode()
    return TransitionSession(
        read.scope,
        read.session_revision,
        TransitionCommit(
            identity, state.record_revision, state.scratch, state.record, scratch, outcome
        ),
    )


def mutation(read: SessionRead) -> MutateSession:
    assert read.state is not None and read.session_revision is not None
    return MutateSession(
        read.scope,
        read.session_revision,
        read.state.record.model_copy(update={"streak_days": read.state.record.streak_days + 1}),
        read.state.record_revision,
        RecordMutationKind.RECORD,
    )


def test_restart_replay_feedback_and_independent_revisions(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    store = SQLiteSessionStore.open(path)
    initial = initialize(store)
    command = answer(initial)
    accepted = store.commit(command)
    assert accepted.read.state is not None
    assert initial.state is not None
    assert accepted.read.state.record_revision == initial.state.record_revision
    store.close()
    reopened = SQLiteSessionStore.open(path)
    feedback = pending_feedback(reopened.read(SCOPE))
    assert feedback is not None and feedback.outcome.reason == "Canonical reason"
    assert accepted.read.session_revision is not None
    acknowledged = reopened.commit(
        AcknowledgeSession(
            SCOPE,
            accepted.read.session_revision,
            feedback.feedback_id,
            feedback.revision,
        )
    )
    assert acknowledged.read.state is not None
    assert acknowledged.read.state.record_revision == initial.state.record_revision
    assert acknowledged.read.session_revision != accepted.read.session_revision
    assert pending_feedback(acknowledged.read) is None
    with pytest.raises(Conflict):
        reopened.commit(mutation(accepted.read))
    final = reopened.commit(mutation(acknowledged.read)).read
    replay = reopened.commit(command)
    assert replay.replayed and replay.outcome == accepted.outcome and replay.read == final
    assert final.state is not None and final.state.record_revision != initial.state.record_revision


def test_scope_isolation_enumeration_and_tombstone(tmp_path: Path) -> None:
    store = SQLiteSessionStore.open(tmp_path / "state.db")
    scopes = (SCOPE, replace(SCOPE, namespace="other"), replace(SCOPE, learner_id="other"))
    for scope in scopes:
        initial = initialize(store, scope)
        store.commit(answer(initial))
    assert len(store.list_records(SCOPE.namespace, SCOPE.course_id)) == 2
    stale = store.read(SCOPE)
    dead = store.commit(DeleteSession(SCOPE, stale.session_revision)).read
    assert dead.kind == SessionReadKind.DELETED and dead.state is None
    for command in (InitializeSession(SCOPE, None, a_record()), answer(stale), mutation(stale)):
        with pytest.raises(SessionDeleted):
            store.commit(command)
    assert len(store.list_records(SCOPE.namespace, SCOPE.course_id)) == 1
    assert store.read(scopes[1]).kind == SessionReadKind.LIVE
    assert store.export_progress(SCOPE) is None
    with closing(sqlite3.connect(store.path)) as connection, connection:
        assert connection.execute(
            "SELECT payload FROM skilling_sessions WHERE deleted=1"
        ).fetchone() == (None,)


def test_native_backup_restore_preserves_pending_receipt_and_tombstone(tmp_path: Path) -> None:
    store = SQLiteSessionStore.open(tmp_path / "state.db")
    command = answer(initialize(store))
    accepted = store.commit(command)
    deleted_scope = replace(SCOPE, learner_id="deleted")
    deleted = initialize(store, deleted_scope)
    store.commit(DeleteSession(deleted_scope, deleted.session_revision))
    backup = tmp_path / "backup.db"
    store.backup(backup)
    restored = SQLiteSessionStore.restore(backup, tmp_path / "restored.db")
    assert restored.read(SCOPE) == accepted.read
    assert restored.commit(command).replayed
    assert restored.read(deleted_scope).kind == SessionReadKind.DELETED
    assert pending_feedback(restored.read(SCOPE)) is not None
    with pytest.raises(StoreError):
        SQLiteSessionStore.restore(backup, restored.path)
    assert restored.read(SCOPE) == accepted.read


def test_schema_and_corruption_refuse_without_repair(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    store = SQLiteSessionStore.open(path)
    value = initialize(store)
    raw = encode(value)
    wire = json.loads(raw)
    wire["schema_version"] = 2
    with pytest.raises(RecoveryRequired):
        decode(json.dumps(wire).encode(), SCOPE)
    wire = json.loads(raw)
    wire["state"]["unexpected"] = 1
    with pytest.raises(RecoveryRequired):
        decode(json.dumps(wire).encode(), SCOPE)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("UPDATE skilling_sessions SET payload=?", (b"{}",))
    before = path.read_bytes()
    with pytest.raises(RecoveryRequired):
        store.commit(mutation(value))
    assert path.read_bytes() == before
    with pytest.raises(RecoveryRequired):
        store.backup(tmp_path / "bad-backup.db")
    assert not (tmp_path / "bad-backup.db").exists()
    foreign = tmp_path / "foreign.db"
    with closing(sqlite3.connect(foreign)) as connection, connection:
        connection.execute("CREATE TABLE user_data (value TEXT)")
    before = foreign.read_bytes()
    with pytest.raises(StoreError):
        SQLiteSessionStore.open(foreign)
    assert foreign.read_bytes() == before


def test_busy_timeout_closes_connections_and_missing_path_never_recreates(tmp_path: Path) -> None:
    store = SQLiteSessionStore.open(tmp_path / "state.db", timeout=0.02)
    initial = initialize(store)
    with closing(sqlite3.connect(store.path, isolation_level=None)) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        with pytest.raises(StoreBusy):
            store.commit(mutation(initial))
        blocker.rollback()
    changed = store.commit(mutation(initial))
    assert changed.read != initial
    store.path.unlink()
    with pytest.raises(RecoveryRequired):
        store.read(SCOPE)
    assert not store.path.exists()
    store.close()
    with pytest.raises(StoreError):
        store.read(SCOPE)


def worker(path: Path, mode: str, phase: str = "none"):
    import subprocess
    import sys

    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "packages.skilling.tests.session_store.backends.sqlite_worker",
            str(path),
            mode,
            phase,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def line(process) -> str:
    from queue import Queue
    from threading import Thread

    received: Queue[str] = Queue()

    def read() -> None:
        assert process.stdout
        received.put(process.stdout.readline().strip())

    Thread(target=read, daemon=True).start()
    return received.get(timeout=15)


def test_two_process_creation_has_one_winner(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    first, second = worker(path, "create"), worker(path, "create")
    try:
        for process in (first, second):
            assert process.stdout and process.stdin
            assert line(process) == "READY"
        for process in (first, second):
            assert process.stdin
            process.stdin.write("go\n")
            process.stdin.flush()
        outcomes = [p.communicate(timeout=10) for p in (first, second)]
        assert sorted(out[0].strip() for out in outcomes) == ["CONFLICT", "CREATED"], outcomes
        assert first.returncode == second.returncode == 0
        assert SQLiteSessionStore.open(path).read(SCOPE).kind == SessionReadKind.LIVE
    finally:
        for process in (first, second):
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


@pytest.mark.parametrize("phase", ["before", "after"])
@pytest.mark.parametrize("mode", ["answer", "mutation"])
def test_process_exit_at_actual_commit_boundary(tmp_path: Path, phase: str, mode: str) -> None:
    store = SQLiteSessionStore.open(tmp_path / "state.db")
    initial = initialize(store)
    process = worker(store.path, mode, phase)
    try:
        assert process.stdout and process.stdin
        assert line(process) == "READY"
        process.stdin.write("go\n")
        process.stdin.flush()
        assert line(process) == "BOUNDARY"
        # The process is stopped at a signaled real commit boundary, not a timed sleep.
        process.kill()
        process.communicate(timeout=10)
        reopened = SQLiteSessionStore.open(store.path)
        current = reopened.read(SCOPE)
        if phase == "before":
            assert current == initial
        else:
            assert current != initial
            if mode == "answer":
                assert pending_feedback(current) is not None
                assert reopened.commit(answer(initial)).replayed
            else:
                assert current.state and current.state.record.streak_days == 1
                with pytest.raises(Conflict):
                    reopened.commit(mutation(initial))
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


@pytest.mark.parametrize("delete", [False, True])
def test_two_process_update_and_delete_race(tmp_path: Path, delete: bool) -> None:
    store = SQLiteSessionStore.open(tmp_path / "state.db")
    initial = initialize(store)
    process = worker(store.path, "mutation")
    try:
        assert process.stdout and process.stdin
        assert line(process) == "READY"
        store.commit(
            DeleteSession(SCOPE, initial.session_revision) if delete else mutation(initial)
        )
        out, err = process.communicate("go\n", timeout=10)
        assert out.strip() == ("SessionDeleted" if delete else "Conflict"), (out, err)
        assert store.read(SCOPE).kind == (
            SessionReadKind.DELETED if delete else SessionReadKind.LIVE
        )
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


def completion(read: SessionRead):
    from skilling.store import CompletionCommit, CompletionReceipt, HomeworkWrite
    from skilling.store._protocol import CompleteSession

    from ...test_store import a_slot, an_entry

    assert read.state is not None and read.session_revision is not None
    entry = an_entry("0.1")
    receipt = CompletionReceipt(
        key_digest("complete-0.1"),
        SCOPE.learner_id,
        SCOPE.course_id,
        "1.0.0",
        "0.1",
        entry.completed_at,
        ("first",),
        None,
        True,
        False,
    )
    return CompleteSession(
        SCOPE,
        read.session_revision,
        CompletionCommit(
            receipt,
            read.state.record_revision,
            read.state.record.model_copy(update={"completed": ["0.1"]}),
            read.state.log,
            entry,
            HomeworkWrite(read.state.homework_revision, a_slot()),
        ),
    )


def submission(read: SessionRead):
    from skilling.course import HomeworkArchiveEntry
    from skilling.store import SubmissionCommit, SubmissionReceipt, SubmissionToken
    from skilling.store._protocol import SubmitSession

    from ...test_store import an_entry

    assert read.state and read.session_revision
    state = read.state
    slot = state.homework
    assert slot and state.homework_revision
    token = SubmissionToken.for_slot(
        SCOPE.learner_id,
        SCOPE.course_id,
        state.record.course_version,
        slot,
        state.homework_revision,
    )
    archive = HomeworkArchiveEntry(
        coordinate=slot.coordinate,
        title=slot.title,
        requirements=slot.requirements,
        stretch_goals=slot.stretch_goals,
        submitted_at=an_entry("0.1").completed_at,
    )
    receipt = SubmissionReceipt(
        token.encode(),
        SCOPE.learner_id,
        SCOPE.course_id,
        state.record.course_version,
        slot.coordinate,
        token.instance_id,
        archive,
    )
    return SubmitSession(
        SCOPE, read.session_revision, SubmissionCommit(receipt, state.homework_revision, None)
    )


def test_completion_submission_full_restore_preserves_original_effects(tmp_path: Path) -> None:
    store = SQLiteSessionStore.open(tmp_path / "state.db")
    initial = initialize(store)
    complete = completion(initial)
    completed = store.commit(complete)
    assert completed.read.state
    assert len(completed.read.state.log) == 1 and completed.read.state.homework is not None
    submit = submission(completed.read)
    submitted = store.commit(submit)
    assert submitted.read.state and submitted.read.state.homework is None
    assert len(submitted.read.state.archive) == 1
    assert submitted.read.state.record_revision == completed.read.state.record_revision
    # Pending feedback and accepted homework coexist in the complete backup.
    answered = store.commit(answer(submitted.read))
    backup = tmp_path / "backup.db"
    store.backup(backup)
    restored = SQLiteSessionStore.restore(backup, tmp_path / "restored.db")
    for command, original in ((complete, completed), (submit, submitted)):
        retry = restored.commit(command)
        assert retry.replayed and retry.outcome == original.outcome
        assert retry.read == answered.read
    assert restored.read(SCOPE).state == answered.read.state
    assert pending_feedback(restored.read(SCOPE)) is not None


def test_explicit_upgrade_preserves_key_reservations_and_rejects_pending(tmp_path: Path) -> None:
    from skilling.store import IdempotencyKeyConflict, UpgradeCommit, UpgradeIdentity
    from skilling.store._protocol import UpgradeSession

    store = SQLiteSessionStore.open(tmp_path / "state.db")
    accepted = store.commit(answer(initialize(store))).read
    assert accepted.state and accepted.session_revision
    upgrade = UpgradeSession(
        SCOPE,
        accepted.session_revision,
        UpgradeCommit(
            UpgradeIdentity(SCOPE.learner_id, SCOPE.course_id, "1.0.0", "1.0.1"),
            accepted.state.record_revision,
            accepted.state.scratch,
            accepted.state.record.model_copy(update={"course_version": "1.0.1"}),
            b"",
        ),
        "a" * 64,
    )
    with pytest.raises(RecoveryRequired):
        store.commit(upgrade)
    feedback = pending_feedback(accepted)
    assert feedback
    acknowledged = store.commit(
        AcknowledgeSession(
            SCOPE,
            accepted.session_revision,
            feedback.feedback_id,
            feedback.revision,
        )
    ).read
    assert acknowledged.state and acknowledged.session_revision
    upgraded = store.commit(
        replace(
            upgrade,
            expected_revision=acknowledged.session_revision,
            commit=replace(upgrade.commit, expected_scratch=acknowledged.state.scratch),
        )
    ).read
    assert upgraded.state
    assert upgraded.state.record.course_version == "1.0.1"
    assert upgraded.state.source_digest == "a" * 64
    assert len(upgraded.state.reservations) == 1
    with pytest.raises(IdempotencyKeyConflict):
        store.commit(answer(upgraded))
    assert store.read(SCOPE) == upgraded


@pytest.mark.parametrize("mode", ["complete", "submit", "ack"])
@pytest.mark.parametrize("phase", ["before", "after"])
def test_complete_submit_ack_interrupted_commit(tmp_path: Path, mode: str, phase: str) -> None:
    store = SQLiteSessionStore.open(tmp_path / "state.db")
    initial = initialize(store)
    if mode == "submit":
        initial = store.commit(completion(initial)).read
    elif mode == "ack":
        initial = store.commit(answer(initial)).read
    process = worker(store.path, mode, phase)
    try:
        assert process.stdin and process.stdout
        assert line(process) == "READY"
        process.stdin.write("go\n")
        process.stdin.flush()
        assert line(process) == "BOUNDARY"
        process.kill()
        process.communicate(timeout=10)
        reopened = SQLiteSessionStore.open(store.path)
        current = reopened.read(SCOPE)
        if phase == "before":
            assert current == initial
        elif mode == "complete":
            assert current.state and len(current.state.log) == 1 and current.state.homework
            assert reopened.commit(completion(initial)).replayed
        elif mode == "submit":
            assert (
                current.state and len(current.state.archive) == 1 and current.state.homework is None
            )
            assert reopened.commit(submission(initial)).replayed
        else:
            assert current.state and initial.state
            assert pending_feedback(current) is None
            assert current.session_revision != initial.session_revision
            assert current.state.record_revision == initial.state.record_revision
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


def test_readonly_missing_config_and_invalid_timeout_refuse(tmp_path: Path) -> None:
    import stat

    path = tmp_path / "readonly.db"
    store = SQLiteSessionStore.open(path)
    initialize(store)
    before = path.read_bytes()
    path.chmod(stat.S_IRUSR)
    try:
        with pytest.raises(StoreError):
            SQLiteSessionStore.open(path).commit(mutation(store.read(SCOPE)))
        assert path.read_bytes() == before
    finally:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    with pytest.raises(StoreError):
        SQLiteSessionStore.open(tmp_path / "missing-parent" / "state.db")
    with pytest.raises(StoreError):
        SQLiteSessionStore.open(Path("relative.db"))
    for timeout in (-1, float("nan"), float("inf"), 61, True):
        with pytest.raises(ValueError):
            SQLiteSessionStore.open(tmp_path / "never-created.db", timeout=timeout)
    assert not (tmp_path / "never-created.db").exists()


def test_changed_key_identity_and_bad_pending_receipt_leave_bytes_unchanged(tmp_path: Path) -> None:
    from skilling.store import IdempotencyKeyConflict

    store = SQLiteSessionStore.open(tmp_path / "state.db")
    original = answer(initialize(store))
    accepted = store.commit(original)
    assert isinstance(original.commit.outcome, QuizAnswerOutcome)
    changed = replace(
        original,
        commit=replace(
            original.commit,
            identity=replace(original.commit.identity, input="c"),
            outcome=replace(original.commit.outcome, label="c"),
        ),
    )
    with pytest.raises(IdempotencyKeyConflict):
        store.commit(changed)
    assert store.read(SCOPE) == accepted.read
    body = json.loads(encode(accepted.read))
    scratch = yaml.safe_load(bytes.fromhex(body["state"]["scratch"]))
    scratch["pending_feedback"]["receipt_digest"] = "0" * 64
    body["state"]["scratch"] = yaml.safe_dump(scratch).encode().hex()
    with closing(sqlite3.connect(store.path)) as connection, connection:
        connection.execute("UPDATE skilling_sessions SET payload=?", (json.dumps(body).encode(),))
    before = store.path.read_bytes()
    with pytest.raises(RecoveryRequired):
        store.commit(original)
    assert store.path.read_bytes() == before


def test_new_backup_path_never_replaces_a_competing_database(tmp_path: Path, monkeypatch) -> None:
    import os

    store = SQLiteSessionStore.open(tmp_path / "state.db")
    initialize(store)
    destination = tmp_path / "backup.db"
    original = os.link

    def competing_link(source, target):
        SQLiteSessionStore.open(destination).close()
        return original(source, target)

    monkeypatch.setattr(os, "link", competing_link)
    with pytest.raises(StoreError):
        store.backup(destination)
    with SQLiteSessionStore.open(destination) as competitor:
        assert competitor.read(SCOPE).kind == SessionReadKind.ABSENT
    assert not list(tmp_path.glob(".skilling-backup-*"))


def test_backup_flushes_writable_staging_before_publish(tmp_path: Path, monkeypatch) -> None:
    import os
    import stat

    store = SQLiteSessionStore.open(tmp_path / "state.db")
    expected = initialize(store)
    destination = tmp_path / "backup.db"
    original = os.fsync
    flushed: list[int] = []

    def fsync(descriptor: int) -> None:
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            # A zero-byte write checks the Windows flush requirement on every platform.
            assert os.write(descriptor, b"") == 0
            assert not destination.exists()
            flushed.append(descriptor)
        original(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    store.backup(destination)
    assert len(flushed) == 1
    with SQLiteSessionStore.open(destination) as backup:
        assert backup.read(SCOPE) == expected
    assert not list(tmp_path.glob(".skilling-backup-*"))


def test_legacy_key_cannot_alias_a_trusted_event(tmp_path: Path) -> None:
    from skilling.store import IdempotencyKeyConflict, TransitionIdentity, TransitionVerb

    store = SQLiteSessionStore.open(tmp_path / "state.db")
    initial = initialize(store)
    assert initial.state and initial.session_revision
    legacy = TransitionIdentity(
        SCOPE.learner_id,
        SCOPE.course_id,
        "1.0.0",
        "0.1",
        TransitionVerb.ADVANCE,
        "next",
        "same-event",
    )
    store.commit(
        TransitionSession(
            SCOPE,
            initial.session_revision,
            TransitionCommit(
                legacy,
                initial.state.record_revision,
                initial.state.scratch,
                initial.state.record,
                b"",
            ),
        )
    )
    with pytest.raises(IdempotencyKeyConflict):
        store.commit(answer(store.read(SCOPE)))


def test_submission_cannot_forge_archive_or_discard_successor(tmp_path: Path) -> None:
    from ...test_store import a_slot

    store = SQLiteSessionStore.open(tmp_path / "state.db")
    complete = completion(initialize(store))
    assert complete.commit.homework
    complete = replace(
        complete,
        commit=replace(
            complete.commit,
            homework=replace(
                complete.commit.homework,
                slot=a_slot(queued=[a_slot("1.1")]),
            ),
        ),
    )
    current = store.commit(complete).read
    command = submission(current)
    forged = replace(
        command,
        commit=replace(
            command.commit,
            receipt=replace(
                command.commit.receipt,
                archive=command.commit.receipt.archive.model_copy(update={"title": "FORGED"}),
            ),
        ),
    )
    for refused in (command, forged):
        with pytest.raises(RecoveryRequired):
            store.commit(refused)
        assert store.read(SCOPE) == current
    accepted = store.commit(replace(command, commit=replace(command.commit, slot=a_slot("1.1"))))
    assert accepted.read.state and accepted.read.state.homework == a_slot("1.1")


def test_later_retry_clock_returns_original_completion_and_submission(tmp_path: Path) -> None:
    from datetime import timedelta

    store = SQLiteSessionStore.open(tmp_path / "state.db")
    command = completion(initialize(store))
    accepted = store.commit(command)
    clock = command.commit.receipt.completed_at + timedelta(seconds=1)
    changed = replace(
        command,
        commit=replace(
            command.commit,
            receipt=replace(command.commit.receipt, completed_at=clock),
            entry=command.commit.entry.model_copy(update={"completed_at": clock}),
        ),
    )
    replay = store.commit(changed)
    assert replay.replayed and replay.outcome == accepted.outcome
    submit = submission(accepted.read)
    submitted = store.commit(submit)
    changed_submit = replace(
        submit,
        commit=replace(
            submit.commit,
            receipt=replace(
                submit.commit.receipt,
                archive=submit.commit.receipt.archive.model_copy(update={"submitted_at": clock}),
            ),
        ),
    )
    replay = store.commit(changed_submit)
    assert replay.replayed and replay.outcome == submitted.outcome


def test_transition_requires_captured_coordinate_and_own_feedback(tmp_path: Path) -> None:
    store = SQLiteSessionStore.open(tmp_path / "state.db")
    initial = initialize(store)
    command = answer(initial)
    changed_coordinate = replace(
        command,
        commit=replace(
            command.commit,
            identity=replace(command.commit.identity, coordinate="99.99"),
        ),
    )
    missing_feedback = replace(command, commit=replace(command.commit, scratch=b""))
    for malformed in (changed_coordinate, missing_feedback):
        with pytest.raises(RecoveryRequired):
            store.commit(malformed)
        assert store.read(SCOPE) == initial


def test_completion_preserves_legacy_scratch_key_reservation(tmp_path: Path) -> None:
    store = SQLiteSessionStore.open(tmp_path / "state.db")
    initial = initialize(store)
    assert initial.state
    legacy = replace(initial, state=replace(initial.state, scratch=b"last_key: same-event\n"))
    with closing(sqlite3.connect(store.path)) as connection, connection:
        connection.execute("UPDATE skilling_sessions SET payload=?", (encode(legacy),))
    with pytest.raises(StoreError):
        store.commit(answer(legacy))
    completed = store.commit(completion(legacy)).read
    assert completed.state
    assert any(r.key == key_digest("same-event") for r in completed.state.reservations)
    with pytest.raises(StoreError):
        store.commit(answer(completed))
