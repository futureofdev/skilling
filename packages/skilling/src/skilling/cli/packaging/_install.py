"""``skilling install`` / ``skilling uninstall`` — writing a generated pack into the Claude
Code and generic Agent-Skills host conventions, and removing exactly what was written.

Both platforms by default: no single directory is read by both hosts, so installing
"cross-host" means writing both conventions unless ``--platform`` narrows it. ``--project``
writes into the current directory's ``.claude``/``.agents`` (to commit alongside a course
repo) instead of the user's home profile.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...course import Course, CourseLoadError
from ...pack import HostTarget, Pack, PackRefused, Platform
from ...pack import install as _install
from ...pack import uninstall as _uninstall
from .. import _render as render

ALL_PLATFORMS = tuple(Platform)


def install(
    course: Path = typer.Argument(..., help="Path to the course directory."),
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
    name: str = typer.Option(
        None, "--name", help="Override the skill name. Defaults to the course id."
    ),
) -> None:
    """Generate the Agent Skill pack for COURSE and install it into one or both Agent-Skills
    host conventions."""
    try:
        resolved = Course.load(course)
    except CourseLoadError as exc:
        render.err_console.print(f"[red]{exc.code}[/] {exc.message}")
        raise typer.Exit(1) from exc

    try:
        generated = Pack.generate(resolved, name=name)
    except PackRefused as exc:
        for finding in exc.findings:
            render.err_console.print(f"[red]{finding.code}[/] {finding.message}")
        raise typer.Exit(1) from exc
    except ValueError as exc:
        render.err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc

    project_dir = Path.cwd() if project else None
    for chosen in platform or ALL_PLATFORMS:
        target = HostTarget(chosen)
        result = _install(generated, target, project=project_dir, home=Path.home())
        invocation = target.invocation(generated.name)
        render.console.print(f"[bold green]installed[/] {result.skill_dir}  ({invocation})")

    if project_dir is not None:
        render.console.print(
            "[dim]run[/] git add .claude .agents [dim]to track the installed skill.[/]"
        )


def uninstall(
    name: str = typer.Argument(..., help="Installed skill name to remove."),
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
    """Remove exactly what ``install`` wrote for NAME, per its receipt. A foreign file left in
    the skill directory is never touched; a receipted file that changed since install stops
    the whole removal for that host, with nothing deleted."""
    project_dir = Path.cwd() if project else None
    removed_any = False
    for chosen in platform or ALL_PLATFORMS:
        target = HostTarget(chosen)
        try:
            removed = _uninstall(name, target, project=project_dir, home=Path.home())
        except ValueError as exc:
            render.err_console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from exc
        if removed:
            removed_any = True
            skill_dir = target.skills_dir(project=project_dir, home=Path.home()) / name
            render.console.print(f"[bold green]removed[/] {skill_dir}")

    if not removed_any:
        render.err_console.print(f"[yellow]nothing installed for {name!r}[/]")
        raise typer.Exit(1)
