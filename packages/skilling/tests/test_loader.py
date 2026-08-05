"""Derivation. Every count in this file is computed; none of it is read from a course."""

from __future__ import annotations

from pathlib import Path

import pytest

from skilling.errors import Code
from skilling.loader import (
    Course,
    CourseLoadError,
    discover_lesson_files,
    lesson_filename,
    phase_dirname,
)


def test_counts_are_derived(clean: Course) -> None:
    assert clean.phase_count == 2
    assert clean.lesson_count == 3
    assert [p.lesson_count for p in clean.phases] == [2, 1]
    assert clean.coordinates == ["0.1", "0.2", "1.1"]


def test_paths_are_derived_not_declared(clean: Course) -> None:
    lesson = clean.lesson_at("0.2")
    assert lesson
    assert lesson.path.name == "lesson-02-two.md"
    assert lesson.path.parent.name == "phase-0-start"
    assert lesson.path.is_file()


def test_lesson_numbers_are_zero_padded() -> None:
    assert lesson_filename(2, "two") == "lesson-02-two.md"
    assert lesson_filename(12, "twelve") == "lesson-12-twelve.md"


def test_phase_directory_shape(clean: Course) -> None:
    assert phase_dirname(clean.phases[0]) == "phase-0-start"


def test_navigation(clean: Course) -> None:
    assert clean.first_lesson.coordinate == "0.1"

    following = clean.next_lesson("0.2")
    assert following and following.coordinate == "1.1"
    assert clean.next_lesson("1.1") is None

    assert clean.is_last_in_phase("0.2")
    assert not clean.is_last_in_phase("0.1")
    assert clean.is_last_in_phase("1.1")


def test_phase_lookup(clean: Course) -> None:
    phase = clean.phase_of("1.1")
    assert phase and phase.name == "Next"
    assert clean.phase_at(9) is None
    assert clean.lesson_at("9.9") is None


def test_position_in_course(clean: Course) -> None:
    assert clean.position_in_course("0.1") == 1
    assert clean.position_in_course("1.1") == 3
    assert clean.position_in_course("9.9") is None


def test_progress_arithmetic(clean: Course) -> None:
    assert clean.completed_count([]) == 0
    assert clean.remaining_count([]) == 3
    assert clean.percent_complete([]) == 0.0

    assert clean.completed_count(["0.1", "0.2"]) == 2
    assert clean.percent_complete(["0.1", "0.2"]) == 66.7
    assert clean.percent_complete(["0.1", "0.2", "1.1"]) == 100.0


def test_unknown_coordinates_do_not_inflate_progress(clean: Course) -> None:
    assert clean.completed_count(["0.1", "9.9"]) == 1


def test_phase_completion_is_computed(clean: Course) -> None:
    assert not clean.phase_is_complete(0, ["0.1"])
    assert clean.phase_is_complete(0, ["0.1", "0.2"])
    assert not clean.phase_is_complete(9, ["0.1", "0.2"])


def test_overview_is_optional_and_found_when_present(clean: Course) -> None:
    assert clean.phases[0].overview_path is not None
    assert clean.phases[1].overview_path is None


def test_discovery_finds_files_the_manifest_does_not_know_about(clean_dir: Path) -> None:
    before = len(discover_lesson_files(clean_dir))
    (clean_dir / "phases" / "phase-0-start" / "lesson-09-stray.md").write_text("x", "utf-8")
    assert len(discover_lesson_files(clean_dir)) == before + 1


def test_a_missing_manifest_is_a_load_failure(tmp_path: Path) -> None:
    with pytest.raises(CourseLoadError) as caught:
        Course.load(tmp_path)
    assert caught.value.code is Code.MANIFEST_MISSING


def test_a_broken_manifest_is_a_load_failure(tmp_path: Path) -> None:
    (tmp_path / "course.yaml").write_text("id: [unclosed\n", encoding="utf-8")
    with pytest.raises(CourseLoadError) as caught:
        Course.load(tmp_path)
    assert caught.value.code is Code.MANIFEST_UNPARSEABLE


def test_a_course_with_missing_lesson_files_still_loads(clean_dir: Path) -> None:
    """Loading must survive a broken course, or the validator could never report on it."""
    (clean_dir / "phases" / "phase-0-start" / "lesson-01-one.md").unlink()
    course = Course.load(clean_dir)
    assert course.lesson_count == 3
    lesson = course.lesson_at("0.1")
    assert lesson and not lesson.path.is_file()


def test_registered_badges_are_exposed(clean: Course) -> None:
    assert clean.manifest.badge_ids == {"alpha"}


def test_example_course_shape(example: Course) -> None:
    assert example.id == "hello-skilling"
    assert example.lesson_count == 3
    assert example.is_last_in_phase("1.3")
    lesson = example.lesson_at("1.3")
    assert lesson and lesson.homework
