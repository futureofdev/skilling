"""Skilling — the reference implementation of the Skilling course format.

An LLM-free core: typed models of the format, a loader that derives everything structural,
a validator with a stable error-code catalogue, the delivery loop as a pure state machine,
and a progress store. Nothing here imports an agent framework or needs an API key, so a CI
job can validate a course and a reporting job can read a record without either.
"""

from .conformance import SPEC_MAJOR, SPEC_MINOR, Code, Finding, Report, Severity, validate_course
from .course import (
    Assignment,
    CompletionEntry,
    Course,
    CourseLoadError,
    HomeworkArchiveEntry,
    HomeworkSlot,
    LessonFrontmatter,
    Manifest,
    Position,
    Record,
    Requirement,
    ResolvedLesson,
    ResolvedPhase,
)
from .delivery import Beat, IllegalTransition, Input, LessonShape, LessonState, advance
from .store import Conflict, FileProgressStore, ProgressStore

SPEC_VERSION = f"{SPEC_MAJOR}.{SPEC_MINOR}"
__version__ = "0.5.0"
"""The independently released reference-package version.

``SPEC_VERSION`` reports the separate normative format version implemented by this package.
"""

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
    "validate_course",
]
