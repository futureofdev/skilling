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

from ...course import Course, CourseLoadError, Record, ResolvedLesson
from ...delivery import load_or_create
from ...store import FileProgressStore, ProgressStore, open_store

DEFAULT_STATE_ROOT = Path(".skilling")
"""Matches ``deliver``'s own default, so a learner does not get two conventions."""

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


def _scratch_path(state_root: Path, course_id: str) -> Path:
    return state_root / course_id / SCRATCH_NAME


def _load_scratch(state_root: Path, course_id: str) -> Scratch:
    path = _scratch_path(state_root, course_id)
    if not path.is_file():
        return Scratch()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Scratch(
        wrong_count=data.get("wrong_count", 0),
        returning_to_quiz=data.get("returning_to_quiz", False),
        last_key=data.get("last_key"),
        last_result=data.get("last_result"),
    )


def save_scratch(session: Session, scratch: Scratch) -> None:
    """Overwrite the scratch file beside this session's record.

    Coupled to the file backend: ``Session.store`` is typed against the store ``Protocol``,
    but scratch's file layout — beside the record, keyed by course id — is the file
    backend's own layout, not something the protocol promises. ``open_session`` below
    selects the backend through ``open_store``, which can in principle return a non-file
    backend (a third-party ``skilling.stores`` entry point); the ``TypeError`` here is the
    honest refusal for that case rather than a silent no-op.
    """
    if not isinstance(session.store, FileProgressStore):
        raise TypeError("runtime-private scratch currently needs the file store backend")
    path = session.store.course_dir(session.course.id) / SCRATCH_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "wrong_count": scratch.wrong_count,
                "returning_to_quiz": scratch.returning_to_quiz,
                "last_key": scratch.last_key,
                "last_result": scratch.last_result,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def open_session(course_ref: str, state: Path | None, learner: str) -> Session:
    """Load everything one verb needs: the course, the record (created fresh if absent), the
    lesson the record currently points at, and the scratch beside it.

    Never writes beyond the record's own creation-on-first-use (``load_or_create``) — each
    verb decides for itself whether *it* makes a write, and through what CAS.
    """
    try:
        course = Course.load(Path(course_ref))
    except CourseLoadError as exc:
        fail(ExitCode.INVALID, "course-invalid", f"{exc.code}: {exc.message}")

    state_root = state if state is not None else DEFAULT_STATE_ROOT
    store = open_store(str(state_root))
    record, revision = load_or_create(store, course, learner)

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

    scratch = _load_scratch(state_root, course.id)
    return Session(course, lesson, store, record, revision, scratch)
