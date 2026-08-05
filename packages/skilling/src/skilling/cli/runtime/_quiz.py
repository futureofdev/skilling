"""The quiz verbs: one question at a time, the answer withheld until submitted.

``quiz next`` serves the open question's number, text, and options — nothing that reveals
which option is correct, why, or even the word "correct" itself. ``answer`` is the one place
a submitted label is ever compared against the lesson's own ``answer_label``; only the
*result* of that comparison (and, only once answered, the reason) crosses back to stdout.

Both verbs rebuild the machine state the same way ``_session.py`` does — directly from the
record and the scratch beside it, never via ``LessonState.resume`` — because a wrong answer's
``wrong_count`` has to survive the process exit between one call and the next. Unlike
``_session.py``'s own reconstruction, this module never needs the lesson's real
``LessonShape``: nothing the QUIZ or REMEDIATE beats do — the transitions, their legal
inputs, ``should_offer_revisit`` — reads ``has_exercise`` or ``is_phase_end``, so the default
shape (still three questions, via ``LessonShape()``) is exactly as good as parsing one.

Neither function imports ``mark_objectives_met`` or ``settle_objective``. The objectives an
answer surfaces on a wrong answer steer remediation — where a learner should look next — and
are never evidence that anything was learned: ``test_a_quiz_settles_no_objective`` is this
module's own fixture for that claim.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...course import ParsedLesson, QuizQuestion, Record, parse_lesson, parse_quiz
from ...delivery import (
    Beat,
    IllegalTransition,
    Input,
    LessonShape,
    LessonState,
    should_offer_revisit,
)
from ...delivery import advance as apply_input
from ...store import LOCAL_LEARNER, Conflict
from ._common import ExitCode, Scratch, emit, fail, open_session, save_scratch

COURSE_HELP = "Path to the course directory."
STATE_HELP = "Where to keep the learner's progress record."
LEARNER_HELP = "Learner id for the record."

_CourseOption = typer.Option(..., "--course", help=COURSE_HELP)
_StateOption = typer.Option(None, "--state", envvar="SKILLING_STATE_ROOT", help=STATE_HELP)
_LearnerOption = typer.Option(LOCAL_LEARNER, "--learner", help=LEARNER_HELP)

app = typer.Typer(no_args_is_help=True, help="The open quiz question, served one at a time.")


def _quiz_state(record: Record, scratch: Scratch) -> LessonState:
    """Rebuild only the fields a QUIZ/REMEDIATE transition ever reads.

    See the module docstring: ``LessonShape()``'s defaults stand in for the lesson's real
    shape because nothing this module touches consults ``has_exercise`` or ``is_phase_end``.
    """
    beat = record.position.beat
    if beat is None or beat not in set(Beat):
        return LessonState.start(LessonShape())
    return LessonState(
        beat=Beat(beat),
        shape=LessonShape(),
        question_index=record.position.question_index or 0,
        wrong_count=scratch.wrong_count,
        returning_to_quiz=scratch.returning_to_quiz,
    )


def _questions(parsed: ParsedLesson) -> list[QuizQuestion]:
    quiz = parsed.section("quiz")
    return parse_quiz(quiz.body, quiz.body_line) if quiz else []


def _open_question(current: LessonState, questions: list[QuizQuestion]) -> QuizQuestion:
    if current.beat is not Beat.QUIZ:
        fail(
            ExitCode.ILLEGAL,
            "illegal-transition",
            f"the lesson is at {current.beat!s}, not the quiz beat",
        )
    if current.question_index >= len(questions):
        fail(ExitCode.ILLEGAL, "quiz-finished", "no question is open")
    return questions[current.question_index]


# ------------------------------------------------------------------------------------ quiz next


def next(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """The open question's number, text, and options — never the answer or the reason."""
    session = open_session(course, state, learner)
    current = _quiz_state(session.record, session.scratch)
    parsed = parse_lesson(session.lesson.path)
    question = _open_question(current, _questions(parsed))

    emit(
        {
            "ok": True,
            "question": {
                "number": question.number,
                "text": question.text,
                "options": {o.label: o.text for o in question.options},
            },
        }
    )


app.command("next")(next)


# -------------------------------------------------------------------------------------- answer


def answer(
    label: str = typer.Argument(..., help="The option label to submit, e.g. 'b'."),
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """Submit an answer to the open question: one machine transition, plus scratch and
    remediation bookkeeping. Never a write to ``objectives_met`` — see the module docstring."""
    session = open_session(course, state, learner)
    current = _quiz_state(session.record, session.scratch)
    parsed = parse_lesson(session.lesson.path)
    question = _open_question(current, _questions(parsed))

    normalized = label.strip().lower()
    if normalized not in question.labels:
        fail(
            ExitCode.INVALID,
            "unknown-option",
            f"{label!r} is not one of the options for question {question.number}",
        )

    correct = normalized == question.answer_label
    given = Input.ANSWER_CORRECT if correct else Input.ANSWER_WRONG

    try:
        new_state = apply_input(current, given)
    except IllegalTransition as exc:  # pragma: no cover - QUIZ always permits both inputs
        fail(ExitCode.ILLEGAL, "illegal-transition", str(exc))

    new_position = session.record.position.model_copy(
        update={
            "beat": str(new_state.beat),
            "question_index": (
                new_state.question_index if new_state.beat in (Beat.QUIZ, Beat.REMEDIATE) else None
            ),
        }
    )
    updated_record = session.record.model_copy(update={"position": new_position})

    try:
        session.store.put_record(updated_record, session.revision)
    except Conflict as exc:
        fail(ExitCode.CONFLICT, "conflict", str(exc))

    save_scratch(
        session,
        Scratch(
            wrong_count=new_state.wrong_count,
            returning_to_quiz=new_state.returning_to_quiz,
            last_key=session.scratch.last_key,
            last_result=session.scratch.last_result,
        ),
    )

    objectives: list[str] = []
    fm = parsed.frontmatter
    if not correct and fm and fm.objectives:
        objectives = [o.text for o in fm.objectives_for_question(question.number)]

    emit(
        {
            "ok": True,
            "correct": correct,
            "reason": question.answer_reason,
            "remediation": {
                "offered": False if correct else should_offer_revisit(new_state),
                "objectives": objectives,
            },
        }
    )
