"""Where everything in a workspace lives.

The layout is specified (spec/workspace.md#the-layout) so any implementation can find any
learner's workspace: the machinery hides under ``.skilling/`` while the visible root grows
with what the learner builds. ``.skilling/state`` is a ``<state-root>`` exactly as
spec/runtime.md#the-file-layout binds it — re-pointed, not forked — and ``.skilling/courses``
uses the fetch cache's own ``<id>@<version>`` naming, so state and content are structurally
disjoint subtrees and a course id in one can never collide with a keyed directory in the other.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..course import is_course_id
from ._manifest import WorkspaceManifest

SKILLING_DIR = ".skilling"
MANIFEST_NAME = "workspace.yaml"
STATE_DIR = "state"
COURSES_DIR = "courses"
SHOWCASE_DIR = "showcase"


def manifest_path(workspace: Path) -> Path:
    return workspace / SKILLING_DIR / MANIFEST_NAME


def state_root(workspace: Path) -> Path:
    """The workspace's ``<state-root>``, readable by any conforming runtime unchanged."""
    return workspace / SKILLING_DIR / STATE_DIR


def courses_dir(workspace: Path) -> Path:
    """Fetched course content, one ``<id>@<version>`` directory per resolved course —
    ``sources``' cache layout, re-pointed inside the workspace."""
    return workspace / SKILLING_DIR / COURSES_DIR


def showcase_dir(workspace: Path, course_id: str) -> Path:
    """The one visible per-course output directory, ``showcase/<course-id>/``. Guarded the
    same way the cache guards its keys: a non-id must not become a path segment."""
    if not is_course_id(course_id):
        raise ValueError(f"not a course id: {course_id!r}")
    return workspace / SHOWCASE_DIR / course_id


def load_manifest(workspace: Path) -> WorkspaceManifest:
    """The manifest as it stands. Raises ``FileNotFoundError`` when the folder is not a
    workspace at all — callers who are unsure should discover first, not probe with this."""
    text = manifest_path(workspace).read_text(encoding="utf-8")
    return WorkspaceManifest.model_validate(yaml.safe_load(text) or {})


def save_manifest(workspace: Path, manifest: WorkspaceManifest) -> None:
    path = manifest_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        manifest.model_dump(mode="json"), sort_keys=False, allow_unicode=True, width=100
    )
    path.write_text(text, encoding="utf-8")
