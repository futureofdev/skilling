"""Public completion contract and hostile persisted descriptors, with fixed-date models."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from skilling import delivery
from skilling.course import Course, HomeworkArchiveEntry
from skilling.store import (
    CompletionCommit,
    CompletionCommitResult,
    CompletionReceipt,
    Conflict,
    FileProgressStore,
    HomeworkWrite,
    NotSupported,
    ProgressStore,
    RecoveryRequired,
    _journal,
)

from .test_completion_recovery import NOW, complete, seed_completion_fixture, snapshot
from .test_completion_recovery import controlled_calendar as controlled_calendar
from .test_store import BACKENDS, a_record, a_slot, an_entry

pytestmark = pytest.mark.storage_native


def a_commit(store: ProgressStore) -> CompletionCommit:
    record = a_record()
    revision = store.put_record(record, None)
    entry = an_entry("0.1")
    receipt = CompletionReceipt(
        "a" * 64,
        record.learner_id,
        record.course_id,
        record.course_version,
        entry.coordinate,
        entry.completed_at,
        ("alpha",),
        None,
        True,
        False,
    )
    return CompletionCommit(
        receipt,
        revision,
        record.model_copy(update={"completed": ["0.1"]}),
        (),
        entry,
        HomeworkWrite(None, a_slot()),
    )


@pytest.mark.parametrize("backend", sorted(BACKENDS))
def test_completion_commit_protocol_cas_and_replay(tmp_path: Path, backend: str) -> None:
    store = BACKENDS[backend](tmp_path)
    assert isinstance(store, ProgressStore)
    commit = a_commit(store)
    with pytest.raises(Conflict):
        store.commit_completion(replace(commit, expected_record_revision="stale"))
    assert store.get_log("local", commit.receipt.course_id) == []
    first = store.commit_completion(commit)
    assert not first.replayed and first.record == commit.record
    changed = first.record.model_copy(update={"timezone": "Pacific/Auckland"})
    revision = store.put_record(changed, first.revision)
    second = store.commit_completion(commit)
    assert second.replayed and second.record == changed and second.revision == revision
    assert second.receipt == first.receipt
    assert store.get_log("local", commit.receipt.course_id) == [commit.entry]
    assert store.get_homework("local", commit.receipt.course_id)[0] == a_slot()


@pytest.mark.parametrize("target", ["log", "homework"])
def test_completion_commit_rejects_stale_independent_targets(tmp_path: Path, target: str) -> None:
    store = FileProgressStore(tmp_path / "state")
    commit = a_commit(store)
    if target == "log":
        store.append_completion("local", commit.receipt.course_id, an_entry("0.2"))
    else:
        store.put_homework("local", commit.receipt.course_id, a_slot("0.3"), None)
    before = snapshot(store.state_root)
    with pytest.raises(Conflict, match="completed.yaml" if target == "log" else "active.yaml"):
        store.commit_completion(commit)
    assert snapshot(store.state_root) == before


def pending(
    store: FileProgressStore, commit: CompletionCommit, monkeypatch: pytest.MonkeyPatch
) -> Path:
    writer = _journal._write_bytes_atomic

    def stop(path: Path, data: bytes) -> None:
        writer(path, data)
        if path.name == "completion.yaml":
            raise OSError("prepared interruption")

    with monkeypatch.context() as patch:
        patch.setattr(_journal, "_write_bytes_atomic", stop)
        with pytest.raises(OSError, match="prepared interruption"):
            store.commit_completion(commit)
    return store.course_dir(commit.receipt.course_id) / "completion.yaml"


@pytest.mark.parametrize(
    "damage", ["duplicate", "missing", "record", "homework", "scratch", "order", "path"]
)
def test_recovery_invalid_later_descriptor_refuses_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str
) -> None:
    store = FileProgressStore(tmp_path / "state")
    commit = a_commit(store)
    path = pending(store, commit, monkeypatch)
    data = yaml.safe_load(path.read_bytes())
    mutations = data["mutations"]
    if damage == "duplicate":
        mutations.append(mutations[-1])
    elif damage == "missing":
        mutations.pop()
    elif damage == "record":
        mutations[1]["after"] = b"invalid: record\n"
    elif damage == "homework":
        mutations[2]["after"] = b"invalid: slot\n"
    elif damage == "scratch":
        mutations[-1]["after"] = b"not empty"
    elif damage == "order":
        mutations.reverse()
    else:
        mutations[-1]["target"] = "../record.yaml"
    path.write_bytes(yaml.safe_dump(data).encode())
    before = snapshot(store.state_root)
    with pytest.raises(RecoveryRequired):
        store.get_record("local", commit.receipt.course_id)
    assert snapshot(store.state_root) == before


def test_recovery_unexpected_target_bytes_refuses_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileProgressStore(tmp_path / "state")
    commit = a_commit(store)
    pending(store, commit, monkeypatch)
    store.checked_path(commit.receipt.course_id, "scratch.yaml").write_bytes(b"foreign last target")
    before = snapshot(store.state_root)
    with pytest.raises(RecoveryRequired, match="runtime-state"):
        store.get_record("local", commit.receipt.course_id)
    assert snapshot(store.state_root) == before


@pytest.mark.parametrize(
    "operation",
    [
        "record-read",
        "record-write",
        "log-read",
        "log-write",
        "homework-read",
        "homework-write",
        "archive-read",
        "archive-write",
        "list",
        "receipt",
        "scratch-read",
        "scratch-write",
    ],
)
def test_recovery_before_every_public_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    store = FileProgressStore(tmp_path / "state")
    commit = a_commit(store)
    pending(store, commit, monkeypatch)
    course = commit.receipt.course_id
    calls = {
        "record-read": lambda: store.get_record("local", course),
        "record-write": lambda: store.put_record(commit.record, commit.expected_record_revision),
        "log-read": lambda: store.get_log("local", course),
        "log-write": lambda: store.append_completion("local", course, an_entry("0.2")),
        "homework-read": lambda: store.get_homework("local", course),
        "homework-write": lambda: store.put_homework("local", course, None, None),
        "archive-read": lambda: store.get_homework_archive("local", course),
        "archive-write": lambda: store.append_homework_archive(
            "local",
            course,
            HomeworkArchiveEntry(
                coordinate="0.2", title="Archived", requirements=[], submitted_at=NOW
            ),
        ),
        "list": lambda: store.list_records(course),
        "receipt": lambda: store.get_completion_receipt("local", course),
        "scratch-read": lambda: store.read_runtime_state(course),
        "scratch-write": lambda: store.write_runtime_state(
            course, b"delayed", commit.expected_record_revision
        ),
    }
    if operation in {"record-write", "homework-write", "scratch-write"}:
        with pytest.raises(Conflict):
            calls[operation]()
    else:
        calls[operation]()
    record = store.get_record("local", course)
    assert record and record[0].completed == ["0.1"]
    assert store.get_log("local", course)[0] == commit.entry
    assert store.get_homework("local", course)[0] == a_slot()
    assert store.read_runtime_state(course) == b""


@pytest.mark.parametrize(
    "damage", ["identity", "record-model", "entry", "slot-model", "receipt", "learner"]
)
def test_completion_same_id_malformed_identity_refuses_before_replay(
    tmp_path: Path, damage: str
) -> None:
    store = FileProgressStore(tmp_path / "state")
    commit = a_commit(store)
    store.commit_completion(commit)
    before = snapshot(store.state_root)
    if damage == "identity":
        commit = replace(commit, receipt=replace(commit.receipt, course_version="wrong"))
    elif damage == "record-model":
        commit = replace(commit, record=commit.record.model_copy(update={"streak_days": -1}))
    elif damage == "entry":
        commit = replace(
            commit, entry=commit.entry.model_copy(update={"coordinate": "../../unsafe"})
        )
    elif damage == "slot-model":
        commit = replace(
            commit,
            homework=HomeworkWrite(None, a_slot().model_copy(update={"requirements": []})),
        )
    elif damage == "receipt":
        commit = replace(
            commit, receipt=replace(commit.receipt, completed_at=NOW.replace(tzinfo=None))
        )
    else:
        commit = replace(commit, receipt=replace(commit.receipt, learner_id="another"))
    with pytest.raises(RecoveryRequired):
        store.commit_completion(commit)
    assert snapshot(store.state_root) == before


@pytest.mark.parametrize(
    "data",
    [
        b"[bad",
        b"kind: unknown\n",
        b"version: 2\nkind: prepared\n",
        b"version: true\nkind: prepared\n",
        b"version: 1.0\nkind: prepared\n",
    ],
)
def test_recovery_corrupt_journal_refuses_without_guessing(tmp_path: Path, data: bytes) -> None:
    store = FileProgressStore(tmp_path / "state")
    commit = a_commit(store)
    store.checked_path(commit.receipt.course_id, "completion.yaml").write_bytes(data)
    before = snapshot(store.state_root)
    with pytest.raises(RecoveryRequired):
        store.get_log("local", commit.receipt.course_id)
    assert snapshot(store.state_root) == before


def test_completion_backend_without_commit_contract_refuses_before_writes(
    tmp_path: Path, example: Course
) -> None:
    store = seed_completion_fixture(tmp_path, example)
    found = store.get_record("local", example.id)
    lesson = example.lesson_at("1.3")
    assert found and lesson

    class OldBackend:
        def __getattr__(self, name):
            if name in {"commit_completion", "get_completion_receipt"}:
                raise AttributeError(name)
            return getattr(store, name)

    before = snapshot(store.state_root)
    with pytest.raises(NotSupported, match="upgrade"):
        delivery.complete_lesson(OldBackend(), example, *found, lesson, now=NOW)  # type: ignore[arg-type]
    assert snapshot(store.state_root) == before


def test_recovery_receipt_coordinate_missing_from_result_refuses(
    tmp_path: Path, example: Course, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skilling.delivery import _completion

    from .recovery_worker import utc_storage_test_day

    monkeypatch.setattr(_completion, "today_in", utc_storage_test_day)
    store = seed_completion_fixture(tmp_path, example)
    found = store.get_record("local", example.id)
    assert found

    def invalid_result(commit: CompletionCommit) -> CompletionCommitResult:
        return CompletionCommitResult(found[0], found[1], commit.receipt, True)

    monkeypatch.setattr(store, "commit_completion", invalid_result)
    with pytest.raises(RecoveryRequired, match="returned record snapshot"):
        complete(store, example)


def test_recovery_aliased_last_target_refuses_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from .test_state_paths import file_alias

    store = FileProgressStore(tmp_path / "state")
    commit = a_commit(store)
    pending(store, commit, monkeypatch)
    file_alias(
        store.checked_path(commit.receipt.course_id, "scratch.yaml"),
        store.checked_path(commit.receipt.course_id, "record.yaml"),
    )
    before = snapshot(store.state_root)
    with pytest.raises(RecoveryRequired):
        store.get_record("local", commit.receipt.course_id)
    assert snapshot(store.state_root) == before


def test_completion_file_learner_identity_remains_implicit(tmp_path: Path) -> None:
    store = FileProgressStore(tmp_path / "state")
    record = a_record(learner_id="alice")
    revision = store.put_record(record, None)
    entry = an_entry("0.1")
    receipt = CompletionReceipt(
        "a" * 64,
        "alice",
        record.course_id,
        record.course_version,
        "0.1",
        entry.completed_at,
        (),
        None,
        False,
        False,
    )
    commit = CompletionCommit(
        receipt, revision, record.model_copy(update={"completed": ["0.1"]}), (), entry, None
    )
    store.commit_completion(commit)
    reopened = FileProgressStore(store.state_root)
    found = reopened.get_record("local", record.course_id)
    assert found and found[0].learner_id == "alice"
    assert reopened.commit_completion(commit).replayed


@pytest.mark.parametrize("damage", ["receipt", "record", "slot"])
def test_completion_invalid_input_creates_no_lock_or_state(tmp_path: Path, damage: str) -> None:
    # A complete in-memory boundary is validated even when no persisted stream exists.
    source = FileProgressStore(tmp_path / "source")
    commit = a_commit(source)
    if damage == "receipt":
        commit = replace(commit, receipt=replace(commit.receipt, coordinate="../bad"))
    elif damage == "record":
        commit = replace(
            commit, record=commit.record.model_copy(update={"course_version": "wrong"})
        )
    else:
        commit = replace(
            commit, homework=HomeworkWrite(None, a_slot().model_copy(update={"requirements": []}))
        )
    absent = FileProgressStore(tmp_path / "absent")
    with pytest.raises(RecoveryRequired):
        absent.commit_completion(commit)
    assert not absent.state_root.exists()


@pytest.mark.parametrize("damage", ["missing", "learner", "course-version"])
def test_completion_replay_refuses_missing_or_replaced_stream(tmp_path: Path, damage: str) -> None:
    store = FileProgressStore(tmp_path / "state")
    commit = a_commit(store)
    first = store.commit_completion(commit)
    path = store.checked_path(commit.receipt.course_id, "record.yaml")
    if damage == "missing":
        path.unlink()
    else:
        field = "learner_id" if damage == "learner" else "course_version"
        store.put_record(first.record.model_copy(update={field: "replaced"}), first.revision)
    before = snapshot(store.state_root)
    with pytest.raises(RecoveryRequired):
        store.commit_completion(commit)
    assert snapshot(store.state_root) == before


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_recovery_valid_receipt_rejects_noninteger_or_unknown_version(
    tmp_path: Path, version: object
) -> None:
    store = FileProgressStore(tmp_path / "state")
    commit = a_commit(store)
    store.commit_completion(commit)
    path = store.checked_path(commit.receipt.course_id, "completion.yaml")
    data = yaml.safe_load(path.read_bytes())
    data["version"] = version
    path.write_bytes(yaml.safe_dump(data).encode())
    before = snapshot(store.state_root)
    with pytest.raises(RecoveryRequired):
        store.get_completion_receipt("local", commit.receipt.course_id)
    assert snapshot(store.state_root) == before


@pytest.mark.parametrize("delete", [False, True])
def test_completion_optional_homework_write_is_mechanical(tmp_path: Path, delete: bool) -> None:
    store = FileProgressStore(tmp_path / "state")
    commit = a_commit(store)
    revision = store.put_homework("local", commit.receipt.course_id, a_slot("4.2"), None)
    path = store.checked_path(commit.receipt.course_id, "homework", "active.yaml")
    before = path.read_bytes()
    commit = replace(commit, homework=HomeworkWrite(revision, None) if delete else None)
    store.commit_completion(commit)
    if delete:
        assert not path.exists()
    else:
        assert path.read_bytes() == before


def test_completion_identity_is_stable_and_noop_uses_current_record(
    tmp_path: Path, example: Course
) -> None:
    import hashlib
    import json

    store = seed_completion_fixture(tmp_path, example)
    result = complete(store, example)
    receipt = store.get_completion_receipt("local", example.id)
    assert receipt is not None
    expected = json.dumps(
        ["local", example.id, example.version, "1.3"], separators=(",", ":")
    ).encode()
    assert receipt.operation_id == hashlib.sha256(expected).hexdigest()
    changed = result.record.model_copy(update={"timezone": "Pacific/Auckland"})
    assert result.revision is not None
    revision = store.put_record(changed, result.revision)
    lesson = example.lesson_at("1.3")
    assert lesson is not None
    replay = delivery.complete_lesson(
        store, example, result.record, result.revision, lesson, now=NOW
    )
    assert replay.already_completed and replay.record == changed and replay.revision == revision


def test_recovery_metadata_directory_refuses_without_mutation(tmp_path: Path) -> None:
    store = FileProgressStore(tmp_path / "state")
    commit = a_commit(store)
    path = store.checked_path(commit.receipt.course_id, "completion.yaml")
    path.mkdir()
    (path / "evidence").write_bytes(b"preserve")
    before = snapshot(store.state_root)
    with pytest.raises(RecoveryRequired, match="metadata is not a file"):
        store.get_record("local", commit.receipt.course_id)
    assert snapshot(store.state_root) == before
