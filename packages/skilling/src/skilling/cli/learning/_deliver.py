"""``skilling deliver`` — the command; the loop it walks lives in ``_walk``."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml

from ...conformance import validate_course
from ...course import Course, CourseLoadError
from ...delivery import Dispatcher, parse_sink, set_telemetry_consent
from ...store import (
    LOCAL_LEARNER,
    FileProgressStore,
    NotSupported,
    RecoveryRequired,
    StatePathError,
)
from ...workspace import resolve_state_root
from .. import _render as render
from ._walk import Walker


def deliver(
    course: Path = typer.Argument(..., help="Path to the course directory."),
    state: Path | None = typer.Option(
        None,
        "--state",
        envvar="SKILLING_STATE_ROOT",
        help="Where to keep the learner's progress record. Defaults to the enclosing "
        "workspace's state, or ~/.skilling/state outside one.",
    ),
    learner: str = typer.Option(LOCAL_LEARNER, "--learner", help="Learner id for the record."),
    zone: str = typer.Option("UTC", "--timezone", help="IANA timezone for streak dates."),
    sink: list[str] = typer.Option(
        None,
        "--sink",
        help="First-party hook sink, inside your trust boundary. e.g. jsonl:events.jsonl",
    ),
    telemetry_sink: list[str] = typer.Option(
        None,
        "--telemetry-sink",
        help="Sink that leaves your trust boundary. Consent-gated and anonymised.",
    ),
    no_telemetry: bool = typer.Option(
        False, "--no-telemetry", help="Record a decline without asking, and send nothing."
    ),
) -> None:
    """Walk the delivery loop. A Conforming Runtime — no language model involved."""
    try:
        report = validate_course(course)
        resolved = Course.load(course)
    except CourseLoadError as exc:
        render.err_console.print(f"[red]{exc.code}[/] {exc.message}")
        raise typer.Exit(1) from exc
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        render.err_console.print(f"[red]course-invalid[/] Cannot read course: {type(exc).__name__}")
        raise typer.Exit(1) from exc

    if not report.ok:
        render.err_console.print(
            f"[red]This course does not conform ({len(report.errors)} error(s)).[/] "
            f"Run: skilling validate {course}"
        )
        raise typer.Exit(1)

    try:
        first_party = [parse_sink(spec) for spec in (sink or [])]
        telemetry = [] if no_telemetry else [parse_sink(spec) for spec in (telemetry_sink or [])]
    except ValueError as exc:
        render.err_console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc

    try:
        store = FileProgressStore(resolve_state_root(state), learner_id=learner)
        store.ensure_course_paths(resolved.id)
    except StatePathError as exc:
        render.err_console.print(f"[red]state-invalid[/] {exc}")
        raise typer.Exit(1) from exc

    dispatcher = Dispatcher(first_party=first_party, telemetry=telemetry)
    try:
        walker = Walker(
            resolved,
            store,
            learner_id=learner,
            console=render.console,
            zone=zone,
            hooks=dispatcher,
            ask_consent=not no_telemetry,
        )
        code = walker.run()
        if no_telemetry and walker.record.telemetry.opt_in is None:
            set_telemetry_consent(store, walker.record, walker.revision, False)
    except StatePathError as exc:
        render.err_console.print(f"[red]state-invalid[/] {exc}")
        raise typer.Exit(1) from exc
    except RecoveryRequired as exc:
        render.err_console.print(f"[red]recovery-required[/] {exc}")
        raise typer.Exit(1) from exc
    except NotSupported as exc:
        render.err_console.print(f"[red]completion-not-supported[/] {exc}")
        raise typer.Exit(1) from exc
    finally:
        dispatcher.close()
    raise typer.Exit(code)
