"""Shared plumbing for this group's read-only verbs: how a refusal is reported, and the one
JSON-envelope contract every verb here uses.

Deliberately small: ``courses`` is the first verb in this group, so this carries only what it
needs — no ``Session``, no scratch, no course-loading (there is no single course to load; that
is the entire point of an enumeration verb). The JSON transition verbs (``next``, ``advance``,
``progress``, ...) already exist on their own in-flight branches with a richer ``_common.py``
of the same name and contract; when they land here, their additions merge in over this one
rather than replacing it.
"""

from __future__ import annotations

import json
import sys
from enum import IntEnum
from typing import NoReturn

import typer


class ExitCode(IntEnum):
    """Process exit codes this group's verbs use. Stable — a driving pack switches on these."""

    OK = 0
    ERROR = 1


def emit(payload: dict[str, object]) -> None:
    """The one and only way any verb in this group writes to stdout: one JSON object, one line."""
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")


def fail(code: ExitCode, error: str, message: str) -> NoReturn:
    emit({"ok": False, "error": {"code": error, "message": message}})
    raise typer.Exit(code)
