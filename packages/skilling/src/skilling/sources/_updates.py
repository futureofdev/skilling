"""Where a newer version of an already-resolved remote course would come from.

Ordinary resolution treats a bound ref as a snapshot. ``skilling upgrade --check`` is the
sanctioned refresh (spec/workspace.md#checking-for-updates), and this module decides *what* it
fetches, without fetching anything itself beyond listing the remote's tags:

- a ref pinned to a full commit sha is pinned on purpose — no automatic upgrades;
- an unpinned ref, or one pinned to a semver tag, follows the remote's semver tags
  (``v1.2.3`` or ``1.2.3``): the newest tag with the record's major version is offered, and a
  newer major is reported but never offered as resumable;
- a repository with no semver tags falls back to its default branch head;
- a ref pinned to anything else (a branch) refreshes that branch's head.
"""

from __future__ import annotations

import re
import subprocess
from enum import StrEnum
from typing import NamedTuple

from . import _git
from ._errors import GitFailed
from ._identity import safe_source_ref
from ._resolve import GhResolver, UrlResolver, _parse_gh_ref

SEMVER_TAG = re.compile(r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class UpdateKind(StrEnum):
    PINNED = "pinned"
    """Pinned to a full commit sha: nothing to discover."""

    TAG = "tag"
    BRANCH = "branch"
    HEAD = "head"


class UpdateSource(NamedTuple):
    kind: UpdateKind
    fetch: bool
    """Whether there is anything to fetch (false when pinned or already at the newest tag)."""

    pin: str | None
    """The tag or branch to fetch; ``None`` fetches the default branch head."""

    ref: str
    """The ref to record and bind once applied: a tag-pinned GitHub ref moves to the new tag;
    every other ref keeps its own spelling."""

    tag: str | None = None
    newer_major: str | None = None
    """The newest tag with a higher major version, reported only."""


def _semver(tag: str) -> tuple[int, int, int] | None:
    match = SEMVER_TAG.fullmatch(tag)
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def _url(ref: str) -> str:
    if GhResolver.claims(ref):
        return f"https://github.com/{_parse_gh_ref(ref).repository}"
    return ref.removeprefix("git+")


def _with_pin(ref: str, pin: str) -> str:
    gh = _parse_gh_ref(ref)
    subdirectory = f"#{gh.subdirectory}" if gh.subdirectory else ""
    return f"gh:{gh.repository}@{pin}{subdirectory}"


def find_update(ref: str, current_version: str) -> UpdateSource:
    """Decide where a newer version of ``ref`` would come from. Lists remote tags only."""
    if not (GhResolver.claims(ref) or UrlResolver.claims(ref)):
        raise ValueError("only remote refs have remote updates")
    own_pin = _parse_gh_ref(ref).pin if GhResolver.claims(ref) else None
    if own_pin is not None and _git.is_full_sha(own_pin):
        return UpdateSource(UpdateKind.PINNED, False, own_pin, ref)
    if own_pin is not None and _semver(own_pin) is None:
        return UpdateSource(UpdateKind.BRANCH, True, own_pin, ref)
    try:
        names = _git.remote_tags(_url(ref))
    except (OSError, subprocess.CalledProcessError):
        raise GitFailed(
            f"Git could not list tags for {safe_source_ref(ref)!r}; check the source and "
            "Git authentication"
        ) from None
    tags = {name: version for name in names if (version := _semver(name)) is not None}
    if not tags:
        return UpdateSource(UpdateKind.HEAD, True, None, ref)
    current = _semver(current_version.split("-", 1)[0].split("+", 1)[0]) or (0, 0, 0)
    same = [n for n, v in tags.items() if v[0] == current[0]]
    newer = [n for n, v in tags.items() if v[0] > current[0]]
    newer_major = max(newer, key=lambda n: tags[n]) if newer else None
    if not same:
        return UpdateSource(UpdateKind.TAG, False, None, ref, None, newer_major)
    best = max(same, key=lambda n: (tags[n], n.startswith("v")))
    target = _with_pin(ref, best) if own_pin is not None else ref
    return UpdateSource(UpdateKind.TAG, tags[best] > current, best, target, best, newer_major)
