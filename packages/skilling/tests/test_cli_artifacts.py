"""Tests for ``artifact add``/``artifact list``, and the ``showcase`` key ``ceremony`` gains
inside a workspace (spec/workspace.md#artifacts).

Records are written straight through ``FileProgressStore`` for setup — matching
``test_cli_courses.py``'s convention — rather than driven through a full ``advance``/``complete``
walk, since that walk is ``test_cli_runtime.py``'s own dependency surface, not this module's.
Every ``artifact add`` test puts the current directory somewhere inside the workspace, because
discovery (``find_workspace``) walks up from the cwd, exactly as ``test_workspace.py`` exercises
it directly.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skilling.cli import app
from skilling.course import Position, Record
from skilling.store import LOCAL_LEARNER, Conflict, FileProgressStore
from skilling.workspace import (
    SKILLING_DIR,
    WORKSPACE_ENV,
    WorkspaceCourse,
    WorkspaceManifest,
    save_manifest,
    state_root,
)

from . import fixtures as fx

runner = CliRunner()


def run(args: list[str], tmp: Path | None = None):
    full = [*args, "--state", str(tmp)] if tmp is not None else list(args)
    return runner.invoke(app, full, catch_exceptions=False)


@pytest.fixture(autouse=True)
def _no_ambient_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Discovery keys on the cwd; scrub the env override so nothing outside this test's own
    setup can make ``find_workspace`` see (or fail to see) a workspace."""
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty workspace, with the cwd already inside it — the baseline every ``add`` test
    needs, since discovery walks up from wherever the process actually stands."""
    root = tmp_path / "workspace"
    save_manifest(root, WorkspaceManifest())
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def course_dir(workspace: Path) -> Path:
    """The clean-course fixture, written directly under the workspace root."""
    return fx.build(workspace / "clean-course")


def _write_record(root: Path, course_id: str = "clean-course", **overrides) -> None:
    """Seed a record as if 0.1 and 0.2 (clean-course's whole first phase) were already
    completed, positioned at 1.1 — the same place ``advance``/``complete`` would leave it."""
    base = {
        "learner_id": LOCAL_LEARNER,
        "course_id": course_id,
        "course_version": "1.0.0",
        "spec_version": "1.4",
        "position": Position(phase=1, lesson=1),
        "completed": ["0.1", "0.2"],
        "started_at": date(2026, 8, 3),
        "last_activity": date(2026, 8, 3),
    }
    record = Record(**{**base, **overrides})
    FileProgressStore(root).put_record(record, None)


def _write_artifact_file(
    workspace: Path, relative: str = "showcase/clean-course/index.html"
) -> Path:
    path = workspace / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<html></html>", encoding="utf-8")
    return path


def _manifest_course(real_dir: Path, workspace: Path, course_id: str) -> WorkspaceCourse:
    return WorkspaceCourse(
        id=course_id,
        version="1.0.0",
        ref="local",
        path=real_dir.relative_to(workspace / SKILLING_DIR).as_posix(),
        showcase=f"showcase/{course_id}",
        added_at=datetime(2026, 8, 3, 14, 31, 7, tzinfo=UTC),
    )


# --------------------------------------------------------------------------------------- add


def test_add_records_a_workspace_relative_path_from_a_subdirectory(
    workspace: Path, course_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = state_root(workspace)
    _write_record(state)
    artifact_file = _write_artifact_file(workspace)

    monkeypatch.chdir(course_dir)  # a workspace subdirectory, not the root
    result = run(
        [
            "artifact",
            "add",
            str(artifact_file),
            "--title",
            "My first page",
            "--course",
            str(course_dir),
        ],
        state,
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["ok"] is True
    assert body["verb"] == "artifact-add"
    assert body["artifact"]["path"] == "showcase/clean-course/index.html"
    assert body["artifact"]["title"] == "My first page"
    assert body["artifact"]["coordinate"] == "0.2"  # record.completed[-1], not the position

    stored = FileProgressStore(state).get_record(LOCAL_LEARNER, "clean-course")
    assert stored is not None
    assert stored[0].artifacts[0].path == "showcase/clean-course/index.html"


def test_add_upserts_by_path(workspace: Path, course_dir: Path) -> None:
    state = state_root(workspace)
    _write_record(state)
    artifact_file = _write_artifact_file(workspace)
    args = ["artifact", "add", str(artifact_file), "--course", str(course_dir)]

    first = run([*args, "--title", "First title"], state)
    assert first.exit_code == 0, first.output
    second = run([*args, "--title", "Updated title"], state)
    assert second.exit_code == 0, second.output

    stored = FileProgressStore(state).get_record(LOCAL_LEARNER, "clean-course")
    assert stored is not None
    assert len(stored[0].artifacts) == 1
    assert stored[0].artifacts[0].title == "Updated title"


def test_add_with_an_explicit_coordinate(workspace: Path, course_dir: Path) -> None:
    state = state_root(workspace)
    _write_record(state)
    artifact_file = _write_artifact_file(workspace)

    result = run(
        [
            "artifact",
            "add",
            str(artifact_file),
            "--title",
            "T",
            "--course",
            str(course_dir),
            "--coordinate",
            "0.1",
        ],
        state,
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["artifact"]["coordinate"] == "0.1"


def test_add_missing_path_is_refused(workspace: Path, course_dir: Path) -> None:
    state = state_root(workspace)
    _write_record(state)
    missing = workspace / "showcase" / "clean-course" / "nope.html"

    result = run(
        ["artifact", "add", str(missing), "--title", "T", "--course", str(course_dir)], state
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "artifact-missing"


def test_add_outside_the_workspace_root_is_refused(
    workspace: Path, course_dir: Path, tmp_path: Path
) -> None:
    state = state_root(workspace)
    _write_record(state)
    outside = tmp_path / "elsewhere" / "index.html"
    outside.parent.mkdir(parents=True)
    outside.write_text("x", encoding="utf-8")

    result = run(
        ["artifact", "add", str(outside), "--title", "T", "--course", str(course_dir)], state
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "artifact-outside-workspace"


def test_add_with_a_coordinate_not_in_the_course_is_refused(
    workspace: Path, course_dir: Path
) -> None:
    state = state_root(workspace)
    _write_record(state)
    artifact_file = _write_artifact_file(workspace)

    result = run(
        [
            "artifact",
            "add",
            str(artifact_file),
            "--title",
            "T",
            "--course",
            str(course_dir),
            "--coordinate",
            "9.9",
        ],
        state,
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "coordinate-unknown"


def test_add_with_nothing_completed_and_no_coordinate_is_refused(
    workspace: Path, course_dir: Path
) -> None:
    state = state_root(workspace)
    _write_record(state, completed=[], position=Position(phase=0, lesson=1))
    artifact_file = _write_artifact_file(workspace)

    result = run(
        ["artifact", "add", str(artifact_file), "--title", "T", "--course", str(course_dir)],
        state,
    )
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "coordinate-unknown"


def test_add_outside_a_workspace_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lonely = tmp_path / "just-a-directory"
    lonely.mkdir()
    monkeypatch.chdir(lonely)
    artifact_file = lonely / "index.html"
    artifact_file.write_text("x", encoding="utf-8")

    result = run(["artifact", "add", str(artifact_file), "--title", "T"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "no-workspace"


def test_add_conflict_on_race(
    workspace: Path, course_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = state_root(workspace)
    _write_record(state)
    artifact_file = _write_artifact_file(workspace)

    def _boom(self, record, expected_revision):  # noqa: ANN001
        raise Conflict("record.yaml", expected_revision, "elsewhere")

    monkeypatch.setattr(FileProgressStore, "put_record", _boom)

    result = run(
        ["artifact", "add", str(artifact_file), "--title", "T", "--course", str(course_dir)],
        state,
    )
    assert result.exit_code == 3
    assert json.loads(result.stdout)["error"]["code"] == "conflict"


def test_course_id_resolves_through_the_manifest(workspace: Path) -> None:
    real_dir = fx.build(workspace / SKILLING_DIR / "courses" / "clean-course@1.0.0")
    course = _manifest_course(real_dir, workspace, "clean-course")
    save_manifest(workspace, WorkspaceManifest(courses=[course]))
    state = state_root(workspace)
    _write_record(state)
    artifact_file = _write_artifact_file(workspace)

    result = run(
        ["artifact", "add", str(artifact_file), "--title", "T", "--course", "clean-course"], state
    )
    assert result.exit_code == 0, result.output


def test_omitted_course_defaults_to_the_workspaces_sole_course(workspace: Path) -> None:
    real_dir = fx.build(workspace / SKILLING_DIR / "courses" / "clean-course@1.0.0")
    course = _manifest_course(real_dir, workspace, "clean-course")
    save_manifest(workspace, WorkspaceManifest(courses=[course]))
    state = state_root(workspace)
    _write_record(state)
    artifact_file = _write_artifact_file(workspace)

    result = run(["artifact", "add", str(artifact_file), "--title", "T"], state)
    assert result.exit_code == 0, result.output


def test_omitted_course_with_several_workspace_courses_is_refused(workspace: Path) -> None:
    real_dir = fx.build(workspace / SKILLING_DIR / "courses" / "clean-course@1.0.0")
    entry_a = _manifest_course(real_dir, workspace, "clean-course")
    entry_b = entry_a.model_copy(update={"id": "other-course", "showcase": "showcase/other-course"})
    save_manifest(workspace, WorkspaceManifest(courses=[entry_a, entry_b]))
    artifact_file = _write_artifact_file(workspace)

    result = run(["artifact", "add", str(artifact_file), "--title", "T"], state_root(workspace))
    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "course-required"


def test_add_defaults_state_to_the_workspaces_state_root_when_omitted(
    workspace: Path, course_dir: Path
) -> None:
    """No ``--state`` at all: the interim local resolution (documented on ``_artifacts.py``)
    must find the workspace's own ``<state-root>``, not the plain ``.skilling`` every other
    verb defaults to outside a workspace."""
    _write_record(state_root(workspace))
    artifact_file = _write_artifact_file(workspace)

    result = run(
        ["artifact", "add", str(artifact_file), "--title", "T", "--course", str(course_dir)]
    )
    assert result.exit_code == 0, result.output

    stored = FileProgressStore(state_root(workspace)).get_record(LOCAL_LEARNER, "clean-course")
    assert stored is not None
    assert stored[0].artifacts[0].path == "showcase/clean-course/index.html"


# -------------------------------------------------------------------------------------- list


def test_list_enumerates_artifacts(workspace: Path, course_dir: Path) -> None:
    state = state_root(workspace)
    _write_record(state)
    artifact_file = _write_artifact_file(workspace)
    run(["artifact", "add", str(artifact_file), "--title", "T", "--course", str(course_dir)], state)

    out = json.loads(run(["artifact", "list", "--course", str(course_dir)], state).stdout)
    assert out["ok"] is True
    assert out["verb"] == "artifact-list"
    assert len(out["artifacts"]) == 1
    assert out["artifacts"][0]["title"] == "T"


def test_list_works_without_a_workspace(clean_dir: Path, tmp_path: Path) -> None:
    """``list`` reuses plain ``open_session`` — no workspace discovery of its own."""
    out = json.loads(run(["artifact", "list", "--course", str(clean_dir)], tmp_path).stdout)
    assert out == {
        "ok": True,
        "verb": "artifact-list",
        "course": {"id": "clean-course", "version": "1.0.0"},
        "artifacts": [],
    }


def test_list_is_read_only(workspace: Path, course_dir: Path) -> None:
    state = state_root(workspace)
    _write_record(state)
    before = (state / "clean-course" / "record.yaml").read_bytes()
    run(["artifact", "list", "--course", str(course_dir)], state)
    assert (state / "clean-course" / "record.yaml").read_bytes() == before


# ----------------------------------------------------------------------------- ceremony showcase


def test_ceremony_includes_showcase_inside_a_workspace(workspace: Path, course_dir: Path) -> None:
    state = state_root(workspace)
    _write_record(state)

    result = run(["ceremony", "--course", str(course_dir)], state)
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["beat"]["content"]["showcase"] == "showcase/clean-course"


def test_ceremony_omits_showcase_outside_a_workspace(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lonely = tmp_path / "no-workspace-here"
    lonely.mkdir()
    monkeypatch.chdir(lonely)
    state = tmp_path / "state"
    _write_record(state)

    result = run(["ceremony", "--course", str(clean_dir)], state)
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert "showcase" not in body["beat"]["content"]
