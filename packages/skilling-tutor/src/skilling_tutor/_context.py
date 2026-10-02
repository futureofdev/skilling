"""Bounded immutable copies; controller objects and mutation identities never cross here."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from skilling.session import HomeworkCheck, ObjectiveType, ObjectiveView, SessionSnapshot

from ._errors import TutorError, TutorErrorKind


class TutorPurpose(StrEnum):
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
    persona: str
    tone: tuple[str, ...]
    material: str

    def __post_init__(self) -> None:
        for value in (self.course_title, self.coordinate, self.persona, self.material):
            _text(value, limit=100_000)
        if type(self.tone) is not tuple or len(self.tone) > 32:
            raise TutorError(TutorErrorKind.CONTEXT, "Tone must be an immutable bounded tuple")
        for tone in self.tone:
            _text(tone, limit=1_000)

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
            tutor.persona if tutor and tutor.persona else "A patient, clear tutor",
            tuple(tutor.tone) if tutor else (),
            json.dumps(material, ensure_ascii=False, sort_keys=True),
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


SafeContext = NarrationContext | ObjectiveAdviceContext | HomeworkAdviceContext


def validate_context(context: SafeContext, purpose: TutorPurpose) -> SafeContext:
    expected = {
        TutorPurpose.NARRATION: NarrationContext,
        TutorPurpose.OBJECTIVE_ADVICE: ObjectiveAdviceContext,
        TutorPurpose.HOMEWORK_ADVICE: HomeworkAdviceContext,
    }[purpose]
    if type(context) is not expected:
        raise TutorError(TutorErrorKind.CONTEXT, "Context does not match the tutor purpose")
    context.__post_init__()
    return context
