"""The only module that shells out to git. Every clone runs under the learner's own
credentials — SSH keys, a configured credential helper, ``gh auth`` — Skilling never reads,
stores, or forwards one.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

GIT_TOKEN_ENV = "SKILLING_GIT_TOKEN"
"""Set by the learner for headless HTTPS (CI, a container with no keyring or interactive
prompt). Read only here, and only to name it to git's own credential helper — the value
itself never appears in an argv or a log line."""


def clone(url: str, dst: Path, *, pin: str | None) -> None:
    """Shallow-clone ``url`` into ``dst`` (must not yet exist), pinned to ``pin`` (a tag or
    sha) when given. Raises ``OSError`` (git missing) or ``subprocess.CalledProcessError``
    (git ran and refused) — the caller translates both into the public ``GitFailed``.
    """
    argv = [
        "git",
        *_credential_args(),
        "clone",
        "--depth",
        "1",
        *(["--branch", pin] if pin else []),
        url,
        str(dst),
    ]
    subprocess.run(
        argv,
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
