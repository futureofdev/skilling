"""Completion chronology is append order, independent of record ordering and wall clocks."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import pytest
from typer.testing import CliRunner

from skilling.cli import app
from skilling.course import CompletionEntry, Course, Record
from skilling.store import LOCAL_LEARNER, FileProgressStore
from skilling.workspace import WorkspaceManifest, save_manifest, state_root

from .conftest import REPO_ROOT

WORKBENCH = REPO_ROOT / "examples" / "workbench"

runner = CliRunner()


class HistoryFixture(NamedTuple):
    course: Course
    state: Path


def seed(root: Path, completed: list[str], *, log: bool = True) -> HistoryFixture:
    save_manifest(root, WorkspaceManifest())
    course = Course.load(WORKBENCH)
    state = state_root(root)
    store = FileProgressStore(state)
    record = Record.new(course, LOCAL_LEARNER).model_copy(update={"completed": completed})
    store.put_record(record, None)
    if log:
        for coordinate, year in [("1.2", 2026), ("2.2", 2025)]:
            store.append_completion(
                LOCAL_LEARNER,
                course.id,
                CompletionEntry(
                    coordinate=coordinate,
                    title=coordinate,
                    completed_at=datetime(year, 8, 3, tzinfo=UTC),
                    course_version="0.1.0" if year == 2026 else course.version,
                ),
            )
    (root / "artifact.txt").write_text("work", encoding="utf-8")
    return HistoryFixture(course, state)


def files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def invoke(verb: str, state: Path, coordinate: str | None = None):
    args = (
        ["ceremony"]
        if verb == "ceremony"
        else ["artifact", "add", "artifact.txt", "--title", "Work"]
    )
    args += ["--course", str(WORKBENCH), "--state", str(state)]
    if coordinate is not None:
        args += ["--coordinate", coordinate]
    return runner.invoke(app, args, catch_exceptions=False)


@pytest.mark.parametrize("completed", [["1.2", "2.2"], ["2.2", "1.2"]])
@pytest.mark.parametrize("verb", ["ceremony", "artifact"])
def test_defaults_use_append_order_not_record_or_timestamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, completed: list[str], verb: str
) -> None:
    _, state = seed(tmp_path, completed)
    monkeypatch.chdir(tmp_path)
    result = invoke(verb, state)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    selected = payload["beat"]["content"] if verb == "ceremony" else payload["artifact"]
    assert selected["coordinate"] == "2.2"


@pytest.mark.parametrize("verb", ["ceremony", "artifact"])
@pytest.mark.parametrize("completed", [[], ["1.2", "2.2"]])
def test_missing_ambiguous_history_refuses_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verb: str, completed: list[str]
) -> None:
    _, state = seed(tmp_path, completed, log=False)
    monkeypatch.chdir(tmp_path)
    before = files(state)
    result = invoke(verb, state)
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"] == "coordinate-required"
    assert files(state) == before


@pytest.mark.parametrize("verb", ["ceremony", "artifact"])
@pytest.mark.parametrize(
    "completed,override,expected",
    [
        (["1.2"], None, "1.2"),
        (["1.2", "2.2"], "1.2", "1.2"),
        (["1.2", "2.2"], "2.2", "2.2"),
    ],
)
def test_missing_log_allows_sole_completion_or_explicit_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    verb: str,
    completed: list[str],
    override: str | None,
    expected: str,
) -> None:
    _, state = seed(tmp_path, completed, log=False)
    monkeypatch.chdir(tmp_path)
    result = invoke(verb, state, override)
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    content = body["beat"]["content"] if verb == "ceremony" else body["artifact"]
    assert content["coordinate"] == expected


@pytest.mark.parametrize("verb", ["ceremony", "artifact"])
@pytest.mark.parametrize("override", ["1.1", "9.9", "nonsense"])
def test_override_requires_known_completed_coordinate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verb: str, override: str
) -> None:
    _, state = seed(tmp_path, ["1.2", "2.2"])
    monkeypatch.chdir(tmp_path)
    before = files(state)
    result = invoke(verb, state, override)
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"] == "chronology-invalid"
    assert files(state) == before


@pytest.mark.parametrize("verb", ["ceremony", "artifact"])
@pytest.mark.parametrize("override", [None, "1.2"])
@pytest.mark.parametrize(
    "corruption",
    [
        "{}",
        "false",
        "0",
        "null",
        "",
        "''",
        "[",
        "[42]",
        "[{}]",
        "unknown",
        "not-completed",
        "conflicting-duplicate",
        "missing-entry",
        "empty-version",
    ],
)
def test_entire_log_is_validated_even_with_override_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    verb: str,
    override: str | None,
    corruption: str,
) -> None:
    import yaml

    _, state = seed(tmp_path, ["1.2", "2.2"])
    monkeypatch.chdir(tmp_path)
    path = state / "workbench" / "completed.yaml"
    entries = yaml.safe_load(path.read_text())
    if corruption == "unknown":
        entries[0]["coordinate"] = "9.9"
    elif corruption == "not-completed":
        entries[0]["coordinate"] = "1.1"
    elif corruption == "conflicting-duplicate":
        entries.append({**entries[0], "title": "conflicting"})
    elif corruption == "missing-entry":
        entries.pop(0)
    elif corruption == "empty-version":
        entries[0]["course_version"] = " "
    else:
        entries = None
    path.write_text(corruption if entries is None else yaml.safe_dump(entries), encoding="utf-8")
    before = files(state)
    result = invoke(verb, state, override)
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"] == "chronology-invalid"
    assert files(state) == before


@pytest.mark.parametrize("verb", ["ceremony", "artifact"])
def test_no_record_is_not_initialized_on_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verb: str
) -> None:
    save_manifest(tmp_path, WorkspaceManifest())
    (tmp_path / "artifact.txt").write_text("work")
    monkeypatch.chdir(tmp_path)
    before = files(tmp_path)
    result = invoke(verb, state_root(tmp_path))
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"] == "coordinate-required"
    assert files(tmp_path) == before


def test_latest_non_phase_endpoint_refuses_ceremony_but_override_works(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, state = seed(tmp_path, ["1.2", "2.2", "1.1"])
    store = FileProgressStore(state)
    store.append_completion(
        LOCAL_LEARNER,
        "workbench",
        CompletionEntry(
            coordinate="1.1",
            title="first",
            completed_at=datetime(2024, 1, 1, tzinfo=UTC),
            course_version="0.2.0",
        ),
    )
    monkeypatch.chdir(tmp_path)
    before = files(state)
    result = invoke("ceremony", state)
    assert result.exit_code == 4
    assert json.loads(result.stdout)["error"]["code"] == "not-a-phase-boundary"
    assert files(state) == before
    assert invoke("ceremony", state, "1.2").exit_code == 0
    assert files(state) == before
    assert invoke("artifact", state).exit_code == 0


def test_later_artifact_and_workspace_relocation_preserve_chronology(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "original"
    _, state = seed(root, ["2.2", "1.2"])
    monkeypatch.chdir(root)
    log_before = (state / "workbench" / "completed.yaml").read_bytes()
    assert invoke("artifact", state, "1.2").exit_code == 0
    monkeypatch.chdir(tmp_path)
    moved = root.rename(tmp_path / "moved")
    monkeypatch.chdir(moved)
    moved_state = state_root(moved)
    result = invoke("ceremony", moved_state)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["beat"]["content"]["coordinate"] == "2.2"
    before = files(moved_state)
    assert invoke("ceremony", moved_state).exit_code == 0
    assert files(moved_state) == before
    assert (moved_state / "workbench" / "completed.yaml").read_bytes() == log_before


@pytest.mark.parametrize("corruption", ["wrong-course", "unknown-completed", "wrong-learner"])
@pytest.mark.parametrize("verb", ["ceremony", "artifact"])
def test_record_stream_and_completed_membership_are_validated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
    verb: str,
) -> None:
    import yaml

    _, state = seed(tmp_path, ["1.2", "2.2"])
    monkeypatch.chdir(tmp_path)
    path = state / "workbench" / "record.yaml"
    data = yaml.safe_load(path.read_text())
    if corruption == "wrong-course":
        data["course_id"] = "another-course"
    elif corruption == "wrong-learner":
        data["learner_id"] = "another-learner"
    else:
        data["completed"].append("9.9")
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    before = files(state)
    result = invoke(verb, state, "1.2")
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"] == "chronology-invalid"
    assert files(state) == before


def test_equal_legacy_duplicates_are_read_without_repair(tmp_path: Path) -> None:
    from skilling.delivery import completed_coordinate

    course, state = seed(tmp_path, ["1.2", "2.2"])
    store = FileProgressStore(state)
    log = store.get_log(LOCAL_LEARNER, course.id)
    store.append_completion(LOCAL_LEARNER, course.id, log[0])
    found = store.get_record(LOCAL_LEARNER, course.id)
    assert found is not None
    before = files(state)
    assert completed_coordinate(course, found[0], store.get_log(LOCAL_LEARNER, course.id)) == "1.2"
    assert files(state) == before


@pytest.mark.parametrize("fault_kind", ["error", "exit"])
@pytest.mark.parametrize("boundary", ["log", "record", "committed"])
def test_interrupted_completion_recovery_and_receipt_retry_preserve_chronology(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    fault_kind: str,
) -> None:
    from skilling.delivery import complete_lesson
    from skilling.store import _journal

    from .recovery_worker import boundary_for

    course, state = seed(tmp_path, ["1.2", "2.2"])
    store = FileProgressStore(state)
    found = store.get_record(LOCAL_LEARNER, course.id)
    assert found is not None
    record, revision = found
    lesson = course.lesson_at("2.1")
    assert lesson is not None
    original_write = _journal._write_bytes_atomic

    def interrupted(path: Path, data: bytes) -> None:
        if boundary_for(path, data) == boundary:
            raise OSError("synthetic interruption")
        original_write(path, data)

    moment = datetime(2024, 8, 3, tzinfo=UTC)
    if fault_kind == "error":
        with monkeypatch.context() as fault:
            fault.setattr(_journal, "_write_bytes_atomic", interrupted)
            with pytest.raises(OSError, match="synthetic interruption"):
                complete_lesson(store, course, record, revision, lesson, now=moment)
    else:
        worker = subprocess.run(
            [
                sys.executable,
                "-m",
                "packages.skilling.tests.recovery_worker",
                "complete",
                "--state",
                str(state),
                "--course",
                str(WORKBENCH),
                "--coordinate",
                "2.1",
                "--now",
                moment.isoformat(),
                "--exit-after",
                boundary,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert worker.returncode == 73, worker.stderr
    moved = tmp_path / "relocated"
    moved.mkdir()
    (tmp_path / ".skilling").rename(moved / ".skilling")
    (tmp_path / "artifact.txt").rename(moved / "artifact.txt")
    state = state_root(moved)
    monkeypatch.chdir(moved)
    reopened = FileProgressStore(state)
    recovered = reopened.get_record(LOCAL_LEARNER, course.id)
    assert recovered is not None
    receipt = reopened.get_completion_receipt(LOCAL_LEARNER, course.id)
    assert receipt is not None and receipt.coordinate == "2.1" and receipt.completed_at == moment
    before = files(state)
    replay = runner.invoke(
        app, ["complete", "--course", str(WORKBENCH), "--state", str(state)], catch_exceptions=False
    )
    assert replay.exit_code == 0, replay.output
    assert json.loads(replay.stdout)["already_completed"] is True
    assert files(state) == before
    added = invoke("artifact", state)
    assert added.exit_code == 0, added.output
    assert json.loads(added.stdout)["artifact"]["coordinate"] == "2.1"
    after = files(state)
    replay = runner.invoke(
        app, ["complete", "--course", str(WORKBENCH), "--state", str(state)], catch_exceptions=False
    )
    assert replay.exit_code == 0, replay.output
    assert json.loads(replay.stdout)["already_completed"] is True
    assert files(state) == after
