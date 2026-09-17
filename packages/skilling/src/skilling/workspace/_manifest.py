"""The workspace manifest: which courses live in this workspace, and where.

``.skilling/workspace.yaml`` is what makes a folder a workspace (spec/workspace.md#the-manifest):
discovery keys on it existing, and it records the one fact progress state alone deliberately
never holds — where each course's content lives. Every path in it is relative, so zipping or
syncing the folder into a sandboxed host carries everything the manifest points at.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from ..course import Strict, is_course_id, is_semver, require_relative_posix


class WorkspaceCourse(Strict):
    """One course a learner added to the workspace."""

    id: str
    version: str
    ref: str = Field(min_length=1)
    """Source provenance: local paths and GitHub refs retain their spelling; newly persisted
    remote URLs omit credentials and query secrets. Legacy recovery before-images retain exact
    historical bytes. Provenance alone is exempt from the relative-paths rule."""

    path: str
    """Where the content lives, relative to ``.skilling/``."""

    showcase: str
    """The course's visible output directory, relative to the workspace root."""

    added_at: datetime

    @field_validator("id")
    @classmethod
    def _course_id(cls, v: str) -> str:
        if not is_course_id(v):
            raise ValueError(f"{v!r} is not a course id")
        return v

    @field_validator("version")
    @classmethod
    def _semver(cls, v: str) -> str:
        if not is_semver(v):
            raise ValueError(f"{v!r} is not a semantic version")
        return v

    @field_validator("path", "showcase")
    @classmethod
    def _relative(cls, v: str) -> str:
        return require_relative_posix(v)


class WorkspaceManifest(Strict):
    """The document at ``.skilling/workspace.yaml``. An empty ``courses`` list is a normal
    state — a workspace that exists but has had nothing added yet."""

    courses: list[WorkspaceCourse] = Field(default_factory=list)

    def course(self, course_id: str) -> WorkspaceCourse | None:
        for candidate in self.courses:
            if candidate.id == course_id:
                return candidate
        return None
