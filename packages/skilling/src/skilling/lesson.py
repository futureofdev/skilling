"""Markdown parsing for lesson files: frontmatter, the section registry, the quiz
grammar, and the homework assignment grammar.

Everything here keeps line numbers, because a finding without a line number makes the
author hunt for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import LessonFrontmatter


@dataclass(frozen=True)
class SectionSpec:
    heading: str
    slot: str
    required: bool
    declared_as: str | None = None
    """The ``sections:`` key that must declare this section, when it is optional."""


SECTION_REGISTRY: tuple[SectionSpec, ...] = (
    SectionSpec("Learning Objectives", "objectives", required=True),
    SectionSpec("The Concept", "concept", required=True),
    SectionSpec("Key Terms", "key_terms", required=False, declared_as="key_terms"),
    SectionSpec("Hands-On Exercise", "exercise", required=False, declared_as="exercise"),
    SectionSpec("Quick Quiz", "quiz", required=True),
    SectionSpec("Homework Assignment", "homework", required=False),
    SectionSpec("Next Up", "next_up", required=False, declared_as="next_up"),
)

REGISTRY_ORDER: dict[str, int] = {s.heading: i for i, s in enumerate(SECTION_REGISTRY)}
BY_HEADING: dict[str, SectionSpec] = {s.heading: s for s in SECTION_REGISTRY}
BY_SLOT: dict[str, SectionSpec] = {s.slot: s for s in SECTION_REGISTRY}


@dataclass
class Section:
    heading: str
    line: int
    """1-indexed line of the ``## `` heading itself."""
    body: str
    body_line: int
    """1-indexed line where the body starts."""

    @property
    def slot(self) -> str | None:
        spec = BY_HEADING.get(self.heading)
        return spec.slot if spec else None


@dataclass
class ParsedLesson:
    path: Path
    raw: str
    frontmatter: LessonFrontmatter | None = None
    frontmatter_error: str | None = None
    frontmatter_missing: bool = False
    sections: list[Section] = field(default_factory=list)

    def section(self, slot: str) -> Section | None:
        for s in self.sections:
            if s.slot == slot:
                return s
        return None

    @property
    def slots(self) -> set[str]:
        return {s.slot for s in self.sections if s.slot}


# ------------------------------------------------------------------------- frontmatter

_FM_DELIM = re.compile(r"^---\s*$")


def split_frontmatter(text: str) -> tuple[str | None, str, int]:
    """Return ``(frontmatter_yaml, body, body_start_line)``.

    ``frontmatter_yaml`` is None when the file does not open with a ``---`` block.
    ``body_start_line`` is 1-indexed.
    """
    lines = text.splitlines()
    if not lines or not _FM_DELIM.match(lines[0]):
        return None, text, 1
    for i in range(1, len(lines)):
        if _FM_DELIM.match(lines[i]):
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1 :]), i + 2
    return None, text, 1


def parse_lesson(path: Path) -> ParsedLesson:
    raw = path.read_text(encoding="utf-8")
    fm_text, body, body_line = split_frontmatter(raw)
    parsed = ParsedLesson(path=path, raw=raw)

    if fm_text is None:
        parsed.frontmatter_missing = True
    else:
        try:
            data = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError as exc:
            parsed.frontmatter_error = f"frontmatter is not valid YAML: {_yaml_reason(exc)}"
        else:
            if not isinstance(data, dict):
                parsed.frontmatter_error = "frontmatter must be a mapping"
            else:
                try:
                    parsed.frontmatter = LessonFrontmatter.model_validate(data)
                except ValidationError as exc:
                    parsed.frontmatter_error = format_validation_error(exc)

    parsed.sections = parse_sections(body, body_line)
    return parsed


def _yaml_reason(exc: yaml.YAMLError) -> str:
    return str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__


def format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


# ---------------------------------------------------------------------------- sections

_H2 = re.compile(r"^##\s+(.+?)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def parse_sections(body: str, offset: int) -> list[Section]:
    """Split a lesson body on ``## `` headings, ignoring headings inside code fences."""
    lines = body.splitlines()
    found: list[tuple[str, int, int]] = []  # heading, heading index, body start index
    in_fence = False
    for i, line in enumerate(lines):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _H2.match(line)
        if m:
            found.append((m.group(1), i, i + 1))

    sections: list[Section] = []
    for n, (heading, h_index, b_index) in enumerate(found):
        end = found[n + 1][1] if n + 1 < len(found) else len(lines)
        sections.append(
            Section(
                heading=heading,
                line=h_index + offset,
                body="\n".join(lines[b_index:end]).strip("\n"),
                body_line=b_index + offset,
            )
        )
    return sections


def strip_code(text: str) -> str:
    """Blank out fenced blocks and inline code spans, preserving line numbering.

    Quoting a counter-example is what code formatting is for, so scanners that look for
    forbidden phrasing must not fire on text an author deliberately marked as a sample.
    """
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else re.sub(r"`[^`]*`", "``", line))
    return "\n".join(out)


# -------------------------------------------------------------------------------- quiz

_QUESTION = re.compile(r"^(\d+)\.\s+(.+?)\s*$")
_OPTION = re.compile(r"^\s*[-*]\s*([a-dA-D])\)\s*(.+?)\s*$")
_ANSWER = re.compile(r"^\s*\*\*Answer:\*\*\s*(.*?)\s*$")
_ANSWER_LABEL = re.compile(r"^([a-dA-D])\)\s*(.*)$", re.DOTALL)


