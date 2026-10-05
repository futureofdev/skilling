"""The session verbs: ``next``, ``advance``, ``complete``, ``ceremony``.

One process, one transition, one line of JSON on stdout — never anything else, so a driving
pack can pipe this straight into a parser without scraping prose. ``advance`` drives the pure
per-beat walk (welcome through remediate); reaching the completion beat is where the pure
machine's job ends and ``complete`` — which alone knows how to write the completion write set
— takes over. ``ceremony`` is read-only, presentational, and keyed off the most recently
completed lesson rather than the record's current position, because by the time a phase
boundary is worth showing, ``complete`` has already moved the position past it.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...session import (
    SessionRefusal,
    SessionSnapshot,
)
from ...store import (
    LOCAL_LEARNER,
    Conflict,
    NotSupported,
)
from ...workspace import find_workspace
from ._common import (
    ExitCode,
    emit,
    fail,
    known_upgrade,
    load_session_course,
    now_override,
    open_file_chronology_session,
    open_file_session,
    refuse_session,
)

COURSE_HELP = "Path to the course directory."
STATE_HELP = "Where to keep the learner's progress record."
LEARNER_HELP = "Learner id for the record."

_CourseOption = typer.Option(..., "--course", help=COURSE_HELP)
_StateOption = typer.Option(None, "--state", envvar="SKILLING_STATE_ROOT", help=STATE_HELP)
_LearnerOption = typer.Option(LOCAL_LEARNER, "--learner", help=LEARNER_HELP)


def _view_envelope(verb: str, snapshot: SessionSnapshot) -> dict[str, object]:
    position = snapshot.position
    envelope: dict[str, object] = {
        "ok": True,
        "verb": verb,
        "course": {
            "id": snapshot.course.id,
            "version": snapshot.course.version,
            "title": snapshot.course.title,
        },
        "position": {
            "phase": position.phase,
            "lesson": position.lesson,
            "beat": position.beat,
            "question_index": position.question_index,
        },
        "beat": {"name": snapshot.beat.name, "content": snapshot.beat.content()},
        "legal_inputs": [str(i) for i in snapshot.legal_inputs],
        "revision": snapshot.revision,
        "completed_count": snapshot.completed_count,
        "lesson_count": snapshot.lesson_count,
    }
    if snapshot.tutor is not None:
        envelope["tutor"] = {"persona": snapshot.tutor.persona, "tone": list(snapshot.tutor.tone)}
    return envelope


# --------------------------------------------------------------------------------------- next


def next(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """Resume current content; first use initializes and pending completion recovers."""
    service = open_file_session(course, state, learner)
    try:
        envelope = _view_envelope("next", service.snapshot())
    except SessionRefusal as exc:
        refuse_session(exc, course)
    hint = known_upgrade(load_session_course(course))
    if hint is not None:
        envelope["upgrade"] = hint
    emit(envelope)


# ------------------------------------------------------------------------------------ advance


def advance(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
    given_input: str = typer.Option(..., "--input", help="The Input this transition applies."),
    key: str | None = typer.Option(
        None, "--key", help="Idempotency key: a repeated key exits 0 without reapplying."
    ),
) -> None:
    """Apply exactly one transition and persist the resulting position."""
    service = open_file_session(course, state, learner)
    try:
        result = service.advance(given_input, event_id=key)
    except SessionRefusal as exc:
        refuse_session(exc, course)
    envelope = _view_envelope("advance", result.snapshot)
    if key is not None:
        envelope["replayed"] = result.replayed
    emit(envelope)


# ----------------------------------------------------------------------------------- complete


def complete(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """Complete the explicit lesson or replay its durable immediate completion receipt."""
    service = open_file_session(course, state, learner)
    try:
        result = service.complete(service.snapshot().revision, now=now_override())
    except SessionRefusal as exc:
        refuse_session(exc, course)
    except Conflict as exc:
        fail(ExitCode.CONFLICT, "conflict", str(exc))
    except NotSupported as exc:
        fail(ExitCode.ERROR, "completion-not-supported", str(exc))
    envelope = _view_envelope("complete", result.snapshot)
    envelope.update(
        {
            "already_completed": result.already_completed,
            "badges_awarded": list(result.badges_awarded),
            "phase_completed": result.phase_completed,
            "homework_placed": result.homework_placed,
            "homework_queued": result.homework_queued,
        }
    )
    emit(envelope)


# ----------------------------------------------------------------------------------- ceremony


def ceremony(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
    coordinate: str | None = typer.Option(
        None, "--coordinate", help="Completed phase endpoint; defaults to the final log entry."
    ),
) -> None:
    """Resolved ceremony facts and copy for the selected completed phase boundary."""
    service = open_file_chronology_session(course, state, learner)
    try:
        result = service.ceremony(coordinate, workspace_root=find_workspace())
    except SessionRefusal as exc:
        refuse_session(exc, course)
    envelope = _view_envelope("ceremony", result.snapshot)
    content: dict[str, object] = {
        "coordinate": result.coordinate,
        "phase_number": result.phase_number,
        "phase_name": result.phase_name,
        "phase_highlight": result.phase_highlight,
        "share_text": result.share_text,
        "course_complete": result.course_complete,
    }
    if result.showcase is not None:
        content["showcase"] = result.showcase
    envelope["beat"] = {"name": "ceremony", "content": content}
    emit(envelope)
