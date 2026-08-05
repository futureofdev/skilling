"""Resolving a course ref — a local path, a ``gh:`` shorthand, or any git URL — to a
validated, cached course directory. ``git`` is shelled out to in ``_git`` alone; nothing
here ever reads, stores, or forwards a credential of the learner's.
"""

from ._resolve import (
    CACHE_ENV,
    CourseInvalid,
    GhResolver,
    GitFailed,
    ResolvedSource,
    ResolveError,
    Resolver,
    UnknownRef,
    UrlResolver,
    resolve,
)

__all__ = [
    "CACHE_ENV",
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
