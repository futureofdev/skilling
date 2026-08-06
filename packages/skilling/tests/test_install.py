"""Tests for ``skilling install`` / ``skilling uninstall``: writing the bundled
``learn``/``progress``/``homework`` skill triad into the Claude Code and generic Agent-Skills
host conventions, and removing exactly what a receipt says it wrote.

There is no course argument any more (docs/superpowers/specs/
2026-08-06-generic-delivery-skills-design.md) — the triad is fixed and installed once per
learner, not once per course. ``uninstall`` treats the triad as one atomic unit: a hand-edit
to any one of the three skills refuses the whole removal, not just that skill's.

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
from skilling.skills import (
    RECEIPT_NAME,
    SKILL_NAMES,
    HostTarget,
    Platform,
    install,
    skill_md_path,
    uninstall,
)
from skilling.skills import skill_dir as bundled_skill_dir

runner = CliRunner()


# --------------------------------------------------------------------------------- HostTarget


def test_claude_target_paths_and_invocation(tmp_path: Path) -> None:
    target = HostTarget(Platform.CLAUDE)
    assert target.skills_dir(project=None, home=tmp_path) == tmp_path / ".claude" / "skills"
    assert target.invocation("learn") == "/learn"


def test_agents_target_paths_and_invocation(tmp_path: Path) -> None:
    target = HostTarget(Platform.AGENTS)
    assert target.skills_dir(project=None, home=tmp_path) == tmp_path / ".agents" / "skills"
    assert target.invocation("learn") == "$learn"


def test_project_target_ignores_home(tmp_path: Path) -> None:
    target = HostTarget(Platform.CLAUDE)
    project = tmp_path / "repo"
    home = tmp_path / "home"
    assert target.skills_dir(project=project, home=home) == project / ".claude" / "skills"


# ------------------------------------------------------------------------------------ install


def test_install_writes_all_three_skills_and_a_receipt_each(tmp_path: Path) -> None:
    target = HostTarget(Platform.CLAUDE)
    result = install(target, project=None, home=tmp_path)

    base = tmp_path / ".claude" / "skills"
    assert result.skill_dirs == tuple(base / name for name in SKILL_NAMES)

    for name in SKILL_NAMES:
        skill_dir = base / name
        assert (skill_dir / "SKILL.md").is_file()
        assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == skill_md_path(
            name
        ).read_text(encoding="utf-8")

        receipt = yaml.safe_load((skill_dir / RECEIPT_NAME).read_text(encoding="utf-8"))
        assert receipt["name"] == name
        expected_relatives = {
            p.relative_to(bundled_skill_dir(name)).as_posix()
            for p in bundled_skill_dir(name).rglob("*.md")
        }
        assert set(receipt["files"]) == expected_relatives


def test_reinstall_upgrades_in_place_with_no_duplicate_files(tmp_path: Path) -> None:
    target = HostTarget(Platform.CLAUDE)
    first = install(target, project=None, home=tmp_path)

    # Simulate a stale previous install: hand-edit one file as if an older `skilling`
    # release had written different content there.
    stale_skill_md = first.skill_dirs[0] / "SKILL.md"
    stale_skill_md.write_text("stale content from a previous version\n", encoding="utf-8")

    second = install(target, project=None, home=tmp_path)

    assert first.skill_dirs == second.skill_dirs
    assert stale_skill_md.read_text(encoding="utf-8") == skill_md_path(SKILL_NAMES[0]).read_text(
        encoding="utf-8"
    )

    base = tmp_path / ".claude" / "skills"
    for name in SKILL_NAMES:
        skill_dir = base / name
        expected = {
            p.relative_to(bundled_skill_dir(name)) for p in bundled_skill_dir(name).rglob("*.md")
        } | {Path(RECEIPT_NAME)}
        actual = {p.relative_to(skill_dir) for p in skill_dir.rglob("*") if p.is_file()}
        assert actual == expected


def test_install_defaults_to_home_when_no_project(tmp_path: Path) -> None:
    target = HostTarget(Platform.AGENTS)
    result = install(target, project=None, home=tmp_path)
    assert all(str(p).startswith(str(tmp_path)) for p in result.skill_dirs)


# ---------------------------------------------------------------------------------- uninstall


def test_uninstall_removes_exactly_the_receipted_files_and_keeps_foreign_ones(
    tmp_path: Path,
) -> None:
    target = HostTarget(Platform.CLAUDE)
    result = install(target, project=None, home=tmp_path)

    foreign = result.skill_dirs[0] / "notes.txt"
    foreign.write_text("do not touch\n", encoding="utf-8")

    removed = uninstall(target, project=None, home=tmp_path)

    assert result.skill_dirs[0] / "SKILL.md" in removed
    for skill_dir in result.skill_dirs:
        assert not (skill_dir / "SKILL.md").is_file()
        assert not (skill_dir / RECEIPT_NAME).is_file()
    assert not (result.skill_dirs[1]).exists()  # fully removed, nothing foreign left behind
    assert not (result.skill_dirs[2]).exists()
    assert foreign.is_file()
    assert foreign.read_text(encoding="utf-8") == "do not touch\n"
    assert result.skill_dirs[0].is_dir()  # the foreign file kept it alive


def test_uninstall_of_a_never_installed_triad_is_a_no_op(tmp_path: Path) -> None:
    target = HostTarget(Platform.CLAUDE)
    assert uninstall(target, project=None, home=tmp_path) == []


def test_uninstall_refuses_atomically_when_any_one_skill_was_hand_edited(
    tmp_path: Path,
) -> None:
    """A hand-edit to just one of the three skills refuses the *whole* uninstall — nothing is
    removed from any of the three, not only the edited one."""
    target = HostTarget(Platform.CLAUDE)
    result = install(target, project=None, home=tmp_path)

    edited_dir = result.skill_dirs[1]  # "progress", untouched otherwise
    (edited_dir / "SKILL.md").write_text("hand-edited\n", encoding="utf-8")

    with pytest.raises(ValueError):
        uninstall(target, project=None, home=tmp_path)

    # nothing removed anywhere in the triad, including the two untouched skills
    for skill_dir in result.skill_dirs:
        assert (skill_dir / RECEIPT_NAME).is_file()
    assert (result.skill_dirs[0] / "SKILL.md").is_file()
    assert (result.skill_dirs[2] / "SKILL.md").is_file()


# ---------------------------------------------------------------------------------------- CLI


def test_cli_install_writes_both_conventions_by_default(tmp_path: Path) -> None:
    result = runner.invoke(app, ["install"], env={"HOME": str(tmp_path)})
    assert result.exit_code == 0, result.output
    for name in SKILL_NAMES:
        assert (tmp_path / ".claude" / "skills" / name / "SKILL.md").is_file()
        assert (tmp_path / ".agents" / "skills" / name / "SKILL.md").is_file()
    assert "/learn" in result.stdout
    assert "$learn" in result.stdout


def test_cli_install_platform_flag_narrows_to_one_convention(tmp_path: Path) -> None:
    result = runner.invoke(app, ["install", "--platform", "claude"], env={"HOME": str(tmp_path)})
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".claude" / "skills" / "learn" / "SKILL.md").is_file()
    assert not (tmp_path / ".agents").exists()


def test_cli_install_project_writes_into_the_repo_with_a_git_add_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["install", "--project"],
        env={"HOME": str(tmp_path / "unused-home")},
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".claude" / "skills" / "learn" / "SKILL.md").is_file()
    assert "git add" in result.stdout


def test_cli_reinstall_is_idempotent_and_upgrades_in_place(tmp_path: Path) -> None:
    env = {"HOME": str(tmp_path)}
    first = runner.invoke(app, ["install", "--platform", "claude"], env=env)
    assert first.exit_code == 0, first.output

    skill_md = tmp_path / ".claude" / "skills" / "learn" / "SKILL.md"
    skill_md.write_text("stale content from a previous version\n", encoding="utf-8")

    second = runner.invoke(app, ["install", "--platform", "claude"], env=env)
    assert second.exit_code == 0, second.output

    assert skill_md.read_text(encoding="utf-8") == skill_md_path("learn").read_text(
        encoding="utf-8"
    )


def test_cli_uninstall_removes_exactly_what_was_written_and_keeps_foreign_files(
    tmp_path: Path,
) -> None:
    env = {"HOME": str(tmp_path)}
    installed = runner.invoke(app, ["install"], env=env)
    assert installed.exit_code == 0, installed.output

    claude_dir = tmp_path / ".claude" / "skills" / "learn"
    foreign = claude_dir / "notes.txt"
    foreign.write_text("do not touch\n", encoding="utf-8")

    result = runner.invoke(app, ["uninstall"], env=env)
    assert result.exit_code == 0, result.output

    assert foreign.is_file()
    assert foreign.read_text(encoding="utf-8") == "do not touch\n"
    assert not (claude_dir / "SKILL.md").is_file()
    assert not (claude_dir / RECEIPT_NAME).is_file()
    for name in SKILL_NAMES:
        assert not (tmp_path / ".agents" / "skills" / name).exists()
    assert not (tmp_path / ".claude" / "skills" / "progress").exists()
    assert not (tmp_path / ".claude" / "skills" / "homework").exists()


def test_cli_uninstall_of_nothing_installed_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["uninstall"], env={"HOME": str(tmp_path)})
    assert result.exit_code == 1
