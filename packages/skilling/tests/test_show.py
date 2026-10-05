"""``skilling show --objectives``: the objective <-> quiz-question mapping, for authors.

Authoring-facing only — nothing here is read by a runtime. The point is to let an author see,
at a glance, which quiz question each objective's `about` points to, and the two ways that
mapping can go stale: an objective that points at nothing, and a question nothing points at.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from skilling.cli import app
from skilling.course import Course

runner = CliRunner()


def test_show_objectives_prints_question_text_beside_each_objective(clean_dir: Path) -> None:
    result = runner.invoke(app, ["show", str(clean_dir), "--objectives"])
    assert result.exit_code == 0, result.output
    # The fixture's lesson two maps the "second-thing" objective to question 1; both the
    # objective's id and the full text of the question it points to must co-occur.
    # That stem wraps onto a second source line in the fixture, so this also proves the
    # continuation is joined rather than dropped (#98).
    assert "second-thing" in result.output
    assert "What is the second thing?" in result.output


def test_loose_ends_are_both_visible(clean_dir: Path) -> None:
    result = runner.invoke(app, ["show", str(clean_dir), "--objectives"])
    assert result.exit_code == 0, result.output
    # "builds-on-first" has no `about` at all.
    assert "no about" in result.output.lower()
    assert "builds-on-first" in result.output
    # Questions 2 and 3 of lesson two are not pointed at by any objective.
    assert "no objective" in result.output.lower()
    assert "What does it build on?" in result.output


def test_show_totals_declared_durations_in_text_and_json(clean_dir: Path) -> None:
    text = runner.invoke(app, ["show", str(clean_dir)])
    assert text.exit_code == 0, text.output
    assert "20 min" in text.output
    assert "30 min" in text.output
    assert "incomplete" not in text.output
    result = runner.invoke(app, ["show", str(clean_dir), "--json"])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["duration_minutes"] == 30
    assert summary["missing_duration_lessons"] == []
    assert [phase["duration_minutes"] for phase in summary["phases"]] == [20, 10]
    assert [
        lesson["duration_minutes"] for phase in summary["phases"] for lesson in phase["lessons"]
    ] == [10, 10, 10]
    assert summary["lesson_count"] == 3


def test_show_incomplete_duration_is_not_silently_zero(clean_dir: Path) -> None:
    lesson = Course.load(clean_dir).first_lesson
    lesson.path.write_text(lesson.path.read_text().replace("duration_minutes: 10\n", ""))
    result = runner.invoke(app, ["show", str(clean_dir), "--json"])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["duration_minutes"] == 20
    assert summary["missing_duration_lessons"] == [lesson.coordinate]
    phase = summary["phases"][0]
    assert phase["duration_minutes"] == 10
    assert phase["missing_duration_lessons"] == [lesson.coordinate]
    assert phase["lessons"][0]["duration_minutes"] is None
    text = runner.invoke(app, ["show", str(clean_dir)])
    assert text.exit_code == 0, text.output
    assert "incomplete" in text.output
    assert "duration not declared or unavailable" in text.output


def test_show_missing_or_invalid_lesson_metadata_remains_visible(clean_dir: Path) -> None:
    lessons = list(Course.load(clean_dir).lessons())
    lessons[0].path.unlink()
    lessons[1].path.write_text(
        lessons[1].path.read_text().replace("duration_minutes: 10", "duration_minutes: -3")
    )
    result = runner.invoke(app, ["show", str(clean_dir), "--json"])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["duration_minutes"] == 10
    assert summary["missing_duration_lessons"] == [lessons[0].coordinate, lessons[1].coordinate]
    text = runner.invoke(app, ["show", str(clean_dir)])
    assert text.exit_code == 0, text.output
    assert "file missing" in text.output
    assert "incomplete" in text.output


def test_show_json_rejects_objective_mode_without_mixed_output(clean_dir: Path) -> None:
    result = runner.invoke(app, ["show", str(clean_dir), "--json", "--objectives"])
    assert result.exit_code == 2
    assert "cannot be combined" in result.output
