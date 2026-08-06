"""``skilling show --objectives``: the objective <-> quiz-question mapping, for authors.

Authoring-facing only — nothing here is read by a runtime. The point is to let an author see,
at a glance, which quiz question each objective's `about` points to, and the two ways that
mapping can go stale: an objective that points at nothing, and a question nothing points at.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from skilling.cli import app

runner = CliRunner()


def test_show_objectives_prints_question_text_beside_each_objective(clean_dir: Path) -> None:
    result = runner.invoke(app, ["show", str(clean_dir), "--objectives"])
    assert result.exit_code == 0, result.output
    # The fixture's lesson two maps the "second-thing" objective to question 1; both the
    # objective's id and the full text of the question it points to must co-occur.
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