@dataclass
class QuizOption:
    label: str
    text: str
    line: int


@dataclass
class QuizQuestion:
    number: int
    text: str
    line: int
    options: list[QuizOption] = field(default_factory=list)
    answer_line: int | None = None
    answer_raw: str = ""

    @property
    def labels(self) -> list[str]:
        return [o.label for o in self.options]

    def option(self, label: str) -> QuizOption | None:
        for o in self.options:
            if o.label == label:
                return o
        return None

    @property
    def answer_label(self) -> str | None:
        m = _ANSWER_LABEL.match(self.answer_raw)
        if not m:
            return None
        label = m.group(1).lower()
        return label if label in self.labels else None

    @property
    def answer_reason(self) -> str:
        """Whatever the answer line says beyond restating the correct option.

        Leading separators are trimmed, trailing punctuation is not: this text is read
        out to the learner verbatim, and a sentence should end in a full stop.
        """
        m = _ANSWER_LABEL.match(self.answer_raw)
        if not m:
            return ""
        rest = " ".join(m.group(2).split())
        label = m.group(1).lower()
        option = self.option(label)
        if option:
            opt_text = " ".join(option.text.split())
            if rest.lower().startswith(opt_text.lower()):
                rest = rest[len(opt_text) :]
        return rest.lstrip(" —–-:;,").strip()

    @property
    def has_reason(self) -> bool:
        """A reason that is only punctuation is not a reason."""
        return bool(self.answer_reason.strip(" —–-:;,.!?\t"))


def parse_quiz(body: str, offset: int) -> list[QuizQuestion]:
    lines = body.splitlines()
    questions: list[QuizQuestion] = []
    collecting_answer = False

    for i, line in enumerate(lines):
        line_no = i + offset

        m = _QUESTION.match(line)
        if m:
            questions.append(QuizQuestion(number=int(m.group(1)), text=m.group(2), line=line_no))
            collecting_answer = False
            continue

        if not questions:
            continue
        current = questions[-1]

        m = _OPTION.match(line)
        if m:
            current.options.append(
                QuizOption(label=m.group(1).lower(), text=m.group(2), line=line_no)
            )
            collecting_answer = False
            continue

        m = _ANSWER.match(line)
        if m:
            current.answer_line = line_no
            current.answer_raw = m.group(1)
            collecting_answer = True
            continue

        if collecting_answer:
            if line.strip():
                current.answer_raw = f"{current.answer_raw} {line.strip()}".strip()
            else:
                collecting_answer = False

    return questions


# ---------------------------------------------------------------------------- homework

_HW_TITLE = re.compile(r"^###\s+(.+?)\s*$")
_HW_OBJECTIVE = re.compile(r"^\*\*Objective:\*\*\s*(.*?)\s*$")
_HW_STRETCH = re.compile(r"^\*\*Stretch Goals:\*\*\s*$")
_HW_SUBMISSION = re.compile(r"^\*\*Submission:\*\*\s*(.*?)\s*$")
_HW_CHECKBOX = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s*(.+?)\s*$")


@dataclass
class ParsedHomework:
    title: str | None = None
    objective: str | None = None
    requirements: list[str] = field(default_factory=list)
    stretch_goals: list[str] = field(default_factory=list)
    submission: str | None = None

    @property
    def complete(self) -> bool:
        return bool(self.title and self.objective and self.requirements and self.submission)

    def missing(self) -> list[str]:
        gaps = []
        if not self.title:
            gaps.append("a '###' assignment title")
        if not self.objective:
            gaps.append("an '**Objective:**' line")
        if not self.requirements:
            gaps.append("at least one '- [ ]' requirement")
        if not self.submission:
            gaps.append("a '**Submission:**' line")
        return gaps


def parse_homework(body: str) -> ParsedHomework:
    hw = ParsedHomework()
    in_stretch = False
    for line in body.splitlines():
        if m := _HW_TITLE.match(line):
            if hw.title is None:
                hw.title = m.group(1)
            continue
        if m := _HW_OBJECTIVE.match(line):
            hw.objective = m.group(1) or None
            continue
        if _HW_STRETCH.match(line):
            in_stretch = True
            continue
        if m := _HW_SUBMISSION.match(line):
            hw.submission = m.group(1) or None
            in_stretch = False
            continue
        if m := _HW_CHECKBOX.match(line):
            (hw.stretch_goals if in_stretch else hw.requirements).append(m.group(1))
    return hw


# ------------------------------------------------------------------------------ assets

_MD_LINK = re.compile(r"!?\[[^\]]*\]\(\s*([^)\s]+)")
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", re.IGNORECASE)


def asset_references(text: str, offset: int = 1) -> list[tuple[str, int]]:
    """Local file references from markdown links and images, with line numbers.

    Code blocks are stripped first: a reference shown as an example is not a reference.
    """
    refs: list[tuple[str, int]] = []
    for i, line in enumerate(strip_code(text).splitlines()):
        for m in _MD_LINK.finditer(line):
            target = m.group(1)
            if _EXTERNAL.match(target):
                continue
            refs.append((target, i + offset))
    return refs
