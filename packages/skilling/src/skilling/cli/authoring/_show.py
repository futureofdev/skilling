"""``skilling show`` — the resolved structure, and every count derived rather than authored."""

from __future__ import annotations

from pathlib import Path

import typer

from ...course import Course, CourseLoadError
from ...store import LOCAL_LEARNER, FileProgressStore
from .. import _render as render


def show(
    course: Path = typer.Argument(..., help="Path to the course directory."),
    state: Path = typer.Option(
        None, "--state", help="Progress state root, to show a learner's position too."
    ),
) -> None:
    """Print the resolved structure and every derived count."""
    try:
        resolved = Course.load(course)
    except CourseLoadError as exc:
        render.err_console.print(f"[red]{exc.code}[/] {exc.message}")
        raise typer.Exit(1) from exc

    completed: list[str] = []
    if state:
        store = FileProgressStore(state)
        found = store.get_record(LOCAL_LEARNER, resolved.id)
        if found:
            completed = found[0].completed
    render.course_summary(resolved, completed=completed)
