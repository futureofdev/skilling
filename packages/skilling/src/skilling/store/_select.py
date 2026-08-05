"""Store selection: turn a URI (or nothing) into an open ``ProgressStore``.

The scheme space is deliberately small and open at once: ``file:`` and bare paths are
built in, and anything else is a lookup in the ``skilling.stores`` entry-point group —
so a third-party backend (Postgres, S3, whatever) never needs a change here, only a
``pyproject.toml`` entry.
"""

from __future__ import annotations

import importlib.metadata
import os
import re
from collections.abc import Callable
from pathlib import Path

from ._file import FileProgressStore
from ._protocol import ProgressStore, StoreError

STORE_ENTRY_POINT_GROUP = "skilling.stores"
STATE_ROOT_ENV = "SKILLING_STATE_ROOT"

# RFC 3986 scheme syntax, anchored at the start. A single matched letter is excluded by
# the caller (below) rather than the pattern, so "C:\Users\..." is not mistaken for a
# one-letter scheme on Windows.
_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")


class UnknownScheme(StoreError):
    """A URI scheme with no ``file:`` handling and no matching entry point."""

    def __init__(self, scheme: str, known: set[str]) -> None:
        super().__init__(
            f"Unknown store scheme {scheme!r}. Known schemes: {', '.join(sorted(known))}. "
            f"To add one, register a {scheme!r} entry point in the "
            f"{STORE_ENTRY_POINT_GROUP!r} group (pointing at a callable "
            f"that takes the URI and returns a ProgressStore)."
        )
        self.scheme = scheme


def default_state_root() -> Path:
    """$SKILLING_STATE_ROOT, else ~/.skilling/state (spec leaves <state-root> open;
    the default follows the learner, not the directory they started in — see strategy
    open-questions)."""
    root = os.environ.get(STATE_ROOT_ENV)
    return Path(root) if root else Path.home() / ".skilling" / "state"


def _entry_points() -> importlib.metadata.EntryPoints:
    """Seam wrapping stdlib discovery so tests can inject entry points without
    packaging a real distribution."""
    return importlib.metadata.entry_points(group=STORE_ENTRY_POINT_GROUP)


def open_store(uri: str | None = None) -> ProgressStore:
    """None/'' → file backend at default_state_root(). A bare path or file:<path> → file
    backend there. Any other scheme → an entry point named after the scheme in the
    'skilling.stores' group, called with the URI. Unknown scheme → UnknownScheme naming
    the scheme, the group, and how to register one."""
    if not uri:
        return FileProgressStore(default_state_root())

    match = _SCHEME_RE.match(uri)
    if match is None or len(match.group(1)) == 1:
        return FileProgressStore(Path(uri))

    scheme = match.group(1).lower()
    if scheme == "file":
        return FileProgressStore(Path(uri[match.end() :]))

    points = {ep.name: ep for ep in _entry_points()}
    entry_point = points.get(scheme)
    if entry_point is None:
        raise UnknownScheme(scheme, {"file", *points})

    factory: Callable[[str], ProgressStore] = entry_point.load()
    return factory(uri)
