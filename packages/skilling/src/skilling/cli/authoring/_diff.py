"""``skilling diff`` — what changed between two course versions, and whether the bump covers it."""

from __future__ import annotations

from pathlib import Path

import typer

from ...course import CourseLoadError, compare_paths
from .. import _render as render


def diff(
    old: Path = typer.Argument(..., help="The published course version."),
    new: Path = typer.Argument(..., help="The candidate course version."),
    strict: bool = typer.Option(
        False, "--strict", help="Exit non-zero when the declared bump is insufficient."
    ),
) -> None:
    """Classify the change between two course versions and check coordinate stability."""
    try:
        result = compare_paths(old, new)
    except CourseLoadError as exc:
        render.err_console.print(f"[red]{exc.code}[/] {exc.message}")
        raise typer.Exit(1) from exc

    render.diff_summary(result)
    raise typer.Exit(1 if strict and not result.satisfied else 0)
