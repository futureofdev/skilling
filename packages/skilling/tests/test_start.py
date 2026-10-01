"""Tests for ``skilling start``: the one-command path from a course ref to an openable
learner workspace (spec/workspace.md; GitHub issue #40).

End-to-end against ``examples/hello-skilling`` rather than a synthetic fixture, because the
whole point of this command is what a real course, opened for real, looks like afterwards —
layout, receipts, manifest, record, showcase, entry files, all at once. ``examples/workbench``
stands in for "a second course," so the growth path is exercised against another real course
rather than a hand-rolled one.

Every invocation pins ``HOME`` to a throwaway directory the same way ``test_install.py``
does: ``start`` folder-scopes the skill triad into the workspace (``project=``), so ``home``
is never actually read, but pinning it means a bug that starts reading it again can never
reach the developer's real ``~/.claude`` or ``~/.agents``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skilling.cli import app
from skilling.skills import RECEIPT_NAME, SKILL_NAMES
from skilling.sources import ResolveError
from skilling.store import FileProgressStore
from skilling.workspace import (
    ENTRY_BLOCK_END,
    ENTRY_BLOCK_START,
    load_manifest,
    state_root,
    validate_local_import,
)

from .conftest import EXAMPLE_COURSE, REPO_ROOT

WORKBENCH_COURSE = REPO_ROOT / "examples" / "workbench"

runner = CliRunner()


def run(args: list[str], home: Path):
    return runner.invoke(app, args, env={"HOME": str(home)}, catch_exceptions=False)


def start_hello_skilling(ws: Path, home: Path, *, dir_arg: bool = True):
    args = ["start", str(EXAMPLE_COURSE), *([str(ws)] if dir_arg else []), "--json"]
    return run(args, home)


# ---------------------------------------------------------------------------------------- e2e


def test_git_start_discovers_and_delivers_after_remote_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SKILLING_STATE_ROOT", raising=False)
    monkeypatch.delenv("SKILLING_WORKSPACE", raising=False)
    source = tmp_path / "remote"
    shutil.copytree(EXAMPLE_COURSE, source)
    for args in (
        ["init", "-q"],
        ["config", "user.name", "Test"],
        ["config", "user.email", "test@example.invalid"],
        ["add", "."],
        ["commit", "-qm", "course"],
    ):
        subprocess.run(["git", *args], cwd=source, check=True, capture_output=True)
    ws = tmp_path / "workspace"
    home = tmp_path / "unused-home"
    started = run(["start", source.as_uri(), str(ws), "--json"], home)
    assert started.exit_code == 0, started.output
    payload = json.loads(started.stdout)
    assert payload["course"]["id"] == "hello-skilling"
    source.rename(tmp_path / "unavailable")
    monkeypatch.chdir(ws / "showcase" / "hello-skilling")
    listed = run(["courses", "--json"], home)
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.stdout)["courses"][0]["id"] == "hello-skilling"
    resumed = run(["next", "--course", "hello-skilling"], home)
    assert resumed.exit_code == 0, resumed.output
    assert json.loads(resumed.stdout)["beat"]["name"] == "welcome"
    progress = run(["progress", "--course", "hello-skilling"], home)
    assert progress.exit_code == 0, progress.output
    assert not (home / ".skilling").exists()


def test_start_builds_a_complete_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    result = start_hello_skilling(ws, tmp_path / "unused-home")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    assert payload["verb"] == "start"
    assert payload["workspace"] == str(ws.resolve())
    assert payload["course"] == {
        "id": "hello-skilling",
        "version": "1.0.0",
        "title": "Hello, Skilling",
    }
    assert payload["showcase"] == "showcase/hello-skilling"
    assert payload["state_initialised"] is True
    assert set(payload["entry_files"]) == {"CLAUDE.md", "AGENTS.md"}
    assert set(payload["skills"]) == {
        f"{convention}/skills/{name}"
        for convention in (".claude", ".agents")
        for name in SKILL_NAMES
    }

    # course content is copied into the workspace, not referenced in place
    course_dir = ws / ".skilling" / "courses" / "hello-skilling@1.0.0"
    assert (course_dir / "course.yaml").is_file()
    assert course_dir != EXAMPLE_COURSE

    # the skill triad, both host conventions, each receipted
    for convention in (".claude", ".agents"):
        for name in SKILL_NAMES:
            skill_dir = ws / convention / "skills" / name
            assert (skill_dir / "SKILL.md").is_file()
            assert (skill_dir / RECEIPT_NAME).is_file()

    manifest = load_manifest(ws)
    entry = manifest.course("hello-skilling")
    assert entry is not None
    assert entry.version == "1.0.0"
    assert entry.ref == str(EXAMPLE_COURSE)
    assert entry.path == "courses/hello-skilling@1.0.0"
    assert entry.showcase == "showcase/hello-skilling"

    store = FileProgressStore(state_root(ws))
    assert store.get_record("local", "hello-skilling") is not None

    assert (ws / "showcase" / "hello-skilling" / "README.md").is_file()

    for name in ("CLAUDE.md", "AGENTS.md"):
        text = (ws / name).read_text(encoding="utf-8")
        assert ENTRY_BLOCK_START in text
        assert ENTRY_BLOCK_END in text
        assert "/learn" in text
        assert "$learn" in text
        assert ".skilling/" in text
        assert "showcase/" in text
        assert "installed and on PATH" in text


def test_dir_defaults_to_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    result = start_hello_skilling(cwd, tmp_path / "home", dir_arg=False)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["workspace"] == str(cwd.resolve())


def test_human_output_matches_the_documented_format(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    result = run(["start", str(EXAMPLE_COURSE), str(ws)], tmp_path / "home")
    assert result.exit_code == 0, result.output
    out = result.output

    assert "hello-skilling 1.0.0" in out
    assert "Hello, Skilling" in out
    assert f"workspace  {ws.resolve()}" in out
    assert "course     .skilling/courses/hello-skilling@1.0.0" in out
    assert "showcase   showcase/hello-skilling/" in out
    assert ".claude/skills/ + .agents/skills/ (learn, progress, homework, upgrade)" in out
    for host in ("Claude Code", "Codex"):
        assert host in out
    assert f"open {ws.resolve()}" in out
    assert "Claude Code and run /learn" in out
    assert "Codex and run $learn" in out


# --------------------------------------------------------------------------------- idempotent


def test_rerun_is_idempotent_except_for_refreshed_skill_files(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    home = tmp_path / "home"
    first = start_hello_skilling(ws, home)
    assert first.exit_code == 0, first.output

    manifest_before = (ws / ".skilling" / "workspace.yaml").read_text(encoding="utf-8")
    claude_before = (ws / "CLAUDE.md").read_text(encoding="utf-8")
    agents_before = (ws / "AGENTS.md").read_text(encoding="utf-8")
    readme_before = (ws / "showcase" / "hello-skilling" / "README.md").read_text(encoding="utf-8")
    record_before = (state_root(ws) / "hello-skilling" / "record.yaml").read_text(encoding="utf-8")

    # a stale skill file, as if an older skilling release had installed different content
    stale = ws / ".claude" / "skills" / "learn" / "SKILL.md"
    stale.write_text("stale content from a previous version\n", encoding="utf-8")

    second = start_hello_skilling(ws, home)
    assert second.exit_code == 0, second.output

    assert (ws / ".skilling" / "workspace.yaml").read_text(encoding="utf-8") == manifest_before
    assert (ws / "CLAUDE.md").read_text(encoding="utf-8") == claude_before
    assert (ws / "AGENTS.md").read_text(encoding="utf-8") == agents_before
    assert (ws / "showcase" / "hello-skilling" / "README.md").read_text(
        encoding="utf-8"
    ) == readme_before
    assert (state_root(ws) / "hello-skilling" / "record.yaml").read_text(
        encoding="utf-8"
    ) == record_before
    assert stale.read_text(encoding="utf-8") != "stale content from a previous version\n"


def test_a_second_course_grows_the_workspace_without_disturbing_the_first(
    tmp_path: Path,
) -> None:
    ws = tmp_path / "ws"
    home = tmp_path / "home"
    first = start_hello_skilling(ws, home)
    assert first.exit_code == 0, first.output
    first_readme = (ws / "showcase" / "hello-skilling" / "README.md").read_text(encoding="utf-8")

    second = run(["start", str(WORKBENCH_COURSE), str(ws), "--json"], home)
    assert second.exit_code == 0, second.output

    manifest = load_manifest(ws)
    assert {c.id for c in manifest.courses} == {"hello-skilling", "workbench"}

    assert (ws / ".skilling" / "courses" / "hello-skilling@1.0.0" / "course.yaml").is_file()
    assert (ws / ".skilling" / "courses" / "workbench@1.0.0" / "course.yaml").is_file()
    assert (ws / "showcase" / "workbench" / "README.md").is_file()
    assert (ws / "showcase" / "hello-skilling" / "README.md").read_text(
        encoding="utf-8"
    ) == first_readme

    store = FileProgressStore(state_root(ws))
    assert store.get_record("local", "hello-skilling") is not None
    assert store.get_record("local", "workbench") is not None


def test_foreign_entry_file_content_is_preserved(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    foreign = "# My Project\n\nNotes I wrote before running skilling start.\n"
    (ws / "CLAUDE.md").write_text(foreign, encoding="utf-8")

    first = start_hello_skilling(ws, tmp_path / "home")
    assert first.exit_code == 0, first.output
    text = (ws / "CLAUDE.md").read_text(encoding="utf-8")
    assert foreign.strip() in text
    assert text.count(ENTRY_BLOCK_START) == 1

    second = start_hello_skilling(ws, tmp_path / "home")
    assert second.exit_code == 0, second.output
    text_again = (ws / "CLAUDE.md").read_text(encoding="utf-8")
    assert foreign.strip() in text_again
    assert text_again.count(ENTRY_BLOCK_START) == 1  # no duplicate block on re-run


# ---------------------------------------------------------------------------------- refusals


def test_invalid_local_course_is_refused_with_findings_and_nothing_half_created(
    tmp_path: Path, clean_dir: Path
) -> None:
    (clean_dir / "course.yaml").unlink()
    ws = tmp_path / "ws"

    result = run(["start", str(clean_dir), str(ws)], tmp_path / "home")

    assert result.exit_code == 1
    assert not ws.exists()


def test_invalid_local_course_json_reports_findings_and_nothing_half_created(
    tmp_path: Path, clean_dir: Path
) -> None:
    (clean_dir / "course.yaml").unlink()
    ws = tmp_path / "ws"

    result = run(["start", str(clean_dir), str(ws), "--json"], tmp_path / "home")

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"] >= 1
    assert not ws.exists()


def test_unknown_ref_is_refused_and_nothing_is_created(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    result = run(["start", str(tmp_path / "does-not-exist"), str(ws)], tmp_path / "home")
    assert result.exit_code == 1
    assert not ws.exists()


@pytest.mark.parametrize("alias", [False, True])
def test_reimporting_workspace_course_preserves_its_files(tmp_path: Path, alias: bool) -> None:
    ws = tmp_path / "ws"
    home = tmp_path / "home"
    assert start_hello_skilling(ws, home).exit_code == 0
    content = ws / ".skilling/courses/hello-skilling@1.0.0"
    before = {p.relative_to(content): p.read_bytes() for p in content.rglob("*") if p.is_file()}
    source = content
    if alias:
        source = tmp_path / "alias"
        try:
            source.symlink_to(content, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlinks unavailable on this platform")
    result = run(["start", str(source), str(ws), "--json"], home)
    assert result.exit_code == 0, result.output
    assert {
        p.relative_to(content): p.read_bytes() for p in content.rglob("*") if p.is_file()
    } == before


@pytest.mark.parametrize("workspace_relative", [".", "nested/workspace"])
def test_workspace_inside_source_is_refused_before_copy(
    tmp_path: Path, clean_dir: Path, workspace_relative: str
) -> None:
    ws = clean_dir / workspace_relative
    result = runner.invoke(app, ["start", str(clean_dir), str(ws)], catch_exceptions=True)
    assert result.exit_code == 1
    assert "overlap" in result.output
    assert not (ws / ".skilling").exists()
    assert (clean_dir / "course.yaml").is_file()


def test_copy_failure_preserves_previous_content_and_retry_succeeds(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    ws = tmp_path / "ws"
    home = tmp_path / "home"
    assert run(["start", str(clean_dir), str(ws)], home).exit_code == 0
    course_id = json.loads(run(["start", str(clean_dir), str(ws), "--json"], home).stdout)[
        "course"
    ]["id"]
    content = ws / ".skilling/courses" / f"{course_id}@1.0.0"
    old_files = {p.relative_to(content): p.read_bytes() for p in content.rglob("*") if p.is_file()}
    old_manifest = (ws / ".skilling/workspace.yaml").read_bytes()
    (clean_dir / "new-asset.txt").write_text("updated content")
    real_copytree = shutil.copytree

    def interrupted_copy(source, destination, *args, **kwargs):
        Path(destination).mkdir(parents=True)
        (Path(destination) / "partial.txt").write_text("incomplete")
        raise OSError("injected copy interruption")

    monkeypatch.setattr(shutil, "copytree", interrupted_copy)
    failed = run(["start", str(clean_dir), str(ws)], home)
    assert failed.exit_code == 1
    assert "injected copy interruption" in failed.output
    assert {
        p.relative_to(content): p.read_bytes() for p in content.rglob("*") if p.is_file()
    } == old_files
    assert (ws / ".skilling/workspace.yaml").read_bytes() == old_manifest
    monkeypatch.setattr(shutil, "copytree", real_copytree)
    retried = run(["start", str(clean_dir), str(ws)], home)
    assert retried.exit_code == 0, retried.output
    assert (content / "new-asset.txt").read_text() == "updated content"
    assert not (content / "partial.txt").exists()


def test_invalid_staged_copy_preserves_previous_content(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    ws = tmp_path / "ws"
    home = tmp_path / "home"
    initial = run(["start", str(clean_dir), str(ws), "--json"], home)
    course_id = json.loads(initial.stdout)["course"]["id"]
    content = ws / ".skilling/courses" / f"{course_id}@1.0.0"
    before = (content / "course.yaml").read_bytes()
    real_copytree = shutil.copytree

    def changed_during_copy(source, destination, *args, **kwargs):
        result = real_copytree(source, destination, *args, **kwargs)
        if Path(source) == clean_dir:
            (Path(destination) / "course.yaml").unlink()
        return result

    monkeypatch.setattr(shutil, "copytree", changed_during_copy)
    result = run(["start", str(clean_dir), str(ws), "--json"], home)
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False
    assert (content / "course.yaml").read_bytes() == before


def test_interior_symlink_is_refused_without_following_it(tmp_path: Path, clean_dir: Path) -> None:
    link = clean_dir / "recursive-link"
    try:
        link.symlink_to(clean_dir, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable on this platform")
    ws = tmp_path / "ws"
    result = runner.invoke(app, ["start", str(clean_dir), str(ws)], catch_exceptions=True)
    assert result.exit_code == 1
    assert "symlink" in result.output
    assert not (ws / ".skilling").exists()


# ------------------------------------------------- local import payload (GitHub issue #101)


def files_under(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if not p.is_dir()}


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def course_in_repository(tmp_path: Path, clean_dir: Path) -> tuple[Path, set[str]]:
    """A course one directory down in a Git repository, everything committed; returns the
    course directory and its tracked files."""
    repo = tmp_path / "project"
    course = repo / "course"
    shutil.copytree(clean_dir, course)
    (repo / ".gitignore").write_text(".venv/\n__pycache__/\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "course")
    return course, files_under(course)


def symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")


def installed(ws: Path, clean_dir: Path) -> Path:
    return ws / ".skilling/courses" / f"{clean_dir.name}@1.0.0"


def test_git_course_copies_tracked_files_and_ignores_untracked_symlinks(
    tmp_path: Path, clean_dir: Path
) -> None:
    course, tracked = course_in_repository(tmp_path, clean_dir)
    venv = course / ".venv/bin"
    venv.mkdir(parents=True)
    symlink_or_skip(venv / "python", Path("/usr/bin/python3"))
    (course / "__pycache__").mkdir()
    (course / "__pycache__/answer.pyc").write_bytes(b"\0")
    (course / "scratch.txt").write_text("untracked notes", encoding="utf-8")
    symlink_or_skip(course / "untracked-link", course / "course.yaml")
    ws = tmp_path / "ws"
    result = run(["start", str(course), str(ws), "--json"], tmp_path / "home")
    assert result.exit_code == 0, result.output
    course_id = json.loads(result.stdout)["course"]["id"]
    content = ws / ".skilling/courses" / f"{course_id}@1.0.0"
    assert files_under(content) == tracked
    assert not (content / ".git").exists() and not (content / ".venv").exists()


def test_tracked_symlink_is_refused_naming_the_path(tmp_path: Path, clean_dir: Path) -> None:
    course, _ = course_in_repository(tmp_path, clean_dir)
    symlink_or_skip(course / "tracked-link", Path("course.yaml"))
    git(course.parent, "add", "-A")
    git(course.parent, "commit", "-qm", "link")
    with pytest.raises(ResolveError, match=r"symlink.*: tracked-link$"):
        validate_local_import(tmp_path / "ws", course)
    assert not (tmp_path / "ws").exists()


def test_tracked_file_replaced_by_symlink_is_refused_naming_the_path(
    tmp_path: Path, clean_dir: Path
) -> None:
    course, _ = course_in_repository(tmp_path, clean_dir)
    outside = tmp_path / "outside.txt"
    outside.write_text("not course content", encoding="utf-8")
    (course / "notes.txt").write_text("tracked", encoding="utf-8")
    git(course.parent, "add", "-A")
    git(course.parent, "commit", "-qm", "notes")
    (course / "notes.txt").unlink()
    symlink_or_skip(course / "notes.txt", outside)
    with pytest.raises(ResolveError, match="symlink") as refused:
        validate_local_import(tmp_path / "ws", course)
    assert str(course / "notes.txt") in str(refused.value)


def test_course_git_tracks_nothing_of_falls_back_to_directory_walk(
    tmp_path: Path, clean_dir: Path
) -> None:
    repo = tmp_path / "home-dotfiles"
    repo.mkdir()
    git(repo, "init", "-q")
    course = repo / "course"
    shutil.copytree(clean_dir, course)
    ws = tmp_path / "ws"
    assert run(["start", str(course), str(ws)], tmp_path / "home").exit_code == 0
    assert files_under(installed(ws, clean_dir)) == files_under(clean_dir)


def test_plain_directory_excludes_vcs_and_environment_dirs(tmp_path: Path, clean_dir: Path) -> None:
    expected = files_under(clean_dir)
    (clean_dir / ".venv/bin").mkdir(parents=True)
    symlink_or_skip(clean_dir / ".venv/bin/python", Path("/usr/bin/python3"))
    (clean_dir / ".git").mkdir()
    (clean_dir / ".git/HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (clean_dir / "answer/__pycache__").mkdir(parents=True)
    (clean_dir / "answer/__pycache__/key.pyc").write_bytes(b"\0")
    (clean_dir / "answer/key.py").write_text("ANSWER = 42\n", encoding="utf-8")
    ws = tmp_path / "ws"
    result = run(["start", str(clean_dir), str(ws)], tmp_path / "home")
    assert result.exit_code == 0, result.output
    assert files_under(installed(ws, clean_dir)) == expected | {"answer/key.py"}


def test_plain_directory_symlink_outside_exclusions_is_refused_by_name(
    tmp_path: Path, clean_dir: Path
) -> None:
    (clean_dir / "assets").mkdir(exist_ok=True)
    symlink_or_skip(clean_dir / "assets/logo.png", tmp_path / "elsewhere.png")
    with pytest.raises(ResolveError, match="symlink") as refused:
        validate_local_import(tmp_path / "ws", clean_dir)
    assert str(clean_dir / "assets/logo.png") in str(refused.value)
    assert not (tmp_path / "ws").exists()


@pytest.mark.parametrize("foreign", ["# Learner notes\n\n\n\n", "  \n\t\n"])
def test_entry_creation_preserves_foreign_whitespace(tmp_path: Path, foreign: str) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    entry = ws / "AGENTS.md"
    entry.write_text(foreign, encoding="utf-8")
    result = start_hello_skilling(ws, tmp_path / "home")
    assert result.exit_code == 0, result.output
    assert entry.read_text(encoding="utf-8").startswith(foreign)


def test_publication_failure_restores_previous_course(
    tmp_path: Path, clean_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "ws"
    home = tmp_path / "home"
    initial = run(["start", str(clean_dir), str(ws), "--json"], home)
    course_id = json.loads(initial.stdout)["course"]["id"]
    content = ws / ".skilling/courses" / f"{course_id}@1.0.0"
    old_manifest = (content / "course.yaml").read_bytes()
    (clean_dir / "new-asset.txt").write_text("new")
    real_rename = Path.rename

    def failed_publish(source: Path, target: Path) -> Path:
        if source.name == "course" and source.parent.name.startswith(".skilling-import-"):
            raise OSError("injected publication failure")
        return real_rename(source, target)

    monkeypatch.setattr(Path, "rename", failed_publish)
    result = run(["start", str(clean_dir), str(ws)], home)
    assert result.exit_code == 1
    assert "injected publication failure" in result.output
    assert (content / "course.yaml").read_bytes() == old_manifest
    assert not (content / "new-asset.txt").exists()


def test_workspace_content_symlink_is_refused(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / ".skilling").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (ws / ".skilling/courses").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable on this platform")
    result = run(["start", str(EXAMPLE_COURSE), str(ws)], tmp_path / "home")
    assert result.exit_code == 1
    assert "symlink" in result.output
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("existing_block", [False, True])
def test_entry_refresh_preserves_foreign_newline_bytes(
    tmp_path: Path, existing_block: bool
) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    prefix = b"# Learner notes\r\n\r\nKeep CRLF and trailing spaces.  \r\n"
    suffix = b"\r\nForeign suffix\nMixed newlines stay intact.\r\n" if existing_block else b""
    block = (
        f"{ENTRY_BLOCK_START}\r\nOld generated content\r\n{ENTRY_BLOCK_END}".encode()
        if existing_block
        else b""
    )
    entry = ws / "AGENTS.md"
    entry.write_bytes(prefix + block + suffix)
    result = start_hello_skilling(ws, tmp_path / "home")
    assert result.exit_code == 0, result.output
    updated = entry.read_bytes()
    assert updated.startswith(prefix)
    assert updated.endswith(suffix)


def test_started_workspace_resumes_by_id_after_relocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    monkeypatch.delenv("SKILLING_STATE_ROOT", raising=False)
    monkeypatch.delenv("SKILLING_WORKSPACE", raising=False)
    source = tmp_path / "source"
    shutil.copytree(EXAMPLE_COURSE, source)
    ws = tmp_path / "ws"
    home = tmp_path / "home"
    started = run(["start", str(source), str(ws), "--json"], home)
    assert started.exit_code == 0, started.output
    shutil.rmtree(source)
    monkeypatch.chdir(ws / "showcase/hello-skilling")
    advanced = run(["advance", "--course", "hello-skilling", "--input", "next"], home)
    assert advanced.exit_code == 0, advanced.output
    before = json.loads(advanced.stdout)
    record_before = (state_root(ws) / "hello-skilling/record.yaml").read_bytes()

    monkeypatch.chdir(tmp_path)
    relocated = tmp_path / "relocated"
    ws.rename(relocated)
    monkeypatch.chdir(relocated / "showcase/hello-skilling")
    resumed = run(["next", "--course", "hello-skilling"], home)
    assert resumed.exit_code == 0, resumed.output
    after = json.loads(resumed.stdout)
    assert after["position"] == before["position"]
    assert after["revision"] == before["revision"]
    assert after["beat"] == before["beat"]
    assert (state_root(relocated) / "hello-skilling/record.yaml").read_bytes() == record_before
    listed = run(["courses", "--json"], home)
    assert listed.exit_code == 0, listed.output
    courses = json.loads(listed.stdout)["courses"]
    assert [(course["id"], course["title"]) for course in courses] == [
        ("hello-skilling", "Hello, Skilling")
    ]
    assert not (home / ".skilling/state").exists()
