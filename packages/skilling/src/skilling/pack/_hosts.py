"""Where a generated pack lands per Agent-Skills host, and the receipt that lets
``uninstall`` remove exactly what ``install`` wrote.

Two conventions, not one: Claude Code reads ``.claude/skills/<name>/`` and a learner invokes
the skill as ``/<name>``; the generic Agent-Skills convention — Codex and roughly forty other
hosts — reads ``.agents/skills/<name>/`` and invokes it as ``$<name>``. Installing writes both
by default, because no single directory is read by both hosts. ``install`` records the
relative path and content hash of every file it writes in a receipt beside them, so
``uninstall`` can remove exactly those files later — and refuse, rather than silently delete,
if one has changed since.
"""

from __future__ import annotations

import hashlib
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

import yaml

from ._generate import GeneratedPack

RECEIPT_NAME = ".skilling-receipt.yaml"


class Platform(StrEnum):
    CLAUDE = "claude"
    AGENTS = "agents"


@dataclass(frozen=True)
class HostTarget:
    """One Agent-Skills host convention: where its skills directory lives, and how a learner
    invokes a skill once it is installed there."""

    platform: Platform

    def skills_dir(self, *, project: Path | None, home: Path) -> Path:
        root = home if project is None else project
        subdir = ".claude/skills" if self.platform is Platform.CLAUDE else ".agents/skills"
        return root / subdir

    def invocation(self, name: str) -> str:
        return f"/{name}" if self.platform is Platform.CLAUDE else f"${name}"


class InstallResult(NamedTuple):
    skill_dir: Path
    files: tuple[Path, ...]


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def install(
    pack: GeneratedPack, target: HostTarget, *, project: Path | None, home: Path
) -> InstallResult:
    """Write ``pack`` under ``target``'s skills directory, overwriting any previous install of
    the same name in place (same relative paths in, same relative paths out — nothing stale is
    left behind), and record a receipt of exactly what was written."""
    skill_dir = target.skills_dir(project=project, home=home) / pack.name
    entries: dict[str, str] = {}
    written: list[Path] = []
    for file in pack.files:
        path = skill_dir / file.relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file.content, encoding="utf-8")
        entries[file.relative.as_posix()] = _hash(file.content)
        written.append(path)

    receipt_path = skill_dir / RECEIPT_NAME
    receipt_path.write_text(
        yaml.safe_dump(
            {"name": pack.name, "platform": target.platform.value, "files": entries},
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return InstallResult(skill_dir=skill_dir, files=tuple(written))


def uninstall(name: str, target: HostTarget, *, project: Path | None, home: Path) -> list[Path]:
    """Remove exactly the files ``install`` wrote for ``name``, per its receipt. Anything else
    found in the skill directory — a foreign file, a hand-edit that added a new one — is left
    alone. Refuses, removing nothing, if a receipted file's content no longer matches the hash
    recorded at install time; the caller decides what to do with that.

    Returns an empty list, doing nothing, if ``name`` was never installed for ``target``.
    """
    skill_dir = target.skills_dir(project=project, home=home) / name
    receipt_path = skill_dir / RECEIPT_NAME
    if not receipt_path.is_file():
        return []

    loaded = yaml.safe_load(receipt_path.read_text(encoding="utf-8")) or {}
    entries = loaded.get("files", {})

    to_remove: list[Path] = []
    for relative, recorded_hash in entries.items():
        path = skill_dir / relative
        if not path.is_file():
            continue  # already gone; nothing to refuse over
        actual_hash = _hash(path.read_text(encoding="utf-8"))
        if actual_hash != recorded_hash:
            raise ValueError(
                f"refusing to uninstall {path}: its content changed since install "
                f"(expected sha256:{recorded_hash}, found sha256:{actual_hash})"
            )
        to_remove.append(path)

    for path in to_remove:
        path.unlink()
    receipt_path.unlink()
    removed = [*to_remove, receipt_path]

    # Deepest directories first, so `references/` is tried before `skill_dir` itself. Either
    # rmdir silently no-ops (a foreign file is still there) or clears a now-empty directory.
    directories = sorted(
        {path.parent for path in removed}, key=lambda p: len(p.parts), reverse=True
    )
    for directory in directories:
        with suppress(OSError):
            directory.rmdir()
    return removed
