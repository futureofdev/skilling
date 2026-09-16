"""Resolving a course ref to a validated, cached course directory.

A local path loads directly and is never cached — it is already exactly where the author
left it. Everything else is fetched with ``git`` (see ``_git``) into a scratch directory,
validated exactly as ``skilling validate`` would, and only then moved into the cache (see
``_cache``) under ``<id>@<version>``. A course with any findings — error or warning — is
refused rather than cached, because the cache is shared with tooling that never sees the
findings a human running ``validate`` would: better to fail loudly once at fetch time.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import NamedTuple

from ..conformance import validate_course
from ..course import Course
from . import _cache, _git
from ._errors import CacheInvalid, CourseInvalid, GitFailed, UnknownRef
from ._identity import (
    Provenance,
    check_subdirectory,
    course_key,
    inspect_payload,
    safe_source_ref,
)
from ._paths import remove_tree, root_path

CACHE_ENV = "SKILLING_CACHE_DIR"
"""Default ``~/.skilling/courses``, consulted only when ``resolve`` is not given an
explicit ``cache=``."""

GH_PREFIX = "gh:"


class ResolvedSource(NamedTuple):
    course: Course
    path: Path
    """The validated, cached course directory (or, for a local ref, the ref itself)."""
    ref: str
    """The ref exactly as given."""
    pinned: str | None
    """The tag or sha the ref pinned, if any."""


class Resolver(ABC):
    """One way of turning a ref into course files on disk. ``claims`` is a classmethod so
    ``resolve`` can pick a resolver without instantiating every candidate."""

    @classmethod
    @abstractmethod
    def claims(cls, ref: str) -> bool: ...

    @abstractmethod
    def fetch(self, ref: str, workdir: Path) -> Path:
        """Populate ``workdir`` (which does not yet exist) and return the course root —
        ``workdir`` itself, or a subdirectory of it for a ref naming one."""


class GhResolver(Resolver):
    """``gh:owner/repo[@tag-or-sha][#subdir]`` — GitHub's own shorthand, expanded to the
    plain HTTPS URL GitHub always serves, no API token required to clone a public repo."""

    @classmethod
    def claims(cls, ref: str) -> bool:
        return ref.startswith(GH_PREFIX)

    def fetch(self, ref: str, workdir: Path) -> Path:
        owner_repo, pin, subdir = _parse_gh_ref(ref)
        _git.clone(f"https://github.com/{owner_repo}", workdir, pin=pin)
        return workdir / subdir if subdir else workdir


class UrlResolver(Resolver):
    """Any URL git already understands natively — https://, ssh://, file://, git:// — plus
    the git+ssh:// convenience alias some tooling uses for the same ssh:// transport."""

    @classmethod
    def claims(cls, ref: str) -> bool:
        return "://" in ref

    def fetch(self, ref: str, workdir: Path) -> Path:
        _git.clone(ref.removeprefix("git+"), workdir, pin=None)
        return workdir


class GitHubRef(NamedTuple):
    repository: str
    pin: str | None
    subdirectory: str | None


def _parse_gh_ref(ref: str) -> GitHubRef:
    if "?" in ref:
        raise UnknownRef("GitHub shorthand cannot carry URL query parameters")
    body = ref.removeprefix(GH_PREFIX)
    body, _, subdir = body.partition("#")
    owner_repo, _, pin = body.partition("@")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", owner_repo):
        raise UnknownRef("GitHub reference must name owner/repository")
    check_subdirectory(subdir or None)
    return GitHubRef(owner_repo, pin or None, subdir or None)


def resolve(ref: str, *, cache: Path | None = None) -> ResolvedSource:
    """Local path → load directly (never cached). Remote → fetch to a temp dir via ``git``,
    validate, then move to ``<cache>/<id>@<version>/``. A course with findings is refused
    (``CourseInvalid`` carrying the findings) and never cached. Re-resolving an already-
    cached ref is a cache hit: no network."""
    if GhResolver.claims(ref) or UrlResolver.claims(ref):
        return _resolve_remote(ref, cache=cache if cache is not None else _default_cache())

    path = Path(ref)
    if not path.is_dir():
        raise UnknownRef(f"not a recognised ref, and no local directory at {ref!r}")
    return _load_or_refuse(path, ref=ref, pinned=None)


def _resolve_remote(ref: str, *, cache: Path) -> ResolvedSource:
    resolver_cls: type[Resolver] = GhResolver if GhResolver.claims(ref) else UrlResolver
    gh = _parse_gh_ref(ref) if resolver_cls is GhResolver else None
    pin = gh.pin if gh is not None else None
    cache = root_path(cache)
    try:
        cached = _cache.lookup(cache, ref)
    except OSError:
        raise CacheInvalid("cannot read or lock the course cache; preserve it and retry") from None
    if cached.course is not None:
        return ResolvedSource(cached.course, cached.course.root, ref, pin)

    scratch = Path(tempfile.mkdtemp(prefix="skilling-fetch-"))
    staging: Path | None = None
    try:
        workdir = scratch / "clone"
        try:
            fetched = _fetch_into(resolver_cls, ref, workdir)
        except GitFailed:
            if cached.legacy:
                raise GitFailed(
                    "legacy cached source cannot be verified; retry online or use the "
                    "already-installed workspace course ID offline"
                ) from None
            raise
        if not fetched.resolve().is_relative_to(workdir.resolve()):
            raise CacheInvalid("course subdirectory escapes the fetched repository")
        try:
            commit = _git.revision(workdir)
            executables = _git.executable_paths(workdir, fetched)
        except (OSError, subprocess.CalledProcessError):
            raise GitFailed("Git could not inspect the fetched course identity") from None
        payload = inspect_payload(fetched, executables)
        resolved = _load_or_refuse(fetched, ref=ref, pinned=pin)
        key = course_key(resolved.course.id, resolved.course.version)
        source = Provenance(
            transport="https" if gh else ref.removeprefix("git+").partition(":")[0].lower(),
            source=safe_source_ref(ref),
            pin=pin,
            subdirectory=gh.subdirectory if gh else None,
            commit=commit,
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".skilling-cache-", dir=cache.parent))
        candidate = staging / "course"
        _cache.stage(fetched, candidate)
        copied = _load_or_refuse(candidate, ref=ref, pinned=pin)
        if (copied.course.id, copied.course.version) != (
            resolved.course.id,
            resolved.course.version,
        ):
            raise CacheInvalid("course identity changed while staging")
        stored = _cache.publish(cache, candidate, key, payload, ref, source)
        return resolved._replace(course=stored, path=stored.root)
    except OSError:
        raise CacheInvalid("cache operation failed; preserve its content and retry") from None
    finally:
        remove_tree(scratch)
        if staging is not None:
            remove_tree(staging)


def _fetch_into(resolver_cls: type[Resolver], ref: str, workdir: Path) -> Path:
    try:
        return resolver_cls().fetch(ref, workdir)
    except (OSError, subprocess.CalledProcessError):
        raise GitFailed(
            f"Git could not fetch {safe_source_ref(ref)!r}; check the source and Git authentication"
        ) from None


def _load_or_refuse(path: Path, *, ref: str, pinned: str | None) -> ResolvedSource:
    report = validate_course(path)
    if not report.clean:
        raise CourseInvalid(
            f"{path} does not conform to the format ({len(report.findings)} finding(s))",
            findings=report.findings,
        )
    return ResolvedSource(course=Course.load(path), path=path, ref=ref, pinned=pinned)


def _default_cache() -> Path:
    configured = os.environ.get(CACHE_ENV)
    return Path(configured) if configured else Path.home() / ".skilling" / "courses"
