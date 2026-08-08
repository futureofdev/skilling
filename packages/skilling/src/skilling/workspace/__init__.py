"""The learner workspace: one folder, opened in any Agent-Skills host, holding everything a
tutored course needs — the machinery hidden under ``.skilling/``, a visible root that grows
with what the learner builds. Layout, manifest, and discovery per spec/workspace.md.

Nothing here reads or writes learner state itself: the workspace re-points where the store
and the fetch cache already operate, it does not fork either.
"""

from ._discover import WORKSPACE_ENV, find_workspace
from ._layout import (
    COURSES_DIR,
    MANIFEST_NAME,
    SHOWCASE_DIR,
    SKILLING_DIR,
    STATE_DIR,
    courses_dir,
    load_manifest,
    manifest_path,
    save_manifest,
    showcase_dir,
    state_root,
)
from ._manifest import WorkspaceCourse, WorkspaceManifest

__all__ = [
    "COURSES_DIR",
    "MANIFEST_NAME",
    "SHOWCASE_DIR",
    "SKILLING_DIR",
    "STATE_DIR",
    "WORKSPACE_ENV",
    "WorkspaceCourse",
    "WorkspaceManifest",
    "courses_dir",
    "find_workspace",
    "load_manifest",
    "manifest_path",
    "save_manifest",
    "showcase_dir",
    "state_root",
]
