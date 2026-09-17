"""Growing a workspace: creating it, importing a local course into it, and upserting the
manifest entry a course needs to be found there again (spec/workspace.md#the-layout,
#the-manifest, #showcase).

Local courses are copied rather than referenced in place. This is deliberately unrelated to
``sources``' own rule that a local ref is never cached: that rule protects the *shared* fetch
cache from filling with one-off local content. A workspace is not shared — it is exactly what
gets zipped and mounted into a sandboxed host — so a manifest entry pointing at
``/Users/me/dev/my-course`` would be dead on arrival there. Copying gives the workspace its
own portable copy, same as everything else under it. ``import_local_course`` reuses
``sources.CourseInvalid``/``UnknownRef`` rather than inventing parallel exception types: to a
caller, resolving a local ref and resolving a remote one should fail the same way.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import NamedTuple

from ..conformance import validate_course
from ..course import Course, utc_now
from ..sources import CourseInvalid, ResolveError, UnknownRef
from ._layout import (
    SKILLING_DIR,
    courses_dir,
    load_manifest,
    manifest_path,
    save_manifest,
    showcase_dir,
)
from ._manifest import WorkspaceCourse, WorkspaceManifest
from ._recovery import (
    _ref,
    claim_staging,
    publish_import,
    recover_workspace,
    remove_owned_tree,
    workspace_lock,
)

README_NAME = "README.md"


class ImportedCourse(NamedTuple):
    course: Course
    path: Path
    """Where the copy landed: ``<workspace>/.skilling/courses/<id>@<version>/``."""


def ensure_workspace(dir: Path) -> Path:
    """Make ``dir`` a workspace if it is not already one: create the directory and an empty
    manifest. An existing workspace is left exactly as it is — this only ever grows one, it
    never resets it. Returns ``dir``."""
    dir.mkdir(parents=True, exist_ok=True)
    with workspace_lock(dir):
        if not manifest_path(dir).is_file():
            save_manifest(dir, WorkspaceManifest())
    return dir


def _validated_course(path: Path) -> Course:
    report = validate_course(path)
    if not report.clean:
        raise CourseInvalid(
            f"{path} does not conform to the format ({len(report.findings)} finding(s))",
            findings=report.findings,
        )
    return Course.load(path)


def validate_local_import(ws: Path, path: Path) -> ImportedCourse:
    """Validate input and containment before creating any workspace directories."""
    if (ws / SKILLING_DIR / "import.yaml").exists():
        recover_workspace(ws)
    if not path.is_dir():
        raise UnknownRef(f"not a recognised ref, and no local directory at {path}")
    path, ws = path.resolve(), ws.resolve()
    course = _validated_course(path)
    content_root = courses_dir(ws)
    destination = content_root / f"{course.id}@{course.version}"
    if any(p.is_symlink() for p in (ws / SKILLING_DIR, content_root, destination)):
        raise ResolveError("workspace course destination must not be a symlink")
    if path != destination.resolve() and (
        destination.is_relative_to(path) or path.is_relative_to(destination)
    ):
        raise ResolveError("course source and workspace content destination overlap")
    if any(p.is_symlink() for p in path.rglob("*")):
        raise ResolveError("course content contains a symlink; import a standalone course tree")
    if destination.exists() and not destination.is_dir():
        raise ResolveError(f"course destination is not a directory: {destination}")
    return ImportedCourse(course, destination)


def _updated_manifest(ws: Path, course: Course, ref: str, path: Path) -> WorkspaceManifest:
    manifest = load_manifest(ws) if manifest_path(ws).is_file() else WorkspaceManifest()
    existing = manifest.course(course.id)
    entry = WorkspaceCourse(
        id=course.id,
        version=course.version,
        ref=_ref(ref),
        path=path.relative_to(ws / SKILLING_DIR).as_posix(),
        showcase=showcase_dir(ws, course.id).relative_to(ws).as_posix(),
        added_at=existing.added_at if existing is not None else utc_now(),
    )
    return WorkspaceManifest(courses=[*[c for c in manifest.courses if c.id != course.id], entry])


def import_local_course(ws: Path, path: Path, *, ref: str | None = None) -> ImportedCourse:
    """Publish a validated local copy and its manifest as one recoverable operation."""
    checked = validate_local_import(ws, path)
    path, ws = path.resolve(), ws.resolve()
    with workspace_lock(ws):
        checked = validate_local_import(ws, path)
        destination = checked.path
        supplied_ref = ref if ref is not None else str(path)
        if path == destination.resolve():
            save_manifest(ws, _updated_manifest(ws, checked.course, supplied_ref, destination))
            return checked
        content_root = courses_dir(ws)
        content_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".skilling-import-", dir=content_root))
        candidate = staging / "course"
        try:
            claim_staging(staging)
            shutil.copytree(path, candidate)
            copied = _validated_course(candidate)
            if (copied.id, copied.version) != (checked.course.id, checked.course.version):
                raise ResolveError(
                    "course identity changed during import; retry with a stable source"
                )
            manifest = _updated_manifest(ws, copied, supplied_ref, destination)
            publish_import(ws, candidate, destination, manifest)
        finally:
            # Once intent exists, its copies belong to recovery, including caught failures.
            if not (ws / SKILLING_DIR / "import.yaml").exists() and staging.exists():
                remove_owned_tree(staging)
        return ImportedCourse(course=Course.load(destination), path=destination)


def add_course(ws: Path, course: Course, ref: str, path: Path) -> WorkspaceCourse:
    """Upsert ``course``'s manifest entry — a course already in the manifest is replaced,
    never duplicated — and ensure its ``showcase/<id>/`` exists with a starter README.
    ``path`` is where the content now lives, already inside ``.skilling/``.

    ``added_at`` is preserved across an upsert of the same course id: it records when the
    course first joined this workspace, not when it was last refreshed, so a re-run stays
    byte-identical rather than drifting a timestamp forward every time.
    """
    with workspace_lock(ws):
        manifest = _updated_manifest(ws, course, ref, path)
        save_manifest(ws, manifest)
        entry = manifest.course(course.id)
        assert entry is not None

    showcase = showcase_dir(ws, course.id)
    showcase.mkdir(parents=True, exist_ok=True)
    readme = showcase / README_NAME
    if not readme.is_file():
        readme.write_text(
            f"Work you produce for {course.manifest.title} goes here.\n", encoding="utf-8"
        )

    return entry
