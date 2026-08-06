"""Which bundled skill lives where.

Three hand-maintained Agent Skills, shipped as real files (``SKILL.md`` plus
``references/*.md``) beside this module rather than generated: nothing here varies by
course, so there is nothing left to template. ``ROOT`` is package-relative, so a caller —
a test today, an eventual ``skilling install`` — finds bundled content the same way
regardless of where this package was installed from.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent

SKILL_NAMES: tuple[str, ...] = ("learn", "progress", "homework")


def skill_dir(name: str) -> Path:
    if name not in SKILL_NAMES:
        raise ValueError(f"{name!r} is not one of {SKILL_NAMES}")
    return ROOT / name


def skill_md_path(name: str) -> Path:
    return skill_dir(name) / "SKILL.md"


def skill_files(name: str) -> tuple[Path, ...]:
    """Every file belonging to one bundled skill: its ``SKILL.md`` plus every reference
    doc beside it — the manifest a future installer would copy verbatim into a host's
    skills directory, and what a structural test checks for orphaned or dangling files."""
    directory = skill_dir(name)
    references_dir = directory / "references"
    references = sorted(references_dir.glob("*.md")) if references_dir.is_dir() else []
    return (directory / "SKILL.md", *references)
