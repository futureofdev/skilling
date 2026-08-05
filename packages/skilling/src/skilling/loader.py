"""Loading a course directory into a resolved, queryable object.

Everything structural is *derived* here and nowhere else: paths from numbers and slugs,
counts from the phase list, boundaries from lesson positions. Nothing in this module
reads a count that an author wrote down, because the format forbids authoring one.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from .errors import Code
from .lesson import format_validation_error
from .models import Manifest, PhaseEntry

MANIFEST_NAME = "course.yaml"
PHASES_DIR = "phases"
ASSETS_DIR = "assets"
OVERVIEW_NAME = "overview.md"


class CourseLoadError(Exception):
    """A course could not be loaded at all — as distinct from a course that loaded and
    then failed checks. Only the manifest can fail this way."""

    def __init__(self, code: Code, message: str, *, path: Path | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path


@dataclass(frozen=True)
class ResolvedLesson:
    phase: int
    number: int
    slug: str
    title: str
    homework: bool
    path: Path

    @property
    def coordinate(self) -> str:
        return f"{self.phase}.{self.number}"


@dataclass(frozen=True)
class ResolvedPhase:
    number: int
    slug: str
    name: str
    directory: Path
    lessons: tuple[ResolvedLesson, ...]
    highlight: str | None = None
    """Since 1.1. One clause completing "this learner just…", used at ceremony."""

    @property
    def overview_path(self) -> Path | None:
        candidate = self.directory / OVERVIEW_NAME
        return candidate if candidate.is_file() else None

    @property
    def lesson_count(self) -> int:
        return len(self.lessons)


@dataclass(frozen=True)
class Course:
    root: Path
    manifest: Manifest
    phases: tuple[ResolvedPhase, ...]

    # ------------------------------------------------------------------ derived values

    @classmethod
    def load(cls, root: Path) -> Course:
        return resolve(root, load_manifest(root))

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def lesson_count(self) -> int:
        return sum(p.lesson_count for p in self.phases)

    @property
    def phase_count(self) -> int:
        return len(self.phases)

    def lessons(self) -> Iterator[ResolvedLesson]:
        for phase in self.phases:
            yield from phase.lessons

    @property
    def coordinates(self) -> list[str]:
        return [lesson.coordinate for lesson in self.lessons()]

    def lesson_at(self, coordinate: str) -> ResolvedLesson | None:
        for lesson in self.lessons():
            if lesson.coordinate == coordinate:
                return lesson
        return None

    def phase_at(self, number: int) -> ResolvedPhase | None:
        for phase in self.phases:
            if phase.number == number:
                return phase
        return None

    def phase_of(self, coordinate: str) -> ResolvedPhase | None:
        lesson = self.lesson_at(coordinate)
        return self.phase_at(lesson.phase) if lesson else None

    @property
    def first_lesson(self) -> ResolvedLesson:
        return self.phases[0].lessons[0]

    def next_lesson(self, coordinate: str) -> ResolvedLesson | None:
        seq = list(self.lessons())
        for i, lesson in enumerate(seq):
            if lesson.coordinate == coordinate:
                return seq[i + 1] if i + 1 < len(seq) else None
        return None

    def is_last_in_phase(self, coordinate: str) -> bool:
        phase = self.phase_of(coordinate)
        return bool(phase and phase.lessons[-1].coordinate == coordinate)

    def position_in_course(self, coordinate: str) -> int | None:
        """1-indexed position across the whole course, or None if unknown."""
        for i, lesson in enumerate(self.lessons(), start=1):
            if lesson.coordinate == coordinate:
                return i
        return None

    def completed_count(self, completed: list[str]) -> int:
        known = set(self.coordinates)
        return len(known & set(completed))

    def remaining_count(self, completed: list[str]) -> int:
        return self.lesson_count - self.completed_count(completed)

    def percent_complete(self, completed: list[str]) -> float:
        if not self.lesson_count:
            return 0.0
        return round(100 * self.completed_count(completed) / self.lesson_count, 1)

    def phase_is_complete(self, phase_number: int, completed: list[str]) -> bool:
        phase = self.phase_at(phase_number)
        if not phase:
            return False
        return all(lesson.coordinate in completed for lesson in phase.lessons)

    @property
    def assets_dir(self) -> Path:
        return self.root / ASSETS_DIR


# --------------------------------------------------------------------------- derivation


def phase_dirname(phase: PhaseEntry | ResolvedPhase) -> str:
    return f"phase-{phase.number}-{phase.slug}"


def lesson_filename(number: int, slug: str) -> str:
    return f"lesson-{number:02d}-{slug}.md"


def lesson_path(root: Path, phase: PhaseEntry | ResolvedPhase, number: int, slug: str) -> Path:
    return root / PHASES_DIR / phase_dirname(phase) / lesson_filename(number, slug)


def discover_lesson_files(root: Path) -> list[Path]:
    """Every ``lesson-*.md`` under ``phases/``, whether the manifest knows about it or not."""
    phases = root / PHASES_DIR
    if not phases.is_dir():
        return []
    return sorted(p for p in phases.glob("*/lesson-*.md") if p.is_file())


# ------------------------------------------------------------------------------ loading


def load_manifest(root: Path) -> Manifest:
    path = root / MANIFEST_NAME
    if not path.is_file():
        raise CourseLoadError(
            Code.MANIFEST_MISSING,
            f"No {MANIFEST_NAME} at {root}. A course is a directory containing one.",
            path=path,
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        first = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        raise CourseLoadError(
            Code.MANIFEST_UNPARSEABLE, f"{MANIFEST_NAME} is not valid YAML: {first}", path=path
        ) from exc

    if not isinstance(data, dict):
        raise CourseLoadError(
            Code.MANIFEST_INVALID, f"{MANIFEST_NAME} must be a mapping at its top level", path=path
        )

    try:
        return Manifest.model_validate(data)
    except ValidationError as exc:
        raise CourseLoadError(
            Code.MANIFEST_INVALID, format_validation_error(exc), path=path
        ) from exc


def resolve(root: Path, manifest: Manifest) -> Course:
    """Build the resolved course. Does not check that lesson files exist — that is a
    validation finding, not a load failure, so a broken course can still be reported on."""
    phases: list[ResolvedPhase] = []
    for phase in manifest.phases:
        directory = root / PHASES_DIR / phase_dirname(phase)
        lessons = tuple(
            ResolvedLesson(
                phase=phase.number,
                number=entry.number,
                slug=entry.slug,
                title=entry.title,
                homework=entry.homework,
                path=lesson_path(root, phase, entry.number, entry.slug),
            )
            for entry in phase.lessons
        )
        phases.append(
            ResolvedPhase(
                number=phase.number,
                slug=phase.slug,
                name=phase.name,
                directory=directory,
                lessons=lessons,
                highlight=phase.highlight,
            )
        )
    return Course(root=root, manifest=manifest, phases=tuple(phases))
