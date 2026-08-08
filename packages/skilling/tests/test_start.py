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
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skilling.cli import app
from skilling.skills import RECEIPT_NAME, SKILL_NAMES
from skilling.store import FileProgressStore
from skilling.workspace import ENTRY_BLOCK_END, ENTRY_BLOCK_START, load_manifest, state_root

from .conftest import EXAMPLE_COURSE, REPO_ROOT

WORKBENCH_COURSE = REPO_ROOT / "examples" / "workbench"

runner = CliRunner()


def run(args: list[str], home: Path):
    return runner.invoke(app, args, env={"HOME": str(home)}, catch_exceptions=False)


def start_hello_skilling(ws: Path, home: Path, *, dir_arg: bool = True):
    args = ["start", str(EXAMPLE_COURSE), *([str(ws)] if dir_arg else []), "--json"]
    return run(args, home)


# ---------------------------------------------------------------------------------------- e2e


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
        assert "uvx skilling" in text


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
    assert ".claude/skills/ + .agents/skills/ (learn, progress, homework)" in out
    for host in ("Claude Code", "Codex", "Claude Cowork", "ChatGPT Work"):
        assert host in out
    assert 'say "learn"' in out


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
