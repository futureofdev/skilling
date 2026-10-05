"""Relocation-stable identity of the selected authored course bytes."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ...store import StatePathError


def course_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            raise StatePathError("Course source identity refuses aliased descendants")
        if path.is_dir():
            continue
        name, raw = relative.as_posix().encode(), path.read_bytes()
        digest.update(len(name).to_bytes(8, "big") + name + len(raw).to_bytes(8, "big") + raw)
    return digest.hexdigest()
