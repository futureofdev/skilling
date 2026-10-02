"""Public file session safety and state custody, using actual file operations."""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from skilling.course import Course, Record
from skilling.session import FileSession, SessionRefusal, VersionMismatch, load_course
from skilling.store import FileProgressStore, RecoveryRequired

from . import fixtures as fx
from .test_cli_quiz import WALK_TO_QUIZ
from .test_state_paths import file_alias
from .test_state_paths import snapshot as raw_snapshot


def snapshot(root: Path) -> dict[str, bytes]:
    # Lock files are coordination metadata, not learner content or initialization.
    return {
        name: data
        for name, data in raw_snapshot(root).items()
        if not name.endswith(".skilling.lock")
    }


def open_session(course: Path, state: Path, *, initialize: bool = True) -> FileSession:
    return FileSession.open(
        load_course(course), state_root=state, learner_id="local", initialize=initialize
    )


def test_read_only_first_use_and_explicit_configuration(
    clean_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = tmp_path / "state"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SKILLING_STATE_ROOT", str(tmp_path / "ignored"))
    service = open_session(clean_dir, state, initialize=False)
    assert service.snapshot().revision is None
    assert not state.exists()
    with pytest.raises(SessionRefusal, match="initialize"):
        service.advance("next")
    assert not state.exists()
    initialized = open_session(clean_dir, state)
    assert initialized.snapshot().revision is not None
    assert not (tmp_path / "ignored").exists()
    monkeypatch.chdir(clean_dir)
    assert initialized.advance("next").snapshot.beat.name == "objectives"


def test_operations_reload_and_key_replay_returns_current_snapshot(
    clean_dir: Path,
    tmp_path: Path,
) -> None:
    first = open_session(clean_dir, tmp_path / "state")
    second = open_session(clean_dir, tmp_path / "state")
    accepted = first.advance("next", event_id="one")
    assert accepted.replayed is False
    second.advance("next", event_id="two")
    before = snapshot(tmp_path / "state")
    replay = first.advance("next", event_id="one")
    assert replay.replayed is True
    assert replay.snapshot.beat.name == "concept"
    assert replay.snapshot == second.snapshot()
    with pytest.raises(SessionRefusal) as conflict:
        first.advance("deeper", event_id="one")
    assert conflict.value.code == "idempotency-key-conflict"
    assert snapshot(tmp_path / "state") == before


def test_safe_views_are_copied_and_withhold_future_and_answer_material(
    clean_dir: Path,
    tmp_path: Path,
) -> None:
    lesson = clean_dir / fx.LESSON_ONE_PATH
    lesson.write_text(
        lesson.read_text()
        .replace("it has exactly one use.", "FUTURE_REASON_SENTINEL")
        .replace("When would you reach for it?", "FUTURE_QUESTION_SENTINEL")
    )
    future = clean_dir / fx.LESSON_TWO_PATH
    future.write_text(
        future.read_text().replace("The second thing builds", "FUTURE_BODY_SENTINEL builds")
    )
    service = open_session(clean_dir, tmp_path / "state")
    for given in WALK_TO_QUIZ:
        service.advance(given, event_id="PRIVATE_EVENT_SENTINEL" if given == "attempted" else None)
    view = service.snapshot()
    question = service.question()
    serialized = json.dumps(dataclasses.asdict(view)) + json.dumps(dataclasses.asdict(question))
    for secret in (
        "FUTURE_REASON_SENTINEL",
        "FUTURE_QUESTION_SENTINEL",
        "FUTURE_BODY_SENTINEL",
        "PRIVATE_EVENT_SENTINEL",
        "answer_label",
        "answer_reason",
        "record.yaml",
        str(clean_dir),
        str(tmp_path / "state"),
        "because that is what the concept described",
    ):
        assert secret not in serialized
    assert not hasattr(view, "store") and not hasattr(view, "record")
    assert not hasattr(question, "answer_label")
    with pytest.raises(dataclasses.FrozenInstanceError):
        question.text = "changed"  # type: ignore[misc]
    content = view.beat.content()
    content["text"] = "changed"
    assert service.snapshot().beat.question == question
    feedback = service.answer(" B ")
    assert feedback.correct
    assert "because that is what the concept described" in feedback.reason
    assert "FUTURE" not in json.dumps(dataclasses.asdict(feedback))
    record = yaml.safe_load((tmp_path / "state" / "clean-course" / "record.yaml").read_bytes())
    assert record["objectives_met"] == []


@pytest.mark.parametrize(
    "version,resumable,reason", [("1.0.1", True, None), ("2.0.0", False, "major")]
)
def test_version_mismatch_never_writes(
    clean_dir: Path,
    tmp_path: Path,
    version: str,
    resumable: bool,
    reason: str | None,
) -> None:
    state = tmp_path / "state"
    service = open_session(clean_dir, state)
    service.advance("next")
    before = snapshot(state)
    manifest = clean_dir / "course.yaml"
    manifest.write_text(manifest.read_text().replace('version: "1.0.0"', f'version: "{version}"'))
    with pytest.raises(VersionMismatch) as refusal:
        open_session(clean_dir, state)
    assert refusal.value.from_version == "1.0.0"
    assert refusal.value.to_version == version
    assert refusal.value.resumable is resumable
    assert refusal.value.reason == reason
    assert snapshot(state) == before


def test_wrong_learner_stream_is_refused_without_writes(clean_dir: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    open_session(clean_dir, state)
    before = snapshot(state)
    with pytest.raises(RecoveryRequired, match="stream mismatch"):
        FileSession.open(load_course(clean_dir), state_root=state, learner_id="another")
    assert snapshot(state) == before


@pytest.mark.parametrize(
    "damage", ["sequence", "negative", "bool-count", "string-bool", "yaml", "utf8"]
)
def test_corrupt_scratch_refuses_before_writes(
    clean_dir: Path,
    tmp_path: Path,
    damage: str,
) -> None:
    state = tmp_path / "state"
    open_session(clean_dir, state)
    values = {
        "sequence": b"[1,2]",
        "negative": b"wrong_count: -1",
        "bool-count": b"wrong_count: true",
        "string-bool": b"returning_to_quiz: 'false'",
        "yaml": b"[unfinished",
        "utf8": b"\xff",
    }
    (state / "clean-course" / "scratch.yaml").write_bytes(values[damage])
    before = snapshot(state)
    with pytest.raises(RecoveryRequired):
        open_session(clean_dir, state)
    assert snapshot(state) == before


def test_corrupt_or_unsafe_paths_do_not_initialize(clean_dir: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    directory = state / "clean-course"
    directory.mkdir(parents=True)
    scratch = directory / "scratch.yaml"
    scratch.write_bytes(b"wrong_count: -1")
    before = snapshot(tmp_path)
    with pytest.raises(RecoveryRequired):
        open_session(clean_dir, state)
    assert snapshot(tmp_path) == before
    scratch.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(b"sentinel")
    file_alias(scratch, outside)
    before = snapshot(tmp_path)
    with pytest.raises(SessionRefusal) as refusal:
        open_session(clean_dir, state)
    assert refusal.value.code == "state-invalid"
    assert snapshot(tmp_path) == before


def test_explicit_loading_and_backend_refusal(clean_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(SessionRefusal, match="absolute"):
        load_course(Path("clean-course"))
    with pytest.raises(SessionRefusal, match="outside workspace"):
        load_course(clean_dir, workspace_root=tmp_path / "elsewhere")
    with pytest.raises(SessionRefusal) as refusal:
        FileSession.open(
            load_course(clean_dir), state_root=Path("postgres://host"), learner_id="local"
        )
    assert refusal.value.code == "backend-unsupported"
    assert not (tmp_path / "state").exists()


def test_wrong_course_directory_stream_and_invalid_course_are_refused(
    clean_dir: Path,
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    store = FileProgressStore(state)
    record = Record.new(Course.load(clean_dir), "local")
    store.put_record(record, None)
    path = state / "clean-course" / "record.yaml"
    path.write_bytes(
        path.read_bytes().replace(b"course_id: clean-course", b"course_id: other-course")
    )
    before = snapshot(state)
    with pytest.raises(RecoveryRequired, match="stream mismatch"):
        open_session(clean_dir, state)
    assert snapshot(state) == before
    manifest = clean_dir / "course.yaml"
    manifest.write_text(manifest.read_text().replace("id: clean-course", "id: ../escaped"))
    with pytest.raises(SessionRefusal):
        load_course(clean_dir)
    assert snapshot(state) == before


def test_core_import_does_not_load_framework_or_cli() -> None:
    code = """import sys
from skilling.session import FileSession, SessionSnapshot
assert FileSession and SessionSnapshot
assert not any(name.startswith(('pydantic_ai', 'skilling.cli', 'typer')) for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
