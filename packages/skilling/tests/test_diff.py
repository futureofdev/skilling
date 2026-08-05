"""Course versions with teeth: what each bump level is allowed to change."""

from __future__ import annotations

from pathlib import Path

import pytest

from skilling.course import compare_paths, declared_level

from . import fixtures as fx

NEW_LESSON = """\
---
title: "Four"
phase: 1
lesson: 2
prerequisites: ["1.1"]
skills_unlocked: []
sections:
  key_terms:
    status: none
    intent: "No new vocabulary here."
  exercise:
    status: none
    intent: "Project phase: the learner's own build is the exercise."
  next_up:
    status: none
    intent: "Last lesson of the course."
---

## Learning Objectives
By the end of this lesson, you will:
- Know the fourth thing

## The Concept
The fourth thing is new.

## Quick Quiz
1. Is the fourth thing new?
   - a) No
   - b) Yes
   - c) Sometimes
   - d) Unclear

   **Answer:** b) Yes — it was appended after the third.

2. What did it change?
   - a) Nothing before it
   - b) Everything
   - c) The first lesson
   - d) The manifest id

   **Answer:** a) Nothing before it — appending leaves existing coordinates alone.

3. Which bump does appending need?
   - a) Patch
   - b) Minor
   - c) Major
   - d) None

   **Answer:** b) Minor — additive and coordinate-stable.
"""


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    old = fx.build(tmp_path / "old")
    new = fx.build(tmp_path / "new")
    return old, new


def _bump(root: Path, version: str) -> None:
    fx.edit(root, fx.MANIFEST_PATH, 'version: "1.0.0"', f'version: "{version}"')


# ------------------------------------------------------------------- declared level only


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("1.0.0", "1.0.0", "none"),
        ("1.0.0", "1.0.1", "patch"),
        ("1.0.0", "1.1.0", "minor"),
        ("1.0.0", "2.0.0", "major"),
        ("1.1.0", "1.0.0", "downgrade"),
        ("1.0", "1.0.1", "unparseable"),
    ],
)
def test_declared_level(old: str, new: str, expected: str) -> None:
    assert declared_level(old, new) == expected


# ------------------------------------------------------------------------ required level


def test_identical_courses_require_nothing(pair: tuple[Path, Path]) -> None:
    old, new = pair
    result = compare_paths(old, new)
    assert result.required == "none"
    assert result.coordinates_stable
    assert result.satisfied
    assert result.reasons() == []


def test_a_content_edit_requires_a_patch(pair: tuple[Path, Path]) -> None:
    old, new = pair
    fx.edit(
        new, fx.LESSON_ONE_PATH, "The first thing is worth knowing.", "The first thing matters."
    )

    result = compare_paths(old, new)
    assert result.required == "patch"
    assert result.content_changed == ["0.1"]
    assert result.coordinates_stable
    assert not result.satisfied, "the version was not bumped"

    _bump(new, "1.0.1")
    assert compare_paths(old, new).satisfied


def test_appending_a_lesson_requires_a_minor(pair: tuple[Path, Path]) -> None:
    old, new = pair
    fx.edit(
        new,
        fx.MANIFEST_PATH,
        "      - { number: 1, slug: three, title: Three }",
        "      - { number: 1, slug: three, title: Three }\n"
        "      - { number: 2, slug: four, title: Four }",
    )
    fx.write(new, f"{fx.PHASE_ONE}/lesson-02-four.md", NEW_LESSON)

    result = compare_paths(old, new)
    assert result.required == "minor"
    assert result.added_trailing == ["1.2"]
    assert result.added_inserted == []
    assert result.coordinates_stable

    _bump(new, "1.0.1")
    assert not compare_paths(old, new).satisfied
    fx.edit(new, fx.MANIFEST_PATH, 'version: "1.0.1"', 'version: "1.1.0"')
    assert compare_paths(old, new).satisfied


def test_inserting_a_lesson_requires_a_major(pair: tuple[Path, Path]) -> None:
    old, new = pair
    # Renaming lesson 0.2 and adding a new 0.2 is what "inserting" looks like from outside.
    fx.edit(new, fx.MANIFEST_PATH, "{ number: 2, slug: two", "{ number: 2, slug: inserted")

    result = compare_paths(old, new)
    assert result.required == "major"
    assert result.reassigned == [("0.2", "two", "inserted")]
    assert not result.coordinates_stable

    _bump(new, "1.1.0")
    assert not compare_paths(old, new).satisfied
    fx.edit(new, fx.MANIFEST_PATH, 'version: "1.1.0"', 'version: "2.0.0"')
    assert compare_paths(old, new).satisfied


def test_removing_a_lesson_requires_a_major(pair: tuple[Path, Path]) -> None:
    old, new = pair
    fx.edit(new, fx.MANIFEST_PATH, "\n      - { number: 1, slug: three, title: Three }", "")
    fx.edit(
        new,
        fx.MANIFEST_PATH,
        "  - number: 1\n    slug: next\n    name: Next\n    lessons:",
        "",
    )
    (new / fx.LESSON_THREE_PATH).unlink()

    result = compare_paths(old, new)
    assert result.required == "major"
    assert result.removed == ["1.1"]


def test_a_new_trailing_phase_is_only_a_minor(pair: tuple[Path, Path]) -> None:
    old, new = pair
    fx.edit(
        new,
        fx.MANIFEST_PATH,
        "skills:",
        "  - number: 2\n    slug: last\n    name: Last\n    lessons:\n"
        "      - { number: 1, slug: four, title: Four }\nskills:",
    )
    lesson = NEW_LESSON.replace("phase: 1", "phase: 2").replace("lesson: 2", "lesson: 1")
    lesson = lesson.replace('prerequisites: ["1.1"]', 'prerequisites: ["1.1"]')
    fx.write(new, "phases/phase-2-last/lesson-01-four.md", lesson)

    result = compare_paths(old, new)
    assert result.added_trailing == ["2.1"]
    assert result.required == "minor"
    assert result.coordinates_stable


def test_manifest_metadata_change_is_a_patch(pair: tuple[Path, Path]) -> None:
    old, new = pair
    fx.edit(new, fx.MANIFEST_PATH, "description: A course that", "description: A nicer course that")
    result = compare_paths(old, new)
    assert result.manifest_changed
    assert result.required == "patch"


def test_a_version_downgrade_is_never_satisfied(pair: tuple[Path, Path]) -> None:
    old, new = pair
    fx.edit(old, fx.MANIFEST_PATH, 'version: "1.0.0"', 'version: "2.0.0"')
    assert not compare_paths(old, new).satisfied


def test_reasons_are_human_readable(pair: tuple[Path, Path]) -> None:
    old, new = pair
    fx.edit(new, fx.MANIFEST_PATH, "{ number: 2, slug: two", "{ number: 2, slug: renamed")
    reasons = compare_paths(old, new).reasons()
    assert any("0.2" in reason and "renamed" in reason for reason in reasons)
