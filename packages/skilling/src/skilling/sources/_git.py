"""The only module that shells out to git. Every fetch runs under the learner's own
credentials — SSH keys, a configured credential helper, ``gh auth`` — Skilling never reads,
stores, or forwards one.
"""

from __future__ import annotations

import os
import string
import subprocess
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from ._errors import CacheInvalid, ResolveError

GIT_TOKEN_ENV = "SKILLING_GIT_TOKEN"
"""Set by the learner for headless HTTPS (CI, a container with no keyring or interactive
prompt). Read only here, and only to name it to git's own credential helper — the value
itself never appears in an argv or a log line."""


def clone(url: str, dst: Path, *, pin: str | None) -> None:
    """Fetch ``url`` into ``dst`` (must not yet exist), checked out at ``pin`` — a branch,
    a tag, or a **full** commit sha — or at the remote's default branch when ``pin`` is
    ``None``. Abbreviated shas are not promised: pin with a tag or the full sha.

    ``git clone --branch`` takes branches and tags but never a bare sha, so every pin form
    goes through one uniform path instead: init an empty repository, fetch exactly the pin
    at depth 1, and check out ``FETCH_HEAD`` detached. A server may refuse a sha in a fetch
    request (``uploadpack.allowReachableSHA1InWant`` is off by git's default; GitHub turns
    it on) — a sha pin then falls back to fetching the remote's full history and checking
    the sha out of it.

    Raises ``OSError`` (git missing) or ``subprocess.CalledProcessError`` (git ran and
    refused) — the caller translates both into the public ``GitFailed``.
    """
    _git("init", "--quiet", str(dst))
    _git("remote", "add", "origin", url, cwd=dst)
    try:
        _git("fetch", "--depth", "1", "origin", pin or "HEAD", cwd=dst)
    except subprocess.CalledProcessError:
        if pin is None or not is_full_sha(pin):
            raise
        _git("fetch", "--tags", "origin", cwd=dst)
        _git("checkout", "--quiet", "--detach", pin, cwd=dst)
        return
    _git("checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=dst)


def remote_tags(url: str) -> tuple[str, ...]:
    """Tag names the remote advertises (``git ls-remote --tags``), peeled duplicates removed.
    Raises like ``clone``; the caller translates to ``GitFailed``."""
    names: set[str] = set()
    for line in _git("ls-remote", "--tags", url).splitlines():
        _, _, name = line.partition("\t")
        if name.startswith("refs/tags/"):
            names.add(name.removeprefix("refs/tags/").removesuffix("^{}"))
    return tuple(sorted(names))


def is_full_sha(pin: str) -> bool:
    """A full sha1 (40 hex) or sha256 (64 hex) digest — the only sha forms promised."""
    return len(pin) in (40, 64) and all(c in string.hexdigits for c in pin)


def revision(workdir: Path) -> str:
    return _git("rev-parse", "HEAD", cwd=workdir).strip()


class GitPayload(NamedTuple):
    files: tuple[str, ...]
    executables: tuple[str, ...]


def payload_intent(workdir: Path, course: Path) -> GitPayload:
    scope = PurePosixPath(course.relative_to(workdir).as_posix())
    listing = _git(
        "-c",
        "core.fsmonitor=false",
        "--git-dir",
        str(workdir / ".git"),
        "--work-tree",
        str(workdir),
        "ls-files",
        "--stage",
        "-z",
        cwd=workdir,
    )
    return _index_payload(listing, scope)


def tracked_payload(path: Path) -> GitPayload | None:
    """The files Git tracks under ``path``, relative to it, when ``path`` lies inside a Git
    work tree — ``None`` when it does not, or when Git is absent or refuses the repository
    (``safe.directory``), so the caller falls back to walking the directory itself.

    The same index reading and mode checks as a fetched course: a tracked symlink, submodule
    or unmerged entry is refused, never followed. Unlike ``payload_intent`` the repository is
    discovered from ``path`` — a local course is usually a subdirectory of an author's
    project, and that project's ``.git`` may be a file (a linked worktree or submodule).
    """
    try:
        inside = _git("-c", "core.fsmonitor=false", "rev-parse", "--is-inside-work-tree", cwd=path)
    except (OSError, subprocess.CalledProcessError):
        return None
    if inside.strip() != "true":
        return None
    try:
        # Run from inside ``path``, ls-files lists only entries beneath it, relative to it.
        listing = _git("-c", "core.fsmonitor=false", "ls-files", "--stage", "-z", cwd=path)
    except (OSError, subprocess.CalledProcessError):
        raise ResolveError(f"Git could not list the tracked files under {path}") from None
    return _index_payload(listing, PurePosixPath("."))


def _index_payload(listing: str, scope: PurePosixPath) -> GitPayload:
    files: list[str] = []
    found: list[str] = []
    for entry in listing.split("\0"):
        if not entry:
            continue
        metadata, _, name = entry.partition("\t")
        path = PurePosixPath(name)
        if not path.is_relative_to(scope):
            continue
        relative = path.relative_to(scope).as_posix()
        fields = metadata.split()
        if len(fields) != 3 or fields[2] != "0":
            raise CacheInvalid(
                f"Git course index has unresolved or invalid file intent: {relative}"
            )
        mode = fields[0]
        if mode not in {"100644", "100755"}:
            raise CacheInvalid(
                f"Git course payload contains a symlink or unsupported file kind: {relative}"
            )
        files.append(relative)
        if mode == "100755":
            found.append(relative)
    return GitPayload(tuple(sorted(files)), tuple(sorted(found)))


def executable_paths(workdir: Path, course: Path) -> tuple[str, ...]:
    return payload_intent(workdir, course).executables


def _git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", *_credential_args(), *args],
        cwd=cwd,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return done.stdout


def _credential_args() -> list[str]:
    if GIT_TOKEN_ENV not in os.environ:
        return []
    # The helper reads the token from its own environment at credential-fill time, so the
    # secret never sits in argv (visible to `ps`) or gets embedded in this string.
    helper = f'!f() {{ echo username=skilling; echo "password=${GIT_TOKEN_ENV}"; }}; f'
    return ["-c", f"credential.helper={helper}"]
