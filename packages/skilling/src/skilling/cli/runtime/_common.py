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
from ...delivery import (
    ChronologyInvalid,
    CoordinateRequired,
    completed_coordinate,
    load_or_create,
)
from ...store import (
    Conflict,
    FileProgressStore,
    IdempotencyKeyConflict,
    ProgressStore,
    RecoveryRequired,
    StatePathError,
    TransitionCommit,
    TransitionIdentity,
    TransitionResult,
    open_store,
)
from ...workspace import resolve_course_location, resolve_state_root, workspace_read

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

    ``last_key``/``last_result`` are read only for compatibility with older state. New keys
    live in immutable transition receipts; replay renders a current coherent snapshot.
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
    scratch_bytes: bytes


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
    return parse_scratch(store.read_runtime_state(course_id))


def parse_scratch(raw: bytes) -> Scratch:
    data = yaml.safe_load(raw) or {}
    return Scratch(
        wrong_count=data.get("wrong_count", 0),
        returning_to_quiz=data.get("returning_to_quiz", False),
        last_key=data.get("last_key"),
        last_result=data.get("last_result"),
    )


def save_scratch(session: Session, scratch: Scratch, expected_record_revision: str) -> None:
    """Reject delayed scratch writes after another record mutation or completion reset.

    Retained for callers that change only scratch. CLI transitions use ``commit_runtime``
    to commit the record and its teaching residuals together.
    """
    if not isinstance(session.store, FileProgressStore):
        raise TypeError("runtime-private scratch currently needs the file store backend")
    payload = serialize_scratch(scratch)
    try:
        session.store.write_runtime_state(session.course.id, payload, expected_record_revision)
    except Conflict as exc:
        fail(ExitCode.CONFLICT, "conflict", str(exc))


def serialize_scratch(scratch: Scratch) -> bytes:
    return yaml.safe_dump(
        {
            "wrong_count": scratch.wrong_count,
            "returning_to_quiz": scratch.returning_to_quiz,
            "last_key": scratch.last_key,
            "last_result": scratch.last_result,
        },
        sort_keys=False,
    ).encode("utf-8")


def commit_runtime(
    session: Session, record: Record, scratch: Scratch, identity: TransitionIdentity
) -> TransitionResult:
    if not isinstance(session.store, FileProgressStore):
        raise TypeError("runtime transitions currently need the file store backend")
    assert session.revision is not None
    try:
        return session.store.commit_transition(
            TransitionCommit(
                identity,
                session.revision,
                session.scratch_bytes,
                record,
                serialize_scratch(scratch),
            )
        )
    except IdempotencyKeyConflict as exc:
        fail(ExitCode.CONFLICT, "idempotency-key-conflict", str(exc))
    except Conflict as exc:
        fail(ExitCode.CONFLICT, "conflict", str(exc))


def load_session_course(course_ref: str) -> Course:
    """Recover enclosing workspace before consuming content, including direct paths."""
    with workspace_read(Path(course_ref)):
        return _load_session_course(course_ref)


def _load_session_course(course_ref: str) -> Course:
    """Resolve and validate course content without opening learner state."""
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

    return course


def open_session(
    course_ref: str | Course, state: Path | None, learner: str, *, initialize: bool = True
) -> Session:
    """Load everything one verb needs: the course, the record (created fresh if absent), the
    lesson the record currently points at, and the scratch beside it.

    ``course_ref`` is a directory first — today's behaviour, unchanged — and only when that
    is not a directory is it tried as a course id inside the enclosing workspace
    (``resolve_course_location``). An unusable workspace entry earns ``course-not-found``;
    an explicit directory with an invalid manifest still earns ``course-invalid``.

    Initialization is optional for homework reads/refusals. Existing prepared operations
    recover before access; otherwise reads preserve state and writes use CAS.
    """
    course = load_session_course(course_ref) if isinstance(course_ref, str) else course_ref

    try:
        state_root = resolve_state_root(state)
        store = open_store(str(state_root))
        if isinstance(store, FileProgressStore):
            store.ensure_course_paths(course.id)
        if initialize:
            load_or_create(store, course, learner)
        if not isinstance(store, FileProgressStore):
            raise TypeError("runtime-private scratch currently needs the file store backend")
        snapshot = store.read_runtime_snapshot(learner, course.id)
        if snapshot is None:
            record, revision = Record.new(course, learner), None
            scratch_bytes = b""
        else:
            record, revision = snapshot.record, snapshot.revision
            scratch_bytes = snapshot.scratch
        scratch = parse_scratch(scratch_bytes)
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

    return Session(course, lesson, store, record, revision, scratch, scratch_bytes)


def open_chronology_session(course_ref: str, state: Path | None, learner: str) -> Session:
    """Read existing history without initializing a record on a refused selection."""
    try:
        return open_session(course_ref, state, learner, initialize=False)
    except (RecoveryRequired, ValueError, TypeError, OSError, yaml.YAMLError) as exc:
        fail(ExitCode.INVALID, "chronology-invalid", f"cannot read completion history: {exc}")


def select_completed_coordinate(session: Session, learner: str, coordinate: str | None) -> str:
    """Translate history validation to stable CLI diagnostics without initializing records."""
    try:
        if session.record.learner_id != learner:
            raise ChronologyInvalid("record does not belong to the selected learner")
        log = session.store.get_log(learner, session.course.id)
        return completed_coordinate(session.course, session.record, log, coordinate=coordinate)
    except CoordinateRequired as exc:
        fail(ExitCode.INVALID, "coordinate-required", str(exc))
    except (RecoveryRequired, ValueError, TypeError, OSError, yaml.YAMLError) as exc:
        fail(ExitCode.INVALID, "chronology-invalid", f"cannot select completed lesson: {exc}")
