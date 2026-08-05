"""``skilling init`` — the command; the templates it writes live in ``_scaffold``."""

from __future__ import annotations

from pathlib import Path

import typer

from ...conformance import validate_course
from .. import _render as render
from ._scaffold import scaffold


def init(
    target: Path = typer.Argument(..., help="Directory to create the course in."),
    title: str = typer.Option(None, "--title", help="Course title. Defaults from the directory."),
) -> None:
    """Scaffold a conforming course skeleton."""
    if target.exists() and any(target.iterdir()):
        render.err_console.print(f"[red]{target} exists and is not empty.[/]")
        raise typer.Exit(1)

    target.mkdir(parents=True, exist_ok=True)
    written = scaffold(target, title=title)
    for path in written:
        render.console.print(f"[green]created[/] {path}")

    report = validate_course(target)
    render.console.print()
    if report.clean:
        render.console.print("[bold green]The scaffold validates clean.[/] Start editing.")
    else:
        render.findings(report, root=str(target))
    render.console.print(f"\n[dim]Next: skilling deliver {target}[/]")
