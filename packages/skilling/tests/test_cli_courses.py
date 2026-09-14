"""Tests for ``skilling courses``: cross-course enumeration for the skill triad's "which course
did you mean" default (docs/superpowers/specs/2026-08-06-generic-delivery-skills-design.md).

Records are written straight through ``FileProgressStore`` rather than driven through
``next``/``advance`` — those JSON transition verbs live on their own in-flight branches and are
not part of this command's dependency surface. ``courses`` only ever reads what a store already
holds.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skilling.course import Position, Record
from skilling.store import FileProgressStore
from skilling.workspace import WorkspaceCourse, WorkspaceManifest
from skilling.workspace import courses_dir as workspace_courses_dir
from skilling.workspace import save_manifest as save_workspace_manifest
from skilling.workspace import state_root as workspace_state_root

from . import fixtures as fx
from .conftest import EXAMPLE_COURSE

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``courses`` joins each row against a discovered workspace regardless of ``--state`` —
    an autouse chdir keeps that lookup from ever wandering into a real workspace that happens
    to sit above wherever the test runner's own cwd is."""
    monkeypatch.delenv("SKILLING_WORKSPACE", raising=False)
    monkeypatch.delenv("SKILLING_STATE_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)


def run(args: list[str], tmp: Path, cache: Path | None = None):
    full = [*args, "--state", str(tmp)]
    if cache is not None:
        full = [*full, "--cache", str(cache)]
    from skilling.cli import app

    return runner.invoke(app, full, catch_exceptions=False)


def _add_clean_course_to_workspace(workspace: Path, version: str = "1.0.0") -> WorkspaceCourse:
    """Build the ``clean-course`` fixture directly at the workspace's own
    ``.skilling/courses/<id>@<version>`` and add it to the manifest — the layout
    ``courses`` and ``resolve_course_location`` both read (spec/workspace.md#the-layout)."""
    course_id = "clean-course"
    fx.build(workspace_courses_dir(workspace) / f"{course_id}@{version}")
    entry = WorkspaceCourse(
        id=course_id,
        version=version,
        ref="local",
        path=f"courses/{course_id}@{version}",
        showcase=f"showcase/{course_id}",
        added_at=datetime.now(UTC),
    )
    save_workspace_manifest(workspace, WorkspaceManifest(courses=[entry]))
    return entry


def _write_record(
    state_root: Path,
    course_id: str,
    *,
    version: str = "1.0.0",
    last_activity: date,
) -> None:
    store = FileProgressStore(state_root)
    record = Record(
        learner_id=store.learner_id,
        course_id=course_id,
        course_version=version,
        spec_version="1.0",
        position=Position(phase=0, lesson=1),
        started_at=last_activity,
        last_activity=last_activity,
    )
    store.put_record(record, expected_revision=None)


def test_no_state_root_is_an_empty_list(tmp_path: Path) -> None:
    never_created = tmp_path / "state"
    out = json.loads(run(["courses"], never_created).stdout)
    assert out == {"ok": True, "verb": "courses", "courses": []}


def test_state_root_exists_but_holds_no_records(tmp_path: Path) -> None:
    (tmp_path / "some-other-file.txt").write_text("not a course\n", encoding="utf-8")
    out = json.loads(run(["courses"], tmp_path).stdout)
    assert out["courses"] == []


def test_one_course_with_no_cache_entry_falls_back_to_id_as_title(tmp_path: Path) -> None:
    _write_record(tmp_path, "solo-course", last_activity=date(2026, 8, 1))

    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)

    assert out["ok"] is True
    assert out["courses"] == [
        {"id": "solo-course", "title": "solo-course", "last_activity": "2026-08-01"}
    ]


