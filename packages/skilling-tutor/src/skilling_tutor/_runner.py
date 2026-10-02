"""Three purpose-specific Agents using the same native safe capability."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import TypeVar

from pydantic_ai import Agent
from pydantic_ai.exceptions import RunCancelled, UsageLimitExceeded, UserError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.run import AgentRunResult
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from ._advice import HomeworkAdvice, ObjectiveAdvice, _HomeworkAdviceWire, _ObjectiveAdviceWire
from ._capability import SkillingCapability, SkillingRunDeps
from ._context import (
    HomeworkAdviceContext,
    NarrationContext,
    ObjectiveAdviceContext,
    SafeContext,
    TutorPurpose,
    validate_context,
)
from ._errors import TutorError, TutorErrorKind
from ._narration import TutorResult, TutorUsage

OutputT = TypeVar("OutputT")


@dataclass(frozen=True)
class SkillingRunner:
    _narration: Agent[SkillingRunDeps, str]
    _objectives: Agent[SkillingRunDeps, _ObjectiveAdviceWire]
    _homework: Agent[SkillingRunDeps, _HomeworkAdviceWire]
    _usage_limits: UsageLimits

    @classmethod
    def create(
        cls,
        model: Model | str,
        *,
        model_settings: ModelSettings | None = None,
        usage_limits: UsageLimits | None = None,
    ) -> SkillingRunner:
        try:
            narration = Agent(
                model,
                deps_type=SkillingRunDeps,
                capabilities=[SkillingCapability.for_context(TutorPurpose.NARRATION)],
                model_settings=deepcopy(model_settings),
            )
            objectives = Agent(
                model,
                deps_type=SkillingRunDeps,
                output_type=ObjectiveAdvice.output_type(),
                capabilities=[SkillingCapability.for_context(TutorPurpose.OBJECTIVE_ADVICE)],
                model_settings=deepcopy(model_settings),
            )
            homework = Agent(
                model,
                deps_type=SkillingRunDeps,
                output_type=HomeworkAdvice.output_type(),
                capabilities=[SkillingCapability.for_context(TutorPurpose.HOMEWORK_ADVICE)],
                model_settings=deepcopy(model_settings),
            )
        except (ImportError, ValueError, UserError) as error:
            raise TutorError(
                TutorErrorKind.CONFIGURATION,
                "Unable to configure selected model. Install its pydantic-ai-slim provider extra "
                "and configure credentials on the trusted producer.",
            ) from error
        narration.instrument = False
        objectives.instrument = False
        homework.instrument = False
        return cls(
            narration,
            objectives,
            homework,
            deepcopy(usage_limits) if usage_limits else UsageLimits(request_limit=8),
        )

    async def _run(
        self,
        agent: Agent[SkillingRunDeps, OutputT],
        context: SafeContext,
        purpose: TutorPurpose,
        history: Sequence[ModelMessage] | None,
    ) -> AgentRunResult[OutputT]:
        validate_context(context, purpose)
        try:
            return await agent.run(
                "Complete the requested tutor turn using the safe context.",
                deps=SkillingRunDeps.from_context(context),
                message_history=deepcopy(list(history)) if history is not None else None,
                usage_limits=deepcopy(self._usage_limits),
            )
        except (TutorError, RunCancelled):
            raise
        except UsageLimitExceeded as error:
            raise TutorError(TutorErrorKind.USAGE, "Tutor usage limit exceeded") from error
        except Exception as error:
            raise TutorError(
                TutorErrorKind.MODEL, "Selected tutor model failed; no state action implied"
            ) from error

    async def narrate(
        self, context: NarrationContext, *, history: Sequence[ModelMessage] | None = None
    ) -> TutorResult[str]:
        result = await self._run(self._narration, context, TutorPurpose.NARRATION, history)
        return TutorResult(
            result.output,
            TutorUsage.from_usage(result.usage),
            tuple(deepcopy(result.new_messages())),
        )

    async def advise_objectives(
        self, context: ObjectiveAdviceContext, *, history: Sequence[ModelMessage] | None = None
    ) -> TutorResult[ObjectiveAdvice]:
        result = await self._run(self._objectives, context, TutorPurpose.OBJECTIVE_ADVICE, history)
        return TutorResult(
            ObjectiveAdvice.from_output(result.output, context=context),
            TutorUsage.from_usage(result.usage),
            tuple(deepcopy(result.new_messages())),
        )

    async def advise_homework(
        self, context: HomeworkAdviceContext, *, history: Sequence[ModelMessage] | None = None
    ) -> TutorResult[HomeworkAdvice]:
        result = await self._run(self._homework, context, TutorPurpose.HOMEWORK_ADVICE, history)
        return TutorResult(
            HomeworkAdvice.from_output(result.output, context=context),
            TutorUsage.from_usage(result.usage),
            tuple(deepcopy(result.new_messages())),
        )
