"""Lesson rules: frontmatter against the manifest, the section registry, and the grammars
inside the quiz, homework, key-terms, and next-up sections.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..course import (
    BY_HEADING,
    BY_SLOT,
    OPTIONAL_SECTION_KEYS,
    REGISTRY_ORDER,
    SECTION_REGISTRY,
    Course,
    ParsedLesson,
    Section,
    SectionAbsence,
    asset_references,
    parse_homework,
    parse_quiz,
)
from ._counts import _BODY_COUNTS, _scan_counts
from ._errors import Code
from ._findings import _Collector

_BULLET = re.compile(r"^\s*[-*]\s+\S")
# A bolded term, then anything up to the colon, then a definition. Deliberately loose about
# the term itself and about what sits between it and the colon: real courses write
# `- **CPU** (Central Processing Unit): …` and `- **`p-*`**: …`, and the specification asks for
# a bolded term followed by a definition, not for the colon to touch the closing asterisks.
_KEY_TERM = re.compile(r"^\s*[-*]\s*\*\*.+?\*\*[^:]*:\s*\S")
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")

NEXT_UP_MAX_WORDS = 60
NEXT_UP_MAX_SENTENCES = 3


def _check_lesson(out: _Collector, course: Course, resolved, parsed: ParsedLesson) -> None:
    path = parsed.path

    if parsed.frontmatter_missing:
        out.add(
            Code.LESSON_UNPARSEABLE,
            "The file does not open with a '---' YAML frontmatter block.",
            path=path,
            line=1,
        )
        return
    if parsed.frontmatter_error or parsed.frontmatter is None:
        out.add(
            Code.LESSON_FRONTMATTER_INVALID,
            parsed.frontmatter_error or "frontmatter could not be read.",
            path=path,
            line=1,
        )
        return

    fm = parsed.frontmatter

    mismatches = []
    if fm.title != resolved.title:
        mismatches.append(f"title {fm.title!r} vs manifest {resolved.title!r}")
    if fm.phase != resolved.phase:
        mismatches.append(f"phase {fm.phase} vs manifest {resolved.phase}")
    if fm.lesson != resolved.number:
        mismatches.append(f"lesson {fm.lesson} vs manifest {resolved.number}")
    if mismatches:
        out.add(
            Code.FRONTMATTER_MANIFEST_MISMATCH,
            "Frontmatter disagrees with the manifest: " + "; ".join(mismatches) + ".",
            path=path,
            line=1,
        )

    known = set(course.coordinates)
    for prerequisite in fm.prerequisites:
        if prerequisite not in known:
            out.add(
                Code.PREREQUISITE_UNRESOLVED,
                f"Prerequisite {prerequisite!r} is not a lesson in this course.",
                path=path,
                line=1,
            )

    registered = course.manifest.badge_ids
    for badge in fm.skills_unlocked:
        if badge not in registered:
            out.add(
                Code.BADGE_UNREGISTERED,
                f"skills_unlocked names {badge!r}, which is not registered in the manifest's "
                "skills list.",
                path=path,
                line=1,
            )

    _check_sections(out, resolved, parsed)
    _check_section_bodies(out, parsed)
    _check_assets(out, course, parsed)

    body_start = parsed.sections[0].line if parsed.sections else 1
    body = "\n".join(parsed.raw.splitlines()[body_start - 1 :])
    _scan_counts(out, body, _BODY_COUNTS, path=path, offset=body_start, where="This lesson")


def _check_sections(out: _Collector, resolved, parsed: ParsedLesson) -> None:
    path = parsed.path
    fm = parsed.frontmatter
    assert fm is not None

    for section in parsed.sections:
        if section.heading not in BY_HEADING:
            out.add(
                Code.SECTION_UNKNOWN_HEADING,
                f"'## {section.heading}' is not in the section registry. Use '###' subheadings "
                "inside a registered section instead.",
                path=path,
                line=section.line,
            )

    known = [s for s in parsed.sections if s.heading in BY_HEADING]
    positions = [REGISTRY_ORDER[s.heading] for s in known]
    for i in range(1, len(positions)):
        if positions[i] < positions[i - 1]:
            out.add(
                Code.SECTION_OUT_OF_ORDER,
                f"'## {known[i].heading}' appears after '## {known[i - 1].heading}'; sections "
                "must follow registry order.",
                path=path,
                line=known[i].line,
            )
            break

    present = parsed.slots
    structured_objectives = bool(fm.objectives)

    for spec in SECTION_REGISTRY:
        if not spec.required or spec.slot in present:
            continue
        if spec.slot == "objectives" and structured_objectives:
            # Declared structurally in frontmatter; the runtime renders from there instead.
            continue
        out.add(
            Code.SECTION_MISSING,
            f"'## {spec.heading}' is required and absent.",
            path=path,
            line=1,
        )

    if structured_objectives and "objectives" in present:
        section = parsed.section("objectives")
        out.add(
            Code.OBJECTIVES_DECLARED_TWICE,
            "Objectives are declared in frontmatter and as a '## Learning Objectives' section. "
            "They are mutually exclusive — two sources of truth for the same sentences.",
            path=path,
            line=section.line if section else 1,
        )

    seen_objectives: set[str] = set()
    for objective in fm.objectives:
        if objective.id in seen_objectives:
            out.add(
                Code.OBJECTIVE_ID_DUPLICATE,
                f"Two objectives share the id {objective.id!r}.",
                path=path,
                line=1,
            )
        seen_objectives.add(objective.id)
        _scan_counts(
            out,
            objective.text,
            _BODY_COUNTS,
            path=path,
            where=f"Objective {objective.id!r}",
        )

        # Only practice can be observed from outside. A knowledge objective with a verify
        # clause is a category error, not a stricter check.
        if objective.kind == "knowledge" and (objective.verify or objective.check):
            out.add(
                Code.OBJECTIVE_VERIFY_ON_KNOWLEDGE,
                f"Objective {objective.id!r} is knowledge but carries verify or check. Knowledge "
                "is settled by a tutor hearing the learner explain it, not by looking at their "
                "machine — if it can be observed, it is practice.",
                path=path,
                line=1,
            )
        if objective.check and not objective.verify:
            out.add(
                Code.OBJECTIVE_CHECK_WITHOUT_VERIFY,
                f"Objective {objective.id!r} has a check but no verify. A check is one way to "
                "establish something; verify is what says what that something is, and a runtime "
                "may decline the check.",
                path=path,
                line=1,
            )
        if objective.verify:
            _scan_counts(
                out, objective.verify, _BODY_COUNTS, path=path, where=f"{objective.id!r} verify"
            )

    for key in OPTIONAL_SECTION_KEYS:
        spec = BY_SLOT[key]
        declaration = fm.declaration(key)
        if declaration is None:
            out.add(
                Code.SECTION_ABSENCE_UNDECLARED,
                f"sections does not declare {key!r}. Every optional section must be declared "
                "present, or absent with an intent.",
                path=path,
                line=1,
            )
            continue
        if isinstance(declaration, SectionAbsence):
            if not declaration.intent.strip():
                out.add(
                    Code.SECTION_ABSENCE_MISSING_INTENT,
                    f"sections.{key} is declared absent but carries no intent. Say why, so a "
                    "reader can tell a decision from an oversight.",
                    path=path,
                    line=1,
                )
            if key in present:
                out.add(
                    Code.SECTION_DECLARED_PRESENT_BUT_ABSENT,
                    f"sections.{key} is declared absent, but '## {spec.heading}' is in the file.",
                    path=path,
                    line=1,
                )
        elif key not in present:
            out.add(
                Code.SECTION_DECLARED_PRESENT_BUT_ABSENT,
                f"sections.{key} is declared present, but '## {spec.heading}' is not in the file.",
                path=path,
                line=1,
            )

    homework_section = parsed.section("homework")
    if resolved.homework and homework_section is None:
        out.add(
            Code.HOMEWORK_DECLARATION_MISMATCH,
            "The manifest sets homework: true for this lesson, but there is no "
            "'## Homework Assignment' section.",
            path=path,
            line=1,
        )
    elif not resolved.homework and homework_section is not None:
        out.add(
            Code.HOMEWORK_DECLARATION_MISMATCH,
            "This lesson carries '## Homework Assignment' but the manifest does not set "
            "homework: true for it.",
            path=path,
            line=homework_section.line,
        )


def _check_section_bodies(out: _Collector, parsed: ParsedLesson) -> None:
    path = parsed.path

    objectives = parsed.section("objectives")
    if objectives and not any(_BULLET.match(line) for line in objectives.body.splitlines()):
        out.add(
            Code.OBJECTIVES_EMPTY,
            "Learning Objectives must contain a bullet list of outcomes.",
            path=path,
            line=objectives.line,
        )

    if key_terms := parsed.section("key_terms"):
        items = [
            (i, line) for i, line in enumerate(key_terms.body.splitlines()) if _BULLET.match(line)
        ]
        if not items:
            out.add(
                Code.KEY_TERMS_MALFORMED,
                "Key Terms contains no '- **Term**: definition' items.",
                path=path,
                line=key_terms.line,
            )
        for offset, line in items:
            if not _KEY_TERM.match(line):
                out.add(
                    Code.KEY_TERMS_MALFORMED,
                    "Key Terms items must read '- **Term**: definition'.",
                    path=path,
                    line=key_terms.body_line + offset,
                )

    exercise = parsed.section("exercise")
    if exercise and not exercise.body.strip():
        out.add(
            Code.EXERCISE_EMPTY,
            "Hands-On Exercise is present but empty. Declare it absent with an intent "
            "instead, or give the learner something to attempt.",
            path=path,
            line=exercise.line,
        )

    if quiz := parsed.section("quiz"):
        _check_quiz(out, path, quiz)
        _check_about(out, path, parsed, quiz)

    if homework := parsed.section("homework"):
        parsed_hw = parse_homework(homework.body)
        if gaps := parsed_hw.missing():
            out.add(
                Code.HOMEWORK_SECTION_MALFORMED,
                "Homework Assignment is missing " + ", ".join(gaps) + ".",
                path=path,
                line=homework.line,
            )

    if next_up := parsed.section("next_up"):
        text = " ".join(next_up.body.split())
        words = len(text.split())
        sentences = len([m for m in _SENTENCE_END.finditer(text)])
        if words > NEXT_UP_MAX_WORDS or sentences > NEXT_UP_MAX_SENTENCES:
            out.add(
                Code.NEXT_UP_TOO_LONG,
                f"Next Up runs to {words} words in {sentences} sentences; it is meant to be a "
                "one or two sentence teaser.",
                path=path,
                line=next_up.line,
            )


def _check_about(out: _Collector, path: Path, parsed: ParsedLesson, section: Section) -> None:
    """An objective may only point at questions that exist. The coupling is loose by design —
    `about` steers what a tutor says, so a stale entry costs a sentence, not a record."""
    fm = parsed.frontmatter
    if fm is None or not fm.objectives:
        return

    numbers = {q.number for q in parse_quiz(section.body, section.body_line)}
    for objective in fm.objectives:
        for referenced in objective.about:
            if referenced not in numbers:
                out.add(
                    Code.OBJECTIVE_ABOUT_INVALID,
                    f"Objective {objective.id!r} says it is about question {referenced}, which "
                    f"this quiz does not have. It has: {sorted(numbers) or 'none'}.",
                    path=path,
                    line=section.line,
                )


def _check_quiz(out: _Collector, path: Path, section: Section) -> None:
    questions = parse_quiz(section.body, section.body_line)

    if len(questions) != 3:
        out.add(
            Code.QUIZ_WRONG_QUESTION_COUNT,
            f"Quick Quiz has {len(questions)} question(s); exactly 3 are required.",
            path=path,
            line=section.line,
        )

    for question in questions:
        if sorted(question.labels) != ["a", "b", "c", "d"]:
            out.add(
                Code.QUIZ_WRONG_OPTION_COUNT,
                f"Question {question.number} has options {question.labels or '[]'}; exactly "
                "four labelled a) to d) are required.",
                path=path,
                line=question.line,
            )
            continue

        if question.answer_line is None:
            out.add(
                Code.QUIZ_ANSWER_LINE_MISSING,
                f"Question {question.number} has no '**Answer:**' line. Informal courses carry "
                "the correct option inline.",
                path=path,
                line=question.line,
            )
            continue

        if question.answer_label is None:
            out.add(
                Code.QUIZ_ANSWER_AMBIGUOUS,
                f"Question {question.number}'s answer line does not open with one of its four "
                "option labels.",
                path=path,
                line=question.answer_line,
            )
            continue

        if not question.has_reason:
            out.add(
                Code.QUIZ_ANSWER_NO_REASON,
                f"Question {question.number}'s answer names the correct option but gives no "
                "reason. A learner who guessed right still needs the why.",
                path=path,
                line=question.answer_line,
            )


def _check_assets(out: _Collector, course: Course, parsed: ParsedLesson) -> None:
    for target, line in asset_references(parsed.raw):
        if target.startswith("/"):
            out.add(
                Code.ASSET_REFERENCE_ABSOLUTE,
                f"Asset reference {target!r} is absolute. Use a path relative to the lesson "
                "file so the course works wherever it is checked out.",
                path=parsed.path,
                line=line,
            )
            continue
        resolved_target = (parsed.path.parent / target).resolve()
        try:
            resolved_target.relative_to(course.root.resolve())
        except ValueError:
            out.add(
                Code.ASSET_REFERENCE_ABSOLUTE,
                f"Asset reference {target!r} escapes the course directory.",
                path=parsed.path,
                line=line,
            )
            continue
        if not resolved_target.exists():
            out.add(
                Code.ASSET_REFERENCE_DANGLING,
                f"Asset reference {target!r} does not exist.",
                path=parsed.path,
                line=line,
            )
