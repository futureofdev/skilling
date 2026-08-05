"""The ``skilling`` command line.

Assembly only. Commands live in groups by audience — ``authoring`` for people writing courses,
``learning`` for delivering one, ``packaging`` for turning a course into an installable Agent
Skill — so that adding a command touches one new module and one line here, rather than a file
every other change also wants to edit.

Groups re-export their commands; this module decides the order they register in, because
registration order is the order ``--help`` lists them and that should be a single deliberate
statement rather than a side effect of import order.
"""

from __future__ import annotations

import typer

from .. import __version__
from . import _render as render
from .authoring import diff, init, show, today, validate
from .learning import deliver
from .packaging import pack

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


COMMANDS = (validate, init, show, deliver, diff, today, pack)

for _command in COMMANDS:
    app.command()(_command)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
