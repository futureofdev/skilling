"""Public resolver failures, shared without coupling cache and transport implementations."""

from ..conformance import Finding


class ResolveError(Exception):
    """A source could not be resolved safely."""


class UnknownRef(ResolveError):
    """Neither a recognized remote reference nor an existing local directory."""


class GitFailed(ResolveError):
    """Git could not fetch the requested source with the learner's own authentication."""


class CourseInvalid(ResolveError):
    def __init__(self, message: str, *, findings: list[Finding]) -> None:
        super().__init__(message)
        self.findings = findings


class CacheConflict(ResolveError):
    """A different payload already occupies the requested course id/version."""


class CacheInvalid(ResolveError):
    """Cache paths, metadata or payload cannot be verified; preserve them and refuse."""


class CacheBusy(ResolveError):
    """Another cooperating cache operation exceeded the bounded wait."""
