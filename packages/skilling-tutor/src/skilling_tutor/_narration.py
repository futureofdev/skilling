"""Complete-turn results keep framework messages and usage separate from domain output."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import RunUsage

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
