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

from ...course import (
    Course,
    Record,
    parse_lesson,
)
from ...delivery import (
    Beat,
    CompletionOutcome,
    complete_lesson,
    share_text,
)
from ...session import (
    SessionRefusal,
    SessionSnapshot,
    _course_complete,
    _lesson_state,
    _shape,
    _snapshot_view,
)
from ...store import (
    LOCAL_LEARNER,
    Conflict,
    FileProgressStore,
    NotSupported,
    RecoveryRequired,
)
from ...workspace import find_workspace, showcase_dir
from ._common import (
    ExitCode,
    Scratch,
    emit,
    fail,
    known_upgrade,
    load_session_course,
    now_override,
    open_chronology_session,
    open_file_session,
    open_session,
    parse_scratch,
    refuse_session,
    select_completed_coordinate,
)

COURSE_HELP = "Path to the course directory."
STATE_HELP = "Where to keep the learner's progress record."
LEARNER_HELP = "Learner id for the record."

_CourseOption = typer.Option(..., "--course", help=COURSE_HELP)
_StateOption = typer.Option(None, "--state", envvar="SKILLING_STATE_ROOT", help=STATE_HELP)
_LearnerOption = typer.Option(LOCAL_LEARNER, "--learner", help=LEARNER_HELP)


def _showcase(course: Course) -> dict[str, object]:
    """The workspace-relative showcase dir for this course, or nothing outside one.

    Same declared-absence idiom as ``_tutor``: a driving pack tells "no workspace" from "a
    showcase dir that happens to be empty" by ``in`` rather than by inspecting a null value.
    """
    workspace = find_workspace()
    if workspace is None:
        return {}
    return {"showcase": showcase_dir(workspace, course.id).relative_to(workspace).as_posix()}


def _resume_envelope(
    verb: str, course: Course, record: Record, revision: str | None, scratch: Scratch
) -> dict[str, object]:
    """The envelope for "here is where the record now stands" — shared by every verb, since
    ``advance``, ``complete``, and ``ceremony`` all report it alongside whatever else they add."""
    lesson = course.lesson_at(record.position.coordinate)
    if lesson is None:
        fail(
            ExitCode.INVALID,
            "position-invalid",
            f"{record.position.coordinate} is not a lesson in {course.id}",
        )
    return _view_envelope(verb, _snapshot_view(course, record, revision, scratch))


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
    session = open_session(course, state, learner)
    lesson = session.lesson
    parsed = parse_lesson(lesson.path)
    current = _lesson_state(session.record, session.scratch, _shape(session.course, lesson, parsed))
    legacy_noop = False
    if current.beat is not Beat.COMPLETE:
        replay = None
        if session.record.position.beat is None:
            receipt = session.store.get_completion_receipt(learner, session.course.id)
            if receipt is not None:
                if (receipt.learner_id, receipt.course_id, receipt.course_version) != (
                    session.record.learner_id,
                    session.course.id,
                    session.course.version,
                ) or receipt.coordinate not in session.record.completed:
                    raise RecoveryRequired(
                        "Completion receipt does not match this session snapshot"
                    )
                finished = session.course.lesson_at(receipt.coordinate)
                if finished is not None:
                    following = session.course.next_lesson(receipt.coordinate) or finished
                    if following.coordinate == session.record.position.coordinate:
                        replay = finished
            else:
                coordinates = session.course.coordinates
                index = coordinates.index(session.record.position.coordinate)
                legacy_noop = (
                    index > 0 and coordinates[index - 1] in session.record.completed
                ) or (
                    index == len(coordinates) - 1 and coordinates[index] in session.record.completed
                )
        if replay is None and not legacy_noop:
            fail(
                ExitCode.ILLEGAL,
                "illegal-transition",
                f"the lesson is at {current.beat!s}, not the completion beat",
            )
        if replay is not None:
            lesson = replay
    try:
        outcome = (
            CompletionOutcome(session.record, session.revision, already_completed=True)
            if legacy_noop
            else complete_lesson(
                session.store,
                session.course,
                session.record,
                session.revision,
                lesson,
                now=now_override(),
            )
        )
    except Conflict as exc:
        fail(ExitCode.CONFLICT, "conflict", str(exc))
    except NotSupported as exc:
        fail(ExitCode.ERROR, "completion-not-supported", str(exc))
    assert isinstance(session.store, FileProgressStore)
    snapshot = session.store.read_runtime_snapshot(learner, session.course.id)
    assert snapshot is not None
    envelope = _resume_envelope(
        "complete",
        session.course,
        snapshot.record,
        snapshot.revision,
        parse_scratch(snapshot.scratch),
    )
    envelope.update(
        {
            "already_completed": outcome.already_completed,
            "badges_awarded": outcome.badges_awarded,
            "phase_completed": outcome.phase_completed,
            "homework_placed": outcome.homework_placed,
            "homework_queued": outcome.homework_queued,
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
    session = open_chronology_session(course, state, learner)
    coordinate = select_completed_coordinate(session, learner, coordinate)
    finished = session.course.lesson_at(coordinate)
    if finished is None or not session.course.is_last_in_phase(coordinate):
        fail(
            ExitCode.ILLEGAL,
            "not-a-phase-boundary",
            f"{coordinate} is not the last lesson of its phase",
        )

    phase = session.course.phase_of(coordinate)
    course_complete = _course_complete(session.course, session.record)
    text = share_text(session.course, session.record, phase, course_complete=course_complete)

    envelope = _resume_envelope(
        "ceremony", session.course, session.record, session.revision, session.scratch
    )
    content: dict[str, object] = {
        "coordinate": coordinate,
        "phase_number": phase.number if phase else None,
        "phase_name": phase.name if phase else None,
        "phase_highlight": phase.highlight if phase else None,
        "share_text": text,
        "course_complete": course_complete,
    }
    content.update(_showcase(session.course))
    envelope["beat"] = {"name": "ceremony", "content": content}
    emit(envelope)
