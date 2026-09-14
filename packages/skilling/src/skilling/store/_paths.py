"""Checked paths for local state, without filesystem creation.

The caller-selected root may be an alias. Descendants may not: even an alias within the
root could redirect a write into another course. This protects against pre-existing aliases,
not hostile concurrent replacement or hardlinks on a shared filesystem.
"""

from __future__ import annotations

from pathlib import Path

from ..course import is_course_id
from ._protocol import StatePathError


def canonical_root(root: Path | str) -> Path:
    try:
        resolved = Path(root).resolve(strict=False)
        # Non-strict resolution may suppress a cycle/error; check every existing ancestor.
        for path in (resolved, *resolved.parents):
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            if path.resolve(strict=True) != path:
                raise StatePathError(f"Cannot resolve state root alias: {root}")
        return resolved
    except (OSError, RuntimeError, ValueError) as exc:
        raise StatePathError(f"Cannot resolve state root: {exc}") from exc


def checked_path(root: Path, course_id: str, *parts: str) -> Path:
    if not is_course_id(course_id):
        raise StatePathError(f"Invalid state course id: {course_id!r}")
    candidate = root
    for part in (course_id, *parts):
        if not part or part in (".", "..") or any(c in part for c in "/\\:\0"):
            raise StatePathError(f"Invalid state path component: {part!r}")
        candidate = candidate / part
        try:
            if candidate.is_symlink():
                raise StatePathError(f"State descendant must not be an alias: {candidate}")
            try:
                candidate.lstat()
            except FileNotFoundError:
                resolved = candidate.resolve(strict=False)
            else:
                # Existing junctions must resolve strictly: cycles and broken targets refuse.
                try:
                    resolved = candidate.resolve(strict=True)
                except FileNotFoundError:
                    # A cooperating store may have deleted this file since lstat.
                    # An entry still present (e.g. a broken junction) must still refuse.
                    try:
                        candidate.lstat()
                    except FileNotFoundError:
                        resolved = candidate.resolve(strict=False)
                    else:
                        raise
            if not resolved.is_relative_to(root) or resolved != candidate:
                raise StatePathError(f"State descendant must not be an alias: {candidate}")
        except (OSError, RuntimeError, ValueError) as exc:
            raise StatePathError(f"Cannot resolve state path {candidate}: {exc}") from exc
    return candidate
