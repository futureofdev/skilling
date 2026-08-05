"""Ceremony: facts a tutor may not invent, and the templates that override them.

The design being tested is the AI-first one. A tutor writes the prose; the manifest supplies
only the facts it is not allowed to guess. A literal template is the escape hatch, and the
resolution order between them is what the specification pins down.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from skilling import ceremony as cer
from skilling import runtime
from skilling.errors import Code
from skilling.loader import Course
from skilling.models import Brand
from skilling.store import FileProgressStore
from skilling.store.file import LOCAL_LEARNER
from skilling.validate import validate_course

from . import fixtures as fx
from .conftest import EXAMPLE_COURSE

NOW = datetime(2026, 8, 3, tzinfo=UTC)

BRAND_ONLY = """\
ceremony:
  brand:
    product: Clean Courses
    url: clean.example
    mention: "@cleancourses"
    handles:
      x: "@cleanx"
    hashtags: [Learning, CleanCourse]
"""

WITH_TEMPLATE = """\
ceremony:
  brand:
    product: Clean Courses
    url: clean.example
  phase_completed_template: |
    Finished {phase_name} of {course_title}.
    {completed_count} of {lesson_count} lessons done at {url}.
"""


def _with_ceremony(root: Path, block: str, *, highlight: bool = True) -> Course:
    fx.edit(root, fx.MANIFEST_PATH, "phases:", f"{block}phases:")
    if highlight:
        fx.edit(
            root,
            fx.MANIFEST_PATH,
            "  - number: 0\n    slug: start\n    name: Start\n",
            "  - number: 0\n    slug: start\n    name: Start\n    highlight: learned the first "
            "two things\n",
        )
    return Course.load(root)


# --------------------------------------------------------------------------- placeholders


def test_the_placeholder_set_is_closed() -> None:
    assert cer.unknown_placeholders("Hello {phase_name}") == []
    assert cer.unknown_placeholders("Hello {phase_nmae}") == ["phase_nmae"]


def test_placeholders_are_reported_in_order_without_duplicates() -> None:
    found = cer.placeholders_in("{url} {phase_name} {url} {product}")
    assert found == ["url", "phase_name", "product"]


def test_rendering_leaves_unknown_placeholders_alone_rather_than_raising() -> None:
    """Authored copy may contain stray braces; a manifest must never be able to crash a walk."""
    assert cer.render("{nope} and {phase_name}", {"phase_name": "Start"}) == "{nope} and Start"


def test_rendering_reaches_no_expression_syntax() -> None:
    """Deliberately not str.format: nothing in a manifest should be able to evaluate."""
    assert cer.render("{a.__class__}", {}) == "{a.__class__}"


def test_a_bad_placeholder_is_an_error(clean_dir: Path) -> None:
    _with_ceremony(clean_dir, 'ceremony:\n  phase_completed_template: "Hi {phase_nmae}"\n')
    assert Code.CEREMONY_UNKNOWN_PLACEHOLDER in validate_course(clean_dir).codes()


def test_promising_a_highlight_without_one_is_an_error(clean_dir: Path) -> None:
    _with_ceremony(
        clean_dir,
        'ceremony:\n  phase_completed_template: "Done: {phase_highlight}"\n',
        highlight=False,
    )
    assert Code.CEREMONY_HIGHLIGHT_MISSING in validate_course(clean_dir).codes()


def test_a_handle_without_an_at_sign_is_a_warning(clean_dir: Path) -> None:
    _with_ceremony(
        clean_dir,
        "ceremony:\n  brand:\n    handles:\n      x: cleanx\n",
    )
    report = validate_course(clean_dir)
    assert Code.CEREMONY_HANDLE_MALFORMED in report.codes()
    assert report.ok, "a malformed handle is worth mentioning, not worth failing a build over"


def test_a_template_may_not_author_a_count(clean_dir: Path) -> None:
    _with_ceremony(
        clean_dir,
        'ceremony:\n  phase_completed_template: "You finished 2 lessons"\n',
    )
    assert Code.AUTHORED_COUNT in validate_course(clean_dir).codes()


def test_a_highlight_may_not_author_a_count(clean_dir: Path) -> None:
    fx.edit(
        clean_dir,
        fx.MANIFEST_PATH,
        "  - number: 0\n    slug: start\n    name: Start\n",
        "  - number: 0\n    slug: start\n    name: Start\n    highlight: got through lesson 1 of "
        "3\n",
    )
    assert Code.AUTHORED_COUNT in validate_course(clean_dir).codes()


def test_derived_placeholders_are_the_sanctioned_way_to_state_a_count(clean_dir: Path) -> None:
    """The whole trick: an author writes the placeholder, the runtime writes the number."""
    course = _with_ceremony(clean_dir, WITH_TEMPLATE)
    assert validate_course(clean_dir).findings == []

    text = cer.share_text(course, None, course.phases[0])
    assert text and "0 of 3 lessons done" in text


# ------------------------------------------------------------------------- resolution order


def test_a_template_wins_when_present(clean_dir: Path) -> None:
    course = _with_ceremony(clean_dir, WITH_TEMPLATE)
    text = cer.share_text(course, None, course.phases[0])
    assert text and text.startswith("Finished Start of Clean Course.")


def test_facts_are_assembled_when_there_is_no_template(clean_dir: Path) -> None:
    course = _with_ceremony(clean_dir, BRAND_ONLY)
    text = cer.share_text(course, None, course.phases[0])
    assert text
    assert "Phase 0: Start" in text
    assert "learned the first two things" in text
    assert "clean.example" in text
    assert "#Learning #CleanCourse" in text


def test_no_ceremony_block_means_no_share_copy(clean: Course) -> None:
    assert cer.share_text(clean, None, clean.phases[0]) is None


def test_a_ceremony_with_no_brand_and_no_template_yields_nothing(clean_dir: Path) -> None:
    course = _with_ceremony(clean_dir, "ceremony: {}\n")
    assert cer.share_text(course, None, course.phases[0]) is None


def test_a_single_phase_course_still_gets_its_phase_template() -> None:
    """Finishing the only phase finishes the course; an author who wrote one template should
    not be handed flat facts because of it."""
    course = Course.load(EXAMPLE_COURSE)
    text = cer.share_text(course, None, course.phases[0], course_complete=True)
    assert text and text.startswith("Just finished Skilling Basics")


# -------------------------------------------------------------------------------- the facts


def test_hashtags_get_their_hash_from_the_runtime() -> None:
    assert cer.tags(Brand(hashtags=["WebDev", "#Already"])) == ["#WebDev", "#Already"]


def test_facts_lists_only_what_was_declared() -> None:
    listed = cer.facts(Brand(product="P", handles={"x": "@h"}))
    assert listed == ["product: P", "x: @h"]
    assert cer.facts(None) == []


def test_the_fact_list_is_what_a_tutor_may_state(clean_dir: Path) -> None:
    """A model-backed tutor composes from these and invents nothing outside them."""
    course = _with_ceremony(clean_dir, BRAND_ONLY)
    assert course.manifest.ceremony
    listed = cer.facts(course.manifest.ceremony.brand)
    assert "product: Clean Courses" in listed
    assert "url: clean.example" in listed
    assert not any("example.com" in fact for fact in listed), "nothing beyond the manifest"


@pytest.mark.parametrize("field", ["phase_number", "phase_name", "phase_highlight"])
def test_phase_placeholders_are_empty_without_a_phase(clean: Course, field: str) -> None:
    assert cer.values(clean, None, None)[field] == ""


def test_counts_come_from_the_record(tmp_path: Path, clean: Course) -> None:
    store = FileProgressStore(tmp_path / "state")
    record, revision = runtime.load_or_create(store, clean, LOCAL_LEARNER, now=NOW)
    lesson = clean.lesson_at("0.1")
    assert lesson
    outcome = runtime.complete_lesson(store, clean, record, revision, lesson, now=NOW)

    resolved = cer.values(clean, outcome.record, clean.phases[0])
    assert resolved["completed_count"] == "1"
    assert resolved["lesson_count"] == "3"
