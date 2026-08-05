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
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import NamedTuple

from ..conformance import Finding, validate_course
from ..course import Course
from . import _cache, _git

CACHE_ENV = "SKILLING_CACHE_DIR"
"""Default ``~/.skilling/courses``, consulted only when ``resolve`` is not given an
explicit ``cache=``."""

GH_PREFIX = "gh:"


class ResolveError(Exception):
    """A course ref could not be resolved to a validated, cached directory."""


class UnknownRef(ResolveError):
    """Neither a recognised remote scheme nor an existing local directory."""


class GitFailed(ResolveError):
    """The clone itself failed — a bad ref, no network, or missing credentials. Skilling
    never handles a credential itself, so this is always the learner's own git/gh auth
    declining, not a secret Skilling mishandled."""


class CourseInvalid(ResolveError):
    """The resolved course does not conform. Never cached."""

    def __init__(self, message: str, *, findings: list[Finding]) -> None:
        super().__init__(message)
        self.findings = findings


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


def _parse_gh_ref(ref: str) -> tuple[str, str | None, str | None]:
    body = ref.removeprefix(GH_PREFIX)
    body, _, subdir = body.partition("#")
    owner_repo, _, pin = body.partition("@")
    return owner_repo, pin or None, subdir or None


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
    pin = _parse_gh_ref(ref)[1] if resolver_cls is GhResolver else None

    cached = _cache.lookup(cache, ref)
    if cached is not None:
        return ResolvedSource(course=Course.load(cached), path=cached, ref=ref, pinned=pin)

    scratch = Path(tempfile.mkdtemp(prefix="skilling-fetch-"))
    try:
        fetched = _fetch_into(resolver_cls, ref, scratch / "clone")
        resolved = _load_or_refuse(fetched, ref=ref, pinned=pin)
        key = _cache.course_key(resolved.course.id, resolved.course.version)
        stored = _cache.store(cache, fetched, key)
        _cache.remember(cache, ref, key)
        return resolved._replace(path=stored)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _fetch_into(resolver_cls: type[Resolver], ref: str, workdir: Path) -> Path:
    try:
        return resolver_cls().fetch(ref, workdir)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GitFailed(str(exc)) from exc


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
