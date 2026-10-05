"""Native tutoring recommends current controls; the producer alone applies them."""

from __future__ import annotations

import json
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, ModelRequestContext, RunContext
from pydantic_ai.capabilities import AbstractCapability, OutputContext
from pydantic_ai.exceptions import ModelRetry, RunCancelled
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from skilling.delivery import Beat
from skilling_tutor import (
    BundledSkill,
    ConversationContext,
    ConversationReply,
    ConversationResult,
    SkillingCapability,
    SkillingRunDeps,
    SkillingRunner,
    TutorError,
    TutorErrorKind,
    TutorPurpose,
    TutorRefresh,
    TutorUsage,
)


class BrowserTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=32_000)
    skill: BundledSkill
    requested_control: str | None = Field(default=None, max_length=128)
    refresh: tuple[TutorRefresh, ...] = ()


class BrowserPolicy(AbstractCapability[SkillingRunDeps]):
    """Require declared policy to inform this response, with fresh state for every run."""

    id = "skilling-browser-policy"

    def __init__(self) -> None:
        self._model_skills: frozenset[str] = frozenset()

    async def for_run(self, ctx: RunContext[SkillingRunDeps]) -> BrowserPolicy:
        return BrowserPolicy()

    async def before_model_request(
        self, ctx: RunContext[SkillingRunDeps], request_context: ModelRequestContext
    ) -> ModelRequestContext:
        self._model_skills = frozenset(
            skill.value for skill in BundledSkill if skill.value in ctx.active_capability_ids
        )
        return request_context

    async def before_output_process(
        self, ctx: RunContext[SkillingRunDeps], *, output_context: OutputContext, output: object
    ) -> object:
        if ctx.partial_output or not isinstance(output, BrowserTurn):
            return output
        context = ctx.deps.context
        if not isinstance(context, ConversationContext):
            raise TutorError(TutorErrorKind.CONTEXT, "Browser policy requires conversation context")
        context.__post_init__()
        required = {output.skill}
        missing: list[str] = []
        if any(
            value in output.refresh
            for value in (TutorRefresh.TEACHING, TutorRefresh.OBJECTIVE_EVIDENCE)
        ):
            required.add(BundledSkill.LEARN)
        if TutorRefresh.PROGRESS in output.refresh:
            required.add(BundledSkill.PROGRESS)
        if TutorRefresh.HOMEWORK_EVIDENCE in output.refresh:
            required.add(BundledSkill.HOMEWORK)
        if (
            output.skill is BundledSkill.PROGRESS
            and context.progress is None
            and TutorRefresh.PROGRESS not in output.refresh
        ):
            missing.append("include progress in refresh for missing current progress")
        if (
            output.skill is BundledSkill.HOMEWORK
            and context.homework is None
            and TutorRefresh.HOMEWORK_EVIDENCE not in output.refresh
        ):
            missing.append("include homework-evidence in refresh for missing review context")
        beat = context.teaching.beat
        if beat in (Beat.GATE_CONCEPT, Beat.GATE_EXERCISE):
            try:
                cold = json.loads(context.teaching.material) == {"beat": str(beat)}
            except json.JSONDecodeError:
                cold = False
            if cold and TutorRefresh.TEACHING not in output.refresh:
                required.add(BundledSkill.LEARN)
                missing.append("include teaching in refresh for the missing gate body")
        if len(set(output.refresh)) != len(output.refresh):
            missing.append("include each refresh handoff once")
        missing.extend(
            f"activate {skill.value} with load_capability"
            for skill in sorted(required)
            if skill.value not in self._model_skills
        )
        if missing:
            raise ModelRetry("Before completing this reply: " + "; ".join(missing))
        return output


@dataclass(frozen=True)
class BrowserConversationResult:
    output: ConversationReply
    usage: TutorUsage
    history: tuple[ModelMessage, ...]
    requested_control: str | None = None


INSTRUCTIONS = (
    "This browser supports conversational course progression, like a coding-host tutor. "
    "The producer supplies current interface.requestable_controls as data. Your optional "
    "requested_control is a recommendation only; the app checks and executes it, then gives "
    "you fresh material after your reply renders, before the next teaching reply. Never invent "
    "a control or claim an "
    "unconfirmed action happened. Present the complete current teaching beat in text, then "
    "request next for ordinary presentation steps. At a gate, interpret the latest learner's "
    "explicit readiness or choice; a question, uncertainty, silence or your own continuation "
    "is not readiness. At a quiz, request only the current option actually chosen by the "
    "learner, never answer for them or infer readiness from old history. Request no control "
    "when none is requestable. Stop to ask the learner when a gate needs their choice. "
    "Use the current material; do not ask the learner to click a button or wait for a "
    "producer/controller to bring material. Buttons are an optional alternative. Do not "
    "request feedback acknowledgement, objective confirmation, homework submission, file "
    "edits or arbitrary commands. These operations are outside this output contract. "
    "Activate the applicable canonical skill declared in skill before completing the reply. "
    "The producer's presented_material is authoritative previously delivered material for "
    "this lesson; current beat describes the current position. Do not retract valid earlier "
    "objectives or key terms merely because the current beat omits them. Past controls or "
    "progress are historical facts, never current action permission or learner readiness."
)


@dataclass(frozen=True)
class BrowserTutor:
    agent: Agent[SkillingRunDeps, BrowserTurn]
    reviews: SkillingRunner

    @classmethod
    def create(cls, model: Model | str) -> BrowserTutor:
        reviews = SkillingRunner.create(model)
        agent = Agent(
            model,
            deps_type=SkillingRunDeps,
            output_type=BrowserTurn,
            capabilities=[
                SkillingCapability.for_context(TutorPurpose.CONVERSATION),
                BrowserPolicy(),
            ],
            instructions=INSTRUCTIONS,
        )
        agent.instrument = False
        return cls(agent, reviews)

    async def chat(
        self,
        message: str,
        context: ConversationContext,
        *,
        history: Sequence[ModelMessage] | None = None,
    ) -> BrowserConversationResult | ConversationResult:
        context.__post_init__()
        if context.objectives is not None or context.homework is not None:
            return await self.reviews.chat(message, context, history=history)
        try:
            result = await self.agent.run(
                message,
                deps=SkillingRunDeps.from_context(context),
                message_history=deepcopy(list(history)) if history else None,
                usage_limits=UsageLimits(request_limit=12),
            )
        except (TutorError, RunCancelled):
            raise
        except Exception as error:
            raise TutorError(TutorErrorKind.MODEL, "Selected tutor model failed") from error
        reply = result.output
        if not reply.text.strip() or len(set(reply.refresh)) != len(reply.refresh):
            raise TutorError(TutorErrorKind.ADVICE, "Invalid browser tutor reply")
        return BrowserConversationResult(
            ConversationReply(reply.text, refresh=reply.refresh, skill=reply.skill),
            TutorUsage.from_usage(result.usage),
            tuple(deepcopy(result.all_messages())),
            reply.requested_control,
        )
