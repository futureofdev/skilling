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

What gets copied is a payload computed once and checked before copying: inside a Git work
tree it is the tracked files under the course (the same payload a Git fetch yields), so a
git-ignored ``.venv`` or build output never travels; elsewhere it is the directory minus
``EXCLUDED_NAMES``. Either way a symlink in the payload is refused by name, never followed.
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from ..conformance import validate_course
from ..course import Course, utc_now
from ..sources import CacheInvalid, CourseInvalid, ResolveError, UnknownRef, tracked_payload
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

EXCLUDED_NAMES = frozenset({".git", ".venv", "__pycache__"})
"""Skipped, at any depth and of any kind, when a local course is not tracked by Git. Each is
never course content and routinely present: ``.git`` is version-control metadata (a Git fetch
drops it too); ``.venv`` is the environment ``uv`` and ``python -m venv`` create by default
and holds interpreter symlinks by construction; ``__pycache__`` is bytecode Python writes
whenever an answer key runs. Deliberately small — anything else beside the course is copied,
and refused if it is a symlink — because a guessed exclusion silently drops author content."""


class ImportedCourse(NamedTuple):
    course: Course
    path: Path
    """Where the copy landed: ``<workspace>/.skilling/courses/<id>@<version>/``."""


class _CheckedImport(NamedTuple):
    course: Course
    path: Path
    payload: tuple[str, ...]
    """Relative POSIX file paths to copy — the exact list the symlink check ran over."""


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


def _plain_directory(path: Path) -> bool:
    """True for a plain directory, False for a regular file; anything else — a symlink, a
    Windows junction, a device — is refused, naming the path."""
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or (
        info.st_file_attributes & 0x400 if os.name == "nt" else False
    ):
        raise ResolveError(f"course content contains a symlink, which is never followed: {path}")
    if stat.S_ISDIR(info.st_mode):
        return True
    if stat.S_ISREG(info.st_mode):
        return False
    raise ResolveError(f"course content contains an unsupported file kind: {path}")


def _walked_payload(root: Path) -> tuple[str, ...]:
    files: list[str] = []

    def walk(directory: Path) -> None:
        for child in sorted(directory.iterdir(), key=lambda p: p.name):
            if child.name in EXCLUDED_NAMES:
                continue
            if _plain_directory(child):
                walk(child)
            else:
                files.append(child.relative_to(root).as_posix())

    walk(root)
    return tuple(files)


def _tracked_files(root: Path, tracked: tuple[str, ...]) -> tuple[str, ...]:
    """Tracked files present in the work tree. A tracked file deleted but not yet committed is
    left out, as the author's working copy has it; every directory on the way to a present
    one is checked too, so a directory swapped for a symlink is refused rather than walked."""
    checked: set[Path] = set()
    present: list[str] = []
    for name in tracked:
        target = root / name
        try:
            for parent in reversed(target.relative_to(root).parents[:-1]):
                if root / parent not in checked:
                    if not _plain_directory(root / parent):
                        raise ResolveError(
                            f"course content path is not a directory: {root / parent}"
                        )
                    checked.add(root / parent)
            if _plain_directory(target):
                raise ResolveError(f"tracked course file is a directory: {target}")
        except FileNotFoundError:
            continue
        present.append(name)
    return tuple(present)


def _local_payload(path: Path) -> tuple[str, ...]:
    try:
        tracked = tracked_payload(path)
    except CacheInvalid as error:
        raise ResolveError(f"{path}: {error}") from None
    if tracked is not None and tracked.files:
        return _tracked_files(path, tracked.files)
    # Outside Git, or a course Git tracks nothing of (a home-directory dotfiles repository).
    return _walked_payload(path)


def _payload_filter(root: Path, payload: tuple[str, ...]) -> Callable[[str, list[str]], set[str]]:
    keep = set(payload)
    keep.update(p.as_posix() for name in payload for p in Path(name).parents[:-1])

    def ignored(directory: str, names: list[str]) -> set[str]:
        # copytree descends into directory symlinks; refuse one swapped in since the check.
        if not _plain_directory(Path(directory)):
            raise ResolveError(f"course content changed during import; retry: {directory}")
        prefix = Path(directory).relative_to(root).as_posix()
        return {n for n in names if (n if prefix == "." else f"{prefix}/{n}") not in keep}

    return ignored


def _copy_plain_file(source: str, destination: str) -> None:
    if _plain_directory(Path(source)):
        raise ResolveError(f"course content changed during import; retry: {source}")
    shutil.copy2(source, destination)


def _staged_files(candidate: Path) -> tuple[str, ...]:
    return tuple(
        sorted(p.relative_to(candidate).as_posix() for p in candidate.rglob("*") if not p.is_dir())
    )


def validate_local_import(ws: Path, path: Path) -> ImportedCourse:
    """Validate input and containment before creating any workspace directories."""
    checked = _checked_import(ws, path)
    return ImportedCourse(checked.course, checked.path)


def _checked_import(ws: Path, path: Path) -> _CheckedImport:
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
    # Re-importing the installed copy copies nothing; its own tree is still checked.
    payload = _walked_payload(path) if path == destination.resolve() else _local_payload(path)
    if destination.exists() and not destination.is_dir():
        raise ResolveError(f"course destination is not a directory: {destination}")
    return _CheckedImport(course, destination, payload)


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
    validate_local_import(ws, path)
    path, ws = path.resolve(), ws.resolve()
    with workspace_lock(ws):
        checked = _checked_import(ws, path)
        destination = checked.path
        supplied_ref = ref if ref is not None else str(path)
        if path == destination.resolve():
            save_manifest(ws, _updated_manifest(ws, checked.course, supplied_ref, destination))
            return ImportedCourse(checked.course, destination)
        content_root = courses_dir(ws)
        content_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".skilling-import-", dir=content_root))
        candidate = staging / "course"
        try:
            claim_staging(staging)
            shutil.copytree(
                path,
                candidate,
                ignore=_payload_filter(path, checked.payload),
                copy_function=_copy_plain_file,
            )
            copied = _validated_course(candidate)
            if (copied.id, copied.version) != (checked.course.id, checked.course.version):
                raise ResolveError(
                    "course identity changed during import; retry with a stable source"
                )
            if _staged_files(candidate) != tuple(sorted(checked.payload)):
                raise ResolveError("course content changed during import; retry")
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
