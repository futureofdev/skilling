"""The homework verbs: ``homework check``, ``homework submit``.

Both are thin wrappers: ``check`` is a pure read of the store's homework slot, and
``submit`` is a single call into ``delivery.submit_homework``, which already knows how to
archive an assignment and load the next queued one. This module imports neither
``put_record`` nor ``complete_lesson`` — it settles nothing about a lesson and awards no
badge, so it could not accidentally do either even by mistake.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...course import Course
from ...delivery import submit_homework
from ...store import LOCAL_LEARNER
from ._common import ExitCode, emit, fail, now_override, open_session

COURSE_HELP = "Path to the course directory."
STATE_HELP = "Where to keep the learner's progress record."
LEARNER_HELP = "Learner id for the record."

_CourseOption = typer.Option(..., "--course", help=COURSE_HELP)
_StateOption = typer.Option(None, "--state", envvar="SKILLING_STATE_ROOT", help=STATE_HELP)
_LearnerOption = typer.Option(LOCAL_LEARNER, "--learner", help=LEARNER_HELP)

homework = typer.Typer(help="Inspect and submit the active homework assignment.")


def _course_envelope(course: Course) -> dict[str, object]:
    return {"id": course.id, "version": course.version}


@homework.command("check")
def check(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """The active homework slot and its requirements.

    Read-only: never a write, not even scratch — a driving pack can poll this as often as
    it likes.
    """
    session = open_session(course, state, learner)
    active, revision = session.store.get_homework(learner, session.course.id)
    emit(
        {
            "ok": True,
            "verb": "homework-check",
            "course": _course_envelope(session.course),
            "active": active.model_dump(mode="json") if active is not None else None,
            "revision": revision,
        }
    )


@homework.command("submit")
def submit(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """Archive the active assignment.

    A retry after the slot has already been emptied is not a failure: it looks in the
    archive for what was last submitted and asks ``submit_homework`` to replay against
    that coordinate, which is where its own idempotency (checking the archive before
    archiving again) actually answers the call.
    """
    session = open_session(course, state, learner)
    active, _ = session.store.get_homework(learner, session.course.id)
    if active is not None:
        coordinate = active.coordinate
    else:
        archive = session.store.get_homework_archive(learner, session.course.id)
        if not archive:
            fail(ExitCode.ILLEGAL, "no-homework", "no homework is active or archived to submit")
        coordinate = archive[-1].coordinate

    entry = submit_homework(
        session.store, learner, session.course.id, coordinate, now=now_override()
    )
    if entry is None:
        fail(ExitCode.ILLEGAL, "no-homework", f"no homework at {coordinate!r} to submit")

    emit(
        {
            "ok": True,
            "verb": "homework-submit",
            "course": _course_envelope(session.course),
            "archived": entry.model_dump(mode="json"),
        }
    )
