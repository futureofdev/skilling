"""Tests for the quiz verbs: ``quiz next``, ``answer``.

The custody boundary is ``quiz next``'s entire job: it must never let an answer, a reason, or
a "this one is correct" marker cross into the serialised JSON a driving pack parses. The first
test below asserts against the actual payload bytes, not against intent — a custody guarantee
only the source code obeys is not one a fuzzer downstream of it would trust.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from skilling.cli import app
from skilling.course import Course, QuizQuestion, parse_lesson, parse_quiz

runner = CliRunner()


def run(args: list[str], tmp: Path):
    return runner.invoke(app, [*args, "--state", str(tmp)], catch_exceptions=False)


def _advance(course: Path, tmp: Path, given: str):
    result = run(["advance", "--course", str(course), "--input", given], tmp)
    assert result.exit_code == 0, result.output
    return result


def _answer(course: Path, tmp: Path, label: str):
    return run(["answer", label, "--course", str(course)], tmp)


def _record(tmp: Path, course_id: str = "clean-course") -> dict:
    return yaml.safe_load((tmp / course_id / "record.yaml").read_text(encoding="utf-8"))


def _questions_for(course_dir: Path, coordinate: str) -> list[QuizQuestion]:
    course = Course.load(course_dir)
    lesson = course.lesson_at(coordinate)
    assert lesson is not None
    parsed = parse_lesson(lesson.path)
    quiz = parsed.section("quiz")
    assert quiz is not None
    return parse_quiz(quiz.body, quiz.body_line)


# clean-course lesson 0.1 (tests/fixtures.py) is reached via 'attempted' at the exercise gate.
# Its three quiz answers, in order, are b, a, c.
WALK_TO_QUIZ = ["next", "next", "next", "proceed", "next", "attempted"]


def _walk_to_quiz(course: Path, tmp: Path) -> None:
    for given in WALK_TO_QUIZ:
        _advance(course, tmp, given)


def _complete_whole_quiz(course: Path, tmp: Path) -> None:
    """Walk to the quiz and answer all three questions correctly — settling nothing."""
    _walk_to_quiz(course, tmp)
    for label in ["b", "a", "c"]:
        result = _answer(course, tmp, label)
        assert result.exit_code == 0, result.output


# ------------------------------------------------------------------------------------ quiz next


def test_quiz_next_provably_contains_no_answer_material(clean_dir: Path, tmp_path: Path) -> None:
    _walk_to_quiz(clean_dir, tmp_path)
    result = run(["quiz", "next", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 0, result.output
    payload = result.stdout

    questions = _questions_for(clean_dir, "0.1")
    open_q = next(q for q in questions if q.number == 1)
    reason = open_q.answer_reason
    answer_label = open_q.answer_label
    assert answer_label is not None
    correct_option = open_q.option(answer_label)
    assert correct_option is not None

    assert "**Answer" not in payload
    assert reason not in payload
    assert "correct" not in payload

    body = json.loads(payload)
    assert body["question"]["number"] == 1
    assert set(body["question"]["options"]) == {"a", "b", "c", "d"}
    # The correct option's own text legitimately appears — it is one of four choices on
    # display — but nothing in the payload marks it as the one that happens to be right.
    assert body["question"]["options"][answer_label] == correct_option.text


def test_question_three_is_unreachable_while_two_is_open(clean_dir: Path, tmp_path: Path) -> None:
    _walk_to_quiz(clean_dir, tmp_path)
    result = _answer(clean_dir, tmp_path, "b")  # q1 correct (fixture answer is b)
    assert result.exit_code == 0, result.output

    out = json.loads(run(["quiz", "next", "--course", str(clean_dir)], tmp_path).stdout)
    assert out["question"]["number"] == 2  # never 3


def test_quiz_next_refuses_outside_the_quiz_beat(clean_dir: Path, tmp_path: Path) -> None:
    result = run(["quiz", "next", "--course", str(clean_dir)], tmp_path)
    assert result.exit_code == 4
    body = json.loads(result.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == "illegal-transition"


# -------------------------------------------------------------------------------------- answer


def test_wrong_answer_offers_remediation_and_revisit_returns_to_quiz(
    clean_dir: Path, tmp_path: Path
) -> None:
    _walk_to_quiz(clean_dir, tmp_path)
    result = _answer(clean_dir, tmp_path, "a")  # q1 wrong: fixture answer is b
    assert result.exit_code == 0, result.output
    out = json.loads(result.stdout)
    assert out["correct"] is False
    assert out["reason"]  # the reason arrives only now, after answering

    _advance(clean_dir, tmp_path, "revisit-concept")
    _advance(clean_dir, tmp_path, "next")  # concept -> gate-concept
    result = _advance(clean_dir, tmp_path, "proceed")
    out = json.loads(result.stdout)
    assert out["position"]["beat"] == "quiz"  # back to the quiz, not the exercise


def test_answer_rejects_an_unknown_option(clean_dir: Path, tmp_path: Path) -> None:
    _walk_to_quiz(clean_dir, tmp_path)
    result = _answer(clean_dir, tmp_path, "z")
    assert result.exit_code == 2
    body = json.loads(result.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == "unknown-option"


def test_answer_refuses_outside_the_quiz_beat(clean_dir: Path, tmp_path: Path) -> None:
    result = _answer(clean_dir, tmp_path, "a")
    assert result.exit_code == 4
    assert json.loads(result.stdout)["error"]["code"] == "illegal-transition"


def test_a_quiz_settles_no_objective(clean_dir: Path, tmp_path: Path) -> None:
    _complete_whole_quiz(clean_dir, tmp_path)
    record = _record(tmp_path)
    assert record["objectives_met"] == []  # no code path exists to write one
