"""The only module that shells out to git. Every fetch runs under the learner's own
credentials — SSH keys, a configured credential helper, ``gh auth`` — Skilling never reads,
stores, or forwards one.
"""

from __future__ import annotations

import os
import string
import subprocess
from pathlib import Path

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
        if pin is None or not _is_full_sha(pin):
            raise
        _git("fetch", "--tags", "origin", cwd=dst)
        _git("checkout", "--quiet", "--detach", pin, cwd=dst)
        return
    _git("checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=dst)


def _is_full_sha(pin: str) -> bool:
    """A full sha1 (40 hex) or sha256 (64 hex) digest — the only sha forms promised."""
    return len(pin) in (40, 64) and all(c in string.hexdigits for c in pin)


def _git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(
        ["git", *_credential_args(), *args],
        cwd=cwd,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        check=True,
        capture_output=True,
        text=True,
    )


def _credential_args() -> list[str]:
    if GIT_TOKEN_ENV not in os.environ:
        return []
    # The helper reads the token from its own environment at credential-fill time, so the
    # secret never sits in argv (visible to `ps`) or gets embedded in this string.
    helper = f'!f() {{ echo username=skilling; echo "password=${GIT_TOKEN_ENV}"; }}; f'
    return ["-c", f"credential.helper={helper}"]
