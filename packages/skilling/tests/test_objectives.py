"""Addressable objectives.

The point of giving objectives ids is that a runtime can say something specific: this is the
one you missed, and this is the one you demonstrated. Both claims have to be earned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from skilling import lesson as md
from skilling import runtime
from skilling.errors import Code
from skilling.loader import Course, load_course
from skilling.store import FileProgressStore
from skilling.store.file import LOCAL_LEARNER
from skilling.validate import validate_course

from . import fixtures as fx
from .conftest import EXAMPLE_COURSE

NOW = datetime(2026, 8, 3, 14, 31, 7, tzinfo=UTC)

STRUCTURED = """\
objectives:
  - id: know-the-first-thing
    text: Say what the first thing is
    tested_by: [1]
  - id: know-when
    text: Say when to reach for it
    tested_by: [2, 3]
"""


def _make_structured(root: Path) -> None:
    """Convert the clean fixture's first lesson to structured objectives."""
    fx.edit(root, fx.LESSON_ONE_PATH, "skills_unlocked: []\n", f"skills_unlocked: []\n{STRUCTURED}")
    fx.edit(
        root,
        fx.LESSON_ONE_PATH,
        "## Learning Objectives\nBy the end of this lesson, you will:\n- Know the first thing\n\n",
        "",
    )


@pytest.fixture
def structured(clean_dir: Path) -> Course:
    _make_structured(clean_dir)
    return load_course(clean_dir)


# ------------------------------------------------------------------------------ the format


def test_structured_objectives_replace_the_prose_section(clean_dir: Path) -> None:
    _make_structured(clean_dir)
    report = validate_course(clean_dir)
    assert report.findings == [], [f.as_dict() for f in report.findings]

    parsed = md.parse_lesson(clean_dir / fx.LESSON_ONE_PATH)
    assert parsed.frontmatter and len(parsed.frontmatter.objectives) == 2
    assert parsed.section("objectives") is None, "the prose section is gone, not duplicated"


def test_prose_objectives_alone_are_still_valid(clean_dir: Path) -> None:
    """1.0's form keeps working untouched — that is what makes 1.1 additive."""
    assert validate_course(clean_dir).findings == []


def test_declaring_both_is_rejected(clean_dir: Path) -> None:
    fx.edit(
        root := clean_dir,
        fx.LESSON_ONE_PATH,
        "skills_unlocked: []\n",
        f"skills_unlocked: []\n{STRUCTURED}",
    )
    assert Code.OBJECTIVES_DECLARED_TWICE in validate_course(root).codes()


def test_objectives_are_addressable_by_id(structured: Course) -> None:
    lesson = structured.lesson_at("0.1")
    assert lesson
    fm = md.parse_lesson(lesson.path).frontmatter
    assert fm
    assert fm.objective("know-when") is not None
    assert fm.objective("nonexistent") is None


def test_questions_map_back_to_objectives(structured: Course) -> None:
    lesson = structured.lesson_at("0.1")
    assert lesson
    fm = md.parse_lesson(lesson.path).frontmatter
    assert fm
    assert [o.id for o in fm.objectives_for_question(1)] == ["know-the-first-thing"]
    assert [o.id for o in fm.objectives_for_question(2)] == ["know-when"]
    assert fm.objectives_for_question(9) == []


# ---------------------------------------------------------------------- demonstrated by quiz


def test_all_testing_questions_correct_demonstrates_the_objective(structured: Course) -> None:
    lesson = structured.lesson_at("0.1")
    assert lesson
    met = runtime.objectives_demonstrated_by_quiz(lesson, {1: True, 2: True, 3: True})
    assert met == ["know-the-first-thing", "know-when"]


def test_one_wrong_answer_withholds_the_objective(structured: Course) -> None:
    lesson = structured.lesson_at("0.1")
    assert lesson
    met = runtime.objectives_demonstrated_by_quiz(lesson, {1: True, 2: True, 3: False})
    assert met == ["know-the-first-thing"], "know-when needed both 2 and 3"


def test_an_unanswered_question_withholds_the_objective(structured: Course) -> None:
    lesson = structured.lesson_at("0.1")
    assert lesson
    assert runtime.objectives_demonstrated_by_quiz(lesson, {1: True}) == ["know-the-first-thing"]


def test_an_objective_with_no_tested_by_is_never_settled_by_a_quiz(clean_dir: Path) -> None:
    """Guessing would be worse than leaving it absent: a later tutor believes what it reads."""
    fx.edit(
        clean_dir,
        fx.LESSON_ONE_PATH,
        "skills_unlocked: []\n",
        "skills_unlocked: []\nobjectives:\n  - id: unjudgeable\n    text: Appreciate the thing\n",
    )
    fx.edit(
        clean_dir,
        fx.LESSON_ONE_PATH,
        "## Learning Objectives\nBy the end of this lesson, you will:\n- Know the first thing\n\n",
        "",
    )
    course = load_course(clean_dir)
    lesson = course.lesson_at("0.1")
    assert lesson
    assert runtime.objectives_demonstrated_by_quiz(lesson, {1: True, 2: True, 3: True}) == []


def test_a_lesson_without_objectives_yields_nothing(clean: Course) -> None:
    lesson = clean.lesson_at("0.1")
    assert lesson
    assert runtime.objectives_demonstrated_by_quiz(lesson, {1: True}) == []


# ------------------------------------------------------------------------- written to record


