"""Tests for ``skilling install`` / ``skilling uninstall``: writing a generated pack into the
Claude Code and generic Agent-Skills host conventions, and removing exactly what a receipt
says it wrote.

Every test passes an explicit ``home`` — a ``tmp_path`` straight to the pure functions, or a
monkeypatched ``$HOME`` for the CLI — never the developer's real ``~/.claude`` or
``~/.agents`` (global constraint: those directories are shared across worktrees).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from skilling.cli import app
from skilling.course import Course
from skilling.pack import RECEIPT_NAME, HostTarget, Pack, Platform, install, uninstall

from . import fixtures as fx

runner = CliRunner()


# --------------------------------------------------------------------------------- HostTarget


def test_claude_target_paths_and_invocation(tmp_path: Path) -> None:
    target = HostTarget(Platform.CLAUDE)
    assert target.skills_dir(project=None, home=tmp_path) == tmp_path / ".claude" / "skills"
    assert target.invocation("my-course") == "/my-course"


def test_agents_target_paths_and_invocation(tmp_path: Path) -> None:
    target = HostTarget(Platform.AGENTS)
    assert target.skills_dir(project=None, home=tmp_path) == tmp_path / ".agents" / "skills"
    assert target.invocation("my-course") == "$my-course"


def test_project_target_ignores_home(tmp_path: Path) -> None:
    target = HostTarget(Platform.CLAUDE)
    project = tmp_path / "repo"
    home = tmp_path / "home"
    assert target.skills_dir(project=project, home=home) == project / ".claude" / "skills"


# ------------------------------------------------------------------------------------ install


def test_install_writes_pack_files_and_a_receipt(clean: Course, tmp_path: Path) -> None:
    pack = Pack.generate(clean)
    target = HostTarget(Platform.CLAUDE)
    result = install(pack, target, project=None, home=tmp_path)

    assert result.skill_dir == tmp_path / ".claude" / "skills" / "clean-course"
    assert (result.skill_dir / "SKILL.md").is_file()
    assert (result.skill_dir / "references" / "objectives.md").is_file()

    receipt = yaml.safe_load((result.skill_dir / RECEIPT_NAME).read_text(encoding="utf-8"))
    assert receipt["name"] == "clean-course"
    assert set(receipt["files"]) == {
        "SKILL.md",
        "references/delivery-loop.md",
        "references/objectives.md",
        "references/troubleshooting.md",
    }


def test_reinstall_upgrades_in_place_with_no_duplicate_files(
    clean_dir: Path, tmp_path: Path
) -> None:
    target = HostTarget(Platform.CLAUDE)
    first = install(Pack.generate(Course.load(clean_dir)), target, project=None, home=tmp_path)

    fx.edit(clean_dir, fx.MANIFEST_PATH, "title: Clean Course", "title: Clean Course Renamed")

    second = install(Pack.generate(Course.load(clean_dir)), target, project=None, home=tmp_path)

    assert first.skill_dir == second.skill_dir
    skill_md = second.skill_dir / "SKILL.md"
    assert "Clean Course Renamed" in skill_md.read_text(encoding="utf-8")

    all_files = {
        p.relative_to(second.skill_dir) for p in second.skill_dir.rglob("*") if p.is_file()
    }
    assert all_files == {
        Path("SKILL.md"),
        Path("references/delivery-loop.md"),
        Path("references/objectives.md"),
        Path("references/troubleshooting.md"),
        Path(RECEIPT_NAME),
    }


# ---------------------------------------------------------------------------------- uninstall


def test_uninstall_removes_exactly_the_receipted_files_and_keeps_foreign_ones(
    clean: Course, tmp_path: Path
) -> None:
    target = HostTarget(Platform.CLAUDE)
    result = install(Pack.generate(clean), target, project=None, home=tmp_path)

    foreign = result.skill_dir / "notes.txt"
    foreign.write_text("do not touch\n", encoding="utf-8")

    removed = uninstall("clean-course", target, project=None, home=tmp_path)

    assert result.skill_dir / "SKILL.md" in removed
    assert not (result.skill_dir / "SKILL.md").is_file()
    assert not (result.skill_dir / "references").exists()
    assert not (result.skill_dir / RECEIPT_NAME).is_file()
    assert foreign.is_file()
    assert foreign.read_text(encoding="utf-8") == "do not touch\n"
    assert result.skill_dir.is_dir()  # the foreign file kept it alive


def test_uninstall_of_a_never_installed_name_is_a_no_op(tmp_path: Path) -> None:
    target = HostTarget(Platform.CLAUDE)
    assert uninstall("never-installed", target, project=None, home=tmp_path) == []


def test_uninstall_refuses_when_a_receipted_file_was_hand_edited(
    clean: Course, tmp_path: Path
) -> None:
    target = HostTarget(Platform.CLAUDE)
    result = install(Pack.generate(clean), target, project=None, home=tmp_path)
    (result.skill_dir / "SKILL.md").write_text("hand-edited\n", encoding="utf-8")

    with pytest.raises(ValueError):
        uninstall("clean-course", target, project=None, home=tmp_path)

    # refusing means nothing was removed, not even the untouched files
    assert (result.skill_dir / "references" / "objectives.md").is_file()
    assert (result.skill_dir / RECEIPT_NAME).is_file()


# ---------------------------------------------------------------------------------------- CLI


def test_install_writes_both_conventions_by_default(clean_dir: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["install", str(clean_dir)], env={"HOME": str(tmp_path)})
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".claude" / "skills" / "clean-course" / "SKILL.md").is_file()
    assert (tmp_path / ".agents" / "skills" / "clean-course" / "SKILL.md").is_file()
    assert "/clean-course" in result.stdout
    assert "$clean-course" in result.stdout


def test_install_platform_flag_narrows_to_one_convention(clean_dir: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["install", str(clean_dir), "--platform", "claude"], env={"HOME": str(tmp_path)}
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".claude" / "skills" / "clean-course" / "SKILL.md").is_file()
    assert not (tmp_path / ".agents").exists()


def test_project_writes_into_the_repo_with_a_git_add_hint(
    clean_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["install", str(clean_dir), "--project"],
        env={"HOME": str(tmp_path / "unused-home")},
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".claude" / "skills" / "clean-course" / "SKILL.md").is_file()
    assert "git add" in result.stdout


def test_cli_reinstall_is_idempotent_and_upgrades_in_place(clean_dir: Path, tmp_path: Path) -> None:
    env = {"HOME": str(tmp_path)}
    first = runner.invoke(app, ["install", str(clean_dir), "--platform", "claude"], env=env)
    assert first.exit_code == 0, first.output

    fx.edit(clean_dir, fx.MANIFEST_PATH, "title: Clean Course", "title: Clean Course Renamed")

    second = runner.invoke(app, ["install", str(clean_dir), "--platform", "claude"], env=env)
    assert second.exit_code == 0, second.output

    skill_dir = tmp_path / ".claude" / "skills" / "clean-course"
    assert "Clean Course Renamed" in (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    all_files = {p.relative_to(skill_dir) for p in skill_dir.rglob("*") if p.is_file()}
    assert all_files == {
        Path("SKILL.md"),
        Path("references/delivery-loop.md"),
        Path("references/objectives.md"),
        Path("references/troubleshooting.md"),
        Path(RECEIPT_NAME),
    }


def test_cli_uninstall_removes_exactly_what_was_written_and_keeps_foreign_files(
    clean_dir: Path, tmp_path: Path
) -> None:
    env = {"HOME": str(tmp_path)}
    installed = runner.invoke(app, ["install", str(clean_dir)], env=env)
    assert installed.exit_code == 0, installed.output

    claude_dir = tmp_path / ".claude" / "skills" / "clean-course"
    foreign = claude_dir / "notes.txt"
    foreign.write_text("do not touch\n", encoding="utf-8")

    result = runner.invoke(app, ["uninstall", "clean-course"], env=env)
    assert result.exit_code == 0, result.output

    assert foreign.is_file()
    assert foreign.read_text(encoding="utf-8") == "do not touch\n"
    assert not (claude_dir / "SKILL.md").is_file()
    assert not (claude_dir / RECEIPT_NAME).is_file()
    agents_dir = tmp_path / ".agents" / "skills" / "clean-course"
    assert not agents_dir.exists()


def test_cli_uninstall_of_nothing_installed_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["uninstall", "never-installed"], env={"HOME": str(tmp_path)})
    assert result.exit_code == 1
