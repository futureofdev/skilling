"""Addressable objectives.

The point of giving objectives ids is that a runtime can say something specific: this is the
one you missed, and this is the one you demonstrated. Both claims have to be earned.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from skilling import course as md
from skilling import delivery as runtime
from skilling.conformance import Code, validate_course
from skilling.course import Capability, Course
from skilling.store import LOCAL_LEARNER, FileProgressStore

from . import fixtures as fx
from .conftest import EXAMPLE_COURSE

NOW = datetime(2026, 8, 3, 14, 31, 7, tzinfo=UTC)

STRUCTURED = """\
objectives:
  - id: know-the-first-thing
    kind: knowledge
    text: Say what the first thing is
    about: [1]
  - id: do-the-first-thing
    kind: practice
    text: Do the first thing on your own machine
    verify: "The first thing exists where the learner made it"
  - id: judge-it
    kind: practice
    text: Apply the first thing tastefully
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
    return Course.load(clean_dir)


# ------------------------------------------------------------------------------ the format


def test_structured_objectives_replace_the_prose_section(clean_dir: Path) -> None:
    _make_structured(clean_dir)
    report = validate_course(clean_dir)
    assert report.findings == [], [f.as_dict() for f in report.findings]

    parsed = md.parse_lesson(clean_dir / fx.LESSON_ONE_PATH)
    assert parsed.frontmatter and len(parsed.frontmatter.objectives) == 3
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
    assert fm.objective("do-the-first-thing") is not None
    assert fm.objective("nonexistent") is None


def test_questions_map_back_to_objectives(structured: Course) -> None:
    lesson = structured.lesson_at("0.1")
    assert lesson
    fm = md.parse_lesson(lesson.path).frontmatter
    assert fm
    assert [o.id for o in fm.objectives_for_question(1)] == ["know-the-first-thing"]
    assert fm.objectives_for_question(2) == [], "only question 1 is pointed at"
    assert fm.objectives_for_question(9) == []


# ------------------------------------------------------------- capabilities decide evidence


def test_a_runtime_with_nothing_may_settle_nothing(structured: Course) -> None:
    lesson = structured.lesson_at("0.1")
    assert lesson
    assert runtime.settleable(lesson, []) == []


def test_converse_settles_knowledge_only(structured: Course) -> None:
    lesson = structured.lesson_at("0.1")
    assert lesson
    ids = [o.id for o in runtime.settleable(lesson, [Capability.CONVERSE])]
    assert ids == ["know-the-first-thing"]


def test_observe_settles_practice_that_says_what_to_look_for(structured: Course) -> None:
    """A practice objective with no verify cannot be observed, even by a runtime that can
    look — there is nothing telling it what success would be."""
    lesson = structured.lesson_at("0.1")
    assert lesson
    ids = [o.id for o in runtime.settleable(lesson, [Capability.OBSERVE])]
    assert ids == ["do-the-first-thing"], "judge-it has no verify, so it stays unsettleable"


def test_both_capabilities_settle_both_kinds(structured: Course) -> None:
    lesson = structured.lesson_at("0.1")
    assert lesson
    ids = {o.id for o in runtime.settleable(lesson, [Capability.CONVERSE, Capability.OBSERVE])}
    assert ids == {"know-the-first-thing", "do-the-first-thing"}


def test_a_quiz_settles_nothing() -> None:
    """There is no evidence value for a quiz, and no code path that produces one."""
    from skilling.course import SETTLES

    assert "quiz" not in {evidence for _, evidence in SETTLES.values()}


# ------------------------------------------------------------------------- written to record


def test_marking_writes_only_what_the_runtime_could_observe(
    tmp_path: Path, structured: Course
) -> None:
    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, structured, LOCAL_LEARNER, now=NOW)
    lesson = structured.lesson_at("0.1")
    assert lesson

    # A conversational tutor claims all three. Only the knowledge one is its to claim.
    record, revision, fresh = runtime.mark_objectives_met(
        store,
        record,
        revision,
        lesson,
        ["know-the-first-thing", "do-the-first-thing", "judge-it"],
        [Capability.CONVERSE],
        now=NOW,
    )

    assert fresh == ["know-the-first-thing"]
    assert [o.evidence for o in record.objectives_met] == ["explained"]