def test_marking_writes_the_record(tmp_path: Path, structured: Course) -> None:
    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, structured, LOCAL_LEARNER, now=NOW)
    lesson = structured.lesson_at("0.1")
    assert lesson

    record, revision, fresh = runtime.mark_objectives_met(
        store, record, revision, lesson, {1: True, 2: True, 3: True}, now=NOW
    )

    assert fresh == ["know-the-first-thing", "know-when"]
    assert [o.id for o in record.objectives_met] == fresh
    assert all(o.evidence == "quiz" for o in record.objectives_met)
    assert record.has_met("know-when")

    reread = store.get_record(LOCAL_LEARNER, structured.id)
    assert reread and len(reread[0].objectives_met) == 2


def test_marking_is_idempotent(tmp_path: Path, structured: Course) -> None:
    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, structured, LOCAL_LEARNER, now=NOW)
    lesson = structured.lesson_at("0.1")
    assert lesson

    record, revision, first = runtime.mark_objectives_met(
        store, record, revision, lesson, {1: True, 2: True, 3: True}, now=NOW
    )
    record, revision, second = runtime.mark_objectives_met(
        store, record, revision, lesson, {1: True, 2: True, 3: True}, now=NOW
    )

    assert first and second == []
    assert len(record.objectives_met) == 2


def test_nothing_demonstrated_writes_nothing(tmp_path: Path, structured: Course) -> None:
    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, structured, LOCAL_LEARNER, now=NOW)
    lesson = structured.lesson_at("0.1")
    assert lesson

    updated, new_revision, fresh = runtime.mark_objectives_met(
        store, record, revision, lesson, {1: False, 2: False, 3: False}, now=NOW
    )
    assert fresh == []
    assert updated is record
    assert new_revision == revision, "no write at all when there is nothing to say"


def test_a_runtime_that_records_nothing_still_conforms(tmp_path: Path, structured: Course) -> None:
    """The same position as homework checking: no judgement, no claim, still conforming."""
    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, structured, LOCAL_LEARNER, now=NOW)
    lesson = structured.lesson_at("0.1")
    assert lesson

    outcome = runtime.complete_lesson(store, structured, record, revision, lesson, now=NOW)
    assert outcome.record.completed == ["0.1"]
    assert outcome.record.objectives_met == []


# ---------------------------------------------------------------------------- the validator


def test_tested_by_must_name_a_question_that_exists(clean_dir: Path) -> None:
    fx.edit(
        clean_dir,
        fx.LESSON_ONE_PATH,
        "skills_unlocked: []\n",
        "skills_unlocked: []\nobjectives:\n  - id: know-it\n    text: Know it\n"
        "    tested_by: [4]\n",
    )
    fx.edit(
        clean_dir,
        fx.LESSON_ONE_PATH,
        "## Learning Objectives\nBy the end of this lesson, you will:\n- Know the first thing\n\n",
        "",
    )
    assert Code.OBJECTIVE_TESTED_BY_INVALID in validate_course(clean_dir).codes()


def test_objective_ids_must_be_unique_within_a_lesson(clean_dir: Path) -> None:
    fx.edit(
        clean_dir,
        fx.LESSON_ONE_PATH,
        "skills_unlocked: []\n",
        "skills_unlocked: []\nobjectives:\n  - id: same\n    text: One\n"
        "  - id: same\n    text: Two\n",
    )
    fx.edit(
        clean_dir,
        fx.LESSON_ONE_PATH,
        "## Learning Objectives\nBy the end of this lesson, you will:\n- Know the first thing\n\n",
        "",
    )
    assert Code.OBJECTIVE_ID_DUPLICATE in validate_course(clean_dir).codes()


def test_an_objective_may_not_author_a_structural_count(clean_dir: Path) -> None:
    fx.edit(
        clean_dir,
        fx.LESSON_ONE_PATH,
        "skills_unlocked: []\n",
        "skills_unlocked: []\nobjectives:\n  - id: know-it\n"
        "    text: Know where you are in lesson 1 of 3\n",
    )
    fx.edit(
        clean_dir,
        fx.LESSON_ONE_PATH,
        "## Learning Objectives\nBy the end of this lesson, you will:\n- Know the first thing\n\n",
        "",
    )
    assert Code.AUTHORED_COUNT in validate_course(clean_dir).codes()


# ------------------------------------------------------------------------ the example course


def test_the_example_course_uses_structured_objectives() -> None:
    course = load_course(EXAMPLE_COURSE)
    lesson = course.lesson_at("1.2")
    assert lesson
    fm = md.parse_lesson(lesson.path).frontmatter
    assert fm and len(fm.objectives) == 3
    assert all(o.tested_by for o in fm.objectives), "each maps to a question, so the quiz can judge"
    assert validate_course(EXAMPLE_COURSE).findings == []


def test_badges_and_objectives_stay_separate(tmp_path: Path) -> None:
    """A badge marks completion; an objective claims a capability. Neither implies the other."""
    course = load_course(EXAMPLE_COURSE)
    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, course, LOCAL_LEARNER, now=NOW)

    lesson = course.lesson_at("1.2")
    assert lesson
    # Complete the lesson while demonstrating nothing.
    outcome = runtime.complete_lesson(store, course, record, revision, lesson, now=NOW)

    assert outcome.record.skills_unlocked == ["course-anatomy"], "the badge was awarded"
    assert outcome.record.objectives_met == [], "no objective was claimed"
