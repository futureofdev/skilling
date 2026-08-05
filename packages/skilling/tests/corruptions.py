"""One deliberate corruption of the clean course per error code.

A validator whose fixtures were written by the same hand as its checks can be too friendly,
so the discipline here is: every code in the catalogue must have an entry, the test proves
every entry fires, and a code with no corruption fails the suite rather than passing
silently. That last part is what stops the catalogue rotting as codes are added.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from skilling.errors import Code

from . import fixtures as fx

Corruption = Callable[[Path], None]

_EXTRA_LESSON = """\
---
title: "Extra"
phase: 0
lesson: 9
prerequisites: []
skills_unlocked: []
sections:
  key_terms:
    status: none
    intent: "Not needed."
  exercise:
    status: none
    intent: "Not needed."
  next_up:
    status: none
    intent: "Not needed."
---

## Learning Objectives
By the end of this lesson, you will:
- Know nothing, because this file should not exist

## The Concept
A draft nobody removed.

## Quick Quiz
1. Should this file exist?
   - a) Yes
   - b) No
   - c) Maybe
   - d) Unclear

   **Answer:** b) No — it is not listed in the manifest.

2. What catches it?
   - a) The validator
   - b) Nothing
   - c) The tutor
   - d) Luck

   **Answer:** a) The validator — the manifest and disk must match exactly.

3. Why does that matter?
   - a) It does not
   - b) A tutor could deliver an unfinished draft
   - c) Disk space
   - d) Speed

   **Answer:** b) A tutor could deliver an unfinished draft — which is the whole risk.
