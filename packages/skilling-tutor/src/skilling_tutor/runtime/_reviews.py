"""Evidence-bound reviews; model advice never settles or submits learner work."""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Generic, TypeVar

from skilling.course import Capability
from skilling.session import ObjectiveType, SessionSnapshot

from .._advice import AdviceVerdict, HomeworkAdvice, ObjectiveAdvice
from .._capability import SkillingCapability
from .._context import HomeworkAdviceContext, LearnerEvidence, ObjectiveAdviceContext, TutorPurpose
from ._types import Evidence, RuntimeErrorCode, TutorSessionError

if TYPE_CHECKING:
    from ._session import TutorSession

DepsT = TypeVar("DepsT")


@dataclass
class Review:
    id: str
    kind: str
    advice: ObjectiveAdvice | HomeworkAdvice
    snapshot: SessionSnapshot
    evidence: Evidence | None
    submission_token: str | None = None
    displayed: bool = False


class Reviews(Generic[DepsT]):
    def __init__(self, session: TutorSession[DepsT]):
        self.session = session
        self.current: Review | None = None
        self.confirmed: set[str] = set()

    def view(self) -> dict[str, object] | None:
        review = self.current
        if review is None or review.snapshot != self.session.service.snapshot():
            self.current = None
            return None
        return {
            "id": review.id,
            "kind": review.kind,
            "advice": asdict(review.advice),
            "displayed": review.displayed,
            "objective_ids": [
                o.id
                for o in review.advice.objectives
                if review.id + "/" + o.id not in self.confirmed
            ]
            if isinstance(review.advice, ObjectiveAdvice)
            else [],
        }

    async def _evidence(self, snapshot: SessionSnapshot) -> Evidence | None:
        hook = self.session.tutor.evidence_provider
        evidence = (
            await hook(self.session.learner_id, self.session.alias, snapshot) if hook else None
        )
        if evidence is not None and (not evidence.revision.strip() or not evidence.text.strip()):
            raise TutorSessionError(
                RuntimeErrorCode.EVIDENCE, "Evidence requires nonempty text and revision"
            )
        return evidence

    async def review(self, kind: str, explanation: str) -> None:
        if (
            kind not in ("objectives", "homework")
            or not explanation.strip()
            or len(explanation) > 16_000
        ):
            raise TutorSessionError(
                RuntimeErrorCode.INVALID,
                "Choose objectives or homework and supply bounded actual evidence",
                400,
            )
        self.current = None
        session = self.session
        snapshot = session.service.snapshot()
        if snapshot.pending_feedback or snapshot.revision is None:
            raise TutorSessionError(
                RuntimeErrorCode.REVIEW, "Render canonical feedback before reviewing work"
            )
        evidence = await self._evidence(snapshot)
        actual = LearnerEvidence.from_text(
            "Learner's own explanation:\n"
            + explanation
            + ("\nActual application-observed work:\n" + evidence.text if evidence else "")
        )
        agent = session.tutor.review_agent
        factory = session.tutor.deps_factory
        token = None
        advice: ObjectiveAdvice | HomeworkAdvice
        if kind == "objectives":
            objectives = session.service.objectives((Capability.CONVERSE, Capability.OBSERVE))
            if not objectives:
                raise TutorSessionError(
                    RuntimeErrorCode.REVIEW, "No objectives are available at this lesson"
                )
            context = ObjectiveAdviceContext.from_objectives(
                objectives, evidence=actual, revision=snapshot.revision
            )
            capability = SkillingCapability[DepsT].create(
                TutorPurpose.OBJECTIVE_ADVICE, context_getter=lambda _: context
            )
            if factory:
                result = await agent.run(
                    "Review the supplied actual evidence for every objective.",
                    output_type=ObjectiveAdvice.output_type(),
                    capabilities=[capability],
                    deps=factory(session.learner_id, session.alias),
                    usage_limits=session.tutor.usage_limits,
                )
            else:
                result = await agent.run(  # pyright: ignore[reportCallIssue, reportArgumentType]
                    "Review the supplied actual evidence for every objective.",
                    output_type=ObjectiveAdvice.output_type(),
                    capabilities=[capability],
                    usage_limits=session.tutor.usage_limits,
                )
            advice = ObjectiveAdvice.from_output(result.output, context=context)
        else:
            check = session.service.homework_check()
            if check.active is None or check.submission_token is None or evidence is None:
                raise TutorSessionError(
                    RuntimeErrorCode.EVIDENCE,
                    "Homework review requires an active assignment "
                    "and actual application-observed evidence",
                )
            homework_context = HomeworkAdviceContext.from_check(check, evidence=actual)
            homework_capability = SkillingCapability[DepsT].create(
                TutorPurpose.HOMEWORK_ADVICE, context_getter=lambda _: homework_context
            )
            if factory:
                homework_result = await agent.run(
                    "Review the supplied actual evidence for every homework criterion.",
                    output_type=HomeworkAdvice.output_type(),
                    capabilities=[homework_capability],
                    deps=factory(session.learner_id, session.alias),
                    usage_limits=session.tutor.usage_limits,
                )
            else:
                homework_result = await agent.run(  # pyright: ignore[reportCallIssue, reportArgumentType]
                    "Review the supplied actual evidence for every homework criterion.",
                    output_type=HomeworkAdvice.output_type(),
                    capabilities=[homework_capability],
                    usage_limits=session.tutor.usage_limits,
                )
            advice = HomeworkAdvice.from_output(homework_result.output, context=homework_context)
            token = check.submission_token
            if check != session.service.homework_check():
                raise TutorSessionError(
                    RuntimeErrorCode.STALE, "Assignment changed during review; review again"
                )
        if session.service.snapshot() != snapshot or await self._evidence(snapshot) != evidence:
            raise TutorSessionError(
                RuntimeErrorCode.STALE, "Work or course changed during review; review again"
            )
        self.current = Review(secrets.token_urlsafe(24), kind, advice, snapshot, evidence, token)

    async def _fresh(self, review_id: str) -> Review:
        review = self.current
        if (
            review is None
            or review.id != review_id
            or self.session.service.snapshot() != review.snapshot
            or await self._evidence(review.snapshot) != review.evidence
        ):
            self.current = None
            raise TutorSessionError(
                RuntimeErrorCode.STALE, "Review changed or expired; inspect the work again"
            )
        return review

    async def acknowledge(self, review_id: str) -> None:
        (await self._fresh(review_id)).displayed = True

    async def confirm(self, review_id: str, objective_id: str | None) -> None:
        key = review_id + "/" + (objective_id or "homework")
        if key in self.confirmed:
            return
        review = await self._fresh(review_id)
        if not review.displayed:
            raise TutorSessionError(
                RuntimeErrorCode.REVIEW, "Render the complete review before confirming"
            )
        service = self.session.service
        if isinstance(review.advice, ObjectiveAdvice):
            selected = next(
                (
                    o
                    for o in service.objectives((Capability.CONVERSE, Capability.OBSERVE))
                    if o.id == objective_id
                ),
                None,
            )
            item = next((o for o in review.advice.objectives if o.id == objective_id), None)
            if selected is None or item is None or item.verdict is not AdviceVerdict.SUPPORTED:
                raise TutorSessionError(
                    RuntimeErrorCode.REVIEW, "The objective needs positive displayed advice"
                )
            checked = attested = None
            if selected.kind is ObjectiveType.PRACTICE:
                if (
                    review.evidence is None
                    or not review.evidence.checked
                    or not review.evidence.attested_by
                ):
                    raise TutorSessionError(
                        RuntimeErrorCode.EVIDENCE,
                        "Practice settlement requires actual producer inspection and provenance",
                    )
                checked, attested = review.evidence.checked, review.evidence.attested_by
            service.settle_objective(
                selected.id,
                (Capability.CONVERSE, Capability.OBSERVE),
                checked=checked,
                attested_by=attested,
                expected_revision=review.snapshot.revision,
            )
        else:
            if (
                objective_id is not None
                or review.submission_token is None
                or any(r.verdict is not AdviceVerdict.SUPPORTED for r in review.advice.requirements)
            ):
                raise TutorSessionError(
                    RuntimeErrorCode.REVIEW, "Every required item needs positive displayed advice"
                )
            if service.homework_check().submission_token != review.submission_token:
                raise TutorSessionError(RuntimeErrorCode.STALE, "Homework changed; review again")
            service.homework_submit(review.submission_token)
        self.confirmed.add(key)
        if isinstance(review.advice, ObjectiveAdvice) and any(
            review.id + "/" + item.id not in self.confirmed for item in review.advice.objectives
        ):
            # Settling one displayed item preserves the same inspected evidence for the rest.
            review.snapshot = service.snapshot()
            if review.snapshot.revision is not None:
                review.advice = replace(review.advice, revision=review.snapshot.revision)
        else:
            self.current = None
