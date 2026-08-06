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

from ...delivery import set_telemetry_consent
from ...store import LOCAL_LEARNER
from ._common import ExitCode, emit, fail, open_session

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
    session = open_session(course, state, learner)
    record = session.record
    course_obj = session.course
    emit(
        {
            "ok": True,
            "verb": "progress",
            "course": {"id": course_obj.id, "version": course_obj.version},
            "position": {
                "phase": record.position.phase,
                "lesson": record.position.lesson,
                "beat": record.position.beat,
                "question_index": record.position.question_index,
            },
            "completed": list(record.completed),
            "completed_count": course_obj.completed_count(record.completed),
            "lesson_count": course_obj.lesson_count,
            "percent_complete": course_obj.percent_complete(record.completed),
            "skills_unlocked": list(record.skills_unlocked),
            "streak_days": record.streak_days,
            "started_at": record.started_at.isoformat(),
            "last_activity": record.last_activity.isoformat(),
            "revision": session.revision,
        }
    )


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

    session = open_session(course, state, learner)
    envelope: dict[str, object] = {
        "ok": True,
        "verb": "telemetry",
        "course": {"id": session.course.id, "version": session.course.version},
    }

    if action == "ask":
        envelope.update(
            {
                "opt_in": session.record.telemetry.opt_in,
                "question": TELEMETRY_QUESTION,
                "revision": session.revision,
            }
        )
        emit(envelope)
        return

    updated, revision = set_telemetry_consent(
        session.store, session.record, session.revision, action == "on"
    )
    envelope.update(
        {
            "opt_in": updated.telemetry.opt_in,
            "anonymous_id": updated.telemetry.anonymous_id or None,
            "revision": revision,
        }
    )
    emit(envelope)