def test_title_resolves_from_the_fetch_cache_when_present(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    fx.build(cache / "clean-course@1.0.0")  # id: clean-course, title: Clean Course, v1.0.0
    _write_record(tmp_path, "clean-course", version="1.0.0", last_activity=date(2026, 8, 2))

    out = json.loads(run(["courses"], tmp_path, cache=cache).stdout)

    assert out["courses"] == [
        {"id": "clean-course", "title": "Clean Course", "last_activity": "2026-08-02"}
    ]


def test_several_courses_order_most_recent_first(tmp_path: Path) -> None:
    _write_record(tmp_path, "oldest", last_activity=date(2026, 1, 1))
    _write_record(tmp_path, "newest", last_activity=date(2026, 8, 5))
    _write_record(tmp_path, "middle", last_activity=date(2026, 3, 15))

    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)

    assert [c["id"] for c in out["courses"]] == ["newest", "middle", "oldest"]
    assert [c["last_activity"] for c in out["courses"]] == [
        "2026-08-05",
        "2026-03-15",
        "2026-01-01",
    ]


def test_tied_last_activity_breaks_by_id_for_determinism(tmp_path: Path) -> None:
    same_day = date(2026, 8, 5)
    _write_record(tmp_path, "zeta", last_activity=same_day)
    _write_record(tmp_path, "alpha", last_activity=same_day)

    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)

    assert [c["id"] for c in out["courses"]] == ["alpha", "zeta"]


def test_a_course_with_an_unresolvable_content_directory_does_not_crash(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    # A cache entry exists for the id@version but is not a loadable course (no manifest) —
    # e.g. a half-finished or corrupted cache directory.
    (cache / "broken-course@2.0.0").mkdir(parents=True)
    _write_record(tmp_path, "broken-course", version="2.0.0", last_activity=date(2026, 8, 3))

    out = json.loads(run(["courses"], tmp_path, cache=cache).stdout)

    assert out["ok"] is True
    assert out["courses"] == [
        {"id": "broken-course", "title": "broken-course", "last_activity": "2026-08-03"}
    ]


def test_json_envelope_is_stable(tmp_path: Path) -> None:
    _write_record(tmp_path, "solo-course", last_activity=date(2026, 8, 1))
    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)
    assert set(out) == {"ok", "verb", "courses"}
    assert set(out["courses"][0]) == {"id", "title", "last_activity"}


def test_example_course_directly_referenced_has_no_cache_entry_either(tmp_path: Path) -> None:
    """Mirrors how the rest of this test suite points ``--course`` straight at
    examples/hello-skilling: a bare local path is never fetched into the cache, so its title
    is unresolvable from the state root alone, exactly like any other never-fetched course."""
    from skilling.course import Course

    course = Course.load(EXAMPLE_COURSE)
    _write_record(tmp_path, course.id, version=course.version, last_activity=date(2026, 8, 4))

    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)

    assert out["courses"] == [{"id": course.id, "title": course.id, "last_activity": "2026-08-04"}]


# ------------------------------------------------------------------------ the workspace join


def test_path_is_emitted_when_the_workspace_has_the_course(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    entry = _add_clean_course_to_workspace(workspace)
    monkeypatch.chdir(workspace)
    _write_record(tmp_path, "clean-course", last_activity=date(2026, 8, 1))

    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)

    expected_path = workspace_courses_dir(workspace) / f"{entry.id}@{entry.version}"
    assert out["courses"] == [
        {
            "id": "clean-course",
            "title": "Clean Course",
            "last_activity": "2026-08-01",
            "path": str(expected_path),
        }
    ]


def test_path_is_omitted_outside_any_workspace(tmp_path: Path) -> None:
    """The declared-absence idiom (see ``_session._tutor``): the key is missing, not present
    and ``null``, when there is nothing to resolve it from."""
    _write_record(tmp_path, "solo-course", last_activity=date(2026, 8, 1))

    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)

    assert "path" not in out["courses"][0]


