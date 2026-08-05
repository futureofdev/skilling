"""Typed models of every YAML surface in the Skilling format.

These mirror spec/course-format.md (what authors write) and spec/runtime.md (what a
runtime persists). Anything derived — counts, boundaries, percentages — is deliberately
absent: it belongs on the resolved course in ``loader.py``, computed rather than stored.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._clock import today_in
from .errors import SPEC_MAJOR, SPEC_MINOR

if TYPE_CHECKING:
    from .loader import Course

SPEC_VERSION = f"{SPEC_MAJOR}.{SPEC_MINOR}"

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
    highlight: str | None = None
    """Since 1.1. One clause completing "this learner just…", used at ceremony."""

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


class Brand(Strict):
    """Facts a tutor may not invent. Since 1.1.

    Every field is optional, and a runtime composing ceremony copy may state nothing that is
    not here — the whole point is that a model asked for a share post will otherwise guess a
    handle, confidently and wrongly.
    """

    product: str | None = None
    url: str | None = None
    mention: str | None = None
    handles: dict[str, str] = Field(default_factory=dict)
    hashtags: list[str] = Field(default_factory=list)
    """Stored bare; the runtime adds the '#', so an author cannot ship '##WebDev'."""


class Ceremony(Strict):
    """Since 1.1. Facts plus optional literal templates."""

    brand: Brand | None = None
    phase_completed_template: str | None = None
    course_completed_template: str | None = None

    def templates(self) -> dict[str, str]:
        found = {}
        if self.phase_completed_template:
            found["phase_completed_template"] = self.phase_completed_template
        if self.course_completed_template:
            found["course_completed_template"] = self.course_completed_template
        return found


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
    ceremony: Ceremony | None = None
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


ObjectiveKind = Literal["knowledge", "practice"]


class Capability(StrEnum):
    """What a runtime can actually observe. Since 1.2.

    Which capabilities a runtime has decides which objective kinds it may settle — a chat
    tutor cannot see a filesystem, so it must leave every ``practice`` objective alone
    however confident the learner sounds.
    """

    CONVERSE = "converse"
    """Can hold a conversation and judge an explanation. Settles ``knowledge``."""

    OBSERVE = "observe"
    """Can inspect the learner's filesystem, repository or command output. Settles
    ``practice``."""

    ASSESS = "assess"
    """Can judge a submitted work product against requirements. Settles homework."""


#: Which capability settles which kind, and the evidence it produces.
SETTLES: dict[ObjectiveKind, tuple[Capability, str]] = {
    "knowledge": (Capability.CONVERSE, "explained"),
    "practice": (Capability.OBSERVE, "observed"),
}


class Objective(Strict):
    """An addressable learning objective. Since 1.1; ``kind`` and ``verify`` since 1.2.

    A lesson's contract, given an id so a tutor can target remediation at the one a wrong
    answer implicates instead of re-presenting the whole concept.
    """

    id: Slug
    kind: ObjectiveKind
    """What would count as evidence, and therefore which runtimes can settle it at all."""

    text: str = Field(min_length=1)
    about: list[int] = Field(default_factory=list)
    """Quiz questions that touch this objective. Steers remediation; **not** evidence — a
    quiz settles nothing, because one four-option question is guessed right a quarter of the
    time and none can establish that software is installed."""

    verify: str | None = None
    """For a ``practice`` objective: what success looks like, for a runtime that can look.
    Prose rather than a command, because an agent with shell access is good at working out
    *how*, and `node --version` is wrong behind a version manager."""

    check: str | None = None
    """An optional literal command. A *proposal*: a runtime may decline it, must run it
    through its host's permission model, and must never run it silently."""

    @field_validator("id")
    @classmethod
    def _kebab(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("must be lowercase kebab-case")
        return v

    @property
    def observable(self) -> bool:
        """Can a runtime that can look actually settle this from outside?"""
        return self.kind == "practice" and bool(self.verify)

    def settled_by(self) -> tuple[Capability, str] | None:
        return SETTLES.get(self.kind)


class LessonFrontmatter(Strict):
    title: str = Field(min_length=1)
    phase: int = Field(ge=0)
    lesson: int = Field(ge=1)
    duration_minutes: int | None = Field(default=None, ge=1)
    prerequisites: list[str] = Field(default_factory=list)
    skills_unlocked: list[str] = Field(default_factory=list)
    objectives: list[Objective] = Field(default_factory=list)
    sections: dict[str, SectionDecl] = Field(default_factory=dict)

    def objective(self, objective_id: str) -> Objective | None:
        for candidate in self.objectives:
            if candidate.id == objective_id:
                return candidate
        return None

    def objectives_for_question(self, number: int) -> list[Objective]:
        """Objectives a question touches — for remediation, never for evidence."""
        return [o for o in self.objectives if number in o.about]

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


#: How an objective was demonstrated. There is no "quiz": a quiz settles nothing.
Evidence = Literal["explained", "observed", "homework"]


class ObjectiveMet(Strict):
    """A capability claim, with how it was demonstrated. Since 1.1."""

    id: str = Field(min_length=1)
    at: date
    evidence: Evidence


class Telemetry(Strict):
    """Since 1.1. ``opt_in`` is ternary: None means never asked, so ask once."""

    opt_in: bool | None = None
    anonymous_id: str = ""
    """Sink-assigned, write-once. Never derived from ``learner_id``."""


class Record(Strict):
    learner_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    course_version: str
    spec_version: str
    position: Position
    completed: list[str] = Field(default_factory=list)
    skills_unlocked: list[str] = Field(default_factory=list)
    objectives_met: list[ObjectiveMet] = Field(default_factory=list)
    started_at: date
    last_activity: date
    timezone: str = "UTC"
    streak_days: int = Field(default=0, ge=0)
    telemetry: Telemetry = Field(default_factory=Telemetry)

    @classmethod
    def new(
        cls,
        course: Course,
        learner_id: str,
        *,
        zone: str = "UTC",
        now: datetime | None = None,
    ) -> Record:
        today = today_in(zone, now)
        first = course.first_lesson
        return cls(
            learner_id=learner_id,
            course_id=course.id,
            course_version=course.version,
            spec_version=SPEC_VERSION,
            position=Position(phase=first.phase, lesson=first.number),
            completed=[],
            skills_unlocked=[],
            started_at=today,
            last_activity=today,
            timezone=zone,
            streak_days=0,
        )

    def has_met(self, objective_id: str) -> bool:
        return any(o.id == objective_id for o in self.objectives_met)

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
