"""Recoverable first initialization and recorded current-source attachment."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from ...course import Record
from .._io import _fsync_dir
from .._io import _write_bytes_atomic as _write_bytes_atomic
from .._journal._transition_types import Boundary
from .._paths import checked_path
from ._progress import RecoveryRequired
from ._types import SessionScope

SOURCE = "session-source.json"
INTENT = "session-initialize.json"


def unpublished_initialization(name: str) -> bool:
    return (
        re.fullmatch(
            r"\.(?:record\.yaml|session-source\.json|session-initialize\.json)\.[a-zA-Z0-9_-]+\.tmp",
            name,
        )
        is not None
    )


class SourceBinding(Boundary):
    version: Literal[1]
    namespace: str = Field(min_length=1)
    learner_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    course_version: str = Field(min_length=1)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class Initialization(Boundary):
    version: Literal[1]
    record_yaml: str
    source: SourceBinding | None


def source_bytes(scope: SessionScope, record: Record, digest: str) -> bytes:
    return (
        SourceBinding(
            version=1,
            namespace=scope.namespace,
            learner_id=scope.learner_id,
            course_id=scope.course_id,
            course_version=record.course_version,
            digest=digest,
        )
        .model_dump_json()
        .encode()
    )


def inspect_initialize(root: Path, course: str) -> Initialization | None:
    path = checked_path(root, course, INTENT)
    if not path.exists():
        return
    try:
        intent = Initialization.model_validate_json(path.read_bytes())
        record = Record.model_validate(yaml.safe_load(intent.record_yaml))
        from ._file_session import BINDING, RootBinding

        owner_path = root / BINDING
        if owner_path.is_symlink():
            raise ValueError("Initialization owner must not be an alias")
        owner = RootBinding.model_validate_json(owner_path.read_bytes())
        if owner.learner_id != record.learner_id:
            raise ValueError("Initialization learner differs from root ownership")
        if intent.source is not None and owner.namespace != intent.source.namespace:
            raise ValueError("Initialization namespace differs from root ownership")
        allowed = {INTENT, SOURCE, "record.yaml", ".skilling.lock"}
        for child in checked_path(root, course).iterdir():
            checked_path(root, course, child.name)
            if (
                child.name not in allowed and not unpublished_initialization(child.name)
            ) or not child.is_file():
                raise ValueError("Initialization cannot coexist with other learner state")
        if record.course_id != course:
            raise ValueError("Initialization course differs")
        raw = intent.record_yaml.encode()
        target = checked_path(root, course, "record.yaml")
        if target.exists() and target.read_bytes() != raw:
            raise ValueError("Initialization record differs from prepared bytes")
        source = checked_path(root, course, SOURCE)
        if intent.source is not None:
            if (
                intent.source.learner_id,
                intent.source.course_id,
                intent.source.course_version,
            ) != (record.learner_id, record.course_id, record.course_version):
                raise ValueError("Initialization source differs from record")
            metadata = intent.source.model_dump_json().encode()
            if source.exists() and source.read_bytes() != metadata:
                raise ValueError("Initialization source metadata differs")
        elif source.exists():
            raise ValueError("Unexpected initialization source metadata")
        return intent
    except (ValueError, TypeError, OSError, yaml.YAMLError) as exc:
        raise RecoveryRequired("Invalid prepared session initialization") from exc


def apply_initialize(root: Path, course: str, intent: Initialization) -> None:
    if intent.source is not None:
        _write_bytes_atomic(
            checked_path(root, course, SOURCE), intent.source.model_dump_json().encode()
        )
    _write_bytes_atomic(checked_path(root, course, "record.yaml"), intent.record_yaml.encode())
    path = checked_path(root, course, INTENT)
    path.unlink()
    _fsync_dir(path.parent)


def initialize(root: Path, scope: SessionScope, record: Record, digest: str | None) -> None:
    intent = Initialization(
        version=1,
        record_yaml=yaml.safe_dump(
            record.model_dump(mode="json"), sort_keys=False, allow_unicode=True, width=100
        ),
        source=SourceBinding.model_validate_json(source_bytes(scope, record, digest))
        if digest
        else None,
    )
    _write_bytes_atomic(
        checked_path(root, scope.course_id, INTENT), intent.model_dump_json().encode()
    )
    prepared = inspect_initialize(root, scope.course_id)
    assert prepared is not None
    apply_initialize(root, scope.course_id, prepared)
