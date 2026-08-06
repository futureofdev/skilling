"""Where the bundled skill triad lands per Agent-Skills host, and the receipt that lets
``uninstall`` remove exactly what ``install`` wrote.

Two conventions, not one: Claude Code reads ``.claude/skills/<name>/`` and a learner invokes a
skill as ``/<name>``; the generic Agent-Skills convention — Codex and roughly forty other
hosts — reads ``.agents/skills/<name>/`` and invokes it as ``$<name>``. Installing writes both
by default, because no single directory is read by both hosts.

There is nothing left to generate (docs/superpowers/specs/2026-08-06-generic-delivery-skills-
design.md) — every file this writes is copied verbatim from ``skills/<name>/`` — so ``install``
and ``uninstall`` operate on the whole ``learn``/``progress``/``homework`` triad as one unit.
Each skill still gets its own receipt (its relative paths and content hashes), but ``uninstall``
treats the three receipts as one atomic transaction: a hand-edit anywhere in the triad refuses
the entire removal, not just the affected skill's, so a learner never ends up with two of three
skills gone and a dangling third.

Ported from the now-closed ``feat/skilling-install`` branch's ``pack/_hosts.py``, whose
``Platform``/``HostTarget``/receipt design was sound; only its input changed, from one
generated-per-course pack to this fixed, hand-maintained triad.
"""

from __future__ import annotations

import hashlib
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

import yaml

from ._registry import SKILL_NAMES
from ._registry import skill_dir as _bundled_skill_dir
from ._registry import skill_files as _bundled_skill_files

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
    skill_dirs: tuple[Path, ...]  # one per SKILL_NAMES, same order
    files: tuple[Path, ...]  # every content file written, across all three skills


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def install(target: HostTarget, *, project: Path | None, home: Path) -> InstallResult:
    """Write ``learn``, ``progress``, and ``homework`` under ``target``'s skills directory,
    overwriting any previous install of the same skills in place (same relative paths in, same
    relative paths out — nothing stale is left behind), and record one receipt per skill of
    exactly what was written."""
    base = target.skills_dir(project=project, home=home)
    skill_dirs: list[Path] = []
    written: list[Path] = []
    for name in SKILL_NAMES:
        source_dir = _bundled_skill_dir(name)
        skill_dest = base / name
        entries: dict[str, str] = {}
        for source in _bundled_skill_files(name):
            relative = source.relative_to(source_dir)
            dest = skill_dest / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            content = source.read_text(encoding="utf-8")
            dest.write_text(content, encoding="utf-8")
            entries[relative.as_posix()] = _hash(content)
            written.append(dest)

        receipt_path = skill_dest / RECEIPT_NAME
        receipt_path.write_text(
            yaml.safe_dump(
                {"name": name, "platform": target.platform.value, "files": entries},
                sort_keys=False,
                default_flow_style=False,
            ),
            encoding="utf-8",
        )
        skill_dirs.append(skill_dest)

    return InstallResult(skill_dirs=tuple(skill_dirs), files=tuple(written))


def uninstall(target: HostTarget, *, project: Path | None, home: Path) -> list[Path]:
    """Remove exactly the files ``install`` wrote for the triad, per its receipts, as one
    atomic operation across all three skills: if any receipted file anywhere in the triad was
    hand-edited since install, nothing is removed anywhere — not even from a skill that was
    itself untouched. A foreign file left in a skill directory is never touched.

    Returns an empty list, doing nothing, if the triad was never installed for ``target``.
    """
    base = target.skills_dir(project=project, home=home)
    to_remove: list[Path] = []
    installed = False
    for name in SKILL_NAMES:
        skill_dest = base / name
        receipt_path = skill_dest / RECEIPT_NAME
        if not receipt_path.is_file():
            continue
        installed = True

        loaded = yaml.safe_load(receipt_path.read_text(encoding="utf-8")) or {}
        entries = loaded.get("files", {})
        for relative, recorded_hash in entries.items():
            path = skill_dest / relative
            if not path.is_file():
                continue  # already gone; nothing to refuse over
            actual_hash = _hash(path.read_text(encoding="utf-8"))
            if actual_hash != recorded_hash:
                raise ValueError(
                    f"refusing to uninstall: {path} changed since install "
                    f"(expected sha256:{recorded_hash}, found sha256:{actual_hash})"
                )
            to_remove.append(path)
        to_remove.append(receipt_path)

    if not installed:
        return []

    for path in to_remove:
        path.unlink()

    # Deepest directories first, so `references/` is tried before its skill directory, and
    # each skill directory before the shared `skills/` root they sit in. Either rmdir silently
    # no-ops (a foreign file is still there) or clears a now-empty directory.
    directories = sorted(
        {path.parent for path in to_remove}, key=lambda p: len(p.parts), reverse=True
    )
    for directory in directories:
        with suppress(OSError):
            directory.rmdir()
    return to_remove
