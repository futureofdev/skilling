"""Learner language must not manufacture exercise-attempt or quiz-answer authority."""

from dataclasses import replace
from pathlib import Path

import pytest

from skilling.course import Course
from skilling.delivery import Beat, Input
from skilling.session import FileSession
from skilling_tutor.runtime._views import chat_control, controls

COURSE = Path(__file__).resolve().parents[3] / "examples/hello-skilling"


def snapshot_at(tmp_path, beat):
    session = FileSession.open(Course.load(COURSE), state_root=tmp_path, learner_id="learner")
    for _ in range(12):
        snapshot = session.snapshot()
        if snapshot.beat.name is beat:
            return snapshot
        choice = next(
            (
                value
                for value in (Input.NEXT, Input.PROCEED, Input.ATTEMPTED)
                if value in snapshot.legal_inputs
            ),
            None,
        )
        assert choice is not None
        session.advance(choice)
    raise AssertionError(f"Could not reach {beat}")


@pytest.mark.parametrize(
    "text",
    ["Nothing, let's move on", "No more questions, let’s continue.", "I'm ready", "continue"],
)
def test_readiness_requires_no_invented_attempt(tmp_path, text):
    concept = snapshot_at(tmp_path / "concept", Beat.GATE_CONCEPT)
    exercise = snapshot_at(tmp_path / "exercise", Beat.GATE_EXERCISE)
    assert chat_control(text, concept) == Input.PROCEED
    assert chat_control(text, exercise) is None


@pytest.mark.parametrize(
    "text",
    [
        "I've tried it, move on",
        "I attempted it.",
        "I’ve done the exercise",
        "I did it",
        "Attempted",
        "I tried the exercise; let's continue",
    ],
)
def test_explicit_attempt_reports_use_only_current_exercise_gate(tmp_path, text):
    exercise = snapshot_at(tmp_path / "exercise", Beat.GATE_EXERCISE)
    quiz = snapshot_at(tmp_path / "quiz", Beat.QUIZ)
    assert chat_control(text, exercise) == Input.ATTEMPTED
    assert chat_control(text, quiz) is None


@pytest.mark.parametrize(
    "text",
    [
        "I haven't tried it",
        "I tried it, but I am stuck",
        "Can I say I attempted it?",
        "I tried it?",
        "The tutor said 'I tried it'",
        "Nothing",
        "No questions",
        "I will try it later",
    ],
)
def test_questions_negations_and_quoted_claims_do_not_advance(tmp_path, text):
    assert chat_control(text, snapshot_at(tmp_path, Beat.GATE_EXERCISE)) is None


def test_exact_current_quiz_label_can_be_pasted_but_not_quoted_or_discussed(tmp_path):
    quiz = snapshot_at(tmp_path, Beat.QUIZ)
    option = controls(quiz)[1]
    assert chat_control(option["label"], quiz) == option["id"]
    assert (
        chat_control("  " + option["label"].upper().replace(" ", "  ") + "  ", quiz) == option["id"]
    )
    for text in (
        f'"{option["label"]}"',
        f"Is it {option['label']}?",
        option["label"] + "?",
        option["label"] + " because I am not sure",
        option["label"].replace("b)", "z)", 1),
    ):
        assert chat_control(text, quiz) is None


def test_exact_completion_label_requires_current_completion_control(tmp_path):
    exercise = snapshot_at(tmp_path, Beat.GATE_EXERCISE)
    complete = replace(exercise, beat=replace(exercise.beat, name=Beat.COMPLETE))
    assert chat_control("Complete lesson", complete) == "complete"
    assert chat_control("Complete lesson", exercise) is None
    assert chat_control("Complete lesson?", complete) is None
    assert chat_control('"Complete lesson"', complete) is None