def test_path_is_omitted_for_a_course_the_workspace_never_added(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    save_workspace_manifest(workspace, WorkspaceManifest())  # a workspace, but empty
    monkeypatch.chdir(workspace)
    _write_record(tmp_path, "solo-course", last_activity=date(2026, 8, 1))

    out = json.loads(run(["courses"], tmp_path, cache=tmp_path / "cache").stdout)

    assert "path" not in out["courses"][0]
    assert out["courses"][0]["title"] == "solo-course"


def test_title_prefers_the_workspace_over_the_home_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both a workspace entry and a fetch-cache entry resolve for this course; the workspace
    must win — proven by giving the cache copy a different title than the workspace copy."""
    workspace = tmp_path / "workspace"
    _add_clean_course_to_workspace(workspace)
    monkeypatch.chdir(workspace)

    cache = tmp_path / "cache"
    cache_entry = fx.build(cache / "clean-course@1.0.0")
    fx.edit(cache_entry, fx.MANIFEST_PATH, "title: Clean Course", "title: Cache Title")
    _write_record(tmp_path, "clean-course", last_activity=date(2026, 8, 1))

    out = json.loads(run(["courses"], tmp_path, cache=cache).stdout)

    assert out["courses"][0]["title"] == "Clean Course"


# ------------------------------------------------------------------- state-root resolution


def test_state_root_defaults_to_the_enclosing_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    save_workspace_manifest(workspace, WorkspaceManifest())
    monkeypatch.chdir(workspace)
    _write_record(workspace_state_root(workspace), "clean-course", last_activity=date(2026, 8, 1))

    from skilling.cli import app

    out = json.loads(runner.invoke(app, ["courses"], catch_exceptions=False).stdout)

    assert [c["id"] for c in out["courses"]] == ["clean-course"]


def test_courses_agrees_with_every_other_verb_on_home_state_outside_a_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The split-brain defect this issue closes: ``courses`` used to default to
    ``open_store(None)`` (``~/.skilling/state``) while every other verb defaulted to a
    cwd-relative ``.skilling`` — two conventions for the same default. Outside a workspace,
    with nothing else set, they must now agree on exactly the same directory."""
    from skilling.cli import app
    from skilling.course import Course

    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    course = Course.load(EXAMPLE_COURSE)
    next_result = runner.invoke(
        app, ["next", "--course", str(EXAMPLE_COURSE)], catch_exceptions=False
    )
    assert next_result.exit_code == 0

    courses_result = runner.invoke(app, ["courses"], catch_exceptions=False)
    assert courses_result.exit_code == 0
    out = json.loads(courses_result.stdout)

    assert [c["id"] for c in out["courses"]] == [course.id]
    assert (fake_home / ".skilling" / "state" / course.id / "record.yaml").is_file()


@pytest.mark.parametrize("damage", ["missing", "corrupt", "wrong-id", "wrong-version"])
@pytest.mark.parametrize("cached", [True, False])
def test_stale_workspace_content_preserves_fallback_without_a_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str, cached: bool
) -> None:
    workspace = tmp_path / "workspace"
    entry = _add_clean_course_to_workspace(workspace)
    content = workspace / ".skilling" / entry.path
    if damage == "missing":
        shutil.rmtree(content)
    elif damage == "corrupt":
        (content / "course.yaml").write_text("[broken", encoding="utf-8")
    elif damage == "wrong-id":
        fx.edit(content, fx.MANIFEST_PATH, "id: clean-course", "id: other-course")
    else:
        fx.edit(content, fx.MANIFEST_PATH, 'version: "1.0.0"', 'version: "2.0.0"')
    cache = tmp_path / "cache"
    if cached:
        fx.build(cache / "clean-course@1.0.0")
    _write_record(tmp_path / "state", "clean-course", last_activity=date(2026, 8, 1))
    monkeypatch.chdir(workspace)

    result = run(["courses"], tmp_path / "state", cache=cache)

    assert result.exit_code == 0
    assert json.loads(result.stdout)["courses"] == [
        {
            "id": "clean-course",
            "title": "Clean Course" if cached else "clean-course",
            "last_activity": "2026-08-01",
        }
    ]


