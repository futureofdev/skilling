"""``skilling objective settle`` / ``objective show`` — capability-enforced, provenance-
required evidence for one addressable objective (T5's ``settle_objective``/``settleable``).

``settle`` never runs anything: a ``practice`` objective's ``check`` is a proposal, and only
the host — through its own permission model — may decide to run it. This verb only records
what the host already found, and only when it is honest about how: the capabilities it holds
come from repeated ``--capability`` flags, and ``settle_objective`` enforces them mechanically;
what makes the record trustworthy is the attestation, not the enforcement.

``settle_objective`` raises ``ValueError`` naming the failed precondition rather than a typed
exception, so ``_map_settle_error`` below turns its message back into a stable refusal code —
matched by substring, since the exception itself carries no machine-readable reason.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...course import Attestation, Capability, Objective
from ...delivery import objectives_of, settle_objective, settleable
from ...store import LOCAL_LEARNER
from ._common import ExitCode, emit, fail, now_override, open_session

COURSE_HELP = "Path to the course directory."
STATE_HELP = "Where to keep the learner's progress record."
LEARNER_HELP = "Learner id for the record."

_CourseOption = typer.Option(..., "--course", help=COURSE_HELP)
_StateOption = typer.Option(None, "--state", envvar="SKILLING_STATE_ROOT", help=STATE_HELP)
_LearnerOption = typer.Option(LOCAL_LEARNER, "--learner", help=LEARNER_HELP)

_EVIDENCE_VALUES = ("explained", "observed", "homework")

app = typer.Typer(no_args_is_help=True, help="Evidence for one lesson's objectives.")


def _map_settle_error(message: str) -> tuple[ExitCode, str]:
    """``settle_objective``'s ``ValueError`` text, back to (exit code, refusal code).

    Order matters: check the more specific substrings before the ones they could contain.
    """
    if "has no objective" in message:
        return ExitCode.INVALID, "objective-unknown"
    if "settles nothing" in message:
        # Unreachable while every ObjectiveKind maps to a capability in SETTLES — kept as the
        # honest fallback for a kind that stops doing so.
        return ExitCode.ILLEGAL, "unsettleable-kind"
    if "has no verify clause" in message:
        return ExitCode.ILLEGAL, "no-verify"
    if "does not hold" in message:
        return ExitCode.ILLEGAL, "capability-missing"
    if "requires provenance" in message:
        return ExitCode.INVALID, "missing-provenance"
    return ExitCode.ERROR, "settle-failed"


def _attestation_from(
    objective: Objective | None, evidence: str, attested_by: str | None, checked: str | None
) -> Attestation | None:
    """Build the provenance record from what the host supplied, or ``None`` when any of the
    three is missing — leaving ``settle_objective`` to raise its own provenance refusal rather
    than this verb guessing at a substitute.

    The ``verify`` sentence comes from the objective itself, verbatim, never from a flag: a
    host attests to *what it checked*, not to which sentence the objective declares.
    """
    if evidence != "observed" or objective is None or not objective.verify:
        return None
    if not attested_by or not checked:
        return None
    return Attestation(checked=checked, verify=objective.verify, attested_by=attested_by)


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

    session = open_session(course, state, learner)
    lesson = session.lesson
    objective = next((o for o in objectives_of(lesson) if o.id == objective_id), None)
    attestation = _attestation_from(objective, evidence, attested_by, checked)

    try:
        outcome = settle_objective(
            session.store,
            session.record,
            session.revision,
            lesson,
            objective_id,
            capabilities,
            attestation=attestation,
            now=now_override(),
        )
    except ValueError as exc:
        code, error = _map_settle_error(str(exc))
        fail(code, error, str(exc))

    entry = next(o for o in outcome.record.objectives_met if o.id == objective_id)
    emit(
        {
            "ok": True,
            "verb": "settle",
            "course": {"id": session.course.id, "version": session.course.version},
            "objective": {
                "id": entry.id,
                "evidence": entry.evidence,
                "at": str(entry.at),
                "provenance": entry.provenance.model_dump() if entry.provenance else None,
            },
            "newly_met": objective_id in outcome.newly_met,
            "revision": outcome.revision,
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
    """The current lesson's objectives: id, kind, verify sentence, check proposal, and whether
    the held capabilities could settle each one right now. Read-only — ``check`` is printed,
    never executed; running it is the host's decision, through the host's own permissions."""
    try:
        capabilities = [Capability(c) for c in (capability or [])]
    except ValueError as exc:
        fail(ExitCode.INVALID, "capability-unknown", str(exc))

    session = open_session(course, state, learner)
    lesson = session.lesson
    permitted = {o.id for o in settleable(lesson, capabilities)}

    emit(
        {
            "ok": True,
            "verb": "show",
            "course": {"id": session.course.id, "version": session.course.version},
            "objectives": [
                {
                    "id": o.id,
                    "kind": o.kind,
                    "verify": o.verify,
                    "check": o.check,
                    "settleable_now": o.id in permitted,
                }
                for o in objectives_of(lesson)
            ],
        }
    )
