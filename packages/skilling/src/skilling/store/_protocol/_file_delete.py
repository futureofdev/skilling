"""Persistent deletion identity and recoverable cleanup; the course lock survives."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from .._io import _fsync_dir, _write_bytes_atomic
from .._journal._transition_types import Boundary
from .._paths import checked_path
from ._progress import RecoveryRequired
from ._types import SessionScope

NAME = "session-deleted.json"


class Tombstone(Boundary):
    version: Literal[1]
    namespace: str = Field(min_length=1)
    learner_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    generation: str = Field(min_length=1)


def read_deleted(root: Path, course: str) -> Tombstone | None:
    path = checked_path(root, course, NAME)
    if not path.exists():
        return None
    try:
        value = Tombstone.model_validate_json(path.read_bytes())
        if value.course_id != course:
            raise ValueError("Deleted stream identity differs")
        return value
    except (ValueError, TypeError, OSError) as exc:
        raise RecoveryRequired("Invalid session deletion marker") from exc


def cleanup_deleted(root: Path, course: str) -> None:
    """The validated marker wins before any older prepared journal is recovered."""
    directory = checked_path(root, course)
    for path in sorted(directory.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        relative = path.relative_to(directory)
        checked_path(root, course, *relative.parts)
        if path.name == ".skilling.lock" or relative.as_posix() == NAME:
            continue
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
        _fsync_dir(path.parent)


def publish_deleted(root: Path, scope: SessionScope, generation: str) -> None:
    value = Tombstone(
        version=1,
        namespace=scope.namespace,
        learner_id=scope.learner_id,
        course_id=scope.course_id,
        generation=generation,
    )
    _write_bytes_atomic(
        checked_path(root, scope.course_id, NAME),
        json.dumps(value.model_dump(), sort_keys=True).encode(),
    )
    cleanup_deleted(root, scope.course_id)
