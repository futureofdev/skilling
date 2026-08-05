"""``skilling today`` — the unit the streak algorithm counts in, made inspectable."""

from __future__ import annotations

import typer

from ...delivery import today_in
from .. import _render as render


def today(zone: str = typer.Option("UTC", "--timezone")) -> None:
    """Print today's date in a timezone — the unit the streak algorithm counts in."""
    render.console.print(str(today_in(zone)))
