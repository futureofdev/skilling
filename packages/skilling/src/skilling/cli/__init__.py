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

from collections.abc import Callable
from functools import wraps
from inspect import signature
from pathlib import Path
from typing import TypeVar

import typer

from .. import __version__
from ..sources import CacheBusy
from ..store import NotSupported, RecoveryRequired, StatePathError, StoreBusy
from ..workspace import ImportRecoveryError, find_workspace, workspace_read
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


COMMANDS: tuple[Callable[..., None], ...] = (
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

_R = TypeVar("_R")


def _workspace_command(function: Callable[..., _R]) -> Callable[..., _R]:
    """Keep each learner command's content reads inside the workspace recovery barrier."""

    @wraps(function)
    def guarded(*args: object, **kwargs: object) -> _R:
        arguments = signature(function).bind(*args, **kwargs).arguments
        ref = arguments.get("course")
        path = Path(ref) if isinstance(ref, (str, Path)) else Path.cwd()
        if not isinstance(ref, Path) and (
            ref is None
            or isinstance(ref, str)
            and not path.is_dir()
            and "/" not in ref
            and "\\" not in ref
        ):
            path = find_workspace() or path
        with workspace_read(path):
            return function(*args, **kwargs)

    return guarded


for _command in COMMANDS:
    if _command in (
        deliver,
        next,
        advance,
        complete,
        ceremony,
        answer,
        courses,
        progress,
        telemetry,
    ):
        app.command()(_workspace_command(_command))
    else:
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
    for _registration in _group[1].registered_commands:
        if _registration.callback is not None:
            _registration.callback = _workspace_command(_registration.callback)
    app.add_typer(_group[1], name=_group[0])


def main() -> None:
    from .runtime import ExitCode, emit

    try:
        app()
    except (ImportRecoveryError, CacheBusy) as exc:
        emit({"ok": False, "error": {"code": "workspace-recovery-required", "message": str(exc)}})
        raise SystemExit(ExitCode.ERROR) from exc
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
