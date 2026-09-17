"""Resolving a course ref — a local path, a ``gh:`` shorthand, or any git URL — to a
validated, cached course directory. ``git`` is shelled out to in ``_git`` alone; nothing
here retains credentials in the durable source cache; authentication stays with Git.
"""

from ._cache import invalidate_cached_course
from ._errors import (
    CacheBusy,
    CacheConflict,
    CacheInvalid,
    CourseInvalid,
    GitFailed,
    ResolveError,
    UnknownRef,
)
from ._identity import safe_source_ref
from ._locking import locked_directory
from ._resolve import (
    CACHE_ENV,
    GhResolver,
    ResolvedSource,
    Resolver,
    UrlResolver,
    resolve,
)

__all__ = [
    "locked_directory",
    "CACHE_ENV",
    "CacheBusy",
    "CacheConflict",
    "CacheInvalid",
    "invalidate_cached_course",
    "safe_source_ref",
    "CourseInvalid",
    "GhResolver",
    "GitFailed",
    "ResolveError",
    "ResolvedSource",
    "Resolver",
    "UnknownRef",
    "UrlResolver",
    "resolve",
]
