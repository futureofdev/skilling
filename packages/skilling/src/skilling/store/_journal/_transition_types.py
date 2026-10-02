"""Version-one transition boundaries remain readable without invented outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBytes, field_validator, model_validator

from ...course import is_semver


class TransitionVerb(StrEnum):
    ADVANCE = "advance"
    ANSWER = "answer"


@dataclass(frozen=True)
class TransitionIdentity:
    learner_id: str
    course_id: str
    course_version: str
    coordinate: str
    verb: TransitionVerb
    input: str
    key: str | None


class Boundary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("version", mode="before", check_fields=False)
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("journal version must be an integer")
        return value


class Stream(Boundary):
    learner_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    course_version: str

    @field_validator("course_version")
    @classmethod
    def valid_version(cls, value: str) -> str:
        if not is_semver(value):
            raise ValueError("invalid transition course version")
        return value


class Identity(Stream):
    coordinate: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    verb: Literal["advance", "answer"]
    input: str = Field(min_length=1)
    key: str | None = Field(min_length=1)

    @field_validator("input")
    @classmethod
    def valid_input(cls, value: str) -> str:
        if value not in {
            "next",
            "go-deeper",
            "proceed",
            "hint",
            "attempted",
            "answer-correct",
            "answer-wrong",
            "continue",
            "revisit-concept",
            "a",
            "b",
            "c",
            "d",
        }:
            raise ValueError("invalid transition input")
        return value

    @model_validator(mode="after")
    def valid_operation(self) -> Identity:
        if (self.verb == "answer") != (self.input in {"a", "b", "c", "d"}):
            raise ValueError("transition verb/input mismatch")
        if self.verb == "answer" and self.key is not None:
            raise ValueError("quiz answers are unkeyed")
        return self

    def value(self) -> TransitionIdentity:
        return TransitionIdentity(
            self.learner_id,
            self.course_id,
            self.course_version,
            self.coordinate,
            TransitionVerb(self.verb),
            self.input,
            self.key,
        )


class Reservation(Stream):
    version: Literal[1]
    kind: Literal["reserved"]
    key: str = Field(min_length=1)


class Receipt(Boundary):
    version: Literal[1]
    kind: Literal["receipt"]
    identity: Identity


class Prepared(Boundary):
    version: Literal[1]
    kind: Literal["prepared"]
    identity: Identity
    record_before: StrictBytes
    record_after: StrictBytes
    scratch_before: StrictBytes | None
    scratch_after: StrictBytes
    receipt_path: str | None
    receipt: Receipt | None


class Committed(Boundary):
    version: Literal[1]
    kind: Literal["committed"]
    identity: Identity
