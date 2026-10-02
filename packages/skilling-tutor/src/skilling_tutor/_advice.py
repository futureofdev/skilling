"""Wire output boundaries convert to frozen, identity-complete informal advice."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ._context import AdviceIdentity, HomeworkAdviceContext, ObjectiveAdviceContext
from ._errors import TutorError, TutorErrorKind


class AdviceVerdict(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    NOT_YET = "not-yet"


@dataclass(frozen=True)
class AdviceItem:
    id: str
    verdict: AdviceVerdict
    reason: str


class _AdviceItemWire(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=256)
    verdict: AdviceVerdict
    reason: str = Field(min_length=1, max_length=2_000)


class _ObjectiveAdviceWire(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objectives: list[_AdviceItemWire] = Field(max_length=100)


class _HomeworkAdviceWire(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirements: list[_AdviceItemWire] = Field(max_length=100)
    stretch_goals: list[_AdviceItemWire] = Field(max_length=100)


def _complete(
    values: list[_AdviceItemWire], identities: tuple[AdviceIdentity, ...]
) -> tuple[AdviceItem, ...]:
    ids = [value.id for value in values]
    if len(ids) != len(set(ids)) or set(ids) != {identity.id for identity in identities}:
        raise TutorError(
            TutorErrorKind.ADVICE, "Advice must cover every supplied identity exactly once"
        )
    if any(not value.reason.strip() for value in values):
        raise TutorError(TutorErrorKind.ADVICE, "Advice reasons must be meaningful text")
    by_id = {value.id: value for value in values}
    return tuple(
        AdviceItem(identity.id, by_id[identity.id].verdict, by_id[identity.id].reason)
        for identity in identities
    )


@dataclass(frozen=True)
class ObjectiveAdvice:
    objectives: tuple[AdviceItem, ...]
    evidence_digest: str
    revision: str

    @classmethod
    def from_output(
        cls, output: _ObjectiveAdviceWire, *, context: ObjectiveAdviceContext
    ) -> ObjectiveAdvice:
        return cls(
            _complete(output.objectives, context.objectives),
            context.evidence.digest,
            context.revision,
        )

    @classmethod
    def output_type(cls) -> type[_ObjectiveAdviceWire]:
        """Supported adapter wire type for a producer's tool/native/prompted output mode."""
        return _ObjectiveAdviceWire


@dataclass(frozen=True)
class HomeworkAdvice:
    requirements: tuple[AdviceItem, ...]
    stretch_goals: tuple[AdviceItem, ...]
    evidence_digest: str
    revision: str

    @classmethod
    def from_output(
        cls, output: _HomeworkAdviceWire, *, context: HomeworkAdviceContext
    ) -> HomeworkAdvice:
        return cls(
            _complete(output.requirements, context.requirements),
            _complete(output.stretch_goals, context.stretch_goals),
            context.evidence.digest,
            context.revision,
        )

    @classmethod
    def output_type(cls) -> type[_HomeworkAdviceWire]:
        return _HomeworkAdviceWire
