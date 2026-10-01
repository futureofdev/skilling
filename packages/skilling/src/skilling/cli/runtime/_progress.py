"""The record-inspection verbs: ``progress`` and ``telemetry``.

``progress`` is entirely read-only: every count in its envelope — ``completed_count``,
``lesson_count``, ``percent_complete`` — is derived from the manifest and the record's
``completed`` list at print time, never cached on the record itself. ``telemetry`` is
read-only for ``ask`` and a single CAS-guarded write (through ``set_telemetry_consent``)
for ``on``/``off``.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...session import SessionRefusal
from ...store import LOCAL_LEARNER
from ._common import ExitCode, emit, fail, open_file_session, refuse_session, view_data

COURSE_HELP = "Path to the course directory."
STATE_HELP = "Where to keep the learner's progress record."
LEARNER_HELP = "Learner id for the record."

_CourseOption = typer.Option(..., "--course", help=COURSE_HELP)
_StateOption = typer.Option(None, "--state", envvar="SKILLING_STATE_ROOT", help=STATE_HELP)
_LearnerOption = typer.Option(LOCAL_LEARNER, "--learner", help=LEARNER_HELP)

TELEMETRY_QUESTION = (
    "May this course send anonymised usage events (lesson, phase, and course completions; "
    "badges awarded) to help improve it? Nothing you write is ever included."
)


def progress(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """Record plus counts, all computed from the manifest and ``completed`` at print time.

    Read-only, like ``next`` — but reports regardless of where the learner currently
    stands, including after the course is complete.
    """
    service = open_file_session(course, state, learner)
    try:
        result = service.progress()
    except SessionRefusal as exc:
        refuse_session(exc, course)
    data = view_data(result)
    data["course"] = {"id": result.course.id, "version": result.course.version}
    emit({"ok": True, "verb": "progress", **data})


def telemetry(
    action: str = typer.Argument(..., help="ask, on, or off."),
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
) -> None:
    """The ternary telemetry answer.

    ``ask`` never writes: it reports ``opt_in`` exactly as the record holds it — ``null``
    means never asked, and no default is invented — alongside the question a driving pack
    should put to the learner. ``on``/``off`` write the answer through
    ``set_telemetry_consent``, which alone knows to mint an anonymous id on the first yes.
    """
    if action not in ("ask", "on", "off"):
        fail(ExitCode.INVALID, "unknown-action", f"{action!r} is not 'ask', 'on', or 'off'")

    service = open_file_session(course, state, learner)
    try:
        result = service.telemetry(None if action == "ask" else action == "on")
    except SessionRefusal as exc:
        refuse_session(exc, course)
    envelope: dict[str, object] = {
        "ok": True,
        "verb": "telemetry",
        "course": {"id": result.course.id, "version": result.course.version},
        "opt_in": result.opt_in,
        "revision": result.revision,
    }
    if action == "ask":
        envelope["question"] = TELEMETRY_QUESTION
    else:
        envelope["anonymous_id"] = result.anonymous_id
    emit(envelope)
