"""The course cache: ``<cache>/<id>@<version>/`` directories, plus a small ref → key index
so re-resolving the same ref is a genuine cache hit — no network call at all, not merely a
skipped re-validation.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..course import is_course_id, is_semver

INDEX_NAME = ".index.json"


def course_key(course_id: str, version: str) -> str:
    if not (is_course_id(course_id) and is_semver(version)):
        raise ValueError(f"not a cacheable course id/version: {course_id}@{version}")
    return f"{course_id}@{version}"


def lookup(cache: Path, ref: str) -> Path | None:
    """The directory this exact ref last resolved to, if it is still there. Consulted
    before any network call — the whole point of the index."""
    key = _read_index(cache).get(ref)
    if key is None:
        return None
    directory = cache / key
    return directory if directory.is_dir() else None


def remember(cache: Path, ref: str, key: str) -> None:
    index = _read_index(cache)
    index[ref] = key
    cache.mkdir(parents=True, exist_ok=True)
    (cache / INDEX_NAME).write_text(json.dumps(index, indent=2), encoding="utf-8")


def store(cache: Path, fetched: Path, key: str) -> Path:
    """Move a validated, freshly fetched course tree into the cache under ``key``. If
    another resolve already landed the same key first, keep that copy — the content is
    equivalent, and this avoids clobbering a directory a concurrent reader may hold open."""
    destination = cache / key
    if destination.exists():
        return destination
    cache.mkdir(parents=True, exist_ok=True)
    shutil.move(str(fetched), str(destination))
    return destination


def _read_index(cache: Path) -> dict[str, str]:
    path = cache / INDEX_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}
