"""The golden example: a real 64-lesson course, held to every rule.

`hello-skilling` proves the format works on something written to fit it. This one proves it
works on content that existed first and had to be bent into shape — which is the harder and
more useful claim, and the reason this file asserts structural facts rather than just
"it validates".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skilling import course as md
from skilling import delivery as cer
from skilling.conformance import validate_course
from skilling.course import Course

from .conftest import REPO_ROOT

GOLDEN = REPO_ROOT / "examples" / "coding-bootcamp"


@pytest.fixture(scope="module")
def golden() -> Course:
    return Course.load(GOLDEN)


def test_it_validates_with_zero_findings() -> None:
    report = validate_course(GOLDEN)
    assert report.findings == [], [f.as_dict() for f in report.findings]


def test_its_shape_is_what_the_manifest_says(golden: Course) -> None:
    assert golden.id == "coding-bootcamp"
    assert golden.phase_count == 9
    assert golden.lesson_count == 64
    assert [p.number for p in golden.phases] == list(range(9))
    assert [p.lesson_count for p in golden.phases] == [6, 9, 8, 9, 7, 7, 8, 5, 5]


def test_phase_six_numbering_is_repaired(golden: Course) -> None:
    """The source shipped two lesson-04s, two lesson-05s and no 02 or 03, undetected for
    months. The intended order is in the phase overview: Nav, Hero, About, Skills."""
    phase = golden.phase_at(6)
    assert phase
    assert [lesson.number for lesson in phase.lessons] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert [lesson.slug for lesson in phase.lessons][:5] == [
        "portfolio-architecture-overview",
        "building-the-navigation",
        "building-the-hero-section",
        "building-the-about-section",
        "building-the-skills-section",
    ]


def test_every_lesson_file_exists_at_its_derived_path(golden: Course) -> None:
    missing = [lesson.coordinate for lesson in golden.lessons() if not lesson.path.is_file()]
    assert missing == []


def test_homework_lands_at_every_phase_boundary(golden: Course) -> None:
    with_homework = {lesson.coordinate for lesson in golden.lessons() if lesson.homework}
    boundaries = {phase.lessons[-1].coordinate for phase in golden.phases}
    assert with_homework == boundaries, "every phase ends in homework, and nothing else carries it"


def test_all_twelve_badges_are_registered_and_reachable(golden: Course) -> None:
    registered = golden.manifest.badge_ids
    assert len(registered) == 12

    unlocked: set[str] = set()
    for lesson in golden.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        unlocked.update(fm.skills_unlocked)

    assert unlocked == registered, "a badge nobody unlocks is a promise nobody keeps"


# ------------------------------------------------------------------- structured objectives


def test_every_lesson_uses_structured_objectives(golden: Course) -> None:
    for lesson in golden.lessons():
        parsed = md.parse_lesson(lesson.path)
        assert parsed.frontmatter and parsed.frontmatter.objectives, lesson.coordinate
        assert parsed.section("objectives") is None, (
            f"{lesson.coordinate}: prose and structured objectives are mutually exclusive"
        )


def test_objective_ids_are_unique_within_each_lesson(golden: Course) -> None:
    for lesson in golden.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        ids = [o.id for o in fm.objectives]
        assert len(ids) == len(set(ids)), lesson.coordinate


def test_every_objective_declares_what_kind_of_claim_it_is(golden: Course) -> None:
    kinds: dict[str, int] = {"knowledge": 0, "practice": 0}
    for lesson in golden.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        for objective in fm.objectives:
            kinds[objective.kind] += 1

    assert sum(kinds.values()) > 200
    assert kinds["practice"] > kinds["knowledge"], "a hands-on course is mostly practice"


def test_only_practice_objectives_carry_verification(golden: Course) -> None:
    for lesson in golden.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        for objective in fm.objectives:
            if objective.kind == "knowledge":
                assert not objective.verify, f"{lesson.coordinate}/{objective.id}"
                assert not objective.check


def test_verify_is_written_where_observation_is_possible_and_nowhere_else(
    golden: Course,
) -> None:
    """Deliberately partial. Most practice here cannot be observed from outside — "apply the
    design system consistently" is a judgement — and inventing a check for those is exactly
    the false confidence 1.2 exists to remove."""
    observable = unobservable = 0
    for lesson in golden.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        for objective in fm.objectives:
            if objective.kind != "practice":
                continue
            if objective.verify:
                observable += 1
                assert len(objective.verify.split()) >= 5, objective.id
            else:
                unobservable += 1

    assert observable >= 20, "the environment, git and deploy objectives are checkable"
    assert unobservable > observable, "and most of the rest honestly are not"


def test_a_runtime_with_no_capabilities_may_settle_nothing_here(golden: Course) -> None:
    from skilling import delivery as runtime

    for lesson in golden.lessons():
        assert runtime.settleable(lesson, []) == [], lesson.coordinate


def test_observation_reaches_exactly_the_verified_practice_objectives(golden: Course) -> None:
    from skilling import delivery as runtime
    from skilling.course import Capability

    reached = 0
    for lesson in golden.lessons():
        for objective in runtime.settleable(lesson, [Capability.OBSERVE]):
            assert objective.kind == "practice" and objective.verify
            reached += 1
    assert reached >= 20


def test_about_only_names_questions_that_exist(golden: Course) -> None:
    for lesson in golden.lessons():
        parsed = md.parse_lesson(lesson.path)
        fm, quiz = parsed.frontmatter, parsed.section("quiz")
        assert fm and quiz
        numbers = {q.number for q in md.parse_quiz(quiz.body, quiz.body_line)}
        for objective in fm.objectives:
            assert set(objective.about) <= numbers, f"{lesson.coordinate}/{objective.id}"


# ---------------------------------------------------------------------- declared absences


def test_every_absence_carries_a_reason(golden: Course) -> None:
    absences = 0
    for lesson in golden.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        for key, declaration in fm.sections.items():
            if declaration == "present":
                continue
            absences += 1
            intent = getattr(declaration, "intent", "")
            assert len(intent.split()) >= 5, f"{lesson.coordinate}/{key}: {intent!r}"
            assert "TODO" not in intent

    assert absences == 43, "24 exercise, 12 key terms, 7 next-up"


def test_the_project_phases_declare_why_they_have_no_exercise(golden: Course) -> None:
    for coordinate in ("4.1", "5.1", "6.1"):
        lesson = golden.lesson_at(coordinate)
        assert lesson
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        declaration = fm.declaration("exercise")
        assert getattr(declaration, "status", None) == "none", coordinate


# ------------------------------------------------------------------------------- ceremony


def test_ceremony_carries_facts_a_tutor_may_not_invent(golden: Course) -> None:
    ceremony = golden.manifest.ceremony
    assert ceremony and ceremony.brand
    brand = ceremony.brand
    assert brand.product and brand.url and brand.mention
    assert brand.handles and brand.hashtags
    assert all(handle.startswith("@") for handle in brand.handles.values())
    assert all(not tag.startswith("#") for tag in brand.hashtags), "the runtime adds the hash"


def test_every_phase_has_a_pronoun_free_highlight(golden: Course) -> None:
    """A highlight is used in the third person by a tutor and the first by a share post, so a
    possessive pronoun reads wrong in half the places it appears."""
    for phase in golden.phases:
        assert phase.highlight, phase.number
        words = phase.highlight.lower().split()
        for pronoun in ("their", "theirs", "his", "her", "my", "your"):
            assert pronoun not in words, f"phase {phase.number}: {phase.highlight!r}"


def test_the_share_template_renders_with_derived_counts(golden: Course) -> None:
    text = cer.share_text(golden, None, golden.phase_at(0))
    assert text
    assert "Phase 0: Getting Started" in text
    assert "0 of 64 lessons done" in text, "the runtime fills the count; the author never wrote it"
    assert "@claudeai" in text
    assert "#WebDev" in text, "hashtags arrive with their hash added"


def test_no_lesson_authors_a_structural_count() -> None:
    """The source stated a lesson count in its closing section. Nothing may now."""
    from skilling.conformance._validate import _BODY_COUNTS, _MANIFEST_COUNTS

    for path in sorted(GOLDEN.rglob("*.md")):
        for line in md.strip_code(path.read_text(encoding="utf-8")).splitlines():
            for pattern in _MANIFEST_COUNTS + _BODY_COUNTS:
                assert not pattern.search(line), f"{path.name}: {line.strip()[:70]!r}"


def test_the_quiz_grammar_holds_across_all_192_questions(golden: Course) -> None:
    questions = 0
    for lesson in golden.lessons():
        quiz = md.parse_lesson(lesson.path).section("quiz")
        assert quiz
        parsed = md.parse_quiz(quiz.body, quiz.body_line)
        assert len(parsed) == 3, lesson.coordinate
        for question in parsed:
            assert sorted(question.labels) == ["a", "b", "c", "d"], lesson.coordinate
            assert question.answer_label, lesson.coordinate
            assert question.has_reason, f"{lesson.coordinate} q{question.number}"
            questions += 1
    assert questions == 192


def test_prerequisites_form_an_unbroken_chain(golden: Course) -> None:
    """The source's phase-6 prerequisites pointed at a lesson 6-03 that did not exist. Derived
    structurally, they cannot."""
    coordinates = golden.coordinates
    for i, coordinate in enumerate(coordinates):
        lesson = golden.lesson_at(coordinate)
        assert lesson
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        expected = [] if i == 0 else [coordinates[i - 1]]
        assert fm.prerequisites == expected, coordinate


def test_it_is_licensed_for_reuse(golden: Course) -> None:
    assert golden.manifest.license == "CC-BY-4.0"


def test_the_examples_index_describes_both_courses() -> None:
    text = (REPO_ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    assert "coding-bootcamp" in text
    assert "hello-skilling" in text


def test_every_phase_has_an_overview(golden: Course) -> None:
    for phase in golden.phases:
        assert phase.overview_path is not None, phase.number


def test_state_written_by_a_walk_stays_small(tmp_path: Path, golden: Course) -> None:
    """A 64-lesson course must not produce a record that grows unboundedly — the whole point
    of a derived, transcript-free record."""
    from skilling import delivery as runtime
    from skilling.store import LOCAL_LEARNER, FileProgressStore

    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, golden, LOCAL_LEARNER)
    for lesson in golden.lessons():
        outcome = runtime.complete_lesson(store, golden, record, revision, lesson)
        record, revision = outcome.record, outcome.revision

    assert len(record.completed) == 64
    assert len(record.skills_unlocked) == 12
    assert golden.percent_complete(record.completed) == 100.0
    size = (tmp_path / "state" / golden.id / "record.yaml").stat().st_size
    assert size < 4096, f"record.yaml is {size} bytes for a 64-lesson course"
