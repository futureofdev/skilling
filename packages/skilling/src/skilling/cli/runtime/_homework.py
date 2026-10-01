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

from ...session import SessionRefusal
from ...store import LOCAL_LEARNER, Conflict, InvalidSubmissionToken, NotSupported, SubmissionToken
from ._common import (
    ExitCode,
    emit,
    fail,
    load_session_course,
    now_override,
    open_file_session,
    refuse_session,
    view_data,
)

COURSE_HELP = "Path to the course directory."
STATE_HELP = "Where to keep the learner's progress record."
LEARNER_HELP = "Learner id for the record."

_CourseOption = typer.Option(..., "--course", help=COURSE_HELP)
_StateOption = typer.Option(None, "--state", envvar="SKILLING_STATE_ROOT", help=STATE_HELP)
_LearnerOption = typer.Option(LOCAL_LEARNER, "--learner", help=LEARNER_HELP)

homework = typer.Typer(help="Inspect and submit the active homework assignment.")


@homework.command("check")
def check(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """The active homework slot and its requirements.

    Does not initialize state or change the slot. Existing accepted intent may recover.
    """
    service = open_file_session(course, state, learner, initialize=False)
    try:
        result = service.homework_check()
    except SessionRefusal as exc:
        refuse_session(exc, course)
    active = view_data(result.active) if result.active is not None else None
    if active is not None:
        active["queued"] = (
            [{k: v for k, v in view_data(a).items() if k != "queued"} for a in result.active.queued]
            if result.active is not None
            else []
        )
    emit(
        {
            "ok": True,
            "verb": "homework-check",
            "course": {"id": result.course.id, "version": result.course.version},
            "active": active,
            "revision": result.revision,
            "submission_token": result.submission_token,
        }
    )


@homework.command("submit")
def submit(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
    token: str | None = typer.Option(
        None, "--token", help="Required token from the separately confirmed homework check."
    ),
) -> None:
    """Submit the checked assignment, or replay that token's original archive."""
    if token is None:
        fail(
            ExitCode.INVALID,
            "invalid-submission-token",
            "--token is required; check and separately confirm the assignment first",
        )
    try:
        identity = SubmissionToken.parse(token)
    except InvalidSubmissionToken as exc:
        fail(ExitCode.INVALID, "invalid-submission-token", str(exc))
    selected = load_session_course(course)
    if (identity.learner_id, identity.course_id, identity.course_version) != (
        learner,
        selected.id,
        selected.version,
    ):
        fail(
            ExitCode.INVALID,
            "invalid-submission-token",
            "Token belongs to a different record stream",
        )
    service = open_file_session(selected, state, learner, initialize=False)
    try:
        entry = service.homework_submit(token, now=now_override())
    except SessionRefusal as exc:
        refuse_session(exc, course)
    except InvalidSubmissionToken as exc:
        fail(ExitCode.INVALID, "invalid-submission-token", str(exc))
    except Conflict as exc:
        fail(ExitCode.CONFLICT, "conflict", str(exc))
    except NotSupported as exc:
        fail(ExitCode.ERROR, "submission-not-supported", str(exc))

    archived = view_data(entry)
    archived.pop("course")
    emit(
        {
            "ok": True,
            "verb": "homework-submit",
            "course": {"id": entry.course.id, "version": entry.course.version},
            "archived": archived,
        }
    )
