"""Complete-turn results keep framework messages and usage separate from domain output."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import RunUsage

from ._advice import HomeworkAdvice, ObjectiveAdvice, _HomeworkAdviceWire, _ObjectiveAdviceWire
from ._context import ConversationContext
from ._errors import TutorError, TutorErrorKind

OutputT = TypeVar("OutputT")


class TutorStatus(StrEnum):
    COMPLETE = "complete"


@dataclass(frozen=True)
class TutorUsage:
    requests: int
    input_tokens: int
    output_tokens: int
    tool_calls: int

    @classmethod
    def from_usage(cls, usage: RunUsage) -> TutorUsage:
        return cls(usage.requests, usage.input_tokens, usage.output_tokens, usage.tool_calls)


@dataclass(frozen=True)
class TutorResult(Generic[OutputT]):
    output: OutputT
    usage: TutorUsage
    new_messages: tuple[ModelMessage, ...]
    status: TutorStatus = TutorStatus.COMPLETE


class _ConversationReplyWire(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=32_000)
    objectives: _ObjectiveAdviceWire | None = None
    homework: _HomeworkAdviceWire | None = None


@dataclass(frozen=True)
class ConversationReply:
    """Learner-facing conversation and optional informal feedback, never action authority."""

    text: str
    objectives: ObjectiveAdvice | None = None
    homework: HomeworkAdvice | None = None

    @classmethod
    def output_type(cls) -> type[_ConversationReplyWire]:
        return _ConversationReplyWire

    @classmethod
    def from_output(
        cls, output: _ConversationReplyWire, *, context: ConversationContext
    ) -> ConversationReply:
        if not output.text.strip():
            raise TutorError(TutorErrorKind.ADVICE, "Conversation reply must be meaningful text")
        context.__post_init__()
        objectives = None
        homework = None
        if output.objectives is not None:
            if context.objectives is None:
                raise TutorError(
                    TutorErrorKind.ADVICE, "Objective feedback needs actual scoped evidence"
                )
            objectives = ObjectiveAdvice.from_output(output.objectives, context=context.objectives)
        if output.homework is not None:
            if context.homework is None:
                raise TutorError(
                    TutorErrorKind.ADVICE, "Homework feedback needs actual scoped evidence"
                )
            homework = HomeworkAdvice.from_output(output.homework, context=context.homework)
        return cls(output.text, objectives, homework)


@dataclass(frozen=True)
class ConversationResult:
    output: ConversationReply
    usage: TutorUsage
    history: tuple[ModelMessage, ...]
    status: TutorStatus = TutorStatus.COMPLETE
