"""Shared plumbing for the JSON transition verbs.

Every verb in ``cli/runtime`` loads exactly one :class:`Session`, applies at most one write,
and prints exactly one JSON object. This module is the part every verb shares: how a session
is assembled, how a refusal is reported, and where the runtime-private scratch that has to
survive between one process and the next actually lives.

The trusted runtime is the write authority: a store never computes anything, so every derived write
— position after a transition, the completion write set — happens in ``delivery`` or here,
never inside a store backend.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import IntEnum
from pathlib import Path
from typing import NoReturn

import typer
import yaml

from ...course import Course, Record, declared_level, is_semver
from ...delivery import (
    ChronologyInvalid,
    CoordinateRequired,
    completed_coordinate,
)
from ...session import (
    FileSession,
    RefusalKind,
    SessionRefusal,
    VersionMismatch,
    _commit_runtime,
    _load_runtime,
    load_course,
)
from ...session import (
    _parse_scratch as parse_scratch,
)
from ...session import (
    _RuntimeSession as Session,
)
from ...session import (
    _Scratch as Scratch,
)
from ...session import (
    _serialize_scratch as serialize_scratch,
)
from ...store import (
    Conflict,
    FileProgressStore,
    ProgressStore,
    RecoveryRequired,
    StatePathError,
    TransitionIdentity,
    TransitionResult,
    open_store,
)
from ...workspace import (
    courses_dir,
    find_workspace,
    resolve_course_location,
    resolve_state_root,
    workspace_read,
)

__all__ = ["Scratch", "Session", "parse_scratch", "serialize_scratch"]

SCRATCH_NAME = "scratch.yaml"


class ExitCode(IntEnum):
    """Process exit codes every runtime verb uses. Stable — a driving pack switches on these."""

    OK = 0
    ERROR = 1
    INVALID = 2
    CONFLICT = 3
    ILLEGAL = 4
    VERSION_MISMATCH = 5


def now_override() -> datetime | None:
    """``SKILLING_NOW`` (ISO 8601) when set — deterministic runs for the byte-equivalence
    gate and tests. Documented test-only surface; no production caller should ever set it."""
    raw = os.environ.get("SKILLING_NOW")
    return datetime.fromisoformat(raw) if raw else None


def emit(payload: dict[str, object]) -> None:
    """The one and only way any runtime verb writes to stdout: one JSON object, one line."""
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")


def view_data(value: object) -> dict[str, object]:
    """Serialize copied dataclass outputs only at the CLI JSON boundary."""
    if not is_dataclass(value) or isinstance(value, type):
        raise TypeError("expected a session view")

    def json_default(item: object) -> str:
        if isinstance(item, datetime):
            return item.isoformat().replace("+00:00", "Z")
        if isinstance(item, date):
            return item.isoformat()
        raise TypeError(f"unsupported view field: {type(item).__name__}")

    return json.loads(json.dumps(asdict(value), default=json_default))


def fail(
    code: ExitCode, error: str, message: str, *, upgrade: dict[str, object] | None = None
) -> NoReturn:
    body: dict[str, object] = {"code": error, "message": message}
    if upgrade is not None:
        body["upgrade"] = upgrade
    emit({"ok": False, "error": body})
    raise typer.Exit(code)


def load_scratch(store: ProgressStore, course_id: str) -> Scratch:
    if not isinstance(store, FileProgressStore):
        raise TypeError("runtime-private scratch currently needs the file store backend")
    return parse_scratch(store.read_runtime_state(course_id))


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


def commit_runtime(
    session: Session, record: Record, scratch: Scratch, identity: TransitionIdentity
) -> TransitionResult:
    try:
        return _commit_runtime(session, record, scratch, identity)
    except SessionRefusal as exc:
        refuse_session(exc, str(session.course.root))


def refuse_session(exc: SessionRefusal, ref: str) -> NoReturn:
    if isinstance(exc, VersionMismatch):
        command = f"skilling upgrade --course {ref}"
        if exc.resumable:
            message = (
                f"this record is on {exc.course_id} {exc.from_version}, and {exc.to_version} is "
                f"available here. Progress carries over: run `{command} --yes` (or "
                "/upgrade-skilling) to switch. Nothing changes until you do."
            )
        elif exc.refusal_message is not None:
            message = (
                f"{exc.refusal_message} Run `{command} --check` (or /upgrade-skilling) for options."
            )
        else:
            message = (
                f"the record was started against {exc.course_id} {exc.from_version}, but "
                f"{exc.course_id} on disk is {exc.to_version}. Run `{command} --check` for options."
            )
        fail(
            ExitCode.VERSION_MISMATCH,
            "version-mismatch",
            message,
            upgrade={
                "from": exc.from_version,
                "to": exc.to_version,
                "resumable": exc.resumable,
                "reason": exc.reason.value if exc.reason else None,
                "command": command,
            },
        )
    code = {
        RefusalKind.INVALID: ExitCode.INVALID,
        RefusalKind.CONFLICT: ExitCode.CONFLICT,
        RefusalKind.ILLEGAL: ExitCode.ILLEGAL,
    }[exc.kind]
    fail(code, exc.code, str(exc))


def file_state_root(state: Path | None) -> Path:
    """Preserve CLI file: and backend selection before normalizing a local path."""
    try:
        store = open_store(str(resolve_state_root(state)))
    except StatePathError as exc:
        fail(ExitCode.INVALID, "state-invalid", str(exc))
    if not isinstance(store, FileProgressStore):
        raise TypeError("runtime-private scratch currently needs the file store backend")
    return store.state_root


def open_file_session(
    course_ref: str | Course,
    state: Path | None,
    learner: str,
    *,
    initialize: bool = True,
) -> FileSession:
    try:
        return FileSession.open(
            load_session_course(course_ref) if isinstance(course_ref, str) else course_ref,
            state_root=file_state_root(state),
            learner_id=learner,
            initialize=initialize,
        )
    except SessionRefusal as exc:
        refuse_session(exc, course_ref if isinstance(course_ref, str) else str(course_ref.root))


def open_file_chronology_session(course_ref: str, state: Path | None, learner: str) -> FileSession:
    try:
        return open_file_session(course_ref, state, learner, initialize=False)
    except (RecoveryRequired, ValueError, TypeError, OSError, yaml.YAMLError) as exc:
        fail(ExitCode.INVALID, "chronology-invalid", f"cannot read completion history: {exc}")


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
        return load_course(course_path.absolute())
    except SessionRefusal as exc:
        refuse_session(exc, course_ref)


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

    A record started on a different version of the course is never moved implicitly: every
    verb refuses with ``version-mismatch`` and says whether ``skilling upgrade`` can carry the
    progress over (spec/runtime.md#course-version-changes).
    """
    course = load_session_course(course_ref) if isinstance(course_ref, str) else course_ref

    try:
        return _load_runtime(
            course,
            file_state_root(state),
            learner,
            initialize=initialize,
        )
    except SessionRefusal as exc:
        ref = course_ref if isinstance(course_ref, str) else str(course.root)
        refuse_session(exc, ref)


def known_upgrade(course: Course) -> dict[str, object] | None:
    """A newer version of ``course`` already in this workspace's content directory, if any.

    A hint only, never a network call: content lands there when ``skilling upgrade --check``
    fetched it. Nothing is verified or switched here; ``skilling upgrade`` does both.
    """
    workspace = find_workspace()
    if workspace is None:
        return None
    root = courses_dir(workspace)
    newer: list[tuple[tuple[int, int, int], str]] = []
    prefix = f"{course.id}@"
    if root.is_dir():
        for child in root.iterdir():
            version = child.name.removeprefix(prefix)
            if not child.name.startswith(prefix) or not is_semver(version):
                continue
            level = declared_level(course.version, version)
            if level in ("patch", "minor", "major") and "-" not in version:
                major, minor, patch = (int(p) for p in version.split("+")[0].split("."))
                newer.append(((major, minor, patch), version))
    if not newer:
        return None
    version = max(newer)[1]
    return {
        "available": version,
        "level": declared_level(course.version, version),
        "command": f"skilling upgrade --course {course.id}",
    }


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
