"""The delivery loop as a pure state machine.

No I/O, no clock, no language model, no store. Given a state and an input it returns the
next state or refuses. Everything the specification says about beat ordering and gates is
expressible here, which is what makes it testable — and what lets a text walker and a
model-backed tutor share exactly one implementation of the loop.

The machine *permits*; it does not advise. Where the specification says a runtime "should"
offer something, that is a predicate (``should_offer_revisit``) rather than a restriction
on transitions, so a runtime is free to be more generous without becoming illegal.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

QUESTION_COUNT = 3
"""Fixed by the quiz grammar: exactly three questions, in every course."""

REVISIT_THRESHOLD = 2
"""Wrong answers in one quiz after which revisiting the concept should be offered."""


class Beat(StrEnum):
    WELCOME = "welcome"
    OBJECTIVES = "objectives"
    CONCEPT = "concept"
    GATE_CONCEPT = "gate-concept"
    EXERCISE = "exercise"
    GATE_EXERCISE = "gate-exercise"
    QUIZ = "quiz"
    REMEDIATE = "remediate"
    COMPLETE = "complete"
    CEREMONY = "ceremony"
    DONE = "done"


GATES = frozenset({Beat.GATE_CONCEPT, Beat.GATE_EXERCISE})


class Input(StrEnum):
    NEXT = "next"
    """Acknowledge a delivered beat that is not a gate."""

    GO_DEEPER = "go-deeper"
    PROCEED = "proceed"
    HINT = "hint"
    ATTEMPTED = "attempted"
    ANSWER_CORRECT = "answer-correct"
    ANSWER_WRONG = "answer-wrong"
    CONTINUE = "continue"
    REVISIT_CONCEPT = "revisit-concept"


class IllegalTransition(Exception):
    def __init__(self, beat: Beat, given: Input) -> None:
        super().__init__(f"{given!s} is not a legal input at the {beat!s} beat")
        self.beat = beat
        self.given = given


@dataclass(frozen=True)
class LessonShape:
    """What this particular lesson makes possible, derived from the lesson file."""

    has_exercise: bool = True
    is_phase_end: bool = False
    question_count: int = QUESTION_COUNT


@dataclass(frozen=True)
class LessonState:
    beat: Beat
    shape: LessonShape
    question_index: int = 0
    """0-based index of the question awaiting an answer."""

    wrong_count: int = 0
    """Wrong answers so far in this quiz. Never decreases within a lesson."""

    returning_to_quiz: bool = False
    """Set when the learner left a quiz to revisit the concept, so the concept gate sends
    them back to the quiz rather than forward to the exercise."""

    @property
    def at_gate(self) -> bool:
        return self.beat in GATES

    @property
    def terminal(self) -> bool:
        return self.beat is Beat.DONE

    @property
    def questions_remaining(self) -> int:
        return max(0, self.shape.question_count - self.question_index)

    @classmethod
    def start(cls, shape: LessonShape) -> LessonState:
        return cls(beat=Beat.WELCOME, shape=shape)

    @classmethod
    def resume(
        cls, shape: LessonShape, beat: Beat | str, *, question_index: int = 0
    ) -> LessonState:
        """Rebuild state from a recorded position. A gate resumes as the same open gate."""
        return cls(beat=Beat(beat), shape=shape, question_index=question_index)


def should_offer_revisit(state: LessonState) -> bool:
    return state.wrong_count >= REVISIT_THRESHOLD


def _after_quiz_answer(state: LessonState) -> LessonState:
    """Move past the answered question, or finish the quiz."""
    nxt = state.question_index + 1
    if nxt >= state.shape.question_count:
        return replace(state, beat=Beat.COMPLETE, question_index=nxt, returning_to_quiz=False)
    return replace(state, beat=Beat.QUIZ, question_index=nxt, returning_to_quiz=False)


def _leave_concept_gate(state: LessonState) -> LessonState:
    if state.returning_to_quiz:
        return replace(state, beat=Beat.QUIZ, returning_to_quiz=False)
    if state.shape.has_exercise:
        return replace(state, beat=Beat.EXERCISE)
    return replace(state, beat=Beat.QUIZ)


def legal_inputs(state: LessonState) -> tuple[Input, ...]:
    match state.beat:
        case Beat.WELCOME | Beat.OBJECTIVES | Beat.CONCEPT | Beat.EXERCISE:
            return (Input.NEXT,)
        case Beat.GATE_CONCEPT:
            return (Input.GO_DEEPER, Input.PROCEED)
        case Beat.GATE_EXERCISE:
            return (Input.HINT, Input.ATTEMPTED)
        case Beat.QUIZ:
            return (Input.ANSWER_CORRECT, Input.ANSWER_WRONG)
        case Beat.REMEDIATE:
            return (Input.CONTINUE, Input.REVISIT_CONCEPT)
        case Beat.COMPLETE | Beat.CEREMONY:
            return (Input.NEXT,)
        case Beat.DONE:
            return ()


def advance(state: LessonState, given: Input) -> LessonState:
    """The transition function. Raises ``IllegalTransition`` rather than guessing."""
    if given not in legal_inputs(state):
        raise IllegalTransition(state.beat, given)

    match (state.beat, given):
        case (Beat.WELCOME, Input.NEXT):
            return replace(state, beat=Beat.OBJECTIVES)
        case (Beat.OBJECTIVES, Input.NEXT):
            return replace(state, beat=Beat.CONCEPT)
        case (Beat.CONCEPT, Input.NEXT):
            return replace(state, beat=Beat.GATE_CONCEPT)
        case (Beat.GATE_CONCEPT, Input.GO_DEEPER):
            # Curiosity is not progress: the beat returns to the concept and position holds.
            return replace(state, beat=Beat.CONCEPT)
        case (Beat.GATE_CONCEPT, Input.PROCEED):
            return _leave_concept_gate(state)
        case (Beat.EXERCISE, Input.NEXT):
            return replace(state, beat=Beat.GATE_EXERCISE)
        case (Beat.GATE_EXERCISE, Input.HINT):
            return replace(state, beat=Beat.EXERCISE)
        case (Beat.GATE_EXERCISE, Input.ATTEMPTED):
            return replace(state, beat=Beat.QUIZ)
        case (Beat.QUIZ, Input.ANSWER_CORRECT):
            return _after_quiz_answer(state)
        case (Beat.QUIZ, Input.ANSWER_WRONG):
            return replace(state, beat=Beat.REMEDIATE, wrong_count=state.wrong_count + 1)
        case (Beat.REMEDIATE, Input.CONTINUE):
            return _after_quiz_answer(state)
        case (Beat.REMEDIATE, Input.REVISIT_CONCEPT):
            return replace(state, beat=Beat.CONCEPT, returning_to_quiz=True)
        case (Beat.COMPLETE, Input.NEXT):
            return replace(state, beat=Beat.CEREMONY if state.shape.is_phase_end else Beat.DONE)
        case (Beat.CEREMONY, Input.NEXT):
            return replace(state, beat=Beat.DONE)

    raise IllegalTransition(state.beat, given)  # pragma: no cover - guarded above
