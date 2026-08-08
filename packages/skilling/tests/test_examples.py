"""The exercising example: every authoring surface, in a course sized for a test run.

`hello-skilling` teaches the format; `workbench` exists to exercise it. Its job is to touch
every surface the format has — both objective kinds, honest `verify` coverage, a `check`
proposal, declared absences with reasons, badges, ceremony brand facts and a literal share
template, an asset, homework at each phase boundary — while staying small enough that a real
host can deliver it end to end in one sitting. This file asserts those structural facts, so
the course cannot quietly stop covering a surface it exists to cover.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skilling import course as md
from skilling import delivery as cer
from skilling.conformance import validate_course
from skilling.course import Course

from .conftest import REPO_ROOT

EXERCISER = REPO_ROOT / "examples" / "workbench"


@pytest.fixture(scope="module")
def bench() -> Course:
    return Course.load(EXERCISER)


def test_it_validates_with_zero_findings() -> None:
    report = validate_course(EXERCISER)
    assert report.findings == [], [f.as_dict() for f in report.findings]


def test_its_shape_is_what_the_manifest_says(bench: Course) -> None:
    assert bench.id == "workbench"
    assert bench.phase_count == 2
    assert bench.lesson_count == 4
    assert [p.number for p in bench.phases] == [1, 2]
    assert [p.lesson_count for p in bench.phases] == [2, 2]


def test_every_lesson_file_exists_at_its_derived_path(bench: Course) -> None:
    missing = [lesson.coordinate for lesson in bench.lessons() if not lesson.path.is_file()]
    assert missing == []


def test_it_stays_small_enough_to_deliver_in_one_sitting(bench: Course) -> None:
    """The course's reason to exist: a full end-to-end delivery must be a quick test, not an
    afternoon. Durations are estimates, but letting them creep is how a smoke test dies."""
    total = 0
    for lesson in bench.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm and fm.duration_minutes
        total += fm.duration_minutes
    assert total <= 60


def test_homework_lands_at_every_phase_boundary(bench: Course) -> None:
    with_homework = {lesson.coordinate for lesson in bench.lessons() if lesson.homework}
    boundaries = {phase.lessons[-1].coordinate for phase in bench.phases}
    assert with_homework == boundaries, "every phase ends in homework, and nothing else carries it"


def test_every_badge_is_registered_and_reachable(bench: Course) -> None:
    registered = bench.manifest.badge_ids
    assert len(registered) == 3

    unlocked: set[str] = set()
    for lesson in bench.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        unlocked.update(fm.skills_unlocked)

    assert unlocked == registered, "a badge nobody unlocks is a promise nobody keeps"


# ------------------------------------------------------------------- structured objectives


def test_every_lesson_uses_structured_objectives(bench: Course) -> None:
    for lesson in bench.lessons():
        parsed = md.parse_lesson(lesson.path)
        assert parsed.frontmatter and parsed.frontmatter.objectives, lesson.coordinate
        assert parsed.section("objectives") is None, (
            f"{lesson.coordinate}: prose and structured objectives are mutually exclusive"
        )


def test_objective_ids_are_unique_within_each_lesson(bench: Course) -> None:
    for lesson in bench.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        ids = [o.id for o in fm.objectives]
        assert len(ids) == len(set(ids)), lesson.coordinate


def test_both_objective_kinds_appear(bench: Course) -> None:
    kinds: dict[str, int] = {"knowledge": 0, "practice": 0}
    for lesson in bench.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        for objective in fm.objectives:
            kinds[objective.kind] += 1

    assert kinds["knowledge"] >= 4
    assert kinds["practice"] >= 4, "a hands-on course is mostly practice"


def test_only_practice_objectives_carry_verification(bench: Course) -> None:
    for lesson in bench.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        for objective in fm.objectives:
            if objective.kind == "knowledge":
                assert not objective.verify, f"{lesson.coordinate}/{objective.id}"
                assert not objective.check


def test_verify_coverage_is_honest(bench: Course) -> None:
    """Every lesson carries at least one observable practice objective — the surface the
    coding-harness hosts exist to settle — and at least one practice objective stays
    deliberately unverifiable, because pretending judgement is checkable is the false
    confidence the `kind` split exists to remove."""
    verified = unverified = with_check = 0
    for lesson in bench.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        for objective in fm.objectives:
            if objective.kind != "practice":
                continue
            if objective.verify:
                verified += 1
                assert len(objective.verify.split()) >= 5, objective.id
            else:
                unverified += 1
            if objective.check:
                with_check += 1

    assert verified == 4, "one observable practice objective per lesson"
    assert unverified >= 1, "and at least one that stays a judgement"
    assert with_check >= 1, "at least one literal check proposal, so that surface is exercised"


def test_a_runtime_with_no_capabilities_may_settle_nothing_here(bench: Course) -> None:
    from skilling import delivery as runtime

    for lesson in bench.lessons():
        assert runtime.settleable(lesson, []) == [], lesson.coordinate


def test_observation_reaches_exactly_the_verified_practice_objectives(bench: Course) -> None:
    from skilling import delivery as runtime
    from skilling.course import Capability

    reached = 0
    for lesson in bench.lessons():
        for objective in runtime.settleable(lesson, [Capability.OBSERVE]):
            assert objective.kind == "practice" and objective.verify
            reached += 1
    assert reached == 4


def test_about_only_names_questions_that_exist(bench: Course) -> None:
    for lesson in bench.lessons():
        parsed = md.parse_lesson(lesson.path)
        fm, quiz = parsed.frontmatter, parsed.section("quiz")
        assert fm and quiz
        numbers = {q.number for q in md.parse_quiz(quiz.body, quiz.body_line)}
        for objective in fm.objectives:
            assert set(objective.about) <= numbers, f"{lesson.coordinate}/{objective.id}"


# ---------------------------------------------------------------------- declared absences


def test_every_absence_carries_a_reason(bench: Course) -> None:
    absences = 0
    for lesson in bench.lessons():
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        for key, declaration in fm.sections.items():
            if declaration == "present":
                continue
            absences += 1
            intent = getattr(declaration, "intent", "")
            assert len(intent.split()) >= 5, f"{lesson.coordinate}/{key}: {intent!r}"
            assert "TODO" not in intent

    assert absences == 3, "a key-terms absence, and the final lesson's exercise and next-up"


def test_the_final_lesson_declares_why_it_ends_quietly(bench: Course) -> None:
    last = bench.lesson_at(bench.coordinates[-1])
    assert last
    fm = md.parse_lesson(last.path).frontmatter
    assert fm
    for key in ("exercise", "next_up"):
        declaration = fm.declaration(key)
        assert getattr(declaration, "status", None) == "none", key


# ------------------------------------------------------------------------------- ceremony


def test_ceremony_carries_facts_a_tutor_may_not_invent(bench: Course) -> None:
    ceremony = bench.manifest.ceremony
    assert ceremony and ceremony.brand
    brand = ceremony.brand
    assert brand.product and brand.url and brand.mention
    assert brand.handles and brand.hashtags
    assert all(handle.startswith("@") for handle in brand.handles.values())
    assert all(not tag.startswith("#") for tag in brand.hashtags), "the runtime adds the hash"


def test_every_phase_has_a_pronoun_free_highlight(bench: Course) -> None:
    for phase in bench.phases:
        assert phase.highlight, phase.number
        words = phase.highlight.lower().split()
        for pronoun in ("their", "theirs", "his", "her", "my", "your"):
            assert pronoun not in words, f"phase {phase.number}: {phase.highlight!r}"


def test_the_share_template_renders_with_derived_counts(bench: Course) -> None:
    text = cer.share_text(bench, None, bench.phase_at(1))
    assert text
    assert "Shell Basics" in text
    assert "0 of 4 lessons down" in text, "the runtime fills the count; the author never wrote it"
    assert "startskill.ing" in text
    assert "#Skilling" in text, "hashtags arrive with their hash added"


def test_no_lesson_authors_a_structural_count() -> None:
    from skilling.conformance._counts import _BODY_COUNTS, _MANIFEST_COUNTS

    for path in sorted(EXERCISER.rglob("*.md")):
        for line in md.strip_code(path.read_text(encoding="utf-8")).splitlines():
            for pattern in _MANIFEST_COUNTS + _BODY_COUNTS:
                assert not pattern.search(line), f"{path.name}: {line.strip()[:70]!r}"


def test_the_quiz_grammar_holds_across_every_question(bench: Course) -> None:
    questions = 0
    for lesson in bench.lessons():
        quiz = md.parse_lesson(lesson.path).section("quiz")
        assert quiz
        parsed = md.parse_quiz(quiz.body, quiz.body_line)
        assert len(parsed) == 3, lesson.coordinate
        for question in parsed:
            assert sorted(question.labels) == ["a", "b", "c", "d"], lesson.coordinate
            assert question.answer_label, lesson.coordinate
            assert question.has_reason, f"{lesson.coordinate} q{question.number}"
            questions += 1
    assert questions == 12


def test_an_asset_is_referenced_and_resolves(bench: Course) -> None:
    """The assets surface stays exercised: at least one lesson embeds a relative asset
    reference, and the file it names exists."""
    referenced = 0
    for lesson in bench.lessons():
        for line in lesson.path.read_text(encoding="utf-8").splitlines():
            if "](../../assets/" not in line:
                continue
            referenced += 1
            relative = line.split("](", 1)[1].split(")", 1)[0]
            assert (lesson.path.parent / relative).is_file(), relative
    assert referenced >= 1


def test_prerequisites_form_an_unbroken_chain(bench: Course) -> None:
    coordinates = bench.coordinates
    for i, coordinate in enumerate(coordinates):
        lesson = bench.lesson_at(coordinate)
        assert lesson
        fm = md.parse_lesson(lesson.path).frontmatter
        assert fm
        expected = [] if i == 0 else [coordinates[i - 1]]
        assert fm.prerequisites == expected, coordinate


def test_it_is_licensed_for_reuse(bench: Course) -> None:
    assert bench.manifest.license == "CC-BY-4.0"


def test_the_examples_index_describes_both_courses() -> None:
    text = (REPO_ROOT / "examples" / "README.md").read_text(encoding="utf-8")
    assert "workbench" in text
    assert "hello-skilling" in text


def test_every_phase_has_an_overview(bench: Course) -> None:
    for phase in bench.phases:
        assert phase.overview_path is not None, phase.number


def test_a_full_walk_completes_cleanly_and_stays_small(tmp_path: Path, bench: Course) -> None:
    from skilling import delivery as runtime
    from skilling.store import LOCAL_LEARNER, FileProgressStore

    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, bench, LOCAL_LEARNER)
    for lesson in bench.lessons():
        outcome = runtime.complete_lesson(store, bench, record, revision, lesson)
        record, revision = outcome.record, outcome.revision

    assert len(record.completed) == 4
    assert len(record.skills_unlocked) == 3
    assert bench.percent_complete(record.completed) == 100.0
    size = (tmp_path / "state" / bench.id / "record.yaml").stat().st_size
    assert size < 2048, f"record.yaml is {size} bytes for a course this size"
