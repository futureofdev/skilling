"""The bundled generic Agent Skills: ``learn``, ``progress``, ``homework``.

Installed once per learner, not once per course (docs/superpowers/specs/
2026-08-06-generic-delivery-skills-design.md). Course identity, persona, and every
structural fact — lesson counts, phase names, positions — are resolved by calling the
``skilling`` CLI at invocation time; nothing course-specific is ever baked into this
content, so nothing here needs regenerating when a course changes.

Content is plain files, not template strings: with no per-course substitution left to do,
a ``SKILL.md`` and its ``references/*.md`` are just prose, and prose is easiest to read,
review, and keep correct as prose — not as a ``string.Template`` body.
"""

from ._frontmatter import Frontmatter, FrontmatterError, parse_frontmatter
from ._registry import ROOT, SKILL_NAMES, skill_dir, skill_files, skill_md_path

__all__ = [
    "ROOT",
    "SKILL_NAMES",
    "Frontmatter",
    "FrontmatterError",
    "parse_frontmatter",
    "skill_dir",
    "skill_files",
    "skill_md_path",
]
