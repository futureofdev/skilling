"""``skilling fetch`` — the command; resolution itself lives in ``sources``."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ...conformance import Report
from ...sources import CACHE_ENV, CourseInvalid, ResolveError, resolve
from .. import _render as render


def fetch(
    ref: str = typer.Argument(
        ..., help="Course ref: a path, gh:owner/repo[@ref], git+ssh:, or https:."
    ),
    cache: Path = typer.Option(
        None, "--cache", envvar=CACHE_ENV, help="Where fetched courses are cached."
    ),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output for CI."),
) -> None:
    """Resolve a course ref: fetch if remote, validate, cache. Prints where it landed."""
    try:
        resolved = resolve(ref, cache=cache)
    except CourseInvalid as exc:
        report = Report(exc.findings)
        if as_json:
            render.findings_json(report)
        else:
            render.findings(report, root=ref)
        raise typer.Exit(1) from exc
    except ResolveError as exc:
        render.err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc

    if as_json:
        render.console.print_json(
            json.dumps(
                {
                    "id": resolved.course.id,
                    "version": resolved.course.version,
                    "path": str(resolved.path),
                    "ref": resolved.ref,
                    "pinned": resolved.pinned,
                }
            )
        )
    else:
        pinned = f" pinned to {resolved.pinned}" if resolved.pinned else ""
        render.console.print(
            f"[green]{resolved.course.id}@{resolved.course.version}[/]{pinned} → {resolved.path}"
        )
