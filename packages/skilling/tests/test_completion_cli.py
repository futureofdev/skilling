"""Completion CLI recovery using real subprocesses and disposable learner state.

Seeded legal positions are mechanical fixtures, not evidence of learner/host delivery.
These tests use the real calendar on Linux/macOS; they are not storage_native tests.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from rich.text import Text

from skilling.course import CompletionEntry, Course, Position, Record
from skilling.store import FileProgressStore
from skilling.workspace import state_root

from .conftest import REPO_ROOT

NOW = datetime(2026, 8, 3, 23, 59, 59, tzinfo=UTC)


def _cli(
    cwd: Path,
    args: list[str],
    *,
    prefix: str = "",
    now: datetime = NOW,
    force_color: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("SKILLING_")
        and key not in {"FORCE_COLOR", "CLICOLOR", "CLICOLOR_FORCE", "NO_COLOR"}
    }
    env.update(
        HOME=str(cwd / "unused-home"),
        SKILLING_CACHE_DIR=str(cwd / "unused-cache"),
        SKILLING_NOW=now.isoformat(),
    )
    if force_color:
        env["FORCE_COLOR"] = "1"
    return subprocess.run(
        [sys.executable, "-c", prefix + "\nfrom skilling.cli import main\nmain()\n", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _body(result: subprocess.CompletedProcess[str], expected: int = 0) -> dict:
    assert result.returncode == expected, result.stdout + result.stderr
    assert len(result.stdout.splitlines()) == 1, result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    body = json.loads(result.stdout)
    assert body["ok"] is (expected == 0)
    return body


def _args(verb: str, course: Course, state: Path, learner: str = "local") -> list[str]:
    return [verb, "--course", str(course.root), "--state", str(state), "--learner", learner]


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and path.name != ".skilling.lock"
    }


def _seed(
    state: Path, course: Course, coordinate: str = "1.2", learner: str = "local"
) -> FileProgressStore:
    """Seed a legal completion beat, preserving no claim about how a human reached it."""
    store = FileProgressStore(state)
    lesson = course.lesson_at(coordinate)
    assert lesson is not None
    previous = list(course.coordinates[: course.coordinates.index(coordinate)])
    record = Record(
        learner_id=learner,
        course_id=course.id,
        course_version=course.version,
        spec_version="1.4",
        position=Position(phase=lesson.phase, lesson=lesson.number, beat="complete"),
        completed=previous,
        started_at=date(2026, 8, 2),
        last_activity=date(2026, 8, 2),
        streak_days=2,
        timezone="UTC",
    )
    found = store.get_record(learner, course.id)
    revision = store.put_record(record, found[1] if found else None)
    for old in previous:
        store.append_completion(
            learner,
            course.id,
            CompletionEntry(
                coordinate=old,
                title=old,
                completed_at=NOW - timedelta(days=1),
                course_version=course.version,
            ),
        )
    store.write_runtime_state(
        course.id,
        b"wrong_count: 2\nreturning_to_quiz: true\nlast_key: old-key\nlast_result: {}\n",
        revision,
    )
    return store


@pytest.fixture
def workbench() -> Course:
    return Course.load(REPO_ROOT / "examples" / "workbench")


def _complete_phase(tmp_path: Path, course: Course) -> FileProgressStore:
    store = _seed(tmp_path / "state", course)
    first = _body(_cli(tmp_path, _args("complete", course, store.state_root)))
    assert first["already_completed"] is False
    assert first["phase_completed"] == 1
    assert first["homework_placed"] is True
    assert first["position"] == {
        "phase": 2,
        "lesson": 1,
        "beat": None,
        "question_index": None,
    }
    return store


def test_recovery_cli_targets_previous_phase_after_position_advances(
    tmp_path: Path, workbench: Course
) -> None:
    store = _complete_phase(tmp_path, workbench)
    receipt = store.get_completion_receipt("local", workbench.id)
    assert receipt and receipt.coordinate == "1.2" and receipt.completed_at == NOW
    assert store.read_runtime_state(workbench.id) == b""
    before = _snapshot(store.state_root)
    retry = _body(
        _cli(
            tmp_path,
            _args("complete", workbench, store.state_root),
            now=NOW + timedelta(days=1),
        )
    )
    assert retry["already_completed"] is True
    assert retry["position"]["phase"] == 2 and retry["position"]["lesson"] == 1
    assert retry["badges_awarded"] == []
    assert not retry["homework_placed"] and not retry["homework_queued"]
    assert _snapshot(store.state_root) == before
    slot, _ = store.get_homework("local", workbench.id)
    assert slot and slot.coordinate == "1.2" and slot.unlocked_at == NOW
    assert len(store.get_log("local", workbench.id)) == 2


def test_recovery_cli_does_not_use_completed_list_order(tmp_path: Path, workbench: Course) -> None:
    store = _complete_phase(tmp_path, workbench)
    found = store.get_record("local", workbench.id)
    assert found
    store.put_record(found[0].model_copy(update={"completed": ["1.2", "1.1"]}), found[1])
    before = _snapshot(store.state_root)
    # Observe only target selection; the wrapper delegates all actual persistence/replay.
    prefix = (
        "from skilling.cli.runtime import _session\n"
        "original = _session.complete_lesson\n"
        "def checked(store, course, record, revision, lesson, **kwargs):\n"
        "    assert lesson.coordinate == '1.2', lesson.coordinate\n"
        "    return original(store, course, record, revision, lesson, **kwargs)\n"
        "_session.complete_lesson = checked\n"
    )
    body = _body(_cli(tmp_path, _args("complete", workbench, store.state_root), prefix=prefix))
    assert body["already_completed"] is True
    assert _snapshot(store.state_root) == before


def test_recovery_cli_replay_returns_current_revision_and_preserves_later_write(
    tmp_path: Path, workbench: Course
) -> None:
    store = _complete_phase(tmp_path, workbench)
    found = store.get_record("local", workbench.id)
    assert found
    revised = found[0].model_copy(update={"timezone": "Etc/UTC"})
    revision = store.put_record(revised, found[1])
    assert revision != found[1]
    before = _snapshot(store.state_root)
    body = _body(_cli(tmp_path, _args("complete", workbench, store.state_root)))
    assert body["already_completed"] and body["revision"] == revision
    assert _snapshot(store.state_root) == before
    assert store.get_record("local", workbench.id) == (revised, revision)


@pytest.mark.parametrize(
    "beat", ["objectives", "gate-concept", "gate-exercise", "quiz", "remediate"]
)
def test_recovery_receipt_does_not_mask_incomplete_next_lesson(
    tmp_path: Path, workbench: Course, beat: str
) -> None:
    store = _complete_phase(tmp_path, workbench)
    found = store.get_record("local", workbench.id)
    assert found
    position = Position(
        phase=2, lesson=1, beat=beat, question_index=0 if beat in {"quiz", "remediate"} else None
    )
    store.put_record(found[0].model_copy(update={"position": position}), found[1])
    before = _snapshot(store.state_root)
    body = _body(_cli(tmp_path, _args("complete", workbench, store.state_root)), 4)
    assert body["error"]["code"] == "illegal-transition"
    assert _snapshot(store.state_root) == before


def test_recovery_cli_new_completion_wins_over_old_receipt(
    tmp_path: Path, workbench: Course
) -> None:
    store = _complete_phase(tmp_path, workbench)
    found = store.get_record("local", workbench.id)
    assert found
    old_slot = store.get_homework("local", workbench.id)
    store.put_record(
        found[0].model_copy(update={"position": Position(phase=2, lesson=1, beat="complete")}),
        found[1],
    )
    body = _body(_cli(tmp_path, _args("complete", workbench, store.state_root)))
    assert body["already_completed"] is False
    assert body["position"]["phase"] == 2 and body["position"]["lesson"] == 2
    assert store.get_homework("local", workbench.id) == old_slot
    receipt = store.get_completion_receipt("local", workbench.id)
    assert receipt and receipt.coordinate == "2.1"
    assert [entry.coordinate for entry in store.get_log("local", workbench.id)] == [
        "1.1",
        "1.2",
        "2.1",
    ]


def test_recovery_legacy_cli_replay_is_noop_without_tail_guess(
    tmp_path: Path, workbench: Course
) -> None:
    store = _seed(tmp_path / "state", workbench)
    found = store.get_record("local", workbench.id)
    assert found
    store.put_record(
        found[0].model_copy(
            update={"completed": ["1.2", "1.1"], "position": Position(phase=2, lesson=1)}
        ),
        found[1],
    )
    before = _snapshot(store.state_root)
    prefix = (
        "from skilling.cli.runtime import _session\n"
        "def no_guessed_target(*args, **kwargs):\n"
        "    raise AssertionError('legacy replay must not choose a lesson target')\n"
        "_session.complete_lesson = no_guessed_target\n"
    )
    body = _body(_cli(tmp_path, _args("complete", workbench, store.state_root), prefix=prefix))
    assert body["already_completed"] is True
    assert body["phase_completed"] is None and body["badges_awarded"] == []
    assert _snapshot(store.state_root) == before
    assert store.get_completion_receipt("local", workbench.id) is None
    assert store.get_homework("local", workbench.id) == (None, None)


def test_recovery_cli_receipt_must_match_the_session_snapshot(
    tmp_path: Path, workbench: Course
) -> None:
    store = _complete_phase(tmp_path, workbench)
    found = store.get_record("local", workbench.id)
    assert found
    store.put_record(found[0].model_copy(update={"completed": ["1.1"]}), found[1])
    before = _snapshot(store.state_root)
    body = _body(_cli(tmp_path, _args("complete", workbench, store.state_root)), 1)
    assert body["error"]["code"] == "recovery-required"
    assert _snapshot(store.state_root) == before


@pytest.mark.parametrize("metadata", ["invalid-yaml", "unknown-version", "directory"])
@pytest.mark.parametrize("verb", ["next", "complete"])
def test_recovery_cli_invalid_metadata_is_one_error_without_writes(
    tmp_path: Path, example: Course, metadata: str, verb: str
) -> None:
    store = _seed(tmp_path / "state", example, "1.3")
    path = store.course_dir(example.id) / "completion.yaml"
    if metadata == "directory":
        path.mkdir()
        (path / "sentinel").write_bytes(b"preserve unexpected metadata directory")
    else:
        path.write_bytes(
            b"[unterminated" if metadata == "invalid-yaml" else b"version: 999\nkind: prepared\n"
        )
    before = _snapshot(store.state_root)
    body = _body(_cli(tmp_path, _args(verb, example, store.state_root)), 1)
    assert body["error"]["code"] == "recovery-required"
    assert _snapshot(store.state_root) == before
    assert path.is_dir() if metadata == "directory" else path.is_file()


def test_recovery_cli_legacy_log_divergence_is_controlled_and_preserved(
    tmp_path: Path, example: Course
) -> None:
    store = _seed(tmp_path / "state", example, "1.3")
    store.append_completion(
        "local",
        example.id,
        CompletionEntry(
            coordinate="1.3", title="legacy", completed_at=NOW, course_version=example.version
        ),
    )
    before = _snapshot(store.state_root)
    body = _body(_cli(tmp_path, _args("complete", example, store.state_root)), 1)
    assert body["error"]["code"] == "recovery-required"
    assert "legacy" in body["error"]["message"]
    assert _snapshot(store.state_root) == before


@pytest.mark.parametrize("origin", ["unsupported-backend", "main-boundary"])
def test_recovery_cli_not_supported_is_controlled_before_effects(
    tmp_path: Path, example: Course, origin: str
) -> None:
    store = _seed(tmp_path / "state", example, "1.3")
    before = _snapshot(store.state_root)
    if origin == "unsupported-backend":
        prefix = (
            "from skilling.store import FileProgressStore\n"
            "del FileProgressStore.commit_completion\n"
            "del FileProgressStore.get_completion_receipt\n"
        )
    else:
        prefix = (
            "from skilling.cli.runtime import _common\n"
            "from skilling.store import NotSupported\n"
            "def unsupported(*args, **kwargs):\n"
            "    raise NotSupported('upgrade backend completion support')\n"
            "_common.open_store = unsupported\n"
        )
    body = _body(_cli(tmp_path, _args("complete", example, store.state_root), prefix=prefix), 1)
    assert body["error"]["code"] == "completion-not-supported"
    assert "upgrade" in body["error"]["message"]
    assert _snapshot(store.state_root) == before


def test_recovery_cli_nondefault_learner_complete_read_and_retry(
    tmp_path: Path, example: Course
) -> None:
    state = tmp_path / "state"
    _body(_cli(tmp_path, _args("next", example, state, "alice")))
    store = _seed(state, example, "1.3", "alice")
    first = _body(_cli(tmp_path, _args("complete", example, state, "alice")))
    assert first["already_completed"] is False and first["homework_placed"] is True
    before = _snapshot(state)
    for verb in ("next", "progress", "complete"):
        body = _body(_cli(tmp_path, _args(verb, example, state, "alice")))
        assert body["revision"] == first["revision"]
        if verb == "complete":
            assert body["already_completed"] is True
    assert _snapshot(state) == before
    found = store.get_record("alice", example.id)
    receipt = store.get_completion_receipt("alice", example.id)
    assert found and found[0].learner_id == "alice"
    assert receipt and receipt.learner_id == "alice"


def test_recovery_pending_intent_survives_workspace_relocation(tmp_path: Path) -> None:
    source = tmp_path / "source-copy"
    shutil.copytree(REPO_ROOT / "examples" / "workbench", source)
    workspace = tmp_path / "workspace-before"
    started = _cli(tmp_path, ["start", str(source), str(workspace), "--json"])
    assert started.returncode == 0, started.stdout + started.stderr
    assert json.loads(started.stdout)["ok"] is True
    course = Course.load(workspace / ".skilling" / "courses" / "workbench@1.0.0")
    store = _seed(state_root(workspace), course)
    artifact_path = workspace / "showcase" / "workbench" / "audit.txt"
    artifact_path.write_bytes(b"Disposable mechanical relocation artifact.\n")
    artifact = _body(
        _cli(
            workspace,
            [
                "artifact",
                "add",
                str(artifact_path),
                "--title",
                "Relocation fixture",
                "--course",
                "workbench",
                "--coordinate",
                "1.1",
            ],
        )
    )["artifact"]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "packages.skilling.tests.recovery_worker",
            "complete",
            "--state",
            str(store.state_root),
            "--course",
            str(course.root),
            "--coordinate",
            "1.2",
            "--now",
            NOW.isoformat(),
            "--exit-after",
            "prepared",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 73, result.stdout + result.stderr
    journal = store.course_dir(course.id) / "completion.yaml"
    pending = yaml.safe_load(journal.read_bytes())
    assert pending["kind"] == "prepared"
    assert str(workspace) not in repr(pending)
    destination = tmp_path / "workspace-after"
    workspace.rename(destination)
    shutil.rmtree(source)
    nested = destination / "showcase" / "workbench" / "nested"
    nested.mkdir()
    assert not workspace.exists() and not source.exists()
    courses = _body(_cli(nested, ["courses"]))
    assert courses["courses"][0]["id"] == "workbench"
    assert Path(courses["courses"][0]["path"]).is_relative_to(destination)
    next_body = _body(_cli(nested, ["next", "--course", "workbench"]))
    assert next_body["position"]["phase"] == 2 and next_body["position"]["lesson"] == 1
    progress = _body(_cli(nested, ["progress", "--course", "workbench"]))
    assert progress["completed"] == ["1.1", "1.2"]
    assert progress["last_activity"] == NOW.date().isoformat() and progress["streak_days"] == 3
    homework = _body(_cli(nested, ["homework", "check", "--course", "workbench"]))
    assert homework["active"]["coordinate"] == "1.2" and homework["active"]["queued"] == []
    assert homework["active"]["unlocked_at"] == NOW.isoformat().replace("+00:00", "Z")
    listed = _body(_cli(nested, ["artifact", "list", "--course", "workbench"]))
    assert listed["artifacts"] == [artifact]
    assert (
        destination / artifact["path"]
    ).read_bytes() == b"Disposable mechanical relocation artifact.\n"
    moved_store = FileProgressStore(state_root(destination))
    assert [entry.coordinate for entry in moved_store.get_log("local", "workbench")] == [
        "1.1",
        "1.2",
    ]
    receipt = moved_store.get_completion_receipt("local", "workbench")
    assert receipt and receipt.coordinate == "1.2" and receipt.completed_at == NOW
    assert moved_store.read_runtime_state("workbench") == b""
    before = _snapshot(moved_store.state_root)
    retry = _body(_cli(nested, ["complete", "--course", "workbench"], now=NOW + timedelta(days=1)))
    assert retry["already_completed"] and retry["revision"] == progress["revision"]
    assert _snapshot(moved_store.state_root) == before
    assert all(str(workspace).encode() not in data for data in before.values())


@pytest.mark.parametrize("failure", ["recovery-required", "completion-not-supported"])
@pytest.mark.parametrize("force_color", [False, True])
def test_recovery_walker_errors_do_not_announce_completion(
    tmp_path: Path, example: Course, failure: str, force_color: bool
) -> None:
    store = _seed(tmp_path / "state", example, "1.3")
    prefix = ""
    if failure == "recovery-required":
        store.append_completion(
            "local",
            example.id,
            CompletionEntry(
                coordinate="1.3",
                title="legacy",
                completed_at=NOW,
                course_version=example.version,
            ),
        )
    else:
        prefix = (
            "from skilling.store import FileProgressStore\n"
            "del FileProgressStore.commit_completion\n"
            "del FileProgressStore.get_completion_receipt\n"
        )
    before = _snapshot(store.state_root)
    result = _cli(
        tmp_path,
        ["deliver", str(example.root), "--state", str(store.state_root)],
        prefix=prefix,
        force_color=force_color,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert failure in Text.from_ansi(result.stderr).plain
    output = Text.from_ansi(result.stdout).plain
    assert example.manifest.title in output, "Walker.run must start before completion fails"
    for announcement in (
        "Lesson complete:",
        "Badge earned:",
        "Phase 1 complete",
        "Course complete.",
    ):
        assert announcement not in output
    assert "Traceback" not in result.stderr
    assert _snapshot(store.state_root) == before
