"""Bounded immutable copies; controller objects and mutation identities never cross here."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from skilling.delivery import Beat, Input
from skilling.session import (
    HomeworkCheck,
    ObjectiveType,
    ObjectiveView,
    PresentationBeat,
    SessionSnapshot,
)

from ._errors import TutorError, TutorErrorKind


class TutorPurpose(StrEnum):
    CONVERSATION = "conversation"
    NARRATION = "narration"
    OBJECTIVE_ADVICE = "objective-advice"
    HOMEWORK_ADVICE = "homework-advice"


def _text(value: str, *, limit: int = 32_000, empty: bool = False) -> None:
    if type(value) is not str or len(value) > limit or (not empty and not value.strip()):
        raise TutorError(TutorErrorKind.CONTEXT, "Expected bounded nonempty text")


@dataclass(frozen=True)
class LearnerEvidence:
    """Actual producer-selected evidence, never a file handle or a submission token."""

    text: str
    digest: str

    def __post_init__(self) -> None:
        _text(self.text)
        if self.digest != hashlib.sha256(self.text.encode()).hexdigest():
            raise TutorError(TutorErrorKind.CONTEXT, "Evidence digest does not match its text")

    @classmethod
    def from_text(cls, text: str) -> LearnerEvidence:
        _text(text)
        return cls(text, hashlib.sha256(text.encode()).hexdigest())


@dataclass(frozen=True)
class NarrationContext:
    course_title: str
    coordinate: str
    persona: str | None
    tone: tuple[str, ...]
    material: str
    beat: Beat | PresentationBeat | None = None
    legal_inputs: tuple[Input, ...] | None = None

    def __post_init__(self) -> None:
        for value in (self.course_title, self.coordinate, self.material):
            _text(value, limit=100_000)
        if self.persona is not None:
            _text(self.persona)
        if type(self.tone) is not tuple or len(self.tone) > 32:
            raise TutorError(TutorErrorKind.CONTEXT, "Tone must be an immutable bounded tuple")
        for tone in self.tone:
            _text(tone, limit=1_000)
        if self.beat is not None and type(self.beat) not in (Beat, PresentationBeat):
            raise TutorError(TutorErrorKind.CONTEXT, "Expected current delivery beat")
        if self.legal_inputs is not None and (
            type(self.legal_inputs) is not tuple
            or len(self.legal_inputs) > len(Input)
            or any(type(choice) is not Input for choice in self.legal_inputs)
            or len(set(self.legal_inputs)) != len(self.legal_inputs)
        ):
            raise TutorError(TutorErrorKind.CONTEXT, "Expected immutable current legal inputs")

    @classmethod
    def from_snapshot(cls, snapshot: SessionSnapshot) -> NarrationContext:
        material = snapshot.beat.content()
        material["beat"] = snapshot.beat.name.value
        feedback = snapshot.pending_feedback
        if feedback is not None:
            material["feedback"] = {
                "question_number": feedback.question_number,
                "label": feedback.label,
                "correct": feedback.correct,
                "reason": feedback.reason,
                "offered": feedback.offered,
                "objectives": list(feedback.objectives),
            }
        tutor = snapshot.tutor
        return cls(
            snapshot.course.title,
            snapshot.position.coordinate,
            tutor.persona if tutor else None,
            tuple(tutor.tone) if tutor else (),
            json.dumps(material, ensure_ascii=False, sort_keys=True),
            snapshot.beat.name,
            tuple(snapshot.legal_inputs),
        )


@dataclass(frozen=True)
class AdviceIdentity:
    id: str
    text: str
    kind: ObjectiveType | None = None
    verify: str | None = None
    check: str | None = None

    def __post_init__(self) -> None:
        _text(self.id, limit=256)
        _text(self.text)
        if self.kind is not None and type(self.kind) is not ObjectiveType:
            raise TutorError(TutorErrorKind.CONTEXT, "Expected objective kind")
        for criterion in (self.verify, self.check):
            if criterion is not None:
                _text(criterion)


def _identities(values: tuple[AdviceIdentity, ...], *, allow_empty: bool = False) -> None:
    if type(values) is not tuple or len(values) > 100 or (not values and not allow_empty):
        raise TutorError(TutorErrorKind.CONTEXT, "Expected bounded immutable identities")
    if any(type(value) is not AdviceIdentity for value in values):
        raise TutorError(TutorErrorKind.CONTEXT, "Expected safe advice identities")
    for value in values:
        value.__post_init__()
    if len({value.id for value in values}) != len(values):
        raise TutorError(TutorErrorKind.CONTEXT, "Duplicate advice identities")


@dataclass(frozen=True)
class ObjectiveAdviceContext:
    objectives: tuple[AdviceIdentity, ...]
    evidence: LearnerEvidence
    revision: str

    def __post_init__(self) -> None:
        _identities(self.objectives)
        _text(self.revision, limit=256)
        if type(self.evidence) is not LearnerEvidence:
            raise TutorError(TutorErrorKind.CONTEXT, "Expected safe learner evidence")
        self.evidence.__post_init__()

    @classmethod
    def from_objectives(
        cls, objectives: tuple[ObjectiveView, ...], *, evidence: LearnerEvidence, revision: str
    ) -> ObjectiveAdviceContext:
        return cls(
            tuple(AdviceIdentity(o.id, o.text, o.kind, o.verify, o.check) for o in objectives),
            evidence,
            revision,
        )


@dataclass(frozen=True)
class HomeworkAdviceContext:
    title: str
    objective: str
    requirements: tuple[AdviceIdentity, ...]
    stretch_goals: tuple[AdviceIdentity, ...]
    evidence: LearnerEvidence
    revision: str

    def __post_init__(self) -> None:
        _text(self.title)
        _text(self.objective)
        _text(self.revision, limit=256)
        _identities(self.requirements)
        _identities(self.stretch_goals, allow_empty=True)
        if {x.id for x in self.requirements} & {x.id for x in self.stretch_goals}:
            raise TutorError(TutorErrorKind.CONTEXT, "Required and stretch identities overlap")
        if type(self.evidence) is not LearnerEvidence:
            raise TutorError(TutorErrorKind.CONTEXT, "Expected safe learner evidence")
        self.evidence.__post_init__()

    @classmethod
    def from_check(
        cls, check: HomeworkCheck, *, evidence: LearnerEvidence
    ) -> HomeworkAdviceContext:
        assignment = check.active
        if assignment is None or check.revision is None:
            raise TutorError(TutorErrorKind.CONTEXT, "Homework advice needs an active assignment")
        return cls(
            assignment.title,
            assignment.objective,
            tuple(
                AdviceIdentity(f"{assignment.coordinate}/required/{i}", value.text)
                for i, value in enumerate(assignment.requirements, 1)
            ),
            tuple(
                AdviceIdentity(f"{assignment.coordinate}/stretch/{i}", value.text)
                for i, value in enumerate(assignment.stretch_goals, 1)
            ),
            evidence,
            check.revision,
        )


@dataclass(frozen=True)
class ProgressContext:
    """Current public counts only; no record, learner identity or future material."""

    completed_count: int
    lesson_count: int

    def __post_init__(self) -> None:
        if (
            type(self.completed_count) is not int
            or type(self.lesson_count) is not int
            or self.lesson_count < 1
            or not 0 <= self.completed_count <= self.lesson_count
        ):
            raise TutorError(TutorErrorKind.CONTEXT, "Expected valid current progress counts")

    @classmethod
    def from_snapshot(cls, snapshot: SessionSnapshot) -> ProgressContext:
        return cls(snapshot.completed_count, snapshot.lesson_count)


@dataclass(frozen=True)
class ConversationContext:
    """Fresh safe facts and optional actual review evidence for one conversational turn."""

    teaching: NarrationContext
    revision: str | None
    progress: ProgressContext | None = None
    objectives: ObjectiveAdviceContext | None = None
    homework: HomeworkAdviceContext | None = None
    homework_revision: str | None = None

    def __post_init__(self) -> None:
        if type(self.teaching) is not NarrationContext:
            raise TutorError(TutorErrorKind.CONTEXT, "Expected safe current teaching context")
        self.teaching.__post_init__()
        if self.revision is not None:
            _text(self.revision, limit=256)
        if self.progress is not None:
            if type(self.progress) is not ProgressContext:
                raise TutorError(TutorErrorKind.CONTEXT, "Expected safe current progress")
            self.progress.__post_init__()
        if self.objectives is not None:
            if type(self.objectives) is not ObjectiveAdviceContext:
                raise TutorError(TutorErrorKind.CONTEXT, "Expected safe objective advice context")
            self.objectives.__post_init__()
            if self.revision is None or self.objectives.revision != self.revision:
                raise TutorError(
                    TutorErrorKind.CONTEXT, "Objective advice needs the current record revision"
                )
        if self.homework_revision is not None:
            _text(self.homework_revision, limit=256)
        if self.homework is not None:
            if type(self.homework) is not HomeworkAdviceContext:
                raise TutorError(TutorErrorKind.CONTEXT, "Expected safe homework advice context")
            self.homework.__post_init__()
            if self.homework_revision is None or self.homework.revision != self.homework_revision:
                raise TutorError(
                    TutorErrorKind.CONTEXT, "Homework advice needs the current slot revision"
                )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: SessionSnapshot,
        *,
        objectives: ObjectiveAdviceContext | None = None,
        homework: HomeworkAdviceContext | None = None,
        homework_check: HomeworkCheck | None = None,
    ) -> ConversationContext:
        slot_revision = None
        if homework_check is not None:
            if (
                type(homework_check) is not HomeworkCheck
                or homework_check.course != snapshot.course
            ):
                raise TutorError(
                    TutorErrorKind.CONTEXT, "Expected a current homework check for this course"
                )
            slot_revision = homework_check.revision
        if homework is not None:
            if type(homework) is not HomeworkAdviceContext:
                raise TutorError(TutorErrorKind.CONTEXT, "Expected safe homework advice context")
            homework.__post_init__()
            if homework_check is None:
                raise TutorError(
                    TutorErrorKind.CONTEXT, "Homework context needs a fresh public homework check"
                )
            expected = HomeworkAdviceContext.from_check(homework_check, evidence=homework.evidence)
            if homework != expected:
                raise TutorError(
                    TutorErrorKind.CONTEXT, "Homework context does not match the current slot"
                )
        return cls(
            NarrationContext.from_snapshot(snapshot),
            snapshot.revision,
            ProgressContext.from_snapshot(snapshot),
            objectives,
            homework,
            slot_revision,
        )


SafeContext = (
    NarrationContext | ObjectiveAdviceContext | HomeworkAdviceContext | ConversationContext
)


def validate_context(context: SafeContext, purpose: TutorPurpose) -> SafeContext:
    expected = {
        TutorPurpose.CONVERSATION: ConversationContext,
        TutorPurpose.NARRATION: NarrationContext,
        TutorPurpose.OBJECTIVE_ADVICE: ObjectiveAdviceContext,
        TutorPurpose.HOMEWORK_ADVICE: HomeworkAdviceContext,
    }[purpose]
    if type(context) is not expected:
        raise TutorError(TutorErrorKind.CONTEXT, "Context does not match the tutor purpose")
    context.__post_init__()
    return context
