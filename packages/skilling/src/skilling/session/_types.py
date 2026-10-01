"""Copied, immutable teaching views; no course, parser, store or action handle."""

from __future__ import annotations

from dataclasses import dataclass

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