"""

_LONG_TEASER = (
    "Next we look at the second thing, and then after that we will look at several other "
    "things as well, because there is a great deal to cover and it seems sensible to lay "
    "all of it out here in advance so that the learner knows exactly what is coming over "
    "the remainder of the material, including the parts that are optional and the parts "
    "that are not, which is quite a lot of ground for a teaser to cover."
)

_CONCEPT_ONE = (
    "## The Concept\nThe first thing is worth knowing. "
    "See [the diagram](../../assets/diagram.txt) for a picture.\n\n"
)
_KEY_TERMS_ONE = "## Key Terms\n- **First**: the first thing\n\n"
_ANSWER_ONE = "   **Answer:** b) The first thing — because that is what the concept described.\n"


def _drop_section(root: Path, relative: str, heading: str, next_heading: str) -> None:
    text = fx.read(root, relative)
    head, rest = text.split(heading, 1)
    _, tail = rest.split(next_heading, 1)
    fx.write(root, relative, head + next_heading + tail)


def _manifest_missing(root: Path) -> None:
    (root / fx.MANIFEST_PATH).unlink()


def _manifest_unparseable(root: Path) -> None:
    fx.write(root, fx.MANIFEST_PATH, "id: [unclosed\ntitle: nope\n")


def _manifest_invalid(root: Path) -> None:
    fx.edit(root, fx.MANIFEST_PATH, "language: en", "language: en\nunknown_field: 1")


def _spec_version_unsupported(root: Path) -> None:
    fx.edit(root, fx.MANIFEST_PATH, 'spec_version: "1.0"', 'spec_version: "2.0"')


def _spec_version_newer_minor(root: Path) -> None:
    fx.edit(root, fx.MANIFEST_PATH, 'spec_version: "1.0"', 'spec_version: "1.9"')


def _course_id_invalid(root: Path) -> None:
    fx.edit(root, fx.MANIFEST_PATH, "id: clean-course", "id: Clean_Course")


def _course_version_invalid(root: Path) -> None:
    fx.edit(root, fx.MANIFEST_PATH, 'version: "1.0.0"', 'version: "1.0"')


def _license_unknown(root: Path) -> None:
    fx.edit(root, fx.MANIFEST_PATH, "license: CC-BY-4.0", "license: Apache2")


def _badge_id_duplicate(root: Path) -> None:
    fx.edit(
        root,
        fx.MANIFEST_PATH,
        "  - { id: alpha, name: Alpha }",
        "  - { id: alpha, name: Alpha }\n  - { id: alpha, name: Alpha Again }",
    )


def _phase_number_duplicate(root: Path) -> None:
    fx.edit(
        root, fx.MANIFEST_PATH, "  - number: 1\n    slug: next", "  - number: 0\n    slug: next"
    )


def _phase_numbering_gap(root: Path) -> None:
    fx.edit(
        root, fx.MANIFEST_PATH, "  - number: 1\n    slug: next", "  - number: 3\n    slug: next"
    )


def _lesson_number_duplicate(root: Path) -> None:
    fx.edit(root, fx.MANIFEST_PATH, "{ number: 2, slug: two", "{ number: 1, slug: two")


def _lesson_numbering_gap(root: Path) -> None:
    fx.edit(root, fx.MANIFEST_PATH, "{ number: 2, slug: two", "{ number: 3, slug: two")


def _lesson_file_missing(root: Path) -> None:
    (root / fx.LESSON_ONE_PATH).unlink()


def _lesson_file_orphan(root: Path) -> None:
    fx.write(root, f"{fx.PHASE_ZERO}/lesson-09-extra.md", _EXTRA_LESSON)


def _frontmatter_manifest_mismatch(root: Path) -> None:
    fx.edit(root, fx.LESSON_ONE_PATH, 'title: "One"', 'title: "Uno"')


def _homework_declaration_mismatch(root: Path) -> None:
    _drop_section(root, fx.LESSON_TWO_PATH, "## Homework Assignment", "## Next Up")


def _badge_unregistered(root: Path) -> None:
    fx.edit(root, fx.LESSON_TWO_PATH, "skills_unlocked: [alpha]", "skills_unlocked: [omega]")


def _prerequisite_unresolved(root: Path) -> None:
    fx.edit(root, fx.LESSON_TWO_PATH, 'prerequisites: ["0.1"]', 'prerequisites: ["9.9"]')


def _authored_count(root: Path) -> None:
    fx.edit(
        root,
        fx.LESSON_ONE_PATH,
        "The first thing is worth knowing.",
        "The first thing is worth knowing. This is lesson 1 of 3.",
    )


def _lesson_unparseable(root: Path) -> None:
    text = fx.read(root, fx.LESSON_ONE_PATH)
    fx.write(root, fx.LESSON_ONE_PATH, text.replace("---\n", "", 1))


def _lesson_frontmatter_invalid(root: Path) -> None:
    fx.edit(root, fx.LESSON_ONE_PATH, "duration_minutes: 10", "duration_minutes: 10\nunknown: 1")


def _section_missing(root: Path) -> None:
    _drop_section(root, fx.LESSON_ONE_PATH, "## Learning Objectives", "## The Concept")


def _section_out_of_order(root: Path) -> None:
    text = fx.read(root, fx.LESSON_ONE_PATH)
    assert _CONCEPT_ONE in text and _KEY_TERMS_ONE in text
    fx.write(
        root,
        fx.LESSON_ONE_PATH,
        text.replace(_CONCEPT_ONE + _KEY_TERMS_ONE, _KEY_TERMS_ONE + _CONCEPT_ONE),
    )


def _section_unknown_heading(root: Path) -> None:
    fx.edit(
        root,
        fx.LESSON_ONE_PATH,
        "## Quick Quiz",
        "## Further Reading\nSome links we thought you might like.\n\n## Quick Quiz",
    )


def _section_absence_undeclared(root: Path) -> None:
    fx.edit(root, fx.LESSON_ONE_PATH, "  key_terms: present\n", "")


def _section_absence_missing_intent(root: Path) -> None:
    fx.edit(
        root,
        fx.LESSON_THREE_PATH,
        'intent: "Last lesson of the course, so there is nothing to tease."',
        'intent: ""',
    )


def _section_declared_present_but_absent(root: Path) -> None:
    fx.edit(
        root,
        fx.LESSON_THREE_PATH,
        '  next_up:\n    status: none\n    intent: "Last lesson of the course, so there is '
        'nothing to tease."',
        "  next_up: present",
    )


def _objectives_empty(root: Path) -> None:
    fx.edit(root, fx.LESSON_ONE_PATH, "- Know the first thing", "You will know the first thing.")


def _key_terms_malformed(root: Path) -> None:
    fx.edit(root, fx.LESSON_ONE_PATH, "- **First**: the first thing", "- First is the first thing")


def _exercise_empty(root: Path) -> None:
    fx.edit(root, fx.LESSON_ONE_PATH, "Try the first thing yourself.", "")


def _quiz_wrong_question_count(root: Path) -> None:
    text = fx.read(root, fx.LESSON_THREE_PATH)
    head, _ = text.split("3. Is it the end?", 1)
    fx.write(root, fx.LESSON_THREE_PATH, head)


def _quiz_wrong_option_count(root: Path) -> None:
    fx.edit(root, fx.LESSON_ONE_PATH, "   - d) Wrong four\n", "")


def _quiz_answer_line_missing(root: Path) -> None:
    fx.edit(root, fx.LESSON_ONE_PATH, _ANSWER_ONE, "")


def _quiz_answer_ambiguous(root: Path) -> None:
    fx.edit(
        root,
        fx.LESSON_ONE_PATH,
        _ANSWER_ONE,
        "   **Answer:** the second option, because it matches the concept.\n",
    )


def _quiz_answer_no_reason(root: Path) -> None:
    fx.edit(root, fx.LESSON_ONE_PATH, _ANSWER_ONE, "   **Answer:** b) The first thing\n")


def _homework_section_malformed(root: Path) -> None:
    fx.edit(root, fx.LESSON_TWO_PATH, "**Submission:** Tell your tutor when it is ready.\n", "")


def _next_up_too_long(root: Path) -> None:
    fx.edit(root, fx.LESSON_ONE_PATH, "Next we look at the second thing.", _LONG_TEASER)


def _asset_reference_dangling(root: Path) -> None:
    fx.edit(root, fx.LESSON_ONE_PATH, "../../assets/diagram.txt", "../../assets/missing.png")


def _asset_reference_absolute(root: Path) -> None:
    fx.edit(root, fx.LESSON_ONE_PATH, "../../assets/diagram.txt", "/etc/hosts")


# --------------------------------------------------------------- ceremony (since spec 1.1)

_OBJECTIVES_SECTION = (
    "## Learning Objectives\nBy the end of this lesson, you will:\n- Know the first thing\n\n"
)


def _add_ceremony(root: Path, block: str) -> None:
    fx.edit(root, fx.MANIFEST_PATH, "phases:", f"{block}phases:")


def _ceremony_unknown_placeholder(root: Path) -> None:
    _add_ceremony(
        root,
        'ceremony:\n  phase_completed_template: "Phase {phase_nmae} is done"\n',
    )


def _ceremony_highlight_missing(root: Path) -> None:
    # The clean fixture's phases carry no highlight, so a template that promises one has a
    # hole in it.
    _add_ceremony(
        root,
        'ceremony:\n  phase_completed_template: "Done: {phase_highlight}"\n',
    )


def _ceremony_handle_malformed(root: Path) -> None:
    _add_ceremony(
        root,
        "ceremony:\n  brand:\n    product: Clean Courses\n    handles:\n      x: NoAtSign\n",
    )


# ------------------------------------------------- structured objectives (since spec 1.1)


def _objectives_declared_twice(root: Path) -> None:
    # Structured objectives added while the prose section stays: two sources of truth.
    fx.edit(
        root,
        fx.LESSON_ONE_PATH,
        "skills_unlocked: []",
        "skills_unlocked: []\nobjectives:\n  - id: know-the-first-thing\n"
        "    kind: knowledge\n    text: Know the first thing",
    )


def _structured(*body: str) -> str:
    return "skills_unlocked: []\nobjectives:\n" + "\n".join(body)


def _objective_id_duplicate(root: Path) -> None:
    fx.edit(
        root,
        fx.LESSON_ONE_PATH,
        "skills_unlocked: []",
        _structured(
            "  - id: know-it",
            "    kind: knowledge",
            "    text: Know the first thing",
            "  - id: know-it",
            "    kind: knowledge",
            "    text: Know it again",
        ),
    )
    fx.edit(root, fx.LESSON_ONE_PATH, _OBJECTIVES_SECTION, "")


def _objective_about_invalid(root: Path) -> None:
    fx.edit(
        root,
        fx.LESSON_ONE_PATH,
        "skills_unlocked: []",
        _structured(
            "  - id: know-it",
            "    kind: knowledge",
            "    text: Know the first thing",
            "    about: [9]",
        ),
    )
    fx.edit(root, fx.LESSON_ONE_PATH, _OBJECTIVES_SECTION, "")


def _objective_verify_on_knowledge(root: Path) -> None:
    """Only practice can be observed. A knowledge objective with a verify clause is a
    category error, not a stricter check."""
    fx.edit(
        root,
        fx.LESSON_ONE_PATH,
        "skills_unlocked: []",
        _structured(
            "  - id: know-it",
            "    kind: knowledge",
            "    text: Know the first thing",
            '    verify: "The learner has the first thing installed"',
        ),
    )
    fx.edit(root, fx.LESSON_ONE_PATH, _OBJECTIVES_SECTION, "")


def _objective_check_without_verify(root: Path) -> None:
    fx.edit(
        root,
        fx.LESSON_ONE_PATH,
        "skills_unlocked: []",
        _structured(
            "  - id: do-it",
            "    kind: practice",
            "    text: Do the first thing",
            '    check: "first --version"',
        ),
    )
    fx.edit(root, fx.LESSON_ONE_PATH, _OBJECTIVES_SECTION, "")


CORRUPTIONS: dict[Code, Corruption] = {
    Code.MANIFEST_MISSING: _manifest_missing,
    Code.MANIFEST_UNPARSEABLE: _manifest_unparseable,
    Code.MANIFEST_INVALID: _manifest_invalid,
    Code.SPEC_VERSION_UNSUPPORTED: _spec_version_unsupported,
    Code.SPEC_VERSION_NEWER_MINOR: _spec_version_newer_minor,
    Code.COURSE_ID_INVALID: _course_id_invalid,
    Code.COURSE_VERSION_INVALID: _course_version_invalid,
    Code.LICENSE_UNKNOWN: _license_unknown,
    Code.BADGE_ID_DUPLICATE: _badge_id_duplicate,
    Code.PHASE_NUMBER_DUPLICATE: _phase_number_duplicate,
    Code.PHASE_NUMBERING_GAP: _phase_numbering_gap,
    Code.LESSON_NUMBER_DUPLICATE: _lesson_number_duplicate,
    Code.LESSON_NUMBERING_GAP: _lesson_numbering_gap,
    Code.LESSON_FILE_MISSING: _lesson_file_missing,
    Code.LESSON_FILE_ORPHAN: _lesson_file_orphan,
    Code.FRONTMATTER_MANIFEST_MISMATCH: _frontmatter_manifest_mismatch,
    Code.HOMEWORK_DECLARATION_MISMATCH: _homework_declaration_mismatch,
    Code.BADGE_UNREGISTERED: _badge_unregistered,
    Code.PREREQUISITE_UNRESOLVED: _prerequisite_unresolved,
    Code.AUTHORED_COUNT: _authored_count,
    Code.LESSON_UNPARSEABLE: _lesson_unparseable,
    Code.LESSON_FRONTMATTER_INVALID: _lesson_frontmatter_invalid,
    Code.SECTION_MISSING: _section_missing,
    Code.SECTION_OUT_OF_ORDER: _section_out_of_order,
    Code.SECTION_UNKNOWN_HEADING: _section_unknown_heading,
    Code.SECTION_ABSENCE_UNDECLARED: _section_absence_undeclared,
    Code.SECTION_ABSENCE_MISSING_INTENT: _section_absence_missing_intent,
    Code.SECTION_DECLARED_PRESENT_BUT_ABSENT: _section_declared_present_but_absent,
    Code.OBJECTIVES_EMPTY: _objectives_empty,
    Code.KEY_TERMS_MALFORMED: _key_terms_malformed,
    Code.EXERCISE_EMPTY: _exercise_empty,
    Code.QUIZ_WRONG_QUESTION_COUNT: _quiz_wrong_question_count,
    Code.QUIZ_WRONG_OPTION_COUNT: _quiz_wrong_option_count,
    Code.QUIZ_ANSWER_LINE_MISSING: _quiz_answer_line_missing,
    Code.QUIZ_ANSWER_AMBIGUOUS: _quiz_answer_ambiguous,
    Code.QUIZ_ANSWER_NO_REASON: _quiz_answer_no_reason,
    Code.HOMEWORK_SECTION_MALFORMED: _homework_section_malformed,
    Code.NEXT_UP_TOO_LONG: _next_up_too_long,
    Code.ASSET_REFERENCE_DANGLING: _asset_reference_dangling,
    Code.ASSET_REFERENCE_ABSOLUTE: _asset_reference_absolute,
    Code.CEREMONY_UNKNOWN_PLACEHOLDER: _ceremony_unknown_placeholder,
    Code.CEREMONY_HIGHLIGHT_MISSING: _ceremony_highlight_missing,
    Code.CEREMONY_HANDLE_MALFORMED: _ceremony_handle_malformed,
    Code.OBJECTIVES_DECLARED_TWICE: _objectives_declared_twice,
    Code.OBJECTIVE_ID_DUPLICATE: _objective_id_duplicate,
    Code.OBJECTIVE_ABOUT_INVALID: _objective_about_invalid,
    Code.OBJECTIVE_VERIFY_ON_KNOWLEDGE: _objective_verify_on_knowledge,
    Code.OBJECTIVE_CHECK_WITHOUT_VERIFY: _objective_check_without_verify,
}
