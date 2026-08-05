"""``skilling pack`` — generate a conforming Agent Skill from a validated course."""

from __future__ import annotations

from pathlib import Path

import typer

from ...course import Course, CourseLoadError
from ...pack import Pack, PackRefused, audit, write_pack
from .. import _render as render


def pack(
    course: Path = typer.Argument(..., help="Path to the course directory."),
    out: Path = typer.Option(
        Path("packs"), "--out", help="Directory to write the pack into, as <out>/<name>."
    ),
    name: str = typer.Option(
        None, "--name", help="Override the skill/directory name. Defaults to the course id."
    ),
    check: bool = typer.Option(
        False, "--check", help="Verify the pack already at <out>/<name> is current; write nothing."
    ),
) -> None:
    """Generate (or check) the Agent Skill pack for a course. Exits non-zero on any problem:
    a course that fails to load, one that fails to validate, or — with ``--check`` — a pack
    that is missing, stale, or has drifted from the course it claims to describe."""
    try:
        resolved = Course.load(course)
    except CourseLoadError as exc:
        render.err_console.print(f"[red]{exc.code}[/] {exc.message}")
        raise typer.Exit(1) from exc

    if check:
        pack_dir = out / (name or resolved.id)
        if not pack_dir.is_dir():
            render.err_console.print(
                f"[red]no pack at {pack_dir}[/] — run without --check to generate it."
            )
            raise typer.Exit(1)
        findings = audit(pack_dir, resolved)
        for finding in findings:
            render.err_console.print(f"[yellow]{finding.rule}[/] {finding.path}: {finding.message}")
        if findings:
            raise typer.Exit(1)
        render.console.print(f"[bold green]{pack_dir}: current[/] — no findings.")
        return

    try:
        generated = Pack.generate(resolved, name=name)
    except PackRefused as exc:
        for finding in exc.findings:
            render.err_console.print(f"[red]{finding.code}[/] {finding.message}")
        raise typer.Exit(1) from exc
    except ValueError as exc:
        render.err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc

    written = write_pack(generated, out)
    render.console.print(f"[bold green]wrote[/] {written}")
