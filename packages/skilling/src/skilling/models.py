"""Typed models of every YAML surface in the Skilling format.

These mirror spec/course-format.md (what authors write) and spec/runtime.md (what a
runtime persists). Anything derived — counts, boundaries, percentages — is deliberately
absent: it belongs on the resolved course in ``loader.py``, computed rather than stored.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
COORDINATE_RE = re.compile(r"^\d+\.\d+$")

Slug = Annotated[str, Field(min_length=1, max_length=64)]


class Strict(BaseModel):
    """Unknown fields are a mistake, not an extension point — at 1.0 there are no
    optional additions to guess at, so a stray key is a typo worth reporting."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- manifest


class LessonEntry(Strict):
    number: int = Field(ge=1)
    slug: Slug
    title: str = Field(min_length=1)
    homework: bool = False

    @field_validator("slug")
    @classmethod
    def _kebab(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("must be lowercase kebab-case")
        return v


class PhaseEntry(Strict):
    number: int = Field(ge=0)
    slug: Slug
    name: str = Field(min_length=1)
    lessons: list[LessonEntry] = Field(min_length=1)

    @field_validator("slug")
    @classmethod
    def _kebab(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("must be lowercase kebab-case")
        return v


class Skill(Strict):
    id: Slug
    name: str = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def _kebab(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("must be lowercase kebab-case")
        return v


class Tutor(Strict):
    """Guidance for how a tutor speaks. Nothing behavioural depends on it."""

    persona: str | None = None
    tone: list[str] = Field(default_factory=list)


class Manifest(Strict):
    spec_version: str
    id: str
    title: str = Field(min_length=1)
    version: str
    description: str | None = None
    language: str = "en"
    license: str | None = None
    authors: list[str] = Field(default_factory=list)
    tutor: Tutor | None = None
    phases: list[PhaseEntry] = Field(min_length=1)
    skills: list[Skill] = Field(default_factory=list)

    @property
    def badge_ids(self) -> set[str]:
        return {s.id for s in self.skills}


# ------------------------------------------------------------------- lesson frontmatter


class SectionAbsence(Strict):
    """A declared absence. ``intent`` is lenient here so the validator can report a
    missing reason with its own code rather than a generic parse failure."""

    status: Literal["none"]
    intent: str = ""


SectionDecl = Literal["present"] | SectionAbsence

OPTIONAL_SECTION_KEYS: tuple[str, ...] = ("key_terms", "exercise", "next_up")


class LessonFrontmatter(Strict):
    title: str = Field(min_length=1)
    phase: int = Field(ge=0)
    lesson: int = Field(ge=1)
    duration_minutes: int | None = Field(default=None, ge=1)
    prerequisites: list[str] = Field(default_factory=list)
    skills_unlocked: list[str] = Field(default_factory=list)
    sections: dict[str, SectionDecl] = Field(default_factory=dict)

    @field_validator("prerequisites")
    @classmethod
    def _coordinates(cls, v: list[str]) -> list[str]:
        for item in v:
            if not COORDINATE_RE.match(item):
                raise ValueError(f"{item!r} is not a '{{phase}}.{{lesson}}' coordinate")
        return v

    def declaration(self, key: str) -> SectionDecl | None:
        return self.sections.get(key)

    def declares_present(self, key: str) -> bool:
        return self.sections.get(key) == "present"


# ------------------------------------------------------------------------ progress record


class Position(Strict):
    phase: int = Field(ge=0)
    lesson: int = Field(ge=1)
    beat: str | None = None

    @property
    def coordinate(self) -> str:
        return f"{self.phase}.{self.lesson}"


class Record(Strict):
    learner_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    course_version: str
    spec_version: str
    position: Position
    completed: list[str] = Field(default_factory=list)
    skills_unlocked: list[str] = Field(default_factory=list)
    started_at: date
    last_activity: date
    timezone: str = "UTC"
    streak_days: int = Field(default=0, ge=0)

    @field_validator("completed")
    @classmethod
    def _coordinates(cls, v: list[str]) -> list[str]:
        for item in v:
            if not COORDINATE_RE.match(item):
                raise ValueError(f"{item!r} is not a '{{phase}}.{{lesson}}' coordinate")
        return v

    def has_completed(self, coordinate: str) -> bool:
        return coordinate in self.completed


class CompletionEntry(Strict):
    coordinate: str
    title: str
    completed_at: datetime
    course_version: str


# ------------------------------------------------------------------------------ homework

Verdict = Literal["met", "partial", "not-yet"]


class Requirement(Strict):
    text: str = Field(min_length=1)
    verdict: Verdict | None = None
    reason: str = ""


class Assignment(Strict):
    coordinate: str
    title: str = Field(min_length=1)
    objective: str
    requirements: list[Requirement] = Field(min_length=1)
    stretch_goals: list[Requirement] = Field(default_factory=list)
    submission: str
    unlocked_at: datetime


class HomeworkSlot(Assignment):
    """The mailbox. An absent ``active.yaml`` means the slot is empty, so there is no
    'empty' variant of this model — absence is represented by absence."""

    queued: list[Assignment] = Field(default_factory=list)


class HomeworkArchiveEntry(Strict):
    coordinate: str
    title: str = Field(min_length=1)
    requirements: list[Requirement]
    stretch_goals: list[Requirement] = Field(default_factory=list)
    submitted_at: datetime


def is_semver(value: str) -> bool:
    return bool(SEMVER_RE.match(value))


def is_course_id(value: str) -> bool:
    return 1 <= len(value) <= 64 and bool(SLUG_RE.match(value))
