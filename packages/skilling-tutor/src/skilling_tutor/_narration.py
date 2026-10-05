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
from ._skills import BundledSkill

OutputT = TypeVar("OutputT")


class TutorStatus(StrEnum):
    COMPLETE = "complete"


class TutorRefresh(StrEnum):
    """Missing read-only context; never an instruction to execute a controller action."""

    TEACHING = "teaching"
    PROGRESS = "progress"
    OBJECTIVE_EVIDENCE = "objective-evidence"
    HOMEWORK_EVIDENCE = "homework-evidence"


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
    skill: BundledSkill = Field(
        description="Canonical policy for this reply: learn for teaching/objectives, progress for "
        "course progress, homework for homework. Activate this native skill before replying."
    )
    objectives: _ObjectiveAdviceWire | None = None
    homework: _HomeworkAdviceWire | None = None
    refresh: list[TutorRefresh] = Field(
        default_factory=list,
        max_length=len(TutorRefresh),
        description="Required read-only handoffs when requested current data is missing: teaching "
        "for a cold gate without its body, progress for unknown progress, objective-evidence or "
        "homework-evidence for missing review criteria/work. Never request tokens or actions.",
    )


@dataclass(frozen=True)
class ConversationReply:
    """Learner-facing conversation and optional informal feedback, never action authority."""

    text: str
    objectives: ObjectiveAdvice | None = None
    homework: HomeworkAdvice | None = None
    refresh: tuple[TutorRefresh, ...] = ()
    skill: BundledSkill = BundledSkill.LEARN

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
        if len(set(output.refresh)) != len(output.refresh):
            raise TutorError(TutorErrorKind.ADVICE, "Duplicate context refresh requests")
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
        return cls(output.text, objectives, homework, tuple(output.refresh), output.skill)


@dataclass(frozen=True)
class ConversationResult:
    output: ConversationReply
    usage: TutorUsage
    history: tuple[ModelMessage, ...]
    status: TutorStatus = TutorStatus.COMPLETE
