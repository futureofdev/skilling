"""Generating a conforming Agent Skill pack from a validated course.

The pack is pure choreography — verb names and gate rules — and carries zero course-structure
facts (no lesson counts, no titles), so it never goes stale independently of the course it was
generated from. ``pack._generate`` builds it; ``pack._audit`` re-checks an already-written one.
"""

from ._audit import PackFinding, audit
from ._generate import (
    GeneratedFile,
    GeneratedPack,
    Pack,
    PackRefused,
    derive_description,
    write_pack,
)

__all__ = [
    "GeneratedFile",
    "GeneratedPack",
    "Pack",
    "PackFinding",
    "PackRefused",
    "audit",
    "derive_description",
    "write_pack",
]
