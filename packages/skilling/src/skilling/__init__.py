"""Skilling — the reference implementation of the Skilling course format.

An LLM-free core: typed models of the format, a loader that derives everything structural,
a validator with a stable error-code catalogue, the delivery loop as a pure state machine,
and a progress store. Nothing here imports an agent framework or needs an API key, so a CI
job can validate a course and a reporting job can read a record without either.
"""

from .errors import SPEC_MAJOR, SPEC_MINOR, Code, Severity
from .loader import Course, CourseLoadError, ResolvedLesson, ResolvedPhase, load_course
from .machine import Beat, IllegalTransition, Input, LessonShape, LessonState, advance, start
from .models import (
    Assignment,
    CompletionEntry,
    HomeworkArchiveEntry,
    HomeworkSlot,
    LessonFrontmatter,
    Manifest,
    Position,
    Record,
    Requirement,
)
from .store import Conflict, FileProgressStore, ProgressStore
from .validate import Finding, Report, validate_course

SPEC_VERSION = f"{SPEC_MAJOR}.{SPEC_MINOR}"
__version__ = "0.3.0"
"""Bumped whenever the specification version this package implements moves — a build that
reports the wrong spec version is worse than no version at all, and a cached wheel will
happily do exactly that."""

__all__ = [
    "SPEC_MAJOR",
    "SPEC_MINOR",
    "SPEC_VERSION",
    "Assignment",
    "Beat",
    "Code",
    "CompletionEntry",
    "Conflict",
    "Course",
    "CourseLoadError",
    "FileProgressStore",
    "Finding",
    "HomeworkArchiveEntry",
    "HomeworkSlot",
    "IllegalTransition",
    "Input",
    "LessonFrontmatter",
    "LessonShape",
    "LessonState",
    "Manifest",
    "Position",
    "ProgressStore",
    "Record",
    "Report",
    "Requirement",
    "ResolvedLesson",
    "ResolvedPhase",
    "Severity",
    "__version__",
    "advance",
    "load_course",
    "start",
    "validate_course",
]