def test_evidence_follows_from_the_kind_not_the_caller(tmp_path: Path, structured: Course) -> None:
    """A caller cannot label an observation as an explanation, or vice versa."""
    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, structured, LOCAL_LEARNER, now=NOW)
    lesson = structured.lesson_at("0.1")
    assert lesson

    record, _, fresh = runtime.mark_objectives_met(
        store, record, revision, lesson, ["do-the-first-thing"], [Capability.OBSERVE], now=NOW
    )
    assert fresh == ["do-the-first-thing"]
    assert record.objectives_met[0].evidence == "observed"


def test_a_claim_beyond_capability_is_not_merely_ignored_but_unwritable(
    tmp_path: Path, structured: Course
) -> None:
    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, structured, LOCAL_LEARNER, now=NOW)
    lesson = structured.lesson_at("0.1")
    assert lesson

    updated, new_revision, fresh = runtime.mark_objectives_met(
        store, record, revision, lesson, ["do-the-first-thing"], [], now=NOW
    )
    assert fresh == []
    assert updated is record
    assert new_revision == revision, "no write at all when nothing may be claimed"

    reread = store.get_record(LOCAL_LEARNER, structured.id)
    assert reread and reread[0].objectives_met == []


def test_marking_is_idempotent(tmp_path: Path, structured: Course) -> None:
    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, structured, LOCAL_LEARNER, now=NOW)
    lesson = structured.lesson_at("0.1")
    assert lesson
    caps = [Capability.CONVERSE, Capability.OBSERVE]

    record, revision, first = runtime.mark_objectives_met(
        store, record, revision, lesson, ["know-the-first-thing"], caps, now=NOW
    )
    record, revision, second = runtime.mark_objectives_met(
        store, record, revision, lesson, ["know-the-first-thing"], caps, now=NOW
    )
    assert first == ["know-the-first-thing"] and second == []
    assert len(record.objectives_met) == 1


def test_an_unknown_objective_id_is_never_written(tmp_path: Path, structured: Course) -> None:
    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, structured, LOCAL_LEARNER, now=NOW)
    lesson = structured.lesson_at("0.1")
    assert lesson
    _, _, fresh = runtime.mark_objectives_met(
        store, record, revision, lesson, ["invented"], [Capability.CONVERSE], now=NOW
    )
    assert fresh == []


def test_a_runtime_that_records_nothing_still_conforms(tmp_path: Path, structured: Course) -> None:
    """The same position as homework checking: no capability, no claim, still conforming."""
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
        "skills_unlocked: []\nobjectives:\n  - id: know-it\n    kind: knowledge\n"
        "    text: Know it\n    about: [4]\n",
    )
    fx.edit(
        clean_dir,
        fx.LESSON_ONE_PATH,
        "## Learning Objectives\nBy the end of this lesson, you will:\n- Know the first thing\n\n",
        "",
    )
    assert Code.OBJECTIVE_ABOUT_INVALID in validate_course(clean_dir).codes()


def test_objective_ids_must_be_unique_within_a_lesson(clean_dir: Path) -> None:
    fx.edit(
        clean_dir,
        fx.LESSON_ONE_PATH,
        "skills_unlocked: []\n",
        "skills_unlocked: []\nobjectives:\n  - id: same\n    kind: knowledge\n    text: One\n"
        "  - id: same\n    kind: knowledge\n    text: Two\n",
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
        "skills_unlocked: []\nobjectives:\n  - id: know-it\n    kind: knowledge\n"
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
    course = Course.load(EXAMPLE_COURSE)
    lesson = course.lesson_at("1.2")
    assert lesson
    fm = md.parse_lesson(lesson.path).frontmatter
    assert fm and len(fm.objectives) == 3
    assert all(o.kind == "knowledge" for o in fm.objectives), "a conceptual course, all knowledge"
    assert all(o.about for o in fm.objectives), "each points at a question, for remediation"
    assert validate_course(EXAMPLE_COURSE).findings == []


def test_badges_and_objectives_stay_separate(tmp_path: Path) -> None:
    """A badge marks completion; an objective claims a capability. Neither implies the other."""
    course = Course.load(EXAMPLE_COURSE)
    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, course, LOCAL_LEARNER, now=NOW)

    lesson = course.lesson_at("1.2")
    assert lesson
    # Complete the lesson while demonstrating nothing.
    outcome = runtime.complete_lesson(store, course, record, revision, lesson, now=NOW)

    assert outcome.record.skills_unlocked == ["course-anatomy"], "the badge was awarded"
    assert outcome.record.objectives_met == [], "no objective was claimed"
