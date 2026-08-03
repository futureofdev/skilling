"""The ``skilling`` command line."""

from __future__ import annotations

from pathlib import Path

import typer

from .. import __version__
from ..diff import compare_paths
from ..loader import CourseLoadError, load_course
from ..runtime import today_in
from ..store import FileProgressStore
from ..store.file import LOCAL_LEARNER
from ..validate import validate_course
from . import render
from .scaffold import scaffold
from .walk import Walker

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Tooling for the Skilling course format: validate, scaffold, inspect, deliver.",
)

DEFAULT_STATE = Path(".skilling")


def _version(value: bool) -> None:
    if value:
        from .. import SPEC_VERSION

        render.console.print(f"skilling {__version__} · specification {SPEC_VERSION}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Show versions and exit."
    ),
) -> None:
    pass


@app.command()
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


@app.command()
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


@app.command()
def show(
    course: Path = typer.Argument(..., help="Path to the course directory."),
    state: Path = typer.Option(
        None, "--state", help="Progress state root, to show a learner's position too."
    ),
) -> None:
    """Print the resolved structure and every derived count."""
    try:
        resolved = load_course(course)
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


@app.command()
def deliver(
    course: Path = typer.Argument(..., help="Path to the course directory."),
    state: Path = typer.Option(
        DEFAULT_STATE, "--state", help="Where to keep the learner's progress record."
    ),
    learner: str = typer.Option(LOCAL_LEARNER, "--learner", help="Learner id for the record."),
    zone: str = typer.Option("UTC", "--timezone", help="IANA timezone for streak dates."),
) -> None:
    """Walk the delivery loop. A Conforming Runtime — no language model involved."""
    try:
        resolved = load_course(course)
    except CourseLoadError as exc:
        render.err_console.print(f"[red]{exc.code}[/] {exc.message}")
        raise typer.Exit(1) from exc

    report = validate_course(course)
    if not report.ok:
        render.err_console.print(
            f"[red]This course does not conform ({len(report.errors)} error(s)).[/] "
            f"Run: skilling validate {course}"
        )
        raise typer.Exit(1)

    store = FileProgressStore(state, learner_id=learner)
    walker = Walker(resolved, store, learner_id=learner, console=render.console, zone=zone)
    raise typer.Exit(walker.run())


@app.command()
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


@app.command()
def today(zone: str = typer.Option("UTC", "--timezone")) -> None:
    """Print today's date in a timezone — the unit the streak algorithm counts in."""
    render.console.print(str(today_in(zone)))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
