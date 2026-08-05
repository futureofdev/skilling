"""Auditing a pack already written to disk against the course it claims to describe.

Four independent checks: **frontmatter** (is ``SKILL.md``'s frontmatter exactly ``{name,
description}`` and within the Agent Skills constraints), **trigger-drift** (does that
description still match the derived formula), **structure-fact** (did a phase name, a lesson
title, or a count leak into the body), and **stale** (does regenerating from the course
reproduce the pack byte-for-byte). None of this is a validator ``Code`` — a pack is not a
course, so ``PackFinding.rule`` is a small fixed vocabulary of its own.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import yaml

from ..course import Course
from ._generate import (
    MAX_DESCRIPTION_LENGTH,
    MAX_NAME_LENGTH,
    NAME_RE,
    Pack,
    PackRefused,
    derive_description,
)

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


class PackFinding(NamedTuple):
    rule: str
    message: str
    path: Path


def _read_frontmatter(skill_md: Path) -> dict[str, object] | None:
    if not skill_md.is_file():
        return None
    match = _FRONTMATTER_RE.match(skill_md.read_text(encoding="utf-8"))
    if not match:
        return None
    loaded = yaml.safe_load(match.group(1))
    return loaded if isinstance(loaded, dict) else None


def _check_frontmatter(frontmatter: dict[str, object] | None, skill_md: Path) -> list[PackFinding]:
    if frontmatter is None:
        return [
            PackFinding("frontmatter", "SKILL.md is missing or has no frontmatter block", skill_md)
        ]

    findings: list[PackFinding] = []
    if set(frontmatter) != {"name", "description"}:
        findings.append(
            PackFinding(
                "frontmatter",
                f"frontmatter keys must be exactly name, description; found {sorted(frontmatter)}",
                skill_md,
            )
        )
    name = frontmatter.get("name")
    if (
        not isinstance(name, str)
        or not NAME_RE.match(name)
        or not (0 < len(name) <= MAX_NAME_LENGTH)
    ):
        findings.append(
            PackFinding("frontmatter", f"name {name!r} is not a valid skill name", skill_md)
        )

    description = frontmatter.get("description")
    if not isinstance(description, str) or not (0 < len(description) <= MAX_DESCRIPTION_LENGTH):
        findings.append(
            PackFinding(
                "frontmatter",
                f"description must be 1-{MAX_DESCRIPTION_LENGTH} characters",
                skill_md,
            )
        )
    return findings


def _check_trigger_drift(
    frontmatter: dict[str, object], course: Course, skill_md: Path
) -> list[PackFinding]:
    description = frontmatter.get("description")
    if not isinstance(description, str):
        return []
    if description != derive_description(course):
        return [
            PackFinding(
                "trigger-drift",
                "the frontmatter description no longer matches the derived formula",
                skill_md,
            )
        ]
    return []


def _forbidden_facts(course: Course) -> list[str]:
    facts = [f"{course.lesson_count} lesson", f"{course.phase_count} phase"]
    for phase in course.phases:
        facts.append(phase.name)
        facts.extend(lesson.title for lesson in phase.lessons)
    return [fact for fact in facts if fact]


def _check_structure_facts(pack_dir: Path, course: Course) -> list[PackFinding]:
    forbidden = _forbidden_facts(course)
    findings: list[PackFinding] = []
    for path in sorted(pack_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for fact in forbidden:
            if fact in text:
                findings.append(
                    PackFinding("structure-fact", f"course-structure fact leaked: {fact!r}", path)
                )
    return findings


def _check_staleness(
    pack_dir: Path, course: Course, frontmatter: dict[str, object], skill_md: Path
) -> list[PackFinding]:
    name = frontmatter.get("name")
    if not isinstance(name, str):
        return []
    try:
        regenerated = Pack.generate(course, name=name)
    except (PackRefused, ValueError):
        return [
            PackFinding(
                "stale",
                "the course no longer validates cleanly; staleness cannot be confirmed",
                skill_md,
            )
        ]

    findings: list[PackFinding] = []
    for file in regenerated.files:
        on_disk = pack_dir / file.relative
        if not on_disk.is_file() or on_disk.read_text(encoding="utf-8") != file.content:
            findings.append(
                PackFinding("stale", "regenerating produces different content", on_disk)
            )
    return findings


def audit(pack_dir: Path, course: Course) -> list[PackFinding]:
    """Check an already-written pack against ``course``. Read-only: never writes, never
    raises on a course that fails to validate — that itself becomes a ``stale`` finding."""
    skill_md = pack_dir / "SKILL.md"
    frontmatter = _read_frontmatter(skill_md)

    findings = _check_frontmatter(frontmatter, skill_md)
    if frontmatter is not None:
        findings += _check_trigger_drift(frontmatter, course, skill_md)
        findings += _check_staleness(pack_dir, course, frontmatter, skill_md)
    findings += _check_structure_facts(pack_dir, course)
    return findings
