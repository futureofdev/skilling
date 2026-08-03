"""Table tests over the delivery loop.

Every transition in the specification's state diagram is exercised here, plus the ones that
must *not* exist. The interesting cases are the two that are easy to get wrong: going deeper
must not advance position, and leaving the quiz to revisit the concept must come back to the
quiz rather than forward to the exercise.
"""

from __future__ import annotations

import pytest

from skilling.machine import (
    QUESTION_COUNT,
    Beat,
    IllegalTransition,
    Input,
    LessonShape,
    LessonState,
    advance,
    legal_inputs,
    resume,
    should_offer_revisit,
    start,
)

WITH_EXERCISE = LessonShape(has_exercise=True, is_phase_end=False)
NO_EXERCISE = LessonShape(has_exercise=False, is_phase_end=False)
PHASE_END = LessonShape(has_exercise=True, is_phase_end=True)


def at(beat: Beat, shape: LessonShape = WITH_EXERCISE, **kwargs) -> LessonState:
    return LessonState(beat=beat, shape=shape, **kwargs)


TRANSITIONS = [
    (at(Beat.WELCOME), Input.NEXT, Beat.OBJECTIVES),
    (at(Beat.OBJECTIVES), Input.NEXT, Beat.CONCEPT),
    (at(Beat.CONCEPT), Input.NEXT, Beat.GATE_CONCEPT),
    (at(Beat.GATE_CONCEPT), Input.GO_DEEPER, Beat.CONCEPT),
    (at(Beat.GATE_CONCEPT), Input.PROCEED, Beat.EXERCISE),
    (at(Beat.GATE_CONCEPT, NO_EXERCISE), Input.PROCEED, Beat.QUIZ),
    (at(Beat.EXERCISE), Input.NEXT, Beat.GATE_EXERCISE),
    (at(Beat.GATE_EXERCISE), Input.HINT, Beat.EXERCISE),
    (at(Beat.GATE_EXERCISE), Input.ATTEMPTED, Beat.QUIZ),
    (at(Beat.QUIZ), Input.ANSWER_CORRECT, Beat.QUIZ),
    (at(Beat.QUIZ), Input.ANSWER_WRONG, Beat.REMEDIATE),
    (at(Beat.QUIZ, question_index=2), Input.ANSWER_CORRECT, Beat.COMPLETE),
    (at(Beat.REMEDIATE), Input.CONTINUE, Beat.QUIZ),
    (at(Beat.REMEDIATE, question_index=2), Input.CONTINUE, Beat.COMPLETE),
    (at(Beat.REMEDIATE), Input.REVISIT_CONCEPT, Beat.CONCEPT),
    (at(Beat.COMPLETE), Input.NEXT, Beat.DONE),
    (at(Beat.COMPLETE, PHASE_END), Input.NEXT, Beat.CEREMONY),
    (at(Beat.CEREMONY, PHASE_END), Input.NEXT, Beat.DONE),
]


@pytest.mark.parametrize(
    ("state", "given", "expected"),
    TRANSITIONS,
    ids=[f"{s.beat}-{g}-{e}" for s, g, e in TRANSITIONS],
)
def test_transition(state: LessonState, given: Input, expected: Beat) -> None:
    assert advance(state, given).beat is expected


@pytest.mark.parametrize("beat", list(Beat))
def test_every_illegal_input_is_refused(beat: Beat) -> None:
    state = at(beat, PHASE_END)
    allowed = set(legal_inputs(state))
    for given in Input:
        if given in allowed:
            continue
        with pytest.raises(IllegalTransition):
            advance(state, given)


def test_done_accepts_nothing() -> None:
    state = at(Beat.DONE)
    assert legal_inputs(state) == ()
    assert state.terminal


def test_going_deeper_does_not_advance_position() -> None:
    state = at(Beat.GATE_CONCEPT, question_index=0)
    deeper = advance(state, Input.GO_DEEPER)
    assert deeper.beat is Beat.CONCEPT
    assert deeper.question_index == state.question_index
    # ...and back at the gate, nothing has moved.
    assert advance(deeper, Input.NEXT).beat is Beat.GATE_CONCEPT


def test_revisiting_the_concept_returns_to_the_quiz_not_the_exercise() -> None:
    state = at(Beat.REMEDIATE, question_index=1, wrong_count=2)
    concept = advance(state, Input.REVISIT_CONCEPT)
    assert concept.returning_to_quiz is True

    gate = advance(concept, Input.NEXT)
    back = advance(gate, Input.PROCEED)
    assert back.beat is Beat.QUIZ
    assert back.question_index == 1, "the learner resumes the question they were on"
    assert back.returning_to_quiz is False


def test_wrong_answers_accumulate_and_trigger_the_revisit_offer() -> None:
    state = start(WITH_EXERCISE)
    for _ in range(3):
        state = advance(state, Input.NEXT)
    state = advance(state, Input.PROCEED)
    state = advance(state, Input.NEXT)
    state = advance(state, Input.ATTEMPTED)
    assert state.beat is Beat.QUIZ

    state = advance(state, Input.ANSWER_WRONG)
    assert state.wrong_count == 1
    assert not should_offer_revisit(state)

    state = advance(state, Input.CONTINUE)
    state = advance(state, Input.ANSWER_WRONG)
    assert state.wrong_count == 2
    assert should_offer_revisit(state)


def test_a_full_walk_reaches_done_with_a_ceremony() -> None:
    state = start(PHASE_END)
    path = [
        Input.NEXT,  # welcome -> objectives
        Input.NEXT,  # objectives -> concept
        Input.NEXT,  # concept -> gate
        Input.PROCEED,  # gate -> exercise
        Input.NEXT,  # exercise -> gate
        Input.ATTEMPTED,  # gate -> quiz
        Input.ANSWER_CORRECT,
        Input.ANSWER_CORRECT,
        Input.ANSWER_CORRECT,  # -> complete
        Input.NEXT,  # complete -> ceremony
        Input.NEXT,  # ceremony -> done
    ]
    for given in path:
        state = advance(state, given)
    assert state.terminal
    assert state.question_index == QUESTION_COUNT


def test_a_lesson_without_an_exercise_skips_the_beat_and_its_gate() -> None:
    state = start(NO_EXERCISE)
    for _ in range(3):
        state = advance(state, Input.NEXT)
    assert state.beat is Beat.GATE_CONCEPT
    state = advance(state, Input.PROCEED)
    assert state.beat is Beat.QUIZ
    with pytest.raises(IllegalTransition):
        advance(state, Input.ATTEMPTED)


def test_a_gate_resumes_as_the_same_open_gate() -> None:
    for gate in (Beat.GATE_CONCEPT, Beat.GATE_EXERCISE):
        state = resume(WITH_EXERCISE, gate)
        assert state.beat is gate
        assert state.at_gate
        assert set(legal_inputs(state)) == set(legal_inputs(at(gate)))


def test_resume_accepts_the_recorded_string_form() -> None:
    assert resume(WITH_EXERCISE, "gate-concept").beat is Beat.GATE_CONCEPT


def test_state_is_immutable() -> None:
    state = start(WITH_EXERCISE)
    advance(state, Input.NEXT)
    assert state.beat is Beat.WELCOME, "advance must not mutate the state it is given"
