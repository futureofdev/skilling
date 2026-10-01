"""Explicit file-session loading and runtime-private residuals."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import yaml

from ..conformance import validate_course
from ..course import Course, CourseLoadError, Record, ResolvedLesson, is_course_id
from ..delivery import load_or_create, preview_upgrade
from ..store import FileProgressStore, RecoveryRequired, StatePathError
from ..workspace import workspace_read
from ._errors import RefusalKind, SessionRefusal, VersionMismatch


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


class RuntimeSession(NamedTuple):
    course: Course
    lesson: ResolvedLesson
    store: FileProgressStore
    record: Record
    revision: str | None
    scratch: Scratch
    scratch_bytes: bytes


def load_course(path: Path, *, workspace_root: Path | None = None) -> Course:
    """Validate an explicit absolute course path, optionally contained in a workspace."""
    if not path.is_absolute():
        raise SessionRefusal(RefusalKind.INVALID, "course-invalid", "course path must be absolute")
    if workspace_root is not None and (
        not workspace_root.is_absolute()
        or not path.resolve().is_relative_to(workspace_root.resolve())
    ):
        raise SessionRefusal(RefusalKind.INVALID, "course-invalid", "course is outside workspace")
    with workspace_read(path):
        try:
            report = validate_course(path)
            if not report.ok:
                first = report.errors[0]
                raise SessionRefusal(
                    RefusalKind.INVALID,
                    "course-invalid",
                    f"{first.code}: {first.message} ({len(report.errors)} error(s))",
                )
            return Course.load(path)
        except CourseLoadError as exc:
            raise SessionRefusal(
                RefusalKind.INVALID, "course-invalid", f"{exc.code}: {exc.message}"
            ) from exc
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise SessionRefusal(
                RefusalKind.INVALID, "course-invalid", f"Cannot read course: {type(exc).__name__}"
            ) from exc


def file_store(state_root: Path) -> FileProgressStore:
    if not isinstance(state_root, Path):
        raise SessionRefusal(RefusalKind.INVALID, "backend-unsupported", "a file path is required")
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]+:", str(state_root)):
        raise SessionRefusal(
            RefusalKind.INVALID, "backend-unsupported", "only file paths are supported"
        )
    if not state_root.is_absolute():
        raise SessionRefusal(RefusalKind.INVALID, "state-invalid", "state root must be absolute")
    try:
        return FileProgressStore(state_root)
    except StatePathError as exc:
        raise SessionRefusal(RefusalKind.INVALID, "state-invalid", str(exc)) from exc


def load_runtime(
    course: Course,
    state_root: Path,
    learner_id: str,
    *,
    initialize: bool = True,
    now: datetime | None = None,
) -> RuntimeSession:
    if not is_course_id(course.id):
        raise SessionRefusal(RefusalKind.INVALID, "course-invalid", "invalid course id")
    store = file_store(state_root)
    try:
        store.ensure_course_paths(course.id)
        snapshot = store.read_runtime_snapshot(learner_id, course.id)
        # Validate residuals before first-use initialization can publish a record.
        parse_scratch(snapshot.scratch if snapshot else store.read_runtime_state(course.id))
        if snapshot is None and initialize:
            load_or_create(store, course, learner_id, now=now)
            snapshot = store.read_runtime_snapshot(learner_id, course.id)
        if snapshot is None:
            record, revision, scratch_bytes = Record.new(course, learner_id, now=now), None, b""
        else:
            record, revision, scratch_bytes = snapshot.record, snapshot.revision, snapshot.scratch
        scratch = parse_scratch(scratch_bytes)
    except StatePathError as exc:
        raise SessionRefusal(RefusalKind.INVALID, "state-invalid", str(exc)) from exc
    if record.learner_id != learner_id or record.course_id != course.id:
        raise SessionRefusal(
            RefusalKind.INVALID, "stream-mismatch", "record belongs to another stream"
        )
    if record.course_version != course.version:
        plan = preview_upgrade(store, course, learner_id).plan
        raise VersionMismatch(
            course.id,
            record.course_version,
            course.version,
            bool(plan and plan.ok),
            plan.refusal if plan else None,
            plan.refusal_message() if plan and not plan.ok else None,
        )
    lesson = course.lesson_at(record.position.coordinate)
    if lesson is None:
        raise SessionRefusal(
            RefusalKind.INVALID,
            "position-invalid",
            f"{record.position.coordinate} is not a lesson in {course.id}",
        )
    return RuntimeSession(course, lesson, store, record, revision, scratch, scratch_bytes)


def parse_scratch(raw: bytes) -> Scratch:
    try:
        data = yaml.safe_load(raw) if raw else {}
    except (UnicodeError, yaml.YAMLError) as exc:
        raise RecoveryRequired("Cannot parse teaching scratch") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise RecoveryRequired("Teaching scratch must be a mapping")
    wrong = data.get("wrong_count", 0)
    returning = data.get("returning_to_quiz", False)
    key, result = data.get("last_key"), data.get("last_result")
    if (
        type(wrong) is not int
        or wrong < 0
        or type(returning) is not bool
        or key is not None
        and not isinstance(key, str)
        or result is not None
        and not isinstance(result, dict)
    ):
        raise RecoveryRequired("Invalid teaching scratch fields")
    return Scratch(wrong, returning, key, result)


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
