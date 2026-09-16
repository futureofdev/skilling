"""Real completion interruption; synthetic machinery checks, not learner proof.

storage_native isolates only timezone lookup with a fixed UTC calendar in parent/worker.
Native file operations, kernel locks, process exit and recovery are never mocked away.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from skilling import delivery
from skilling.course import (
    Artifact,
    CompletionEntry,
    Course,
    ObjectiveMet,
    Position,
    Record,
    Telemetry,
)
from skilling.delivery import _completion
from skilling.store import Conflict, FileProgressStore, RecoveryRequired, _journal

from .conftest import REPO_ROOT
from .recovery_worker import boundary_for, utc_storage_test_day

NOW = datetime(2026, 8, 3, 23, 59, 59, tzinfo=UTC)
BOUNDARIES = ["prepared", "log", "record", "homework", "runtime-state", "committed"]


@pytest.fixture(autouse=True)
def controlled_calendar(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("storage_native"):
        monkeypatch.setattr(_completion, "today_in", utc_storage_test_day)


def seed_completion_fixture(
    root: Path, course: Course, coordinate: str = "1.3"
) -> FileProgressStore:
    store = FileProgressStore(root / "state")
    lesson = course.lesson_at(coordinate)
    assert lesson is not None
    completed = list(course.coordinates[: course.coordinates.index(coordinate)])
    record = Record(
        learner_id="local",
        course_id=course.id,
        course_version=course.version,
        spec_version="1.4",
        position=Position(phase=lesson.phase, lesson=lesson.number, beat="complete"),
        completed=completed,
        started_at=date(2026, 8, 2),
        last_activity=date(2026, 8, 2),
        streak_days=2,
        timezone="UTC",
        artifacts=[
            Artifact(
                path="showcase/existing.txt",
                title="Prior work",
                coordinate=completed[0],
                added_at=NOW - timedelta(days=1),
            )
        ],
        objectives_met=[
            ObjectiveMet(id="previous-objective", at=date(2026, 8, 2), evidence="explained")
        ],
        telemetry=Telemetry(opt_in=False, anonymous_id="preserved-pseudonym"),
    )
    revision = store.put_record(record, None)
    for previous in completed:
        store.append_completion(
            "local",
            course.id,
            CompletionEntry(
                coordinate=previous,
                title=previous,
                completed_at=NOW - timedelta(days=1),
                course_version=course.version,
            ),
        )
    store.write_runtime_state(course.id, b"wrong_count: 2\nlast_key: old-key\n", revision)
    return store


def complete(store: FileProgressStore, course: Course, coordinate: str = "1.3", **kwargs):
    found = store.get_record("local", course.id)
    lesson = course.lesson_at(coordinate)
    assert found is not None and lesson is not None
    return delivery.complete_lesson(
        store, course, *found, lesson, now=kwargs.pop("now", NOW), **kwargs
    )


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and p.name != ".skilling.lock"
    }


def worker_args(store: FileProgressStore, course: Course, boundary: str | None = None) -> list[str]:
    args = [
        sys.executable,
        "-m",
        "packages.skilling.tests.recovery_worker",
        "complete",
        "--state",
        str(store.state_root),
        "--course",
        str(course.root),
        "--calendar",
        "utc-storage-test",
    ]
    if boundary:
        args += ["--exit-after", boundary]
    return args


def read_worker(store: FileProgressStore, course_id: str) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "packages.skilling.tests.recovery_worker",
            "read",
            "--state",
            str(store.state_root),
            "--course-id",
            course_id,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def assert_restored(data: dict, original_log: list[CompletionEntry]) -> None:
    assert data["record"]["completed"].count("1.3") == 1
    assert data["log"][:-1] == [e.model_dump(mode="json") for e in original_log]
    assert sum(e["coordinate"] == "1.3" for e in data["log"]) == 1
    assert data["log"][-1]["completed_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert data["completed_at"] == NOW.isoformat()
    assert data["slot"]["coordinate"] == "1.3"
    assert data["slot"]["queued"] == []
    assert data["slot"]["unlocked_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert data["record"]["last_activity"] == "2026-08-03"
    assert data["record"]["streak_days"] == 3
    assert set(data["record"]["skills_unlocked"]) == {"course-anatomy", "first-course"}
    assert data["runtime_state"] == ""
    assert data["record"]["artifacts"] == [
        {
            "path": "showcase/existing.txt",
            "title": "Prior work",
            "coordinate": "1.1",
            "added_at": (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        }
    ]
    assert data["record"]["objectives_met"] == [
        {
            "id": "previous-objective",
            "at": "2026-08-02",
            "evidence": "explained",
            "provenance": None,
        }
    ]
    assert data["record"]["telemetry"] == {"opt_in": False, "anonymous_id": "preserved-pseudonym"}


@pytest.mark.storage_native
@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_recovery_caught_error_before_each_write(
    tmp_path: Path, example: Course, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    store = seed_completion_fixture(tmp_path, example)
    previous = store.get_log("local", example.id)
    before = snapshot(store.state_root)
    original = _journal._write_bytes_atomic

    def fail(path: Path, data: bytes) -> None:
        if boundary_for(path, data) == boundary:
            raise OSError("interrupted target")
        original(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(_journal, "_write_bytes_atomic", fail)
        with pytest.raises(OSError, match="interrupted target"):
            complete(store, example)
    if boundary == "prepared":
        assert snapshot(store.state_root) == before
        complete(store, example)
    result = complete(store, example, now=NOW + timedelta(days=1))
    assert result.already_completed
    assert_restored(read_worker(store, example.id), previous)
    committed = snapshot(store.state_root)
    assert complete(store, example).already_completed
    assert snapshot(store.state_root) == committed


@pytest.mark.storage_native
@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_recovery_after_process_exit_at_each_boundary(
    tmp_path: Path, example: Course, boundary: str
) -> None:
    store = seed_completion_fixture(tmp_path, example)
    previous = store.get_log("local", example.id)
    result = subprocess.run(
        worker_args(store, example, boundary),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 73, result.stdout + result.stderr
    assert_restored(read_worker(store, example.id), previous)


@pytest.mark.storage_native
def test_recovery_successful_ack_survives_process_exit(tmp_path: Path, example: Course) -> None:
    store = seed_completion_fixture(tmp_path, example)
    previous = store.get_log("local", example.id)
    result = subprocess.run(
        worker_args(store, example), cwd=REPO_ROOT, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not json.loads(result.stdout)["already_completed"]
    assert_restored(read_worker(store, example.id), previous)


@pytest.mark.storage_native
def test_recovery_killed_lock_owner_does_not_block_next_process(
    tmp_path: Path, example: Course
) -> None:
    store = seed_completion_fixture(tmp_path, example)
    previous = store.get_log("local", example.id)
    marker = tmp_path / "ready"
    process = subprocess.Popen(
        worker_args(store, example, "record") + ["--hold-marker", str(marker)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 30
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists(), process.poll()
        process.kill()
        process.communicate(timeout=10)
        assert process.returncode != 0
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)
    assert_restored(read_worker(store, example.id), previous)


@pytest.mark.storage_native
def test_recovery_pending_intent_survives_state_relocation(tmp_path: Path, example: Course) -> None:
    store = seed_completion_fixture(tmp_path, example)
    previous = store.get_log("local", example.id)
    result = subprocess.run(
        worker_args(store, example, "prepared"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 73, result.stderr
    raw = (store.course_dir(example.id) / "completion.yaml").read_bytes()
    assert str(tmp_path).encode() not in raw
    destination = tmp_path / "moved-state"
    store.state_root.rename(destination)
    assert_restored(read_worker(FileProgressStore(destination), example.id), previous)


@pytest.mark.storage_native
def test_recovery_concurrent_processes_apply_one_intent(tmp_path: Path, example: Course) -> None:
    store = seed_completion_fixture(tmp_path, example)
    previous = store.get_log("local", example.id)
    result = subprocess.run(
        worker_args(store, example, "prepared"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 73, result.stderr
    args = [
        sys.executable,
        "-m",
        "packages.skilling.tests.recovery_worker",
        "read",
        "--state",
        str(store.state_root),
        "--course-id",
        example.id,
    ]
    processes = [
        subprocess.Popen(
            args, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        for _ in range(2)
    ]
    try:
        for process in processes:
            out, err = process.communicate(timeout=30)
            assert process.returncode == 0, out + err
            assert_restored(json.loads(out), previous)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=10)


@pytest.mark.storage_native
@pytest.mark.parametrize("stage", ["parse", "serialize"])
def test_recovery_preparation_failure_leaves_all_bytes(
    tmp_path: Path, example: Course, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    store = seed_completion_fixture(tmp_path, example)
    before = snapshot(store.state_root)

    def fail(*args, **kwargs):
        raise ValueError("cannot parse assignment")

    with monkeypatch.context() as patch:
        if stage == "parse":
            patch.setattr(_completion, "assignment_from_lesson", fail)
        else:
            patch.setattr(_journal, "_dump", fail)
        with pytest.raises(ValueError, match="cannot parse assignment"):
            complete(store, example)
    assert snapshot(store.state_root) == before
    result = complete(store, example, now=NOW + timedelta(days=1))
    assert not result.already_completed
    receipt = store.get_completion_receipt("local", example.id)
    assert receipt and receipt.completed_at == NOW + timedelta(days=1)


@pytest.mark.storage_native
def test_recovery_stale_artifact_writer_conflicts_then_can_retry(
    tmp_path: Path, example: Course
) -> None:
    store = seed_completion_fixture(tmp_path, example)
    stale = store.get_record("local", example.id)
    assert stale
    result = subprocess.run(
        worker_args(store, example, "log"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 73, result.stderr
    with pytest.raises(Conflict):
        store.put_record(stale[0].model_copy(update={"skills_unlocked": ["independent"]}), stale[1])
    current = store.get_record("local", example.id)
    assert current and "1.3" in current[0].completed
    artifact = Artifact(
        path="showcase/new.txt", title="Independent", coordinate="1.3", added_at=NOW
    )
    revision = store.put_record(
        current[0].model_copy(update={"artifacts": [*current[0].artifacts, artifact]}), current[1]
    )
    assert complete(store, example).revision == revision
    final = store.get_record("local", example.id)
    assert final and final[0].artifacts == [*current[0].artifacts, artifact]
    assert final[0].objectives_met == current[0].objectives_met
    assert final[0].telemetry == current[0].telemetry


@pytest.mark.storage_native
def test_recovery_delayed_scratch_write_conflicts(tmp_path: Path, example: Course) -> None:
    store = seed_completion_fixture(tmp_path, example)
    old = store.get_record("local", example.id)
    assert old
    complete(store, example)
    with pytest.raises(Conflict):
        store.write_runtime_state(example.id, b"old scratch", old[1])
    assert store.read_runtime_state(example.id) == b""


@pytest.mark.storage_native
def test_recovery_legacy_divergence_is_not_silently_repaired(
    tmp_path: Path, example: Course
) -> None:
    store = seed_completion_fixture(tmp_path, example)
    store.append_completion(
        "local",
        example.id,
        CompletionEntry(
            coordinate="1.3", title="legacy", completed_at=NOW, course_version=example.version
        ),
    )
    before = snapshot(store.state_root)
    with pytest.raises(RecoveryRequired, match="legacy"):
        complete(store, example)
    assert snapshot(store.state_root) == before
    found = store.get_record("local", example.id)
    assert found
    store.put_record(
        found[0].model_copy(update={"completed": [*found[0].completed, "1.3"]}), found[1]
    )
    before = snapshot(store.state_root)
    assert complete(store, example).already_completed
    assert snapshot(store.state_root) == before
    assert store.get_homework("local", example.id) == (None, None)


@pytest.mark.storage_native
def test_recovery_snapshot_does_not_misclassify_concurrent_completion(
    tmp_path: Path, example: Course, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = seed_completion_fixture(tmp_path, example)
    original = store.get_log
    called = False

    def get_log(learner: str, course_id: str):
        nonlocal called
        if not called:
            called = True
            result = subprocess.run(
                worker_args(store, example),
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
        return original(learner, course_id)

    monkeypatch.setattr(store, "get_log", get_log)
    assert complete(store, example).already_completed
    assert len(original("local", example.id)) == 3


@pytest.mark.storage_native
def test_recovery_hook_policy_suppresses_replay(tmp_path: Path, example: Course) -> None:
    store = seed_completion_fixture(tmp_path, example)
    sink = delivery.RecordingSink()
    hooks = delivery.Dispatcher(first_party=[sink])
    complete(store, example, hooks=hooks)
    count = len(sink.events)
    assert count >= 4
    complete(store, example, hooks=hooks)
    assert len(sink.events) == count
    recovered = seed_completion_fixture(tmp_path / "pending", example)
    result = subprocess.run(
        worker_args(recovered, example, "record"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 73, result.stderr
    complete(recovered, example, hooks=hooks)
    assert len(sink.events) == count
    hooks.close()


@pytest.mark.storage_native
def test_recovery_workbench_queue_preserves_active_verdicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = Course.load(REPO_ROOT / "examples" / "workbench")
    store = seed_completion_fixture(tmp_path, course, "1.2")
    first = complete(store, course, "1.2")
    assert first.record.position.coordinate == "2.1"
    slot, revision = store.get_homework("local", course.id)
    assert slot is not None
    requirements = [
        slot.requirements[0].model_copy(
            update={"verdict": "met", "reason": "seeded mechanical verdict"}
        ),
        *slot.requirements[1:],
    ]
    active = slot.model_copy(update={"requirements": requirements})
    store.put_homework("local", course.id, active, revision)
    complete(store, course, "2.1")
    original = _journal._write_bytes_atomic

    def fail(path: Path, data: bytes) -> None:
        if path.name == "active.yaml":
            raise OSError("queue interrupted")
        original(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(_journal, "_write_bytes_atomic", fail)
        with pytest.raises(OSError, match="queue interrupted"):
            complete(store, course, "2.2")
    recovered = complete(store, course, "2.2", now=NOW + timedelta(days=1))
    assert recovered.already_completed
    restored, _ = store.get_homework("local", course.id)
    assert restored is not None
    assert restored.model_dump(exclude={"queued"}) == active.model_dump(exclude={"queued"})
    assert [item.coordinate for item in restored.queued] == ["2.2"]
    assert restored.queued[0].unlocked_at == NOW
    before = snapshot(store.state_root)
    assert complete(store, course, "2.2").already_completed
    assert snapshot(store.state_root) == before
