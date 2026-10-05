"""Trusted learner controls and ephemeral conversation; no authority enters model deps."""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path

from pydantic_ai.messages import ModelMessage

from skilling.course import Capability, parse_lesson
from skilling.delivery import Beat, Input
from skilling.session import (
    ActionOperation,
    ActionOrigin,
    FileSession,
    HomeworkArchiveView,
    HomeworkCheck,
    PendingFeedback,
    SessionRefusal,
    SessionSnapshot,
    TrustedAction,
    VersionMismatch,
    load_course,
)
from skilling.workspace import load_manifest, state_root
from skilling_tutor import (
    AdviceVerdict,
    ConversationContext,
    HomeworkAdvice,
    HomeworkAdviceContext,
    LearnerEvidence,
    NarrationContext,
    ObjectiveAdvice,
    ObjectiveAdviceContext,
    SkillingRunner,
    TutorError,
)

from ._note import GoalNote, NoteObservation
from ._views import controls, snapshot_view


class ControllerError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status


class ReviewKind(StrEnum):
    OBJECTIVES = "objectives"
    HOMEWORK = "homework"


@dataclass
class Review:
    id: str
    kind: ReviewKind
    advice: ObjectiveAdvice | HomeworkAdvice
    record_revision: str
    note: NoteObservation | None
    explanation: str
    submission_token: str | None = None
    displayed: bool = False


@dataclass(frozen=True)
class Display:
    snapshot: SessionSnapshot | None
    feedback: PendingFeedback | None


