"""``skilling validate`` — the Conforming Course check."""

from __future__ import annotations

from pathlib import Path

import typer

from ...conformance import validate_course
from .. import _render as render


def validate(
    course: Path = typer.Argument(..., help="Path to the course directory."),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output for CI."),
    strict: bool = typer.Option(
        False, "--strict", help="Treat warnings as failures as well as errors."
    ),
) -> None:
    """Check a course against the format. Exits non-zero when it does not conform."""
    report = validate_course(course)
    if as_json:
        render.findings_json(report)
    else:
        render.findings(report, root=str(course))

    failed = not report.ok or (strict and report.warnings)
    raise typer.Exit(1 if failed else 0)
