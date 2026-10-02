"""Version-two file action boundaries and copied original outcomes; no authored schema."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import Field, StrictBool, StrictBytes, StrictInt, model_validator

from ._transition_types import Boundary, Receipt, Reservation, Stream


class ActionOrigin(StrEnum):
    LEARNER = "learner-control"
    PRESENTATION = "runtime-presentation"


class ActionOperation(StrEnum):
    ADVANCE = "advance"
    ANSWER = "answer"
    ACKNOWLEDGE = "feedback-acknowledgement"


@dataclass(frozen=True)
class OutcomePosition:
    phase: int
    lesson: int
    beat: str | None
    question_index: int | None


@dataclass(frozen=True)
class AdvanceOutcome:
    input: str
    position: OutcomePosition


@dataclass(frozen=True)
class QuizAnswerOutcome:
    question_number: int
    label: str
    correct: bool
    reason: str
    offered: bool
    objectives: tuple[str, ...]


@dataclass(frozen=True)
class LegacyOutcomeUnavailable:
    """A version-one receipt contains no original outcome; never reconstruct one."""


OriginalOutcome = AdvanceOutcome | QuizAnswerOutcome


@dataclass(frozen=True)
class ActionIdentity:
    learner_id: str
    course_id: str
    course_version: str
    coordinate: str
    verb: ActionOperation
    input: str
    key: str | None
    origin: ActionOrigin
    expected_revision: str
    question_number: int | None


@dataclass(frozen=True, repr=False)
class FeedbackRef:
    """Opaque controller-only receipt reference, not an answer key or model context."""

    _learner_id: str
    _course_id: str
    _course_version: str
    _answer_key: str
    _receipt_digest: str


@dataclass(frozen=True)
class PendingFeedback:
    feedback_id: FeedbackRef
    outcome: QuizAnswerOutcome
    revision: str


class AcknowledgementStatus(StrEnum):
    PRESENTED = "presented"
    ALREADY_PRESENTED = "already-presented"
    NO_PENDING = "no-pending"


@dataclass(frozen=True)
class FeedbackAcknowledgement:
    status: AcknowledgementStatus
    revision: str | None


@dataclass(frozen=True)
class FeedbackPointer:
    origin_course_version: str
    answer_key: str
    receipt_digest: str
    version: int = 1


class PendingReference(Boundary):
    version: Literal[1]
    origin_course_version: str
    answer_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def origin(self) -> PendingReference:
        from ...course import is_semver

        if not is_semver(self.origin_course_version):
            raise ValueError("invalid pending feedback origin version")
        return self

    def value(self) -> FeedbackPointer:
        return FeedbackPointer(self.origin_course_version, self.answer_key, self.receipt_digest)


class PositionBoundary(Boundary):
    phase: StrictInt = Field(ge=0)
    lesson: StrictInt = Field(ge=1)
    beat: str | None
    question_index: StrictInt | None = Field(ge=0)

    def value(self) -> OutcomePosition:
        return OutcomePosition(**self.model_dump())


class AdvanceBoundary(Boundary):
    kind: Literal["advance"]
    input: str
    position: PositionBoundary

    def value(self) -> AdvanceOutcome:
        return AdvanceOutcome(self.input, self.position.value())


class AnswerBoundary(Boundary):
    kind: Literal["answer"]
    question_number: StrictInt = Field(ge=1)
    label: str = Field(pattern=r"^[a-d]$")
    correct: StrictBool
    reason: str
    offered: StrictBool
    objectives: list[str]

    def value(self) -> QuizAnswerOutcome:
        return QuizAnswerOutcome(
            self.question_number,
            self.label,
            self.correct,
            self.reason,
            self.offered,
            tuple(self.objectives),
        )


class ActionBoundary(Stream):
    coordinate: str = Field(pattern=r"^(0|[1-9][0-9]*)\.[1-9][0-9]*$")
    verb: Literal["advance", "answer", "feedback-acknowledgement"]
    input: str = Field(min_length=1)
    key: str | None = Field(pattern=r"^[a-f0-9]{64}$")
    origin: Literal["learner-control", "runtime-presentation"]
    expected_revision: str = Field(pattern=r"^[a-f0-9]{16}$")
    question_number: StrictInt | None = Field(ge=1)

    @model_validator(mode="after")
    def operation(self) -> ActionBoundary:
        if self.verb == "feedback-acknowledgement":
            if self.origin != "runtime-presentation" or self.key is not None:
                raise ValueError("acknowledgement requires runtime origin and no learner key")
            if len(self.input) != 64 or any(c not in "abcdef0123456789" for c in self.input):
                raise ValueError("invalid acknowledgement receipt digest")
        else:
            if self.key is None:
                raise ValueError("keyed action requires learner origin and event identity")
            if self.verb == "answer":
                if (
                    self.origin != "learner-control"
                    or self.question_number is None
                    or self.input not in {"a", "b", "c", "d"}
                ):
                    raise ValueError("answer requires displayed question and normalized label")
            elif self.question_number is not None or self.input not in {
                "next",
                "go-deeper",
                "proceed",
                "hint",
                "attempted",
                "answer-correct",
                "answer-wrong",
                "continue",
                "revisit-concept",
            }:
                raise ValueError("invalid advance identity")
            if (
                self.verb == "advance"
                and self.origin == "runtime-presentation"
                and self.input != "next"
            ):
                raise ValueError("ordinary presentation acknowledges one non-gate beat with next")
        return self

    def value(self) -> ActionIdentity:
        return ActionIdentity(
            self.learner_id,
            self.course_id,
            self.course_version,
            self.coordinate,
            ActionOperation(self.verb),
            self.input,
            self.key,
            ActionOrigin(self.origin),
            self.expected_revision,
            self.question_number,
        )


class ActionReceipt(Boundary):
    version: Literal[2]
    kind: Literal["receipt"]
    identity: ActionBoundary
    outcome: AdvanceBoundary | AnswerBoundary = Field(discriminator="kind")

    @model_validator(mode="after")
    def binding(self) -> ActionReceipt:
        identity, outcome = self.identity, self.outcome
        if identity.verb != outcome.kind:
            raise ValueError("outcome operation mismatch")
        if isinstance(outcome, AdvanceBoundary):
            if outcome.input != identity.input:
                raise ValueError("advance outcome input mismatch")
        elif (outcome.question_number, outcome.label) != (
            identity.question_number,
            identity.input,
        ):
            raise ValueError("answer outcome question/label mismatch")
        return self


def key_digest(event_id: str) -> str:
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event id must be a nonempty controller string")
    return hashlib.sha256(event_id.encode("utf-8")).hexdigest()


class Scratch(Boundary):
    wrong_count: StrictInt = Field(default=0, ge=0)
    returning_to_quiz: StrictBool = False
    last_key: str | None = None
    last_result: dict[str, object] | None = None
    pending_feedback: PendingReference | None = None
    presented_feedback: PendingReference | None = None


class ActionReservation(Stream):
    version: Literal[2]
    kind: Literal["reserved"]
    key: str = Field(pattern=r"^[a-f0-9]{64}$")


class PreparedAction(Boundary):
    version: Literal[2]
    kind: Literal["prepared"]
    identity: ActionBoundary
    record_before: StrictBytes
    record_after: StrictBytes
    scratch_before: StrictBytes | None
    scratch_after: StrictBytes
    receipt_path: str | None
    receipt: ActionReceipt | None


class CommittedAction(Boundary):
    version: Literal[2]
    kind: Literal["committed"]
    identity: ActionBoundary


def parse_receipt(data: object) -> Receipt | ActionReceipt | Reservation | ActionReservation:

    if isinstance(data, dict) and data.get("version") == 2:
        return (
            ActionReservation.model_validate(data)
            if data.get("kind") == "reserved"
            else ActionReceipt.model_validate(data)
        )
    return (
        Reservation.model_validate(data)
        if isinstance(data, dict) and data.get("kind") == "reserved"
        else Receipt.model_validate(data)
    )


def outcome_boundary(outcome: OriginalOutcome) -> AdvanceBoundary | AnswerBoundary:
    from dataclasses import asdict

    if isinstance(outcome, AdvanceOutcome):
        return AdvanceBoundary.model_validate({"kind": "advance", **asdict(outcome)})
    data = asdict(outcome)
    data["objectives"] = list(outcome.objectives)
    return AnswerBoundary.model_validate({"kind": "answer", **data})


def pending_pointer(identity: ActionIdentity, outcome: QuizAnswerOutcome) -> FeedbackPointer:
    from dataclasses import asdict

    receipt = ActionReceipt(
        version=2,
        kind="receipt",
        identity=ActionBoundary.model_validate(asdict(identity)),
        outcome=outcome_boundary(outcome),
    )
    return FeedbackPointer(identity.course_version, identity.key or "", receipt_digest(receipt))


def receipt_digest(receipt: ActionReceipt) -> str:
    import yaml

    raw = yaml.safe_dump(
        receipt.model_dump(), sort_keys=False, allow_unicode=True, width=100
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
