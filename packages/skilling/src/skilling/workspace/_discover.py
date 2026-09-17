"""Finding the enclosing workspace: git's model, keyed on the manifest.

Walk up from the starting directory until a directory holding ``.skilling/workspace.yaml``
appears; the nearest one wins, and running out of parents means there is no workspace — a
normal state, not an error. Discovery keys on the manifest existing, never on a bare
``.skilling/`` directory, so a stray legacy state directory is never mistaken for a workspace
(spec/workspace.md#discovery).
"""

from __future__ import annotations

import os
from pathlib import Path

from ._layout import manifest_path
from ._recovery import recover_workspace

WORKSPACE_ENV = "SKILLING_WORKSPACE"
"""Overrides the *start point* of the walk, not its answer: pointing it anywhere inside a
workspace finds that workspace's root."""


def find_workspace(start: Path | None = None) -> Path | None:
    """The nearest enclosing workspace root, or None. ``start`` defaults to the current
    directory; ``SKILLING_WORKSPACE``, when set, overrides either."""
    configured = os.environ.get(WORKSPACE_ENV)
    fallback = start if start is not None else Path.cwd()
    origin = Path(configured) if configured else fallback
    current = origin.resolve()
    for candidate in (current, *current.parents):
        if any(
            p.exists() or p.is_symlink()
            for p in (manifest_path(candidate), candidate / ".skilling/import.yaml")
        ):
            recover_workspace(candidate)
            if manifest_path(candidate).is_file():
                return candidate
    return None
