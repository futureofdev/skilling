"""Verified immutable payloads and serialized ref bindings at the existing id@version paths.

Content identity is reserved atomically before the directory rename; only a later atomic
index write binds a ref. A killed publisher may leave a reservation or verified orphan,
never a ref naming a missing tree. Another fetch can finish that publication under the lock.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

from pydantic import TypeAdapter, ValidationError

from ..course import Course, CourseLoadError
from . import _git
from ._errors import CacheConflict, CacheInvalid
from ._identity import (
    Entry,
    Index,
    Payload,
    Provenance,
    course_key,
    inspect_payload,
    payload_paths,
    ref_digest,
    safe_source_ref,
    validate_key,
)
from ._locking import locked_cache
from ._paths import child, fsync_directory, plain, remove_tree, root_path

INDEX_NAME = ".index.json"


class Lookup(NamedTuple):
    course: Course | None
    legacy: bool


def _read_index(cache: Path) -> Index:
    path = child(cache, INDEX_NAME)
    if not path.exists():
        return Index()
    try:
        data = path.read_bytes()
        decoded = json.loads(data)
        if not isinstance(decoded, dict):
            raise ValueError("index must be an object")
        if "version" in decoded:
            if type(decoded["version"]) is not int or decoded["version"] != 1:
                raise ValueError("unsupported cache metadata version")
            return Index.model_validate_json(data)
        legacy = TypeAdapter(dict[str, str]).validate_python(decoded, strict=True)
        for key in legacy.values():
            validate_key(key)
        return Index(pending={ref_digest(ref): key for ref, key in legacy.items()})
    except (ValueError, OSError, ValidationError):
        raise CacheInvalid("cache index is invalid; preserve it and use a separate cache") from None


def _write_index(cache: Path, index: Index) -> None:
    path = child(cache, INDEX_NAME)
    fd, name = tempfile.mkstemp(dir=cache, prefix=".index-", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(index.model_dump_json(indent=2).encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync_directory(cache)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@contextmanager
def _locked(cache: Path) -> Iterator[None]:
    plain(cache, directory=True)
    child(cache, ".cache.lock")
    with locked_cache(cache):
        yield


def _checked_course(cache: Path, key: str, payload: Payload) -> Course:
    directory = child(cache, key, directory=True)
    if inspect_payload(directory, payload.executables) != payload:
        raise CacheInvalid("cached payload changed; preserve it and use a separate cache")
    try:
        course = Course.load(directory)
        if course_key(course.id, course.version) != key:
            raise CacheInvalid("cache directory disagrees with its course identity")
        return course
    except (CourseLoadError, OSError):
        raise CacheInvalid("cached course cannot be loaded; use a separate cache") from None


def _checked_hit(cache: Path, ref: str, index: Index, entry: Entry) -> Course:
    if entry.source.source != safe_source_ref(ref):
        raise CacheInvalid("cache source provenance disagrees with requested reference")
    return _checked_course(cache, entry.key, index.contents[entry.key])


def lookup(cache: Path, ref: str) -> Lookup:
    cache = root_path(cache)
    if not cache.exists():
        return Lookup(None, False)
    with _locked(cache):
        index = _read_index(cache)
        digest = ref_digest(ref)
        entry = index.entries.get(digest)
        if entry is None:
            return Lookup(None, digest in index.pending)
        return Lookup(_checked_hit(cache, ref, index, entry), False)


def stage(fetched: Path, destination: Path) -> None:
    """Copy a checked plain payload to a private same-filesystem staging directory."""
    paths = payload_paths(fetched)
    destination.mkdir()
    for path in paths:
        target = destination / path.relative_to(fetched)
        if path.is_dir():
            target.mkdir()
        else:
            with path.open("rb") as source, target.open("wb") as stream:
                shutil.copyfileobj(source, stream)
                stream.flush()
                os.fsync(stream.fileno())
            shutil.copystat(path, target)
    for directory in reversed((destination, *(p for p in destination.rglob("*") if p.is_dir()))):
        fsync_directory(directory)


def _strip_git_metadata(directory: Path) -> None:
    for current, dirs, files in os.walk(directory):
        if ".git" in dirs:
            metadata = Path(current) / ".git"
            plain(metadata, directory=True)
            remove_tree(metadata)
            dirs.remove(".git")
        if ".git" in files:
            metadata = Path(current) / ".git"
            plain(metadata, directory=False)
            metadata.unlink()


def _conflict(key: str) -> CacheConflict:
    return CacheConflict(
        f"cache conflict for {key}: different content already occupies this id/version; "
        "use a separate workspace/cache or ask the author to bump the course version"
    )


def _unversioned_payload(directory: Path) -> Payload:
    paths = payload_paths(directory)
    if os.name == "nt":
        metadata = directory / ".git"
        if not metadata.is_dir():
            raise CacheInvalid(
                "legacy executable intent cannot be verified on Windows without Git metadata; "
                "preserve installed content and use a separate cache"
            )
        payload_paths(metadata)
        plain(metadata / "index", directory=False)
        try:
            intent = _git.payload_intent(directory, directory)
        except (OSError, subprocess.CalledProcessError):
            raise CacheInvalid(
                "legacy Git executable intent is invalid; use a separate cache"
            ) from None
        if intent.files != tuple(p.relative_to(directory).as_posix() for p in paths if p.is_file()):
            raise CacheInvalid("legacy Git index does not cover the payload; use a separate cache")
        executables = intent.executables
    else:
        executables = tuple(
            p.relative_to(directory).as_posix()
            for p in paths
            if p.is_file() and p.stat().st_mode & 0o111
        )
    return inspect_payload(directory, executables)


def publish(
    cache: Path,
    candidate: Path,
    key: str,
    payload: Payload,
    ref: str,
    source: Provenance,
) -> Course:
    cache = root_path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    with _locked(cache):
        index = _read_index(cache)
        digest = ref_digest(ref)
        entry = index.entries.get(digest)
        if entry is not None:
            return _checked_hit(cache, ref, index, entry)
        destination = child(cache, key, directory=True)
        reserved = index.contents.get(key)
        if destination.exists():
            if reserved is not None:
                _checked_course(cache, key, reserved)
                if reserved != payload:
                    raise _conflict(key)
            elif _unversioned_payload(destination) != payload:
                raise _conflict(key)
        elif any(e.key == key for e in index.entries.values()):
            raise CacheInvalid("verified cache content is missing; use a separate cache")
        if inspect_payload(candidate, payload.executables) != payload:
            raise CacheInvalid("staged course changed before cache publication")
        contents = {**index.contents, key: payload}
        if reserved != payload:
            index = Index(entries=index.entries, pending=index.pending, contents=contents)
            _write_index(cache, index)
        if destination.exists():
            _strip_git_metadata(destination)
        if not destination.exists():
            candidate.rename(destination)
            fsync_directory(cache)
        updated = Index(
            entries={**index.entries, digest: Entry(key=key, source=source)},
            contents=contents,
            pending={k: v for k, v in index.pending.items() if k != digest},
        )
        _write_index(cache, updated)
        return _checked_course(cache, key, payload)


@contextmanager
def invalidate_cached_course(cache: Path, course_id: str, version: str) -> Iterator[None]:
    """Forget every binding/reservation for a deliberate replacement, holding the cache lock.

    Future workspace import calls this inside its workspace lock and replaces content inside
    the context. Failure leaves untrusted content requiring source verification on refetch.
    This function never removes or replaces course files, workspace manifests or learner state.
    """
    key = course_key(course_id, version)
    cache = root_path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    with _locked(cache):
        index = _read_index(cache)
        updated = Index(
            entries={k: v for k, v in index.entries.items() if v.key != key},
            contents={k: v for k, v in index.contents.items() if k != key},
            pending={k: v for k, v in index.pending.items() if v != key},
        )
        if updated != index:
            _write_index(cache, updated)
        yield
