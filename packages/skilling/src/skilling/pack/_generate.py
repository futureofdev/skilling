"""Generating a conforming Agent Skill pack from a validated course.

Generation reads exactly five things off the course: the skill name (the course id, unless
overridden), the derived trigger description, the course id, the course title, and the
tutor's persona/tone lines. It never reads a phase name, a lesson title, or any count — that
omission is the whole point, and ``pack._audit`` re-checks it on anything already written to
disk, in case a hand edit reintroduces one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import yaml

from ..conformance import Finding, validate_course
from ..course import Course
from ._templates import DELIVERY_LOOP, OBJECTIVES, SKILL_BODY, TROUBLESHOOTING

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024


class GeneratedFile(NamedTuple):
    relative: Path
    content: str


class GeneratedPack(NamedTuple):
    name: str
    files: tuple[GeneratedFile, ...]


class PackRefused(Exception):
    """``validate_course`` found errors. Generation never runs on a course it hasn't checked
    itself — the CLI's own validate/pack sequence is not a substitute for this, because
    ``Pack.generate`` is also called directly by tests and, eventually, ``install``/``fetch``.
    """

    def __init__(self, findings: tuple[Finding, ...]) -> None:
        super().__init__(f"{len(findings)} finding(s) must be fixed before packing")
        self.findings = findings


def derive_description(course: Course) -> str:
    """The pack's trigger text — the one place a host decides whether to activate this skill.
    Derived from the manifest every time, never authored, so ``pack._audit`` can recompute it
    and detect drift by comparing rather than trusting the file."""
    title = course.manifest.title
    return (
        f"{title} — an AI-tutored course. Use when the learner asks to start, resume, "
        f"or continue '{title}' or mentions {course.id}."
    )


def _persona_section(course: Course) -> str:
    tutor = course.manifest.tutor
    if tutor is None or not (tutor.persona or tutor.tone):
        return ""
    lines = ["", "## Tutor voice", ""]
    if tutor.persona:
        lines.append(tutor.persona.strip())
        lines.append("")
    lines.extend(f"- {line}" for line in tutor.tone)
    if tutor.tone:
        lines.append("")
    return "\n".join(lines)


def _frontmatter(name: str, description: str) -> str:
    dumped = yaml.safe_dump(
        {"name": name, "description": description},
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    ).strip()
    return f"---\n{dumped}\n---\n"


def _validate_name(name: str) -> None:
    if not NAME_RE.match(name) or not (0 < len(name) <= MAX_NAME_LENGTH):
        raise ValueError(
            f"{name!r} is not a valid skill name: must be lowercase kebab-case, "
            f"1-{MAX_NAME_LENGTH} characters"
        )


class Pack:
    """The generator. A classmethod constructor per this package's convention — there is no
    other way to produce a ``GeneratedPack``."""

    @classmethod
    def generate(cls, course: Course, *, name: str | None = None) -> GeneratedPack:
        report = validate_course(course.root)
        if not report.ok:
            raise PackRefused(tuple(report.errors))

        skill_name = name if name is not None else course.id
        _validate_name(skill_name)

        title = course.manifest.title
        description = derive_description(course)
        if not (0 < len(description) <= MAX_DESCRIPTION_LENGTH):
            raise ValueError(
                f"derived description is {len(description)} characters, "
                f"must be 1-{MAX_DESCRIPTION_LENGTH}"
            )

        skill_md = (
            _frontmatter(skill_name, description)
            + "\n"
            + SKILL_BODY.substitute(
                course_title=title,
                course_id=course.id,
                persona_section=_persona_section(course),
            )
        )
        files = (
            GeneratedFile(Path("SKILL.md"), skill_md),
            GeneratedFile(
                Path("references/delivery-loop.md"),
                DELIVERY_LOOP.substitute(course_title=title),
            ),
            GeneratedFile(
                Path("references/objectives.md"),
                OBJECTIVES.substitute(course_title=title),
            ),
            GeneratedFile(
                Path("references/troubleshooting.md"),
                TROUBLESHOOTING.substitute(course_title=title),
            ),
        )
        return GeneratedPack(name=skill_name, files=files)


def write_pack(pack: GeneratedPack, out: Path) -> Path:
    """Write ``pack`` under ``out``, returning ``out/<pack.name>``."""
    root = out / pack.name
    for file in pack.files:
        path = root / file.relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file.content, encoding="utf-8")
    return root
