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

Neither writes learner state or course content. Course discovery reads manifests to verify
that the location still identifies the requested course before a session uses it.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from ..course import CourseLoadError, is_course_id
from ..course import load_manifest as load_course_manifest
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


def resolve_course_location(ref: str, *, version: str | None = None) -> Path | None:
    """``ref`` as a course id inside the enclosing workspace, resolved to where its content
    was fetched — ``None`` when ``ref`` is not a course id, there is no enclosing workspace,
    or its entry cannot load a matching course manifest. ``version`` additionally restricts
    discovery to the version a progress record names. Callers try ``ref`` as a directory
    first; this is only the fallback for a bare id in place of a path. Never substitutes
    cached content for an unusable workspace entry."""
    if not is_course_id(ref):
        return None
    workspace = find_workspace()
    if workspace is None:
        return None
    try:
        manifest = load_manifest(workspace)
    except (OSError, ValueError, yaml.YAMLError):
        return None
    entry = manifest.course(ref)
    if entry is None or (version is not None and entry.version != version):
        return None
    candidate = workspace / SKILLING_DIR / entry.path
    try:
        course = load_course_manifest(candidate)
    except (CourseLoadError, OSError, UnicodeError):
        return None
    if course.id != entry.id or course.version != entry.version:
        return None
    return candidate
