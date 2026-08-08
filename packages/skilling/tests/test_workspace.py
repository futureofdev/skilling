"""The workspace surface: layout, manifest, discovery, and artifacts on the record.

Everything here exercises spec/workspace.md's contract without any verb reading it yet —
the contract merges first, the verbs follow. The one rule that matters most is negative:
discovery keys on the manifest existing, so a stray legacy ``.skilling/`` state directory
is never mistaken for a workspace.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from skilling.course import Artifact, Position, Record
from skilling.store import FileProgressStore
from skilling.workspace import (
    COURSES_DIR,
    MANIFEST_NAME,
    SHOWCASE_DIR,
    SKILLING_DIR,
    STATE_DIR,
    WORKSPACE_ENV,
    WorkspaceCourse,
    WorkspaceManifest,
    courses_dir,
    find_workspace,
    load_manifest,
    manifest_path,
    save_manifest,
    showcase_dir,
    state_root,
)


def a_course(course_id: str = "hello-skilling", **kwargs) -> WorkspaceCourse:
    base = {
        "id": course_id,
        "version": "1.0.0",
        "ref": "gh:claudeacademy/hello-skilling",
        "path": f"courses/{course_id}@1.0.0",
        "showcase": f"showcase/{course_id}",
        "added_at": datetime(2026, 8, 3, 14, 31, 7, tzinfo=UTC),
    }
    return WorkspaceCourse(**{**base, **kwargs})


def make_workspace(root: Path, manifest: WorkspaceManifest | None = None) -> Path:
    save_manifest(root, manifest or WorkspaceManifest())
    return root


# ------------------------------------------------------------------------------ manifest


def test_manifest_round_trips_through_save_and_load(tmp_path: Path) -> None:
    manifest = WorkspaceManifest(courses=[a_course()])
    save_manifest(tmp_path, manifest)
    assert load_manifest(tmp_path) == manifest


def test_an_empty_manifest_is_a_workspace_with_nothing_added_yet(tmp_path: Path) -> None:
    save_manifest(tmp_path, WorkspaceManifest())
    assert load_manifest(tmp_path).courses == []


def test_an_empty_file_loads_as_an_empty_manifest(tmp_path: Path) -> None:
    """``yaml.safe_load`` of an empty document is None; that is still a workspace."""
    manifest_path(tmp_path).parent.mkdir(parents=True)
    manifest_path(tmp_path).write_text("", encoding="utf-8")
    assert load_manifest(tmp_path).courses == []


def test_loading_a_non_workspace_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path)


def test_course_lookup_by_id() -> None:
    manifest = WorkspaceManifest(courses=[a_course("hello-skilling"), a_course("workbench")])
    found = manifest.course("workbench")
    assert found is not None and found.id == "workbench"
    assert manifest.course("never-added") is None


@pytest.mark.parametrize(
    "bad_path",
    [
        "/etc/passwd",
        "courses\\hello@1.0.0",
        "../outside",
        "courses/../../outside",
        "courses//hello",
        "./courses/hello",
        "",
    ],
)
@pytest.mark.parametrize("field", ["path", "showcase"])
def test_manifest_paths_must_be_relative_posix(field: str, bad_path: str) -> None:
    """Every path is relative — a workspace gets zipped and synced, and one absolute path
    stops the folder surviving the trip. ``ref`` alone is exempt: it is provenance."""
    with pytest.raises(ValidationError):
        a_course(**{field: bad_path})


def test_ref_is_kept_verbatim_even_when_absolute() -> None:
    assert a_course(ref="/home/lena/my-course").ref == "/home/lena/my-course"


def test_course_id_and_version_are_validated() -> None:
    with pytest.raises(ValidationError):
        a_course("Not A Slug")
    with pytest.raises(ValidationError):
        a_course(version="one point oh")


# -------------------------------------------------------------------------------- layout


def test_layout_helpers_agree_with_the_specified_tree(tmp_path: Path) -> None:
    ws = tmp_path
    assert manifest_path(ws) == ws / SKILLING_DIR / MANIFEST_NAME
    assert state_root(ws) == ws / SKILLING_DIR / STATE_DIR
    assert courses_dir(ws) == ws / SKILLING_DIR / COURSES_DIR
    assert showcase_dir(ws, "hello-skilling") == ws / SHOWCASE_DIR / "hello-skilling"


def test_state_and_content_are_disjoint_subtrees(tmp_path: Path) -> None:
    """``state/<course-id>/`` and ``courses/<id>@<version>/`` can never collide — the
    structural fix for course-id collisions, worth asserting rather than assuming."""
    assert state_root(tmp_path) != courses_dir(tmp_path)
    assert not state_root(tmp_path).is_relative_to(courses_dir(tmp_path))
    assert not courses_dir(tmp_path).is_relative_to(state_root(tmp_path))


def test_showcase_dir_refuses_a_non_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        showcase_dir(tmp_path, "../escape")


def test_the_state_root_serves_a_conforming_file_store(tmp_path: Path) -> None:
    """``.skilling/state`` is a ``<state-root>`` per spec/runtime.md#the-file-layout —
    re-pointed, not forked, so the existing store works there unchanged."""
    store = FileProgressStore(state_root(tmp_path))
    store.put_record(a_record(), None)
    assert (state_root(tmp_path) / "hello-skilling" / "record.yaml").is_file()


# ----------------------------------------------------------------------------- discovery


def test_discovery_walks_up_to_the_nearest_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)
    root = make_workspace(tmp_path / "mycourses")
    nested = root / "showcase" / "hello-skilling" / "deep"
    nested.mkdir(parents=True)
    assert find_workspace(nested) == root
    assert find_workspace(root) == root


def test_the_nearest_workspace_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)
    outer = make_workspace(tmp_path / "outer")
    inner = make_workspace(outer / "inner")
    below = inner / "below"
    below.mkdir()
    assert find_workspace(below) == inner
    assert find_workspace(outer) == outer


def test_no_manifest_anywhere_means_no_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)
    lonely = tmp_path / "just-a-directory"
    lonely.mkdir()
    assert find_workspace(lonely) is None


def test_a_bare_skilling_dir_is_not_a_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Discovery keys on the manifest existing — a stray legacy cwd-relative state
    directory must never be mistaken for a workspace."""
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)
    legacy = tmp_path / "old-project"
    (legacy / SKILLING_DIR / STATE_DIR / "some-course").mkdir(parents=True)
    assert find_workspace(legacy) is None


