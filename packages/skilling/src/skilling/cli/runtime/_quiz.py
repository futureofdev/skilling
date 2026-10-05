"""Quiz CLI adapters. Grading and answer custody belong to the shared session service."""

from pathlib import Path

import typer

from ...session import SessionRefusal
from ...store import LOCAL_LEARNER
from ._common import emit, open_file_session, refuse_session

COURSE_HELP = "Path to the course directory."
STATE_HELP = "Where to keep the learner's progress record."
LEARNER_HELP = "Learner id for the record."

_CourseOption = typer.Option(..., "--course", help=COURSE_HELP)
_StateOption = typer.Option(None, "--state", envvar="SKILLING_STATE_ROOT", help=STATE_HELP)
_LearnerOption = typer.Option(LOCAL_LEARNER, "--learner", help=LEARNER_HELP)

app = typer.Typer(no_args_is_help=True, help="The open quiz question, served one at a time.")


def next(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    service = open_file_session(course, state, learner)
    try:
        question = service.question()
    except SessionRefusal as exc:
        refuse_session(exc, course)
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


def answer(
    label: str = typer.Argument(..., help="The option label to submit, e.g. 'b'."),
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    service = open_file_session(course, state, learner)
    try:
        feedback = service.answer(label)
    except SessionRefusal as exc:
        refuse_session(exc, course)
    emit(
        {
            "ok": True,
            "correct": feedback.correct,
            "reason": feedback.reason,
            "remediation": {"offered": feedback.offered, "objectives": list(feedback.objectives)},
        }
    )
