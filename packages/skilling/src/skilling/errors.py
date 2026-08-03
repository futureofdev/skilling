"""The validator's error-code catalogue.

Codes are the stable identifiers people build CI on, so they are immutable: never
renamed, never renumbered, never reused. To change what a code means, retire it and
add a new one. See CONTRIBUTING.md.

The specification itself carries no per-rule identifiers — findings cite an anchor
into the spec instead, which is what ``anchor`` below holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

SPEC_MAJOR = 1
"""The specification major version this implementation supports."""

SPEC_MINOR = 1
"""The specification minor version this implementation supports."""


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class Code(StrEnum):
    """Every finding a validator can report. Immutable — see module docstring."""

    # --- the manifest as a document ---
    MANIFEST_MISSING = "manifest-missing"
    MANIFEST_UNPARSEABLE = "manifest-unparseable"
    MANIFEST_INVALID = "manifest-invalid"
    SPEC_VERSION_UNSUPPORTED = "spec-version-unsupported"
    SPEC_VERSION_NEWER_MINOR = "spec-version-newer-minor"
    COURSE_ID_INVALID = "course-id-invalid"
    COURSE_VERSION_INVALID = "course-version-invalid"
    LICENSE_UNKNOWN = "license-unknown"
    BADGE_ID_DUPLICATE = "badge-id-duplicate"

    # --- structure across manifest and disk ---
    PHASE_NUMBER_DUPLICATE = "phase-number-duplicate"
    PHASE_NUMBERING_GAP = "phase-numbering-gap"
    LESSON_NUMBER_DUPLICATE = "lesson-number-duplicate"
    LESSON_NUMBERING_GAP = "lesson-numbering-gap"
    LESSON_FILE_MISSING = "lesson-file-missing"
    LESSON_FILE_ORPHAN = "lesson-file-orphan"
    FRONTMATTER_MANIFEST_MISMATCH = "frontmatter-manifest-mismatch"
    HOMEWORK_DECLARATION_MISMATCH = "homework-declaration-mismatch"
    BADGE_UNREGISTERED = "badge-unregistered"
    PREREQUISITE_UNRESOLVED = "prerequisite-unresolved"
    AUTHORED_COUNT = "authored-count"

    # --- the lesson as a document ---
    LESSON_UNPARSEABLE = "lesson-unparseable"
    LESSON_FRONTMATTER_INVALID = "lesson-frontmatter-invalid"
    SECTION_MISSING = "section-missing"
    SECTION_OUT_OF_ORDER = "section-out-of-order"
    SECTION_UNKNOWN_HEADING = "section-unknown-heading"
    SECTION_ABSENCE_UNDECLARED = "section-absence-undeclared"
    SECTION_ABSENCE_MISSING_INTENT = "section-absence-missing-intent"
    SECTION_DECLARED_PRESENT_BUT_ABSENT = "section-declared-present-but-absent"
    OBJECTIVES_EMPTY = "objectives-empty"
    KEY_TERMS_MALFORMED = "key-terms-malformed"
    EXERCISE_EMPTY = "exercise-empty"
    QUIZ_WRONG_QUESTION_COUNT = "quiz-wrong-question-count"
    QUIZ_WRONG_OPTION_COUNT = "quiz-wrong-option-count"
    QUIZ_ANSWER_LINE_MISSING = "quiz-answer-line-missing"
    QUIZ_ANSWER_AMBIGUOUS = "quiz-answer-ambiguous"
    QUIZ_ANSWER_NO_REASON = "quiz-answer-no-reason"
    HOMEWORK_SECTION_MALFORMED = "homework-section-malformed"
    NEXT_UP_TOO_LONG = "next-up-too-long"

    # --- assets ---
    ASSET_REFERENCE_DANGLING = "asset-reference-dangling"
    ASSET_REFERENCE_ABSOLUTE = "asset-reference-absolute"

    # --- ceremony (since spec 1.1) ---
    CEREMONY_UNKNOWN_PLACEHOLDER = "ceremony-unknown-placeholder"
    CEREMONY_HIGHLIGHT_MISSING = "ceremony-highlight-missing"
    CEREMONY_HANDLE_MALFORMED = "ceremony-handle-malformed"

    # --- structured objectives (since spec 1.1) ---
    OBJECTIVES_DECLARED_TWICE = "objectives-declared-twice"
    OBJECTIVE_ID_DUPLICATE = "objective-id-duplicate"
    OBJECTIVE_TESTED_BY_INVALID = "objective-tested-by-invalid"


@dataclass(frozen=True)
class CodeInfo:
    severity: Severity
    anchor: str
    summary: str


_C = Code
_E = Severity.ERROR
_W = Severity.WARNING

_FORMAT = "spec/course-format.md"

CATALOGUE: dict[Code, CodeInfo] = {
    _C.MANIFEST_MISSING: CodeInfo(
        _E, f"{_FORMAT}#directory-structure", "No course.yaml at the course root"
    ),
    _C.MANIFEST_UNPARSEABLE: CodeInfo(
        _E, f"{_FORMAT}#the-manifest", "course.yaml is not valid YAML"
    ),
    _C.MANIFEST_INVALID: CodeInfo(
        _E, f"{_FORMAT}#manifest-fields", "course.yaml has a missing, mistyped, or unknown field"
    ),
    _C.SPEC_VERSION_UNSUPPORTED: CodeInfo(
        _E, f"{_FORMAT}#manifest-fields", "spec_version names a major version this tool cannot read"
    ),
    _C.SPEC_VERSION_NEWER_MINOR: CodeInfo(
        _W, f"{_FORMAT}#manifest-fields", "spec_version names a newer minor version than this tool"
    ),
    _C.COURSE_ID_INVALID: CodeInfo(
        _E, f"{_FORMAT}#manifest-fields", "id is not lowercase kebab-case within 1-64 characters"
    ),
    _C.COURSE_VERSION_INVALID: CodeInfo(
        _E, f"{_FORMAT}#course-versions", "version is not a semantic version"
    ),
    _C.LICENSE_UNKNOWN: CodeInfo(
        _E, f"{_FORMAT}#manifest-fields", "license is neither an SPDX identifier nor 'proprietary'"
    ),
    _C.BADGE_ID_DUPLICATE: CodeInfo(
        _E, f"{_FORMAT}#manifest-fields", "Two registered skills share an id"
    ),
    _C.PHASE_NUMBER_DUPLICATE: CodeInfo(
        _E, f"{_FORMAT}#numbering-and-structure", "Two phases share a number"
    ),
    _C.PHASE_NUMBERING_GAP: CodeInfo(
        _E,
        f"{_FORMAT}#numbering-and-structure",
        "Phase numbers do not ascend by exactly 1 from 0 or 1",
    ),
    _C.LESSON_NUMBER_DUPLICATE: CodeInfo(
        _E, f"{_FORMAT}#numbering-and-structure", "Two lessons in a phase share a number"
    ),
    _C.LESSON_NUMBERING_GAP: CodeInfo(
        _E, f"{_FORMAT}#numbering-and-structure", "Lesson numbers do not ascend by exactly 1 from 1"
    ),
    _C.LESSON_FILE_MISSING: CodeInfo(
        _E,
        f"{_FORMAT}#numbering-and-structure",
        "The manifest lists a lesson with no file at its derived path",
    ),
    _C.LESSON_FILE_ORPHAN: CodeInfo(
        _E,
        f"{_FORMAT}#numbering-and-structure",
        "A lesson file on disk does not appear in the manifest",
    ),
    _C.FRONTMATTER_MANIFEST_MISMATCH: CodeInfo(
        _E,
        f"{_FORMAT}#frontmatter",
        "A lesson's title, phase, or lesson number disagrees with the manifest",
    ),
    _C.HOMEWORK_DECLARATION_MISMATCH: CodeInfo(
        _E,
        f"{_FORMAT}#numbering-and-structure",
        "The manifest's homework flag and the lesson's Homework Assignment section disagree",
    ),
    _C.BADGE_UNREGISTERED: CodeInfo(
        _E, f"{_FORMAT}#frontmatter", "skills_unlocked names a badge not registered in the manifest"
    ),
    _C.PREREQUISITE_UNRESOLVED: CodeInfo(
        _E, f"{_FORMAT}#frontmatter", "A prerequisite coordinate does not exist in the manifest"
    ),
    _C.AUTHORED_COUNT: CodeInfo(
        _E,
        f"{_FORMAT}#derived-counts",
        "A structural count is written down instead of derived from the manifest",
    ),
    _C.LESSON_UNPARSEABLE: CodeInfo(
        _E, f"{_FORMAT}#frontmatter", "A lesson file has no readable YAML frontmatter block"
    ),
    _C.LESSON_FRONTMATTER_INVALID: CodeInfo(
        _E, f"{_FORMAT}#frontmatter", "Lesson frontmatter has a missing, mistyped, or unknown field"
    ),
    _C.SECTION_MISSING: CodeInfo(
        _E, f"{_FORMAT}#the-section-registry", "A required section heading is absent"
    ),
    _C.SECTION_OUT_OF_ORDER: CodeInfo(
        _E, f"{_FORMAT}#the-section-registry", "Sections do not appear in registry order"
    ),
    _C.SECTION_UNKNOWN_HEADING: CodeInfo(
        _E, f"{_FORMAT}#the-section-registry", "A '##' heading is not in the section registry"
    ),
    _C.SECTION_ABSENCE_UNDECLARED: CodeInfo(
        _E, f"{_FORMAT}#declared-absence", "An optional section is not declared in 'sections'"
    ),
    _C.SECTION_ABSENCE_MISSING_INTENT: CodeInfo(
        _E, f"{_FORMAT}#declared-absence", "A declared absence carries no intent"
    ),
    _C.SECTION_DECLARED_PRESENT_BUT_ABSENT: CodeInfo(
        _E,
        f"{_FORMAT}#declared-absence",
        "A section declared present, or declared absent while present, contradicts the file",
    ),
    _C.OBJECTIVES_EMPTY: CodeInfo(
        _E, f"{_FORMAT}#learning-objectives", "Learning Objectives contains no bullet list"
    ),
    _C.KEY_TERMS_MALFORMED: CodeInfo(
        _E, f"{_FORMAT}#key-terms", "A Key Terms item is not '- **Term**: definition'"
    ),
    _C.EXERCISE_EMPTY: CodeInfo(
        _E, f"{_FORMAT}#hands-on-exercise", "Hands-On Exercise is declared present but has no body"
    ),
    _C.QUIZ_WRONG_QUESTION_COUNT: CodeInfo(
        _E, f"{_FORMAT}#quick-quiz", "Quick Quiz does not contain exactly three questions"
    ),
    _C.QUIZ_WRONG_OPTION_COUNT: CodeInfo(
        _E, f"{_FORMAT}#quick-quiz", "A quiz question does not have exactly four options a) to d)"
    ),
    _C.QUIZ_ANSWER_LINE_MISSING: CodeInfo(
        _E, f"{_FORMAT}#quick-quiz", "A quiz question has no '**Answer:**' line"
    ),
    _C.QUIZ_ANSWER_AMBIGUOUS: CodeInfo(
        _E, f"{_FORMAT}#quick-quiz", "An answer line does not name exactly one of the four options"
    ),
    _C.QUIZ_ANSWER_NO_REASON: CodeInfo(
        _E, f"{_FORMAT}#quick-quiz", "An answer line states the correct option but gives no reason"
    ),
    _C.HOMEWORK_SECTION_MALFORMED: CodeInfo(
        _E,
        f"{_FORMAT}#homework-assignment",
        "Homework Assignment is missing its title, Objective, requirements, or Submission line",
    ),
    _C.NEXT_UP_TOO_LONG: CodeInfo(
        _W, f"{_FORMAT}#next-up", "Next Up is longer than the one or two sentences intended"
    ),
    _C.ASSET_REFERENCE_DANGLING: CodeInfo(
        _E, f"{_FORMAT}#assets", "A lesson references an asset that does not exist"
    ),
    _C.ASSET_REFERENCE_ABSOLUTE: CodeInfo(
        _E, f"{_FORMAT}#assets", "An asset reference is absolute or escapes the course directory"
    ),
    _C.CEREMONY_UNKNOWN_PLACEHOLDER: CodeInfo(
        _E, f"{_FORMAT}#placeholders", "A ceremony template uses a placeholder no runtime can fill"
    ),
    _C.CEREMONY_HIGHLIGHT_MISSING: CodeInfo(
        _E,
        f"{_FORMAT}#placeholders",
        "A template uses {phase_highlight} but a phase has no highlight to fill it with",
    ),
    _C.CEREMONY_HANDLE_MALFORMED: CodeInfo(
        _W, f"{_FORMAT}#ceremony", "A social handle does not begin with '@'"
    ),
    _C.OBJECTIVES_DECLARED_TWICE: CodeInfo(
        _E,
        f"{_FORMAT}#structured-objectives",
        "Objectives are declared in frontmatter and as a section; they are mutually exclusive",
    ),
    _C.OBJECTIVE_ID_DUPLICATE: CodeInfo(
        _E, f"{_FORMAT}#structured-objectives", "Two objectives in one lesson share an id"
    ),
    _C.OBJECTIVE_TESTED_BY_INVALID: CodeInfo(
        _E,
        f"{_FORMAT}#structured-objectives",
        "An objective's tested_by names a quiz question that does not exist",
    ),
}


def info(code: Code) -> CodeInfo:
    return CATALOGUE[code]


def missing_from_catalogue() -> set[Code]:
    """Codes declared on ``Code`` but absent from ``CATALOGUE``. Should always be empty."""
    return set(Code) - set(CATALOGUE)
