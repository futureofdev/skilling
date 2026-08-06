"""``skilling install`` / ``skilling uninstall`` — writing the bundled ``learn``/``progress``/
``homework`` skill triad into the Claude Code and generic Agent-Skills host conventions, and
removing exactly what was written.

Both platforms by default: no single directory is read by both hosts, so installing
"cross-host" means writing both conventions unless ``--platform`` narrows it. ``--project``
writes into the current directory's ``.claude``/``.agents`` (to commit alongside a course
repo) instead of the learner's home profile. There is no course argument and no ``--name``
override here: the triad's names are fixed, and every learner gets the same three skills.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...skills import SKILL_NAMES, HostTarget, Platform
from ...skills import install as _install
from ...skills import uninstall as _uninstall
from .. import _render as render

ALL_PLATFORMS = tuple(Platform)


def install(
    platform: list[Platform] = typer.Option(
        None,
        "--platform",
        help="Host convention to install into. Repeatable. Defaults to all (claude, agents).",
    ),
    project: bool = typer.Option(
        False,
        "--project",
        help="Write into the current directory's .claude/.agents instead of the home profile.",
    ),
) -> None:
    """Install the bundled learn/progress/homework skill triad into one or both Agent-Skills
    host conventions. Reinstalling upgrades any already-installed copy in place."""
    project_dir = Path.cwd() if project else None
    for chosen in platform or ALL_PLATFORMS:
        target = HostTarget(chosen)
        result = _install(target, project=project_dir, home=Path.home())
        for name, skill_dir in zip(SKILL_NAMES, result.skill_dirs, strict=True):
            invocation = target.invocation(name)
            render.console.print(f"[bold green]installed[/] {skill_dir}  ({invocation})")

    if project_dir is not None:
        render.console.print(
            "[dim]run[/] git add .claude .agents [dim]to track the installed skills.[/]"
        )


def uninstall(
    platform: list[Platform] = typer.Option(
        None,
        "--platform",
        help="Host convention to remove from. Repeatable. Defaults to all (claude, agents).",
    ),
    project: bool = typer.Option(
        False,
        "--project",
        help="Remove from the current directory's .claude/.agents instead of the home profile.",
    ),
) -> None:
    """Remove exactly what ``install`` wrote for the triad, per its receipts, as one atomic
    operation across all three skills. A foreign file left in a skill directory is never
    touched; a receipted file that changed since install stops the whole removal for that
    host, with nothing deleted anywhere in the triad."""
    project_dir = Path.cwd() if project else None
    removed_any = False
    for chosen in platform or ALL_PLATFORMS:
        target = HostTarget(chosen)
        try:
            removed = _uninstall(target, project=project_dir, home=Path.home())
        except ValueError as exc:
            render.err_console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from exc
        if not removed:
            continue
        removed_any = True
        base = target.skills_dir(project=project_dir, home=Path.home())
        touched = sorted({path.relative_to(base).parts[0] for path in removed})
        for name in touched:
            render.console.print(f"[bold green]removed[/] {base / name}")

    if not removed_any:
        render.err_console.print("[yellow]nothing installed[/]")
        raise typer.Exit(1)