def test_env_var_overrides_the_start_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_workspace(tmp_path / "mycourses")
    inside = root / "showcase"
    inside.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv(WORKSPACE_ENV, str(inside))
    assert find_workspace(elsewhere) == root, "the env var wins over the passed start"


def test_start_defaults_to_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)
    root = make_workspace(tmp_path / "mycourses")
    monkeypatch.chdir(root)
    assert find_workspace() == root


# ----------------------------------------------------------------- artifacts on the record


def an_artifact(**kwargs) -> Artifact:
    base = {
        "path": "showcase/hello-skilling/first-page/index.html",
        "title": "My first page",
        "coordinate": "1.3",
        "added_at": datetime(2026, 8, 3, 14, 31, 7, tzinfo=UTC),
    }
    return Artifact(**{**base, **kwargs})


def a_record(**kwargs) -> Record:
    base = {
        "learner_id": "local",
        "course_id": "hello-skilling",
        "course_version": "1.0.0",
        "spec_version": "1.4",
        "position": Position(phase=1, lesson=1),
        "started_at": date(2026, 8, 3),
        "last_activity": date(2026, 8, 3),
    }
    return Record(**{**base, **kwargs})


def test_a_record_with_artifacts_round_trips_through_the_file_store(tmp_path: Path) -> None:
    store = FileProgressStore(state_root(tmp_path))
    record = a_record(artifacts=[an_artifact()])
    store.put_record(record, None)

    found = store.get_record("local", "hello-skilling")
    assert found is not None
    stored, _ = found
    assert stored == record
    assert stored.artifacts[0].path == "showcase/hello-skilling/first-page/index.html"


def test_an_older_record_without_the_field_still_loads() -> None:
    """``artifacts`` is additive — a 1.0..1.3 record deserialises unchanged."""
    data = a_record().model_dump(mode="json")
    del data["artifacts"]
    assert Record.model_validate(data).artifacts == []


def test_artifact_paths_obey_the_workspace_path_rule() -> None:
    with pytest.raises(ValidationError):
        an_artifact(path="/absolute/index.html")
    with pytest.raises(ValidationError):
        an_artifact(path="showcase/../../escape")


def test_artifact_coordinates_are_coordinates() -> None:
    with pytest.raises(ValidationError):
        an_artifact(coordinate="phase one")
