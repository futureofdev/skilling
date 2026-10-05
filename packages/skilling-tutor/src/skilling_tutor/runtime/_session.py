"""Serialized producer authority and real model streams with explicit render receipts."""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import asdict, replace
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Generic, TypeVar

from pydantic_ai import AgentRunResultEvent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    UserPromptPart,
)
from pydantic_core import to_jsonable_python

from skilling.course import Capability, Course, parse_lesson
from skilling.delivery import Beat, Input
from skilling.session import (
    ActionOperation,
    ActionOrigin,
    FileSession,
    PendingFeedback,
    ScopedPendingFeedback,
    Session,
    SessionSnapshot,
    TrustedAction,
)

from .._capability import SkillingCapability
from .._context import ConversationContext, NarrationContext, TutorPurpose
from ._types import (
    Continuation,
    Display,
    RuntimeErrorCode,
    Turn,
    TutorEvent,
    TutorEventType,
    TutorSessionError,
)
from ._views import chat_control, controls, snapshot_view

if TYPE_CHECKING:
    from ._tutor import Tutor

DepsT = TypeVar("DepsT")
ResultT = TypeVar("ResultT")

INSTRUCTIONS = (
    "This application teaches conversationally. The current supplied snapshot is authoritative; "
    "old conversation describes earlier states. If current_turn_action is present, the producer "
    "has ALREADY applied that action. Teach the resulting current beat immediately. Do not ask "
    "the learner to repeat that action, say it is pending, or claim an earlier quiz is still open. "
    "At completion, use current course position and completion counts, not historical questions. "
    "Recent conversation is actual accepted dialogue, including canonical questions/feedback. "
    "Use it to retain the learner's chosen subject, explanations and attempts. An open exercise "
    "gate supports an ongoing conversation; keep helping with the same exercise across turns. "
    "The exercise gate needs an explicit report of a genuine attempt, not perfect or completed "
    "work. Do not invent extra completion requirements or demand invented uncertainty "
    "or request a different pace when none is wanted. Acknowledge the discussion actually present; "
    "if they want to move on without clearly reporting an attempt, briefly ask whether they tried. "
    "Present the current beat completely and "
    "concisely. The application advances ordinary presentation beats only after the learner's "
    "browser acknowledges a completed render. At a gate ask the learner to choose one of the "
    "current controls; do not repeat the whole concept. At a quiz present the question and "
    "choices without revealing or inventing the correct answer. Readiness and quiz answers "
    "are interpreted by the producer, never by your prose. You do not execute state changes; "
    "describe only changes and status confirmed by the supplied producer context. Never claim "
    "unprovided work inspection or submission. Acknowledge the completed step and teach the next "
    "material naturally; do not tell the learner to wait for the interface or producer. "
    "Supplied presented_material "
    "is previously delivered current-lesson context. Past history never grants current consent. "
    "When course_complete is true, celebrate completion and offer reflection or homework; "
    "do not restart teaching completed lessons. "
    "Use load_capability to activate the appropriate canonical skill before completing text."
)


