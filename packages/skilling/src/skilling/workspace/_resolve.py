"""Where a runtime verb finds state and course content by default when the learner does not
say, spec/workspace.md#the-state-root.

Two independent resolutions, both keyed on the nearest enclosing workspace (``_discover``):

- the state root every verb reads and writes absent ``--state`` — explicit flag, then
  ``$SKILLING_STATE_ROOT``, then the workspace's own ``.skilling/state``, then the learner's
  home default (``store.default_state_root``). Steps one and two are ordinarily already
  merged by typer's own ``envvar=`` wiring on ``--state`` before either resolver here runs;
  the environment is checked again so a caller that builds a session without going through
  typer gets the identical precedence.
- a course *id* given to ``--course`` in place of a path, resolved through the workspace
  manifest to the content it points at — so a verb run from anywhere inside a workspace never
  needs the content's path re-stated.

Neither reads nor writes learner state or course content itself: this module only decides
where the store and the course loader should look.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..course import is_course_id
from ..store import default_state_root
from ._discover import find_workspace
from ._layout import SKILLING_DIR, load_manifest, state_root

STATE_ROOT_ENV = "SKILLING_STATE_ROOT"
"""Mirrors ``store._select.STATE_ROOT_ENV`` — duplicated rather than imported, since that
name is private to the store package and this module resolves precedence *around* it, not
inside it (the same deliberate two-line duplicate ``cli/runtime/_courses.py`` already makes
for the fetch-cache env var)."""


def resolve_state_root(explicit: Path | None) -> Path:
    """``explicit``, else ``$SKILLING_STATE_ROOT``, else the enclosing workspace's own
    ``.skilling/state``, else the learner's home default — the one precedence every runtime
    verb uses."""
    if explicit is not None:
        return explicit
    configured = os.environ.get(STATE_ROOT_ENV)
    if configured:
        return Path(configured)
    workspace = find_workspace()
    if workspace is not None:
        return state_root(workspace)
    return default_state_root()


def resolve_course_location(ref: str) -> Path | None:
    """``ref`` as a course id inside the enclosing workspace, resolved to where its content
    was fetched — ``None`` when ``ref`` is not a course id, there is no enclosing workspace,
    or that workspace never added a course by this id. Callers try ``ref`` as a directory
    first; this is only the fallback for a bare id in place of a path."""
    if not is_course_id(ref):
        return None
    workspace = find_workspace()
    if workspace is None:
        return None
    try:
        manifest = load_manifest(workspace)
    except FileNotFoundError:
        return None
    entry = manifest.course(ref)
    if entry is None:
        return None
    return workspace / SKILLING_DIR / entry.path