def test_workspace_title_uses_manifest_path_after_relocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    entry = _add_clean_course_to_workspace(workspace)
    original = workspace / ".skilling" / entry.path
    actual = workspace / ".skilling" / "imported" / original.name
    actual.parent.mkdir()
    original.rename(actual)
    fx.build(original)
    fx.edit(original, fx.MANIFEST_PATH, "title: Clean Course", "title: Decoy Title")
    entry.path = f"imported/{original.name}"
    save_workspace_manifest(workspace, WorkspaceManifest(courses=[entry]))
    _write_record(workspace_state_root(workspace), "clean-course", last_activity=date(2026, 8, 1))
    relocated = tmp_path / "relocated"
    workspace.rename(relocated)
    nested = relocated / "showcase"
    nested.mkdir()
    monkeypatch.chdir(nested)

    result = run(["courses"], workspace_state_root(relocated), cache=tmp_path / "cache")

    assert result.exit_code == 0
    row = json.loads(result.stdout)["courses"][0]
    assert row["title"] == "Clean Course"
    assert row["path"] == str(relocated / ".skilling" / entry.path)


def test_workspace_version_different_from_record_does_not_offer_resume_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    _add_clean_course_to_workspace(workspace)
    _write_record(
        tmp_path / "state", "clean-course", version="0.9.0", last_activity=date(2026, 8, 1)
    )
    monkeypatch.chdir(workspace)

    result = run(["courses"], tmp_path / "state", cache=tmp_path / "cache")

    assert "path" not in json.loads(result.stdout)["courses"][0]


@pytest.mark.parametrize("text", ["[broken", "courses: [{id: invalid}]", "courses: nope"])
def test_invalid_workspace_manifest_does_not_hide_cached_display(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    workspace = tmp_path / "workspace"
    _add_clean_course_to_workspace(workspace)
    (workspace / ".skilling" / "workspace.yaml").write_text(text, encoding="utf-8")
    fx.build(tmp_path / "cache" / "clean-course@1.0.0")
    _write_record(tmp_path / "state", "clean-course", last_activity=date(2026, 8, 1))
    monkeypatch.chdir(workspace)

    result = run(["courses"], tmp_path / "state", cache=tmp_path / "cache")

    row = json.loads(result.stdout)["courses"][0]
    assert row["title"] == "Clean Course"
    assert "path" not in row


@pytest.mark.parametrize("kind", ["alias", "mismatch"])
def test_courses_refuses_unsafe_state(tmp_path: Path, kind: str) -> None:
    from skilling.cli import app

    from .test_state_paths import directory_alias, snapshot
    from .test_store import a_record

    state = tmp_path / "state"
    state.mkdir()
    if kind == "alias":
        target = tmp_path / "outside"
        target.mkdir()
        directory_alias(state / "clean-course", target)
    else:
        store = FileProgressStore(state)
        store.put_record(a_record("other-course"), None)
        (state / "other-course").rename(state / "clean-course")
    before = snapshot(tmp_path)
    result = runner.invoke(app, ["courses", "--state", str(state)])
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"] == "state-invalid"
    assert snapshot(tmp_path) == before


def test_courses_skips_unrelated_invalid_entry_names(tmp_path: Path) -> None:
    from skilling.cli import app

    from .test_state_paths import directory_alias
    from .test_store import a_record

    state = tmp_path / "state"
    FileProgressStore(state).put_record(a_record(), None)
    target = tmp_path / "outside"
    target.mkdir()
    directory_alias(state / ".unrelated", target)
    result = runner.invoke(app, ["courses", "--state", str(state)])
    assert result.exit_code == 0, result.output
    assert [row["id"] for row in json.loads(result.stdout)["courses"]] == ["clean-course"]
