"""The ``skilling`` command line.

Assembly only. Commands live in groups by audience — ``authoring`` for people writing courses,
``learning`` for delivering one, ``packaging`` for fetch and the bundled skill triad's
install/uninstall, ``runtime`` for read-only cross-course queries a driving skill needs — so
that adding a command touches one new module and one line here, rather than a file every other
change also wants to edit.

Groups re-export their commands; this module decides the order they register in, because
registration order is the order ``--help`` lists them and that should be a single deliberate
statement rather than a side effect of import order.
"""

from __future__ import annotations

import typer

from .. import __version__
from ..store import NotSupported, RecoveryRequired, StatePathError, StoreBusy
from . import _render as render
from .authoring import diff, init, show, today, validate
from .learning import deliver
from .packaging import fetch, install, start, uninstall
from .runtime import (
    advance,
    answer,
    artifact,
    ceremony,
    complete,
    courses,
    homework,
    next,
    objective_app,
    progress,
    quiz,
    telemetry,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Tooling for the Skilling course format: validate, scaffold, inspect, deliver.",
)


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


COMMANDS = (
    validate,
    init,
    show,
    deliver,
    diff,
    today,
    next,
    advance,
    complete,
    ceremony,
    answer,
    courses,
    progress,
    telemetry,
    fetch,
    install,
    start,
    uninstall,
)

for _command in COMMANDS:
    app.command()(_command)

GROUPS: tuple[tuple[str, typer.Typer], ...] = (
    ("quiz", quiz),
    ("objective", objective_app),
    ("homework", homework),
    ("artifact", artifact),
)
"""Sub-apps registered as ``skilling <name> ...`` — one line per entry, rather than each
editing this module's imports and registration."""

for _group in GROUPS:
    # Indexed rather than unpacked: pyright narrows an empty tuple literal to `tuple[()]`,
    # whose (nonexistent) element type is Never — destructuring assignment from it is a
    # type error even though the loop body never runs. Indexing sidesteps it; a real entry
    # in GROUPS makes the whole question moot again.
    app.add_typer(_group[1], name=_group[0])


def main() -> None:
    from .runtime import ExitCode, emit

    try:
        app()
    except RecoveryRequired as exc:
        emit({"ok": False, "error": {"code": "recovery-required", "message": str(exc)}})
        raise SystemExit(ExitCode.ERROR) from exc
    except NotSupported as exc:
        emit({"ok": False, "error": {"code": "completion-not-supported", "message": str(exc)}})
        raise SystemExit(ExitCode.ERROR) from exc
    except StoreBusy as exc:
        emit({"ok": False, "error": {"code": "store-busy", "message": str(exc)}})
        raise SystemExit(ExitCode.ERROR) from exc
    except StatePathError as exc:
        emit({"ok": False, "error": {"code": "state-invalid", "message": str(exc)}})
        raise SystemExit(ExitCode.INVALID) from exc


if __name__ == "__main__":
    main()
