"""Copied, immutable teaching views; no course, parser, store or action handle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from ..delivery import Beat, Input


@dataclass(frozen=True)
class CourseView:
    id: str
    version: str
    title: str


@dataclass(frozen=True)
class PositionView:
    phase: int
    lesson: int
    beat: str | None
    question_index: int | None

    @property
    def coordinate(self) -> str:
        return f"{self.phase}.{self.lesson}"


@dataclass(frozen=True)
class TutorView:
    persona: str | None
    tone: tuple[str, ...]


@dataclass(frozen=True)
class OptionView:
    label: str
    text: str


@dataclass(frozen=True)
class QuestionView:
    number: int
    text: str
    options: tuple[OptionView, ...]


@dataclass(frozen=True)
class BeatView:
    name: Beat
    coordinate: str | None = None
    title: str | None = None
    body: str | None = None
    objectives: tuple[str, ...] | None = None
    key_terms: str | None = None
    question: QuestionView | None = None
    offer_revisit: bool | None = None
    objective: str | None = None

    def content(self) -> dict[str, object]:
        """A fresh JSON-safe copy of this beat's open teaching content."""
        result: dict[str, object] = {}
        for name, value in (
            ("coordinate", self.coordinate),
            ("title", self.title),
            ("body", self.body),
            ("key_terms", self.key_terms),
            ("offer_revisit", self.offer_revisit),
            ("objective", self.objective),
        ):
            if value is not None:
                result[name] = value
        if self.objectives is not None:
            result["objectives"] = list(self.objectives)
        if self.question is not None:
            result.update(
                {
                    "number": self.question.number,
                    "text": self.question.text,
                    "options": [{"label": o.label, "text": o.text} for o in self.question.options],
                }
            )
        return result


@dataclass(frozen=True)
class SessionSnapshot:
    course: CourseView
    learner_id: str
    position: PositionView
    revision: str | None
    beat: BeatView
    legal_inputs: tuple[Input, ...]
    completed_count: int
    lesson_count: int
    tutor: TutorView | None = None


@dataclass(frozen=True)
class QuizFeedback:
    correct: bool
    reason: str
    offered: bool
    objectives: tuple[str, ...]


@dataclass(frozen=True)
class ActionResult:
    snapshot: SessionSnapshot
    replayed: bool


@dataclass(frozen=True)
class CompletionResult:
    snapshot: SessionSnapshot
    already_completed: bool
    badges_awarded: tuple[str, ...]
    phase_completed: int | None
    homework_placed: bool
    homework_queued: bool


@dataclass(frozen=True)
class CeremonyView:
    snapshot: SessionSnapshot
    coordinate: str
    phase_number: int | None
    phase_name: str | None
    phase_highlight: str | None
    share_text: str | None
    course_complete: bool
    showcase: str | None


class RequirementVerdict(StrEnum):
    MET = "met"
    PARTIAL = "partial"
    NOT_YET = "not-yet"


class ObjectiveType(StrEnum):
    KNOWLEDGE = "knowledge"
    PRACTICE = "practice"


class EvidenceKind(StrEnum):
    EXPLAINED = "explained"
    OBSERVED = "observed"
    HOMEWORK = "homework"


@dataclass(frozen=True)
class RequirementView:
    text: str
    verdict: RequirementVerdict | None
    reason: str


@dataclass(frozen=True)
class AssignmentView:
    coordinate: str
    title: str
    objective: str
    requirements: tuple[RequirementView, ...]
    stretch_goals: tuple[RequirementView, ...]
    submission: str
    unlocked_at: datetime
    queued: tuple[AssignmentView, ...] = ()


@dataclass(frozen=True)
class HomeworkCheck:
    course: CourseView
    active: AssignmentView | None
    revision: str | None
    submission_token: str | None


@dataclass(frozen=True)
class HomeworkArchiveView:
    course: CourseView
    coordinate: str
    title: str
    requirements: tuple[RequirementView, ...]
    stretch_goals: tuple[RequirementView, ...]
    submitted_at: datetime


@dataclass(frozen=True)
class ObjectiveView:
    id: str
    kind: ObjectiveType
    text: str
    verify: str | None
    check: str | None
    settleable_now: bool


@dataclass(frozen=True)
class ProvenanceView:
    checked: str
    verify: str
    attested_by: str


@dataclass(frozen=True)
class ObjectiveResult:
    course: CourseView
    id: str
    evidence: EvidenceKind
    at: date
    provenance: ProvenanceView | None
    newly_met: bool
    revision: str | None


@dataclass(frozen=True)
class ProgressView:
    course: CourseView
    position: PositionView
    completed: tuple[str, ...]
    completed_count: int
    lesson_count: int
    percent_complete: float
    skills_unlocked: tuple[str, ...]
    streak_days: int
    started_at: date
    last_activity: date
    revision: str | None


@dataclass(frozen=True)
class TelemetryView:
    course: CourseView
    opt_in: bool | None
    revision: str | None
    anonymous_id: str | None = None


@dataclass(frozen=True)
class ArtifactView:
    path: str
    title: str
    coordinate: str
    added_at: datetime


@dataclass(frozen=True)
class ArtifactResult:
    course: CourseView
    artifact: ArtifactView
    revision: str | None
