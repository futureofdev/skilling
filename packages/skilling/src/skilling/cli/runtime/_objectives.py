"""``skilling objective settle`` / ``objective show`` — capability-enforced, provenance-
required evidence for one addressable objective (T5's ``settle_objective``/``settleable``).

``settle`` never runs anything: a ``practice`` objective's ``check`` is a proposal, and only
the host — through its own permission model — may decide to run it. This verb only records
what the host already found, and only when it is honest about how: the capabilities it holds
come from repeated ``--capability`` flags, and ``settle_objective`` enforces them mechanically;
what makes the record trustworthy is the attestation, not the enforcement.

Delivery errors carry typed reasons; the shared session maps them to existing CLI codes.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...course import Capability
from ...session import SessionRefusal
from ...store import LOCAL_LEARNER
from ._common import (
    ExitCode,
    emit,
    fail,
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

_EVIDENCE_VALUES = ("explained", "observed", "homework")

app = typer.Typer(no_args_is_help=True, help="Evidence for one lesson's objectives.")


@app.command("settle")
def settle(
    objective_id: str = typer.Argument(..., help="The objective id to settle."),
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
    evidence: str = typer.Option(
        ..., "--evidence", help="What kind of evidence this is: explained, observed, homework."
    ),
    attested_by: str | None = typer.Option(
        None, "--attested-by", help="Which host attested observed evidence, e.g. 'codex'."
    ),
    checked: str | None = typer.Option(
        None, "--checked", help="What was actually inspected, for observed evidence."
    ),
    capability: list[str] = typer.Option(
        None, "--capability", help="A capability this runtime holds. Repeatable."
    ),
) -> None:
    """Settle one objective from evidence a host already gathered.

    Capability-enforced: ``settle_objective`` refuses unless a held ``--capability`` settles
    this objective's kind. Provenance-required: observed evidence needs ``--attested-by`` and
    ``--checked``, recorded verbatim against the objective's own ``verify`` sentence — because
    the claim cannot be verified here, only recorded for a later reader to weigh.
    """
    if evidence not in _EVIDENCE_VALUES:
        fail(
            ExitCode.INVALID,
            "evidence-unknown",
            f"{evidence!r} is not one of {_EVIDENCE_VALUES}",
        )

    try:
        capabilities = [Capability(c) for c in (capability or [])]
    except ValueError as exc:
        fail(ExitCode.INVALID, "capability-unknown", str(exc))

    service = open_file_session(course, state, learner)
    try:
        result = service.settle_objective(
            objective_id,
            capabilities,
            checked=checked if evidence == "observed" else None,
            attested_by=attested_by if evidence == "observed" else None,
            now=now_override(),
        )
    except SessionRefusal as exc:
        refuse_session(exc, course)
    emit(
        {
            "ok": True,
            "verb": "settle",
            "course": {"id": result.course.id, "version": result.course.version},
            "objective": {
                "id": result.id,
                "evidence": result.evidence,
                "at": str(result.at),
                "provenance": view_data(result.provenance) if result.provenance else None,
            },
            "newly_met": result.newly_met,
            "revision": result.revision,
        }
    )


@app.command("show")
def show(
    course: str = _CourseOption,
    state: Path | None = _StateOption,
    learner: str = _LearnerOption,
    capability: list[str] = typer.Option(
        None, "--capability", help="A capability this runtime holds, for settleable_now."
    ),
) -> None:
    """Show authored checks as proposals; the runtime never executes them."""
    try:
        capabilities = [Capability(c) for c in (capability or [])]
    except ValueError as exc:
        fail(ExitCode.INVALID, "capability-unknown", str(exc))
    service = open_file_session(course, state, learner)
    try:
        objectives = service.objectives(capabilities)
    except SessionRefusal as exc:
        refuse_session(exc, course)
    emit(
        {
            "ok": True,
            "verb": "show",
            "course": {"id": service.course.id, "version": service.course.version},
            "objectives": [
                {k: v for k, v in view_data(o).items() if k != "text"} for o in objectives
            ],
        }
    )