class ProducerController:
    def __init__(self, workspace: Path, runner: SkillingRunner, course_id: str, learner_id: str):
        self.workspace = workspace
        self.runner = runner
        self.course_id = course_id
        self.learner_id = learner_id
        self.state_root = state_root(workspace)
        self.note = GoalNote.open(workspace)
        self.session: FileSession | None = None
        self.course_path: Path | None = None
        self.startup_error: SessionRefusal | None = None
        self.lock = asyncio.Lock()
        self.csrf_token = secrets.token_urlsafe(32)
        self.browser_session: str | None = None
        self.history: tuple[ModelMessage, ...] = ()
        self.messages: list[dict[str, str]] = []
        self.displays: dict[str, Display] = {}
        self.actions: dict[str, TrustedAction] = {}
        self.review: Review | None = None
        self.confirmations: dict[str, HomeworkArchiveView | dict[str, object]] = {}
        self.submitted = False
        self.history_notice = (
            "Conversation history starts empty. Saved progress is durable; "
            "it does not prove what you said or did. Supply fresh evidence for a review."
        )

    @classmethod
    def open(
        cls,
        workspace: Path,
        runner: SkillingRunner,
        *,
        course_id: str = "welcome-skilling",
        learner_id: str = "local",
    ) -> ProducerController:
        workspace = workspace.expanduser().resolve(strict=True)
        if course_id != "welcome-skilling":
            raise ValueError("this reference producer supports unchanged Welcome only")
        entry = load_manifest(workspace).course(course_id)
        if entry is None:
            raise ValueError("Welcome is not installed; run skilling start first")
        course_path = (workspace / ".skilling" / entry.path).resolve(strict=True)
        if not course_path.is_relative_to(workspace):
            raise ValueError("course is outside the explicit workspace")
        course = load_course(course_path)
        if course.id != entry.id or course.version != entry.version:
            raise ValueError("installed course does not match workspace manifest")
        controller = cls(workspace, runner, course_id, learner_id)
        controller.course_path = course_path
        try:
            controller.session = FileSession.open(
                course,
                state_root=controller.state_root,
                learner_id=learner_id,
                workspace_root=workspace,
            )
        except VersionMismatch as error:
            controller.startup_error = error
        return controller

    def _service(self) -> FileSession:
        if self.session is None:
            raise ControllerError(
                "version-mismatch",
                "Selected course differs from saved state. "
                "Present pending feedback, then use the core CLI to reconcile.",
            )
        return self.session

    def _pending(self) -> PendingFeedback | None:
        return FileSession.pending_feedback_at(
            state_root=self.state_root, learner_id=self.learner_id, course_id=self.course_id
        )

    def _observe(self) -> NoteObservation | None:
        try:
            return self.note.inspect()
        except FileNotFoundError:
            return None

    def _invalidate(self, snapshot: SessionSnapshot, note: NoteObservation | None) -> None:
        review = self.review
        if review is None:
            return
        if review.record_revision != snapshot.revision or review.note != note:
            self.review = None
            return
        if review.kind is ReviewKind.HOMEWORK:
            check = self._service().homework_check()
            if (
                check.revision != review.advice.revision
                or check.submission_token != review.submission_token
            ):
                self.review = None

    def state(self) -> dict[str, object]:
        pending = self._pending()
        snapshot = self.session.snapshot() if self.session is not None else None
        note_error = None
        try:
            note = self._observe()
        except (ValueError, OSError, UnicodeError):
            note = None
            note_error = (
                "Cannot inspect goal note safely; repair its path/content and review again."
            )
            self.review = None
        if snapshot is not None:
            self._invalidate(snapshot, note)
        display_id = secrets.token_urlsafe(24)
        self.displays[display_id] = Display(snapshot, pending)
        while len(self.displays) > 128:
            del self.displays[next(iter(self.displays))]
        homework = None
        objectives = []
        if snapshot is not None and pending is None:
            service = self._service()
            check = service.homework_check()
            homework = {
                "active": asdict(check.active) if check.active else None,
                "revision": check.revision,
            }
            objectives = [
                asdict(o) for o in service.objectives((Capability.CONVERSE, Capability.OBSERVE))
            ]
        review = self.review
        review_view = (
            None
            if review is None
            else {
                "id": review.id,
                "kind": str(review.kind),
                "advice": asdict(review.advice),
                "displayed": review.displayed,
                "note_digest": review.note.digest if review.note else None,
                "objective_ids": [i.id for i in review.advice.objectives]
                if isinstance(review.advice, ObjectiveAdvice)
                else [],
            }
        )
        archive = next(reversed(self.confirmations.values())) if self.confirmations else None
        return {
            "csrf_token": self.csrf_token,
            "display_id": display_id,
            "snapshot": snapshot_view(snapshot) if snapshot is not None else None,
            "controls": controls(snapshot) if snapshot is not None else [],
            "feedback": {"display_id": display_id, **asdict(pending.outcome)} if pending else None,
            "objectives": objectives,
            "homework": homework,
            "note": asdict(note) if note else None,
            "note_error": note_error,
            "review": review_view,
            "history_notice": self.history_notice,
            "messages": list(self.messages),
            "artifact_available": bool(
                snapshot and not pending and (snapshot.beat.name is Beat.CEREMONY or self.submitted)
            ),
            "startup_error": str(self.startup_error) if self.startup_error else None,
            "archive": asdict(archive) if isinstance(archive, HomeworkArchiveView) else None,
        }

    def action(self, control_id: str, display_id: str, event_id: str) -> dict[str, object]:
        display = self.displays.get(display_id)
        if display is None or display.snapshot is None:
            raise ControllerError("display-expired", "Refresh the displayed course before acting.")
        snapshot = display.snapshot
        control = next((c for c in controls(snapshot) if c["id"] == control_id), None)
        if control is None:
            raise ControllerError(
                "illegal-control", "This control was not offered by the displayed state."
            )
        service = self._service()
        if control["operation"] == "complete":
            service.complete(snapshot.revision)
        elif control["operation"] == "ceremony":
            if service.snapshot().revision != snapshot.revision:
                raise ControllerError("stale-display", "The celebration changed; refresh first.")
            service.ceremony(workspace_root=self.workspace)
        else:
            operation = ActionOperation(control["operation"])
            origin = (
                ActionOrigin.PRESENTATION
                if control["payload"] == str(Input.NEXT)
                else ActionOrigin.LEARNER
            )
            action = TrustedAction.create(
                snapshot,
                event_id=event_id,
                operation=operation,
                payload=control["payload"],
                origin=origin,
            )
            captured = self.actions.get(event_id)
            if captured is not None and captured != action:
                raise ControllerError(
                    "idempotency-key-conflict", "Event already belongs to another control."
                )
            self.actions[event_id] = action
            result = service.act(action)
            state = self.state()
            state["replayed"] = result.replayed
            state["original_outcome"] = (
                asdict(result.original_outcome) if result.original_outcome else None
            )
            return state
        return self.state()

    def acknowledge_feedback(self, display_id: str) -> dict[str, object]:
        display = self.displays.get(display_id)
        if display is None or display.feedback is None:
            raise ControllerError(
                "feedback-display", "No canonical feedback belongs to this display."
            )
        pending = display.feedback
        FileSession.acknowledge_feedback_at(
            pending.feedback_id,
            pending.revision,
            state_root=self.state_root,
            learner_id=self.learner_id,
            course_id=self.course_id,
        )
        return self.state()

    async def chat(self, message: str) -> dict[str, object]:
        self.review = None
        service = self._service()
        snapshot = await asyncio.to_thread(service.snapshot)
        check = (
            await asyncio.to_thread(service.homework_check)
            if snapshot.pending_feedback is None
            else None
        )
        context = await asyncio.to_thread(self._context, snapshot, homework_check=check)
        try:
            result = await self.runner.chat(message, context, history=self.history)
        except TutorError:
            state = await asyncio.to_thread(self.state)
            state["tutor_error"] = (
                "Tutor unavailable. Saved course position remains visible; retry your question."
            )
            return state
        current = await asyncio.to_thread(service.snapshot)
        if current.revision != snapshot.revision:
            raise ControllerError("stale-tutor", "Course changed during the tutor turn; ask again.")
        self.history = result.history[-128:]
        self.messages.extend(
            [{"role": "learner", "text": message}, {"role": "tutor", "text": result.output.text}]
        )
        self.messages = self.messages[-64:]
        state = await asyncio.to_thread(self.state)
        state["tutor_reply"] = result.output.text
        state["refresh"] = [str(item) for item in result.output.refresh]
        return state

    def _context(
        self,
        snapshot: SessionSnapshot,
        *,
        objectives: ObjectiveAdviceContext | None = None,
        homework: HomeworkAdviceContext | None = None,
        homework_check: HomeworkCheck | None = None,
    ) -> ConversationContext:
        context = ConversationContext.from_snapshot(
            snapshot, objectives=objectives, homework=homework, homework_check=homework_check
        )
        slot = (
            "concept"
            if snapshot.beat.name is Beat.GATE_CONCEPT
            else "exercise"
            if snapshot.beat.name is Beat.GATE_EXERCISE
            else None
        )
        if slot is not None and self.course_path is not None:
            lesson = load_course(self.course_path).lesson_at(snapshot.position.coordinate)
            if lesson is not None:
                section = parse_lesson(lesson.path).section(slot)
                if section is not None:
                    copied = replace(snapshot, beat=replace(snapshot.beat, body=section.body))
                    context = replace(context, teaching=NarrationContext.from_snapshot(copied))
        return context

    def save_note(self, text: str) -> dict[str, object]:
        self.note.save(text)
        self.review = None
        return self.state()

    async def review_work(self, kind: ReviewKind, explanation: str) -> dict[str, object]:
        if not explanation.strip():
            raise ControllerError(
                "missing-explanation", "Supply your own actual explanation or work evidence."
            )
        kind = ReviewKind(kind)
        self.review = None
        service = self._service()
        snapshot = await asyncio.to_thread(service.snapshot)
        if snapshot.pending_feedback is not None or snapshot.revision is None:
            raise ControllerError(
                "pending-feedback", "Present canonical feedback before reviewing work."
            )
        note = await asyncio.to_thread(self._observe)
        objectives = None
        homework = None
        check = None
        token = None
        if kind is ReviewKind.OBJECTIVES:
            selected = await asyncio.to_thread(
                service.objectives, (Capability.CONVERSE, Capability.OBSERVE)
            )
            if not selected:
                raise ControllerError("no-objectives", "There are no objectives at this lesson.")
            evidence_text = "Learner's own explanation:\n" + explanation
            if note is not None:
                evidence_text += "\nActual inspected learner note:\n" + note.text
            objectives = ObjectiveAdviceContext.from_objectives(
                selected,
                evidence=LearnerEvidence.from_text(evidence_text),
                revision=snapshot.revision,
            )
        else:
            check = await asyncio.to_thread(service.homework_check)
            if check.active is None or check.submission_token is None or note is None:
                raise ControllerError(
                    "homework-evidence", "An active assignment and actual saved note are required."
                )
            evidence_text = (
                "Learner-supplied evidence (not inferred from completion):\n" + explanation
            )
            evidence_text += "\nActual inspected goal note including review update:\n" + note.text
            homework = HomeworkAdviceContext.from_check(
                check, evidence=LearnerEvidence.from_text(evidence_text)
            )
            token = check.submission_token
        context = await asyncio.to_thread(
            self._context, snapshot, objectives=objectives, homework=homework, homework_check=check
        )
        prompt = (
            "Review the supplied actual evidence for every authored criterion. Explain why each "
            "is supported, partial, or not-yet. Return complete structured advice "
            "in the same conversation. "
            "Do not infer evidence from progression. Learner evidence: " + explanation
        )
        result = await self.runner.chat(prompt, context, history=self.history)
        advice = (
            result.output.objectives if kind is ReviewKind.OBJECTIVES else result.output.homework
        )
        if advice is None:
            raise ControllerError(
                "missing-advice", "Tutor did not return complete advice; review again."
            )
        current = await asyncio.to_thread(service.snapshot)
        actual_note = await asyncio.to_thread(self._observe)
        if current.revision != snapshot.revision or actual_note != note:
            raise ControllerError(
                "stale-review", "Work or course changed during review; inspect and review again."
            )
        actual_check = (
            await asyncio.to_thread(service.homework_check) if check is not None else None
        )
        if check is not None and actual_check != check:
            raise ControllerError(
                "stale-homework", "Assignment changed during review; review again."
            )
        self.history = result.history[-128:]
        self.messages.append({"role": "tutor", "text": result.output.text})
        self.review = Review(
            secrets.token_urlsafe(24), kind, advice, snapshot.revision, note, explanation, token
        )
        return await asyncio.to_thread(self.state)

    def acknowledge_review(self, review_id: str) -> dict[str, object]:
        review = self._fresh_review(review_id)
        review.displayed = True
        return self.state()

    def _fresh_review(self, review_id: str) -> Review:
        self._invalidate(self._service().snapshot(), self._observe())
        if self.review is None or self.review.id != review_id:
            raise ControllerError(
                "stale-review", "Review is missing or stale; inspect and review again."
            )
        return self.review

    def confirm_review(self, review_id: str, objective_id: str | None) -> dict[str, object]:
        receipt_key = review_id + "/" + (objective_id or "homework")
        if receipt_key in self.confirmations:
            return self.state()
        review = self._fresh_review(review_id)
        if not review.displayed:
            raise ControllerError("review-not-displayed", "Render all advice before confirming it.")
        service = self._service()
        if isinstance(review.advice, ObjectiveAdvice):
            selected = next(
                (
                    o
                    for o in service.objectives((Capability.CONVERSE, Capability.OBSERVE))
                    if o.id == objective_id
                ),
                None,
            )
            item = next((i for i in review.advice.objectives if i.id == objective_id), None)
            if selected is None or item is None or item.verdict is not AdviceVerdict.SUPPORTED:
                raise ControllerError(
                    "unsupported-objective",
                    "The selected objective lacks positive displayed advice.",
                )
            if selected.kind.value == "practice" and (
                review.note is None or not review.note.meaningful
            ):
                raise ControllerError(
                    "meaningful-note",
                    "Actual meaningful Goal, Takeaway, and Next action are required.",
                )
            checked = (
                None
                if selected.kind.value == "knowledge"
                else f"Inspected regular UTF-8 {review.note.path if review.note else ''}; "
                f"SHA-256 {review.note.digest if review.note else ''}; "
                "meaningful learner-authored fields; "
                f"displayed positive review {review.id}; learner confirmed authorship."
            )
            result = service.settle_objective(
                selected.id,
                (Capability.CONVERSE, Capability.OBSERVE),
                checked=checked,
                attested_by="local-reference-producer" if checked else None,
                expected_revision=review.record_revision,
            )
            self.confirmations[receipt_key] = asdict(result)
        else:
            if objective_id is not None or review.submission_token is None:
                raise ControllerError(
                    "review-binding", "Confirmation does not match this homework review."
                )
            if any(i.verdict is not AdviceVerdict.SUPPORTED for i in review.advice.requirements):
                raise ControllerError(
                    "partial-homework", "Every required item needs positive displayed feedback."
                )
            archive = service.homework_submit(review.submission_token)
            self.confirmations[receipt_key] = archive
            self.submitted = True
        self.review = None
        return self.state()

    def artifact(self, title: str) -> dict[str, object]:
        service = self._service()
        snapshot = service.snapshot()
        if snapshot.pending_feedback is not None or not (
            snapshot.beat.name is Beat.CEREMONY or self.submitted
        ):
            raise ControllerError(
                "artifact-timing", "Artifacts are optional at celebration or confirmed submission."
            )
        if self._observe() is None:
            raise ControllerError("missing-note", "Save an actual note before registering it.")
        service.artifact_add(
            self.workspace / "showcase/welcome-skilling/goal.md",
            title,
            workspace_root=self.workspace,
            path_base=self.workspace,
            expected_revision=snapshot.revision,
        )
        return self.state()
