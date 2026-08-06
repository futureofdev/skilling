"""Structural sanity for a bundled skill's ``SKILL.md`` frontmatter.

Agent Skills' portable floor is exactly two keys, ``name`` and ``description``, each within
constraints every host enforces: a lowercase kebab-case name (1-64 characters) and a
non-empty description (1-1024 characters). This mirrors ``_check_frontmatter`` from the
now-closed ``feat/skilling-install`` branch's ``pack/_audit.py`` — the one check there that
still applies once packs stopped being generated per course; the other three (trigger-drift,
structure-fact, stale) all compared an installed pack against the course it was generated
from, which no longer exists here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


@dataclass(frozen=True)
class Frontmatter:
    name: str
    description: str


class FrontmatterError(ValueError):
    """The frontmatter block is missing, malformed, or outside the Agent Skills constraints."""


def parse_frontmatter(skill_md: Path) -> Frontmatter:
    """Read and validate one ``SKILL.md``'s frontmatter block.

    Raises :class:`FrontmatterError` naming exactly what is wrong, rather than returning
    ``None`` — a caller (a test, an eventual installer) should not have to re-derive the
    reason from a missing value.
    """
    if not skill_md.is_file():
        raise FrontmatterError(f"{skill_md} does not exist")

    text = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise FrontmatterError(f"{skill_md} has no frontmatter block")

    loaded = yaml.safe_load(match.group(1))
    if not isinstance(loaded, dict):
        raise FrontmatterError(f"{skill_md} frontmatter is not a mapping")
    if set(loaded) != {"name", "description"}:
        raise FrontmatterError(
            f"{skill_md} frontmatter keys must be exactly name, description; found {sorted(loaded)}"
        )

    name = loaded["name"]
    if (
        not isinstance(name, str)
        or not NAME_RE.match(name)
        or not (0 < len(name) <= MAX_NAME_LENGTH)
    ):
        raise FrontmatterError(
            f"{skill_md} name {name!r} must be lowercase kebab-case, 1-{MAX_NAME_LENGTH} characters"
        )

    description = loaded["description"]
    if not isinstance(description, str) or not (0 < len(description) <= MAX_DESCRIPTION_LENGTH):
        raise FrontmatterError(
            f"{skill_md} description must be 1-{MAX_DESCRIPTION_LENGTH} characters"
        )

    return Frontmatter(name=name, description=description)