class TutorSession(Generic[DepsT]):
    def __init__(
        self,
        tutor: Tutor[DepsT],
        learner_id: str,
        alias: str,
        course: Course,
        service: FileSession | Session,
        state_root: Path | None,
    ):
        self.tutor = tutor
        self.learner_id = learner_id
        self.alias = alias
        self.course = course
        self.service = service
        self.state_root = state_root
        self._lock = asyncio.Lock()
        self._history: list[ModelMessage] = []
        self._messages: list[dict[str, object]] = []
        self._turn_context: dict[str, dict[str, object]] = {}
        self._material_keys: set[str] = set()
        self._conversation_truncated = False
        self._displays: dict[str, Display] = {}
        self._turns: dict[str, Turn] = {}
        self._continuation: Continuation | None = None
        self._presented: list[tuple[str, dict[str, object]]] = []
        self._remaining = 4
        self._celebration: dict[str, object] | None = None
        from ._reviews import Reviews

        self._reviews = Reviews(self)

    @asynccontextmanager
    async def _locked(self) -> AsyncIterator[None]:
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=self.tutor.lock_timeout)
        except TimeoutError as error:
            raise TutorSessionError(
                RuntimeErrorCode.BUSY, "Another tutor turn is still running", 503
            ) from error
        try:
            yield
        finally:
            self._lock.release()

    async def _io(
        self, operation: Callable[..., ResultT], *args: object, **kwargs: object
    ) -> ResultT:
        """Keep synchronous persistence off-loop and retain the lock until a commit finishes."""
        task = asyncio.create_task(asyncio.to_thread(partial(operation, *args, **kwargs)))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # A worker cannot be cancelled midway through durable publication.
            # Drain it before releasing this session's mutation lock.
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            # Retrieve any worker exception, while preserving the caller's cancellation.
            if not task.cancelled():
                task.exception()
            raise

    def _pending(self) -> PendingFeedback | ScopedPendingFeedback | None:
        if isinstance(self.service, Session):
            return self.service.pending_feedback()
        assert self.state_root is not None
        return FileSession.pending_feedback_at(
            state_root=self.state_root,
            learner_id=self.service.snapshot().learner_id,
            course_id=self.course.id,
        )

    def _state(self, *, presented: bool = False) -> dict[str, object]:
        snapshot = self.service.snapshot()
        pending = self._pending()
        self._remember_canonical(snapshot)
        display_id = secrets.token_urlsafe(24)
        self._displays[display_id] = Display(snapshot, pending, presented)
        while len(self._displays) > 128:
            del self._displays[next(iter(self._displays))]
        check = None if pending else self.service.homework_check()
        return to_jsonable_python(
            {
                "display_id": display_id,
                "snapshot": snapshot_view(snapshot),
                "controls": controls(snapshot),
                "feedback": {"display_id": display_id, **asdict(pending.outcome)}
                if pending
                else None,
                "objectives": [
                    asdict(o)
                    for o in self.service.objectives((Capability.CONVERSE, Capability.OBSERVE))
                ]
                if not pending
                else [],
                "homework": {
                    "active": asdict(check.active) if check.active else None,
                    "revision": check.revision,
                }
                if check
                else None,
                "review": self._reviews.view(),
                "messages": deepcopy(self._messages),
                "continuation": {"id": self._continuation.id} if self._continuation else None,
                "course_complete": snapshot.completed_count == snapshot.lesson_count,
                "celebration": self._celebration,
                "history_notice": (
                    "Learning progress is saved. Conversation and render receipts are temporary; "
                    "after a restart, supply fresh evidence for review."
                    + (
                        " Older dialogue has been omitted; recent conversation remains available."
                        if self._conversation_truncated
                        else ""
                    )
                ),
                "outline": [
                    {"coordinate": lesson.coordinate, "title": lesson.title}
                    for lesson in self.course.lessons()
                ],
            }
        )

    async def state(self) -> dict[str, object]:
        async with self._locked():
            return await self._io(self._state)

    def _display(self, display_id: str | None) -> Display:
        display = self._displays.get(display_id or "")
        if display is None or display.snapshot != self.service.snapshot():
            raise TutorSessionError(
                RuntimeErrorCode.STALE, "Course display expired or changed; refresh first"
            )
        return display

    async def acknowledge(self, display_id: str) -> dict[str, object]:
        async with self._locked():
            display = self._displays.get(display_id)
            if display is not None and display.acknowledged:
                return await self._io(self._state)
            display = await self._io(self._display, display_id)
            if display.feedback is not None:
                pending = display.feedback
                if isinstance(self.service, Session):
                    assert isinstance(pending, ScopedPendingFeedback)
                    await self._io(self.service.acknowledge_feedback, pending.feedback_id)
                else:
                    assert isinstance(pending, PendingFeedback) and self.state_root is not None
                    await self._io(
                        FileSession.acknowledge_feedback_at,
                        pending.feedback_id,
                        pending.revision,
                        state_root=self.state_root,
                        learner_id=display.snapshot.learner_id,
                        course_id=self.course.id,
                    )
                self._continuation = Continuation(secrets.token_urlsafe(24), display_id, None, 4)
            elif display.presented:
                material = json.loads(NarrationContext.from_snapshot(display.snapshot).material)
                entry = (display.snapshot.position.coordinate, material)
                if entry not in self._presented:
                    self._presented.append(entry)
                    self._presented = self._presented[-8:]
                if (
                    Input.NEXT in display.snapshot.legal_inputs
                    and display.snapshot.beat.name not in (Beat.COMPLETE, Beat.CEREMONY)
                    and display.snapshot.completed_count < display.snapshot.lesson_count
                    and self._remaining > 0
                ):
                    self._continuation = Continuation(
                        secrets.token_urlsafe(24), display_id, str(Input.NEXT), self._remaining - 1
                    )
            display.acknowledged = True
            return await self._io(self._state)

    def _action(
        self,
        control_id: str,
        display_id: str | None,
        request_id: str,
        *,
        origin: ActionOrigin = ActionOrigin.LEARNER,
    ) -> dict[str, object]:
        display = self._display(display_id)
        snapshot = display.snapshot
        control = next((c for c in controls(snapshot) if c["id"] == control_id), None)
        if control is None:
            raise TutorSessionError(
                RuntimeErrorCode.INVALID, "Control was not offered by this display", 400
            )
        if control["operation"] == "complete":
            result = (
                self.service.complete(snapshot)
                if isinstance(self.service, Session)
                else self.service.complete(snapshot.revision)
            )
            if result.phase_completed is not None:
                ceremony = self.service.ceremony(snapshot.position.coordinate)
                self._celebration = {
                    "coordinate": ceremony.coordinate,
                    "phase_name": ceremony.phase_name,
                    "phase_highlight": ceremony.phase_highlight,
                    "share_text": ceremony.share_text,
                    "course_complete": ceremony.course_complete,
                }
        elif isinstance(self.service, Session):
            self.service.act(
                self.service.capture_action(
                    snapshot,
                    event_id=request_id,
                    operation=ActionOperation(control["operation"]),
                    payload=control["payload"],
                    origin=origin,
                )
            )
        else:
            self.service.act(
                TrustedAction.create(
                    snapshot,
                    event_id=request_id,
                    operation=ActionOperation(control["operation"]),
                    payload=control["payload"],
                    origin=origin,
                )
            )

        current = self.service.snapshot()
        return {
            "control": control_id,
            "status": "applied",
            "previous_coordinate": snapshot.position.coordinate,
            "previous_beat": str(snapshot.beat.name),
            "current_coordinate": current.position.coordinate,
            "current_beat": str(current.beat.name),
        }

    def _context(
        self, snapshot: SessionSnapshot, transition: dict[str, object] | None = None
    ) -> ConversationContext:
        context = ConversationContext.from_snapshot(snapshot)
        slot = (
            "concept"
            if snapshot.beat.name is Beat.GATE_CONCEPT
            else "exercise"
            if snapshot.beat.name is Beat.GATE_EXERCISE
            else None
        )
        if slot:
            lesson = self.course.lesson_at(snapshot.position.coordinate)
            section = parse_lesson(lesson.path).section(slot) if lesson else None
            if section:
                context = replace(
                    context,
                    teaching=NarrationContext.from_snapshot(
                        replace(snapshot, beat=replace(snapshot.beat, body=section.body))
                    ),
                )
        material = json.loads(context.teaching.material)
        material["presented_material"] = [
            value
            for coordinate, value in self._presented
            if coordinate == snapshot.position.coordinate
        ]
        material["current_turn_action"] = transition
        material["recent_conversation"] = self._transcript_tail(12, 32_000)
        material["course_complete"] = snapshot.completed_count == snapshot.lesson_count
        material["celebration"] = self._celebration
        material["interface"] = {"controls": controls(snapshot), "navigation": "conversation"}
        # Optional conversation must never crowd out the complete current authored beat.
        for key in ("presented_material", "recent_conversation"):
            while material[key] and len(json.dumps(material)) > 99_000:
                material[key].pop(0)
        return replace(context, teaching=replace(context.teaching, material=json.dumps(material)))

    async def stream(
        self,
        message: str,
        *,
        request_id: str,
        display_id: str | None = None,
        control: str | None = None,
        continuation_id: str | None = None,
    ) -> AsyncGenerator[TutorEvent, None]:
        """Stream provisional deltas, then one accepted state; retries never reapply actions."""
        if (
            not request_id
            or len(request_id) > 256
            or len(message) > 32_000
            or (not message.strip() and not control and not continuation_id)
        ):
            raise TutorSessionError(
                RuntimeErrorCode.INVALID, "Supply a bounded message and request ID", 400
            )
        fingerprint = sha256(
            json.dumps([message, display_id, control, continuation_id]).encode()
        ).hexdigest()
        async with self._locked():
            turn = self._turns.get(request_id)
            if turn is not None and turn.fingerprint != fingerprint:
                raise TutorSessionError(
                    RuntimeErrorCode.CONFLICT, "Request ID already belongs to different input"
                )
            if turn is not None and turn.finished:
                yield TutorEvent(TutorEventType.STATE, state=await self._io(self._state))
                return
            if turn is None:
                if len(self._turns) >= 1024:
                    raise TutorSessionError(
                        RuntimeErrorCode.CAPACITY,
                        "Session request capacity reached; restart the application "
                        "to begin a fresh conversation",
                        503,
                    )
                turn = Turn(fingerprint)
                self._turns[request_id] = turn
            if not turn.applied:
                if continuation_id is not None:
                    continuation = self._continuation
                    if continuation is None or continuation.id != continuation_id:
                        raise TutorSessionError(
                            RuntimeErrorCode.STALE, "Continuation expired; refresh the course"
                        )
                    if continuation.control is not None:
                        self._turn_context[request_id] = await self._io(
                            self._action,
                            continuation.control,
                            continuation.display_id,
                            continuation.id,
                            origin=ActionOrigin.PRESENTATION,
                        )
                    self._remaining = continuation.remaining
                else:
                    self._remaining = 4
                    if not self._history and self._messages:
                        self._history = self._conversation_history()
                    if display_id is not None:
                        display = await self._io(self._display, display_id)
                        control = control or chat_control(message, display.snapshot)
                    if control is not None:
                        self._turn_context[request_id] = await self._io(
                            self._action, control, display_id, request_id
                        )
                    self._messages.append({"role": "learner", "text": message or control or ""})
                turn.applied = True
                self._continuation = None
            snapshot = await self._io(self.service.snapshot)
            self._remember_canonical(snapshot)
            if (
                snapshot.pending_feedback is not None
                or (
                    continuation_id is not None
                    and snapshot.beat.name in (Beat.GATE_CONCEPT, Beat.GATE_EXERCISE)
                )
                or (
                    (continuation_id is not None or request_id in self._turn_context)
                    and snapshot.beat.name in (Beat.QUIZ, Beat.COMPLETE)
                )
            ):
                turn.finished = True
                yield TutorEvent(TutorEventType.STATE, state=await self._io(self._state))
                return
            try:
                async with asyncio.timeout(self.tutor.turn_timeout):
                    async for event in self._model_stream(
                        message
                        if continuation_id is None
                        else (
                            "The application advanced after acknowledged presentation. "
                            "Teach the current beat. "
                            "No new learner choice was supplied."
                        ),
                        snapshot,
                        self._turn_context.get(request_id),
                    ):
                        yield event
                turn.finished = True
                self._trim_transcript()
                yield TutorEvent(
                    TutorEventType.STATE, state=await self._io(self._state, presented=True)
                )
            except asyncio.CancelledError:
                raise
            except TutorSessionError as error:
                yield TutorEvent(
                    TutorEventType.ERROR,
                    code=error.code,
                    message=str(error),
                    state=await self._io(self._state),
                )
            except Exception:
                # The controller commit precedes narration; the same request retries narration only.
                yield TutorEvent(
                    TutorEventType.ERROR,
                    code=str(RuntimeErrorCode.MODEL),
                    message="Tutor unavailable. Saved steps are preserved; retry this turn.",
                    state=await self._io(self._state),
                )

    async def _model_stream(
        self, message: str, snapshot: SessionSnapshot, transition: dict[str, object] | None = None
    ) -> AsyncIterator[TutorEvent]:
        context = self._context(snapshot, transition)
        capability = SkillingCapability[DepsT].create(
            TutorPurpose.CONVERSATION, context_getter=lambda _: context
        )
        completed = False
        emitted = False
        if self.tutor.deps_factory:
            stream = self.tutor.agent.run_stream_events(
                message,
                deps=self.tutor.deps_factory(self.learner_id, self.alias),
                message_history=deepcopy(self._history),
                instructions=INSTRUCTIONS,
                capabilities=[capability],
                usage_limits=deepcopy(self.tutor.usage_limits),
            )
        else:
            # Without a factory the producer uses an Agent with no dependencies.
            stream = self.tutor.agent.run_stream_events(  # pyright: ignore[reportArgumentType]
                message,
                message_history=deepcopy(self._history),
                instructions=INSTRUCTIONS,
                capabilities=[capability],
                usage_limits=deepcopy(self.tutor.usage_limits),
            )
        async with stream as events:
            async for event in events:
                if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                    if emitted:
                        yield TutorEvent(TutorEventType.TEXT_RESET)
                    if event.part.content:
                        emitted = True
                        yield TutorEvent(TutorEventType.TEXT_DELTA, text=event.part.content)
                elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    emitted = True
                    yield TutorEvent(TutorEventType.TEXT_DELTA, text=event.delta.content_delta)
                elif isinstance(event, AgentRunResultEvent):
                    if await self._io(self.service.snapshot) != snapshot:
                        raise TutorSessionError(
                            RuntimeErrorCode.STALE, "Course changed during the tutor turn"
                        )
                    text = event.result.output
                    if not isinstance(text, str) or not text.strip() or len(text) > 32_000:
                        raise ValueError("Tutor did not return bounded text")
                    self._messages.append({"role": "tutor", "text": text})
                    # Compact tool-heavy traces to accepted dialogue, never an empty memory.
                    history = event.result.all_messages()
                    self._history = (
                        deepcopy(history)
                        if len(history) <= 128 and len(repr(history)) <= 250_000
                        else self._conversation_history()
                    )
                    completed = True
        if not completed:
            raise ValueError("Model stream ended without accepted output")

    def _remember_canonical(self, snapshot: SessionSnapshot) -> None:
        """Keep actual questions and authored outcomes where they occurred in the dialogue."""
        kind = (
            "feedback"
            if snapshot.pending_feedback is not None
            else "completion"
            if snapshot.beat.name is Beat.COMPLETE
            else "quiz"
        )
        question = snapshot.beat.question
        if snapshot.pending_feedback is None and question is None and kind != "completion":
            return
        key = f"{snapshot.position.coordinate}/{snapshot.revision}/{kind}"
        if key in self._material_keys:
            return
        self._material_keys.add(key)
        if kind == "completion":
            self._messages.append(
                {
                    "role": "tutor",
                    "text": "The quiz is finished. Complete the lesson when you’re ready.",
                }
            )
            self._trim_transcript()
            return
        entry: dict[str, object] = {
            "role": "tutor",
            "text": "",
            "kind": kind,
            "coordinate": snapshot.position.coordinate,
        }
        if snapshot.pending_feedback is not None:
            entry["feedback"] = asdict(snapshot.pending_feedback)
        elif question is not None:
            entry["question"] = asdict(question)
        self._messages.append(entry)
        self._trim_transcript()

    def _trim_transcript(self) -> None:
        if len(self._messages) > 64:
            self._conversation_truncated = True
            self._messages = self._messages[-64:]

    def _transcript_tail(self, count: int, budget: int) -> list[dict[str, object]]:
        retained: list[dict[str, object]] = []
        used = 0
        for item in reversed(self._messages[-count:]):
            size = len(json.dumps(item, ensure_ascii=False))
            if used + size > budget:
                break
            retained.append(deepcopy(item))
            used += size
        return list(reversed(retained))

    def _conversation_history(self) -> list[ModelMessage]:
        """Compact whole accepted exchanges without retaining stale instructions/tool payloads.

        The original server transcript is the source, not a model-generated summary. Native
        capabilities reload their policy when needed; no partial tool call/result is retained.
        """
        history: list[ModelMessage] = []
        transcript = self._transcript_tail(64, 200_000)
        if len(transcript) < len(self._messages):
            self._conversation_truncated = True
        for item in transcript:
            text = item.get("text")
            if item.get("kind") in ("quiz", "feedback"):
                text = "Canonical course presentation: " + json.dumps(item, ensure_ascii=False)
            if not isinstance(text, str) or not text.strip():
                continue
            if item["role"] == "learner":
                history.append(ModelRequest(parts=[UserPromptPart(text)]))
            elif history and isinstance(history[-1], ModelResponse):
                history[-1].parts = [*history[-1].parts, TextPart(text)]
            else:
                if not history:
                    history.append(
                        ModelRequest(
                            parts=[
                                UserPromptPart(
                                    "Previously presented course dialogue follows. "
                                    "This is historical context, "
                                    "not a new learner message or choice."
                                )
                            ]
                        )
                    )
                history.append(ModelResponse(parts=[TextPart(text)]))
        return history

    async def review(self, kind: str, explanation: str) -> dict[str, object]:
        async with self._locked():
            async with asyncio.timeout(self.tutor.turn_timeout):
                await self._reviews.review(kind, explanation)
            return await self._io(self._state)

    async def acknowledge_review(self, review_id: str) -> dict[str, object]:
        async with self._locked():
            await self._reviews.acknowledge(review_id)
            return await self._io(self._state)

    async def confirm_review(
        self, review_id: str, objective_id: str | None = None
    ) -> dict[str, object]:
        async with self._locked():
            await self._reviews.confirm(review_id, objective_id)
            return await self._io(self._state)
