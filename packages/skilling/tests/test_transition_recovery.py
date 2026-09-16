"""Synthetic CLI/process evidence for coherent transitions, never learner participation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from skilling.cli import app
from skilling.cli.runtime._common import Scratch, open_session, serialize_scratch
from skilling.course import Artifact, ObjectiveMet, Telemetry
from skilling.delivery import complete_lesson
from skilling.store import (
    Conflict,
    FileProgressStore,
    IdempotencyKeyConflict,
    RecoveryRequired,
    StatePathError,
    TransitionCommit,
    TransitionIdentity,
    TransitionVerb,
    _journal,
)
from skilling.store._journal import _transition

from .conftest import REPO_ROOT
from .test_cli_runtime import LESSON_WITH_EXERCISE, LESSON_WITHOUT_EXERCISE, _walk_to_complete

BOUNDARIES = ("prepared", "record", "scratch", "receipt", "committed")
runner = CliRunner()


def run(course: Path, state: Path, *args: str) -> dict:
    got = runner.invoke(
        app, [*args, "--course", str(course), "--state", str(state)], catch_exceptions=False
    )
    assert got.exit_code == 0, got.output
    return json.loads(got.stdout)


def worker(course: Path, state: Path, verb: str = "advance", **options: str) -> list[str]:
    args = [
        sys.executable,
        "-m",
        "packages.skilling.tests.transition_worker",
        verb,
        "--course",
        str(course),
        "--state",
        str(state),
    ]
    for name, value in options.items():
        args += ["--" + name.replace("_", "-"), value]
    return args


def environment() -> dict[str, str]:
    return {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "PYTHONPATH",
            "PYTHONHOME",
            "SKILLING_STATE_ROOT",
            "SKILLING_CACHE_DIR",
            "SKILLING_WORKSPACE",
            "SKILLING_NOW",
        )
    }


def invoke(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=environment(),
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )


def bytes_at(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and p.name != ".skilling.lock"
    }


def next_commit(course: Path, state: Path, key: str | None = "once") -> TransitionCommit:
    session = open_session(str(course), state, "local")
    position = session.record.position.model_copy(update={"beat": "objectives"})
    assert session.revision is not None
    return TransitionCommit(
        TransitionIdentity(
            "local",
            session.course.id,
            session.course.version,
            session.lesson.coordinate,
            TransitionVerb.ADVANCE,
            "next",
            key,
        ),
        session.revision,
        session.scratch_bytes,
        session.record.model_copy(update={"position": position}),
        serialize_scratch(Scratch()),
    )


@pytest.mark.parametrize("fault", ["error", "exit", "hold"])
@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_process_fault_recovers_exactly_one_keyed_transition(
    clean_dir: Path, tmp_path: Path, fault: str, boundary: str
) -> None:
    state = tmp_path / "state"
    run(clean_dir, state, "next")
    marker = tmp_path / "ready"
    args = worker(clean_dir, state, key="once", fault=fault, boundary=boundary, marker=str(marker))
    if fault == "hold":
        process = subprocess.Popen(
            args,
            cwd=REPO_ROOT,
            env=environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 15
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert marker.exists()
        finally:
            process.kill()
            process.communicate(timeout=10)
        assert process.returncode != 0
    else:
        failed = invoke(args)
        assert failed.returncode == (73 if fault == "exit" else 1), failed.stderr
    inspect = invoke(worker(clean_dir, state, "inspect"))
    assert inspect.returncode == 0, inspect.stderr
    assert json.loads(inspect.stdout)["beat"]["name"] == "objectives"
    before = bytes_at(state)
    retry = invoke(worker(clean_dir, state, key="once"))
    assert retry.returncode == 0, retry.stderr
    body = json.loads(retry.stdout)
    assert body["replayed"] is True
    assert body["beat"]["name"] == "objectives"
    assert bytes_at(state) == before


def test_replay_is_current_after_intervening_key_and_unrelated_write(
    clean_dir: Path, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    run(clean_dir, state, "advance", "--input", "next", "--key", "one")
    run(clean_dir, state, "advance", "--input", "next", "--key", "two")
    store = FileProgressStore(state)
    found = store.get_record("local", "clean-course")
    assert found is not None
    record, revision = found
    updated = record.model_copy(
        update={
            "telemetry": Telemetry(opt_in=True, anonymous_id="kept"),
            "objectives_met": [
                ObjectiveMet(id="first", at=date(2026, 9, 16), evidence="explained")
            ],
            "artifacts": [
                Artifact(
                    path="showcase/goal.md",
                    title="Synthetic fixture",
                    coordinate="0.1",
                    added_at=datetime(2026, 9, 16, tzinfo=UTC),
                )
            ],
        }
    )
    revision = store.put_record(updated, revision)
    before = bytes_at(state)
    result = run(clean_dir, state, "advance", "--input", "next", "--key", "one")
    assert result["beat"]["name"] == "concept"
    assert result["revision"] == revision and result["replayed"] is True
    assert bytes_at(state) == before
    conflict = invoke(worker(clean_dir, state, key="one", input="proceed"))
    assert conflict.returncode == 3
    assert json.loads(conflict.stdout)["error"]["code"] == "idempotency-key-conflict"
    assert bytes_at(state) == before


def test_completion_keeps_keys_and_delayed_writer_conflicts(
    clean_dir: Path, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    run(clean_dir, state, "advance", "--input", "next", "--key", "first")
    stale = next_commit(clean_dir, state, "delayed")
    _walk_to_complete(clean_dir, state, LESSON_WITH_EXERCISE[1:])
    run(clean_dir, state, "complete")
    before = bytes_at(state)
    replay = run(clean_dir, state, "advance", "--input", "next", "--key", "first")
    assert replay["position"]["lesson"] == 2 and replay["beat"]["name"] == "welcome"
    assert bytes_at(state) == before
    store = FileProgressStore(state)
    with pytest.raises(Conflict):
        store.commit_transition(stale)
    assert bytes_at(state) == before


@pytest.mark.parametrize("boundary", ("prepared", "record", "scratch", "committed"))
def test_wrong_answer_and_revisit_scratch_recover(
    clean_dir: Path, tmp_path: Path, boundary: str
) -> None:
    state = tmp_path / "state"
    for given in LESSON_WITH_EXERCISE[:6]:
        run(clean_dir, state, "advance", "--input", given)
    # Fixture Q1 answers b; a is a deliberately synthetic wrong choice.
    failed = invoke(worker(clean_dir, state, "answer", input="a", fault="exit", boundary=boundary))
    assert failed.returncode == 73
    body = run(clean_dir, state, "next")
    assert body["beat"]["name"] == "remediate"
    assert "reason" not in body["beat"]["content"]
    store = FileProgressStore(state)
    snapshot = store.read_runtime_snapshot("local", "clean-course")
    assert snapshot is not None
    assert yaml.safe_load(snapshot.scratch)["wrong_count"] == 1
    failed = invoke(
        worker(
            clean_dir,
            state,
            input="revisit-concept",
            key="revisit",
            fault="exit",
            boundary=boundary,
        )
    )
    assert failed.returncode == 73
    body = run(clean_dir, state, "next")
    assert body["beat"]["name"] == "concept"
    snapshot = store.read_runtime_snapshot("local", "clean-course")
    assert snapshot is not None and snapshot.record.objectives_met == []
    assert yaml.safe_load(snapshot.scratch)["returning_to_quiz"] is True
    retry = run(clean_dir, state, "advance", "--input", "revisit-concept", "--key", "revisit")
    assert retry["beat"]["name"] == "concept" and retry["replayed"] is True
    body = run(clean_dir, state, "advance", "--input", "next")
    assert body["beat"]["name"] == "gate-concept"
    body = run(clean_dir, state, "advance", "--input", "proceed")
    assert body["beat"]["name"] == "quiz"
    assert body["position"]["question_index"] == 0
    snapshot = store.read_runtime_snapshot("local", "clean-course")
    assert snapshot is not None
    assert yaml.safe_load(snapshot.scratch)["returning_to_quiz"] is False


def test_legacy_key_reserved_without_read_writes_then_survives_completion(
    clean_dir: Path, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    run(clean_dir, state, "next")
    scratch = state / "clean-course" / "scratch.yaml"
    scratch.write_text("last_key: old\nlast_result: {}\n", encoding="utf-8")
    before = bytes_at(state)
    result = invoke(worker(clean_dir, state, key="old"))
    assert result.returncode == 3
    assert bytes_at(state) == before
    run(clean_dir, state, "advance", "--input", "next", "--key", "fresh")
    _walk_to_complete(clean_dir, state, LESSON_WITH_EXERCISE[1:])
    run(clean_dir, state, "complete")
    result = invoke(worker(clean_dir, state, key="old"))
    assert result.returncode == 3


def test_pending_state_relocates(clean_dir: Path, tmp_path: Path) -> None:
    old = tmp_path / "old"
    run(clean_dir, old, "next")
    assert (
        invoke(worker(clean_dir, old, key="move", fault="exit", boundary="record")).returncode == 73
    )
    new = tmp_path / "new"
    shutil.move(str(old), new)
    result = invoke(worker(clean_dir, new, key="move"))
    assert result.returncode == 0
    assert json.loads(result.stdout)["beat"]["name"] == "objectives"
    assert str(old).encode() not in b"".join(bytes_at(new).values())


@pytest.mark.parametrize(
    "damage",
    [
        "version",
        "boolean-version",
        "missing-version",
        "missing-kind",
        "stream",
        "coordinate",
        "record",
        "scratch",
        "receipt-path",
        "receipt",
        "operation",
        "keyed-answer",
        "unexpected",
    ],
)
def test_corrupt_pending_intent_refuses_without_writes(
    clean_dir: Path, tmp_path: Path, damage: str
) -> None:
    state = tmp_path / "state"
    run(clean_dir, state, "next")
    assert (
        invoke(
            worker(clean_dir, state, key="corrupt", fault="exit", boundary="prepared")
        ).returncode
        == 73
    )
    path = state / "clean-course" / "transition.yaml"
    data = yaml.safe_load(path.read_bytes())
    if damage == "version":
        data["version"] = 999
    elif damage == "boolean-version":
        data["version"] = True
    elif damage == "missing-version":
        del data["version"]
    elif damage == "missing-kind":
        del data["kind"]
    elif damage == "stream":
        data["identity"]["learner_id"] = "other"
    elif damage == "coordinate":
        data["identity"]["coordinate"] = "9.9"
    elif damage == "record":
        data["record_after"] = b"invalid"
    elif damage == "scratch":
        data["scratch_after"] = b"wrong_count: -1\n"
    elif damage == "receipt-path":
        data["receipt_path"] = "../sentinel"
    elif damage == "receipt":
        data["receipt"]["identity"]["input"] = "proceed"
    elif damage == "operation":
        data["identity"]["verb"] = "answer"
    elif damage == "keyed-answer":
        data["identity"].update(verb="answer", input="a")
    else:
        (path.parent / "scratch.yaml").write_bytes(b"unexpected: true\n")
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    before = bytes_at(state)
    with pytest.raises(RecoveryRequired):
        FileProgressStore(state).get_record("local", "clean-course")
    assert bytes_at(state) == before


@pytest.mark.parametrize("damage", ["key", "verb", "stream", "scratch", "revision"])
def test_invalid_commit_does_not_create_state(clean_dir: Path, tmp_path: Path, damage: str) -> None:
    commit = next_commit(clean_dir, tmp_path / "seed")
    if damage == "key":
        commit = replace(commit, identity=replace(commit.identity, key=""))
    elif damage == "verb":
        commit = replace(commit, identity=replace(commit.identity, verb="delete"))
    elif damage == "stream":
        commit = replace(commit, identity=replace(commit.identity, course_id="../escape"))
    elif damage == "scratch":
        commit = replace(commit, scratch=b"wrong_count: wrong\n")
    else:
        commit = replace(commit, expected_record_revision="")
    state = tmp_path / "absent"
    with pytest.raises((RecoveryRequired, StatePathError)):
        FileProgressStore(state).commit_transition(commit)
    assert not state.exists()


def test_different_key_writers_use_record_and_scratch_cas(clean_dir: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    first = next_commit(clean_dir, state)
    store = FileProgressStore(state)
    second = replace(first, identity=replace(first.identity, key="second"))
    store.commit_transition(first)
    with pytest.raises(Conflict):
        store.commit_transition(second)
    replay = store.commit_transition(first)
    assert replay.replayed is True
    with pytest.raises(IdempotencyKeyConflict):
        store.commit_transition(replace(first, identity=replace(first.identity, input="proceed")))


def test_pending_completion_and_transition_refuse_together(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    _walk_to_complete(clean_dir, state, LESSON_WITH_EXERCISE)
    commit = next_commit(clean_dir, state, "both")
    identity = _transition.Identity.model_validate(vars(commit.identity))
    pending = _transition.Prepared(
        version=1,
        kind="prepared",
        identity=identity,
        record_before=(state / "clean-course" / "record.yaml").read_bytes(),
        record_after=_transition.dump(commit.record.model_dump(mode="json")),
        scratch_before=commit.expected_scratch,
        scratch_after=commit.scratch,
        receipt_path="transition-receipts/" + _transition.receipt_name(identity, "both"),
        receipt=_transition.Receipt(version=1, kind="receipt", identity=identity),
    )
    real = _journal._write_bytes_atomic

    def stop(path: Path, data: bytes) -> None:
        real(path, data)
        if path.name == "completion.yaml" and yaml.safe_load(data)["kind"] == "prepared":
            raise OSError("stop after prepared completion")

    with monkeypatch.context() as patch:
        patch.setattr(_journal, "_write_bytes_atomic", stop)
        with pytest.raises(OSError):
            run(clean_dir, state, "complete")
    (state / "clean-course" / "transition.yaml").write_bytes(_transition.dump(pending.model_dump()))
    # Each journal is valid against the same current bytes; only their coexistence refuses.
    journal = _journal.Journal(state, "clean-course")
    completion = journal._load()
    assert isinstance(completion, _journal.Prepared)
    journal._preflight(completion)
    assert isinstance(
        _transition.TransitionJournal(state, "clean-course").inspect(), _transition.Prepared
    )
    before = bytes_at(state)
    with pytest.raises(RecoveryRequired, match="multiple prepared"):
        FileProgressStore(state).get_record("local", "clean-course")
    assert bytes_at(state) == before


def test_direct_commit_cannot_rebind_legacy_key(clean_dir: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    run(clean_dir, state, "next")
    (state / "clean-course" / "scratch.yaml").write_bytes(b"last_key: old\nlast_result: {}\n")
    commit = next_commit(clean_dir, state, "old")
    before = bytes_at(state)
    with pytest.raises(IdempotencyKeyConflict):
        FileProgressStore(state).commit_transition(commit)
    assert bytes_at(state) == before


def test_same_record_changed_scratch_conflicts(clean_dir: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    commit = next_commit(clean_dir, state)
    store = FileProgressStore(state)
    store.write_runtime_state(
        "clean-course", serialize_scratch(Scratch(wrong_count=2)), commit.expected_record_revision
    )
    before = bytes_at(state)
    with pytest.raises(Conflict, match="scratch.yaml"):
        store.commit_transition(commit)
    assert bytes_at(state) == before


def start_worker(args: list[str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        args,
        cwd=REPO_ROOT,
        env=environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_ready(marker: Path, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 15
    while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert marker.exists(), "worker did not reach the barrier"


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_writers_share_one_snapshot(
    clean_dir: Path, tmp_path: Path, same_key: bool
) -> None:
    state = tmp_path / "state"
    run(clean_dir, state, "next")
    release = tmp_path / "release"
    markers = [tmp_path / f"ready-{i}" for i in range(2)]
    keys = ["once", "once" if same_key else "different"]
    processes = [
        start_worker(worker(clean_dir, state, key=key, ready=str(marker), release=str(release)))
        for key, marker in zip(keys, markers, strict=True)
    ]
    try:
        for marker, process in zip(markers, processes, strict=True):
            wait_ready(marker, process)
        release.write_text("go", encoding="utf-8")
        outputs = [process.communicate(timeout=20) for process in processes]
        assert sorted(process.returncode for process in processes) == (
            [0, 0] if same_key else [0, 3]
        )
        bodies = [json.loads(output[0]) for output in outputs]
        if same_key:
            assert sorted(body["replayed"] for body in bodies) == [False, True]
        else:
            assert [body["error"]["code"] for body in bodies if not body["ok"]] == ["conflict"]
        assert run(clean_dir, state, "next")["beat"]["name"] == "objectives"
        assert len(list((state / "clean-course" / "transition-receipts").glob("*.yaml"))) == 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)


def test_reader_waits_for_killed_owner_then_recovers_coherent_scratch(
    clean_dir: Path, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    _walk_to_complete(clean_dir, state, LESSON_WITH_EXERCISE[:6])
    marker = tmp_path / "held"
    writer = start_worker(
        worker(
            clean_dir,
            state,
            "answer",
            input="a",
            fault="hold",
            boundary="record",
            marker=str(marker),
        )
    )
    reader = None
    try:
        wait_ready(marker, writer)
        reader = start_worker(worker(clean_dir, state, "inspect"))
        with pytest.raises(subprocess.TimeoutExpired):
            reader.communicate(timeout=0.5)
        writer.kill()
        writer.communicate(timeout=10)
        output, error = reader.communicate(timeout=15)
        assert reader.returncode == 0, error
        assert json.loads(output)["beat"]["name"] == "remediate"
        snapshot = FileProgressStore(state).read_runtime_snapshot("local", "clean-course")
        assert snapshot is not None
        assert snapshot.record.position.question_index == 0
        assert yaml.safe_load(snapshot.scratch)["wrong_count"] == 1
    finally:
        for process in (writer, reader):
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=10)


def test_key_replay_after_full_course_completion(clean_dir: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    first = run(clean_dir, state, "advance", "--input", "next", "--key", "first")
    assert first["replayed"] is False
    for inputs in (LESSON_WITH_EXERCISE[1:], LESSON_WITH_EXERCISE, LESSON_WITHOUT_EXERCISE):
        _walk_to_complete(clean_dir, state, inputs)
        run(clean_dir, state, "complete")
    before = bytes_at(state)
    replay = run(clean_dir, state, "advance", "--input", "next", "--key", "first")
    assert replay["beat"]["name"] == "done" and replay["replayed"] is True
    assert replay["completed_count"] == 3 and replay["legal_inputs"] == []
    assert bytes_at(state) == before


def test_complete_renders_coherent_snapshot_after_interleaved_advance(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skilling.cli.runtime import _session

    state = tmp_path / "state"
    _walk_to_complete(clean_dir, state, LESSON_WITH_EXERCISE)

    def complete(*args, **kwargs):
        outcome = complete_lesson(*args, **kwargs)
        advanced = invoke(worker(clean_dir, state, key="after-complete"))
        assert advanced.returncode == 0, advanced.stderr
        return outcome

    monkeypatch.setattr(_session, "complete_lesson", complete)
    body = run(clean_dir, state, "complete")
    assert body["already_completed"] is False and body["completed_count"] == 1
    assert body["position"]["lesson"] == 2 and body["beat"]["name"] == "objectives"
    assert body["revision"] == run(clean_dir, state, "next")["revision"]


@pytest.mark.parametrize("target", ["transition.yaml", "transition-receipts", "receipt"])
def test_transition_paths_refuse_aliases(clean_dir: Path, tmp_path: Path, target: str) -> None:
    state = tmp_path / "state"
    commit = next_commit(clean_dir, state)
    outside = tmp_path / "sentinel"
    if target == "transition-receipts":
        outside.mkdir()
        (outside / "keep").write_bytes(b"unchanged")
        path = state / "clean-course" / target
    else:
        outside.write_bytes(b"unchanged")
        if target == "receipt":
            identity = _transition.Identity.model_validate(vars(commit.identity))
            path = (
                state
                / "clean-course"
                / "transition-receipts"
                / _transition.receipt_name(identity, "once")
            )
            path.parent.mkdir()
        else:
            path = state / "clean-course" / target
    try:
        path.symlink_to(outside, target_is_directory=outside.is_dir())
    except OSError:
        pytest.skip("native symlink privilege unavailable")
    before = bytes_at(tmp_path)
    with pytest.raises((StatePathError, RecoveryRequired)):
        FileProgressStore(state).commit_transition(commit)
    assert bytes_at(tmp_path) == before


def test_prepared_publish_failure_has_no_effects(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    commit = next_commit(clean_dir, state)
    before = bytes_at(state)

    def fail_write(path: Path, data: bytes) -> None:
        assert path.name == "transition.yaml"
        assert yaml.safe_load(data)["kind"] == "prepared"
        raise OSError("failed before publishing intent")

    with monkeypatch.context() as patch:
        patch.setattr(_transition, "_write_bytes_atomic", fail_write)
        with pytest.raises(OSError):
            FileProgressStore(state).commit_transition(commit)
    assert bytes_at(state) == before
    store = FileProgressStore(state)
    assert store.get_transition_identity("local", "clean-course", "once") is None
    assert store.commit_transition(commit).replayed is False


@pytest.mark.parametrize("damage", ["missing-version", "missing-kind", "operation", "key"])
def test_corrupt_receipt_refuses_retry_without_effects(
    clean_dir: Path, tmp_path: Path, damage: str
) -> None:
    state = tmp_path / "state"
    run(clean_dir, state, "advance", "--input", "next", "--key", "once")
    path = next((state / "clean-course" / "transition-receipts").glob("*.yaml"))
    data = yaml.safe_load(path.read_bytes())
    if damage == "missing-version":
        del data["version"]
    elif damage == "missing-kind":
        del data["kind"]
    elif damage == "operation":
        data["identity"]["verb"] = "answer"
    else:
        data["identity"]["key"] = "another"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    before = bytes_at(state)
    result = invoke(worker(clean_dir, state, key="once"))
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]["code"] == "recovery-required"
    assert bytes_at(state) == before


@pytest.mark.parametrize("damage", ["learner_id", "course_version", "missing-record"])
def test_committed_marker_stream_must_match_current_record(
    clean_dir: Path, tmp_path: Path, damage: str
) -> None:
    state = tmp_path / "state"
    run(clean_dir, state, "advance", "--input", "next", "--key", "once")
    path = state / "clean-course" / "transition.yaml"
    if damage == "missing-record":
        (path.parent / "record.yaml").unlink()
    else:
        data = yaml.safe_load(path.read_bytes())
        data["identity"][damage] = "other" if damage == "learner_id" else "2.0.0"
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
    before = bytes_at(state)
    with pytest.raises(RecoveryRequired):
        FileProgressStore(state).get_record("local", "clean-course")
    assert bytes_at(state) == before


def test_completion_reserves_legacy_key_before_clearing_scratch(
    clean_dir: Path, tmp_path: Path
) -> None:
    state = tmp_path / "state"
    _walk_to_complete(clean_dir, state, LESSON_WITH_EXERCISE)
    (state / "clean-course" / "scratch.yaml").write_bytes(b"last_key: old\nlast_result: {}\n")
    run(clean_dir, state, "complete")
    before = bytes_at(state)
    result = invoke(worker(clean_dir, state, key="old"))
    assert result.returncode == 3
    assert bytes_at(state) == before
