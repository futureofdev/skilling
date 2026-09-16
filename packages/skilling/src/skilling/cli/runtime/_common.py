"""Shared plumbing for the JSON transition verbs.

Every verb in ``cli/runtime`` loads exactly one :class:`Session`, applies at most one write,
and prints exactly one JSON object. This module is the part every verb shares: how a session
is assembled, how a refusal is reported, and where the runtime-private scratch that has to
survive between one process and the next actually lives.

The CLI is the sole write authority: a store never computes anything, so every derived write
— position after a transition, the completion write set — happens in ``delivery`` or here,
never inside a store backend.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import NamedTuple, NoReturn

import typer
import yaml

from ...conformance import validate_course
from ...course import Course, CourseLoadError, Record, ResolvedLesson
from ...delivery import load_or_create
from ...store import Conflict, FileProgressStore, ProgressStore, StatePathError, open_store
from ...workspace import resolve_course_location, resolve_state_root

SCRATCH_NAME = "scratch.yaml"


class ExitCode(IntEnum):
    """Process exit codes every runtime verb uses. Stable — a driving pack switches on these."""

    OK = 0
    ERROR = 1
    INVALID = 2
    CONFLICT = 3
    ILLEGAL = 4
    VERSION_MISMATCH = 5


@dataclass(frozen=True)
class Scratch:
    """Runtime-private working state, beside the record but never part of it.

    ``wrong_count`` and ``returning_to_quiz`` mirror the same-named ``LessonState`` fields.
    The machine treats them as in-memory scratch because the interactive walker never leaves
    a lesson mid-quiz without them still in a live Python object. The session verbs *do*
    leave between every single input — one process per transition — so this file is where
    that residual has to live instead, or a wrong answer would be forgotten the instant the
    process that recorded it exited.

    ``last_key``/``last_result`` back ``advance --key``'s idempotent replay: the exact
    envelope a key already produced, so a retried call can be answered without re-applying it.
    """

    wrong_count: int = 0
    returning_to_quiz: bool = False
    last_key: str | None = None
    last_result: dict[str, object] | None = None


class Session(NamedTuple):
    course: Course
    lesson: ResolvedLesson
    store: ProgressStore
    record: Record
    revision: str | None
    scratch: Scratch


def now_override() -> datetime | None:
    """``SKILLING_NOW`` (ISO 8601) when set — deterministic runs for the byte-equivalence
    gate and tests. Documented test-only surface; no production caller should ever set it."""
    raw = os.environ.get("SKILLING_NOW")
    return datetime.fromisoformat(raw) if raw else None


def emit(payload: dict[str, object]) -> None:
    """The one and only way any runtime verb writes to stdout: one JSON object, one line."""
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")


def fail(code: ExitCode, error: str, message: str) -> NoReturn:
    emit({"ok": False, "error": {"code": error, "message": message}})
    raise typer.Exit(code)


def load_scratch(store: ProgressStore, course_id: str) -> Scratch:
    if not isinstance(store, FileProgressStore):
        raise TypeError("runtime-private scratch currently needs the file store backend")
    data = yaml.safe_load(store.read_runtime_state(course_id)) or {}
    return Scratch(
        wrong_count=data.get("wrong_count", 0),
        returning_to_quiz=data.get("returning_to_quiz", False),
        last_key=data.get("last_key"),
        last_result=data.get("last_result"),
    )


def save_scratch(session: Session, scratch: Scratch, expected_record_revision: str) -> None:
    """Reject delayed scratch writes after another record mutation or completion reset.

    General record-plus-scratch interruption remains a separate contract (#64); these
    adapters serialize each operation without pretending the two calls are one transaction.
    """
    if not isinstance(session.store, FileProgressStore):
        raise TypeError("runtime-private scratch currently needs the file store backend")
    payload = yaml.safe_dump(
        {
            "wrong_count": scratch.wrong_count,
            "returning_to_quiz": scratch.returning_to_quiz,
            "last_key": scratch.last_key,
            "last_result": scratch.last_result,
        },
        sort_keys=False,
    ).encode("utf-8")
    try:
        session.store.write_runtime_state(session.course.id, payload, expected_record_revision)
    except Conflict as exc:
        fail(ExitCode.CONFLICT, "conflict", str(exc))


def open_session(course_ref: str, state: Path | None, learner: str) -> Session:
    """Load everything one verb needs: the course, the record (created fresh if absent), the
    lesson the record currently points at, and the scratch beside it.

    ``course_ref`` is a directory first — today's behaviour, unchanged — and only when that
    is not a directory is it tried as a course id inside the enclosing workspace
    (``resolve_course_location``). An unusable workspace entry earns ``course-not-found``;
    an explicit directory with an invalid manifest still earns ``course-invalid``.

    Creates a record on first use and finishes any prepared completion before returning.
    Otherwise reads preserve existing state; verbs perform their own writes through CAS.
    """
    course_path = Path(course_ref)
    if not course_path.is_dir():
        located = resolve_course_location(course_ref)
        if located is None:
            fail(
                ExitCode.INVALID,
                "course-not-found",
                f"{course_ref!r} is not a course directory, and no enclosing workspace has "
                "a usable course by that id. Restore or re-add its workspace content, or pass "
                "an explicit course directory.",
            )
        course_path = located

    try:
        report = validate_course(course_path)
        if not report.ok:
            first = report.errors[0]
            fail(
                ExitCode.INVALID,
                "course-invalid",
                f"{first.code}: {first.message} ({len(report.errors)} error(s))",
            )
        course = Course.load(course_path)
    except CourseLoadError as exc:
        fail(ExitCode.INVALID, "course-invalid", f"{exc.code}: {exc.message}")
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        fail(ExitCode.INVALID, "course-invalid", f"Cannot read course: {type(exc).__name__}")

    try:
        state_root = resolve_state_root(state)
        store = open_store(str(state_root))
        if isinstance(store, FileProgressStore):
            store.ensure_course_paths(course.id)
        record, revision = load_or_create(store, course, learner)
        scratch = load_scratch(store, course.id)
    except StatePathError as exc:
        fail(ExitCode.INVALID, "state-invalid", str(exc))

    if record.course_version != course.version:
        fail(
            ExitCode.VERSION_MISMATCH,
            "version-mismatch",
            f"the record was started against {course.id} {record.course_version}, but "
            f"{course.id} on disk is {course.version}",
        )

    lesson = course.lesson_at(record.position.coordinate)
    if lesson is None:
        fail(
            ExitCode.INVALID,
            "position-invalid",
            f"{record.position.coordinate} is not a lesson in {course.id}",
        )

    return Session(course, lesson, store, record, revision, scratch)
