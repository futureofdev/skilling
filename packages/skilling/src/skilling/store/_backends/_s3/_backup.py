"""Quiesced checksummed backup and exclusive empty-prefix restore."""

from __future__ import annotations

import base64
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..._protocol import (
    ReconciliationRequired,
    RecoveryRequired,
    SessionRead,
    SessionReadKind,
    SessionScope,
)
from ..._protocol._boundary import validate_scope
from .._aggregate import decode
from ._control import CONTROL, Control, Mode, read_control, ready, reserve
from ._objects import MAX_BYTES, ConditionalFailure, Objects, UncertainWrite, stream_key


class _Envelope(BaseModel):
    model_config = ConfigDict(strict=True)
    scope: SessionScope


class _Entry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    key: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    body_base64: str

    def body(self) -> bytes:
        raw = base64.b64decode(self.body_base64, validate=True)
        if len(raw) > MAX_BYTES or sha256(raw).hexdigest() != self.sha256:
            raise ValueError("Invalid backup checksum or size")
        decode_entry(self.key, raw)
        return raw


class _Backup(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    entries: tuple[_Entry, ...]

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_schema(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Schema must be integer")
        return value


def decode_entry(key: str, raw: bytes) -> SessionRead:
    try:
        scope = _Envelope.model_validate_json(raw).scope
        validate_scope(scope)
        if key != stream_key(scope):
            raise ValueError("Object key differs from aggregate scope")
        value = decode(raw, scope)
        if value.kind == SessionReadKind.ABSENT:
            raise ValueError("An existing aggregate cannot represent absence")
        return value
    except (ValueError, TypeError):
        raise RecoveryRequired("Invalid scoped S3 backup or inventory entry") from None


def backup(objects: Objects, destination: Path) -> None:
    ready(objects)
    control = read_control(objects)
    keys = objects.keys()
    entries: list[_Entry] = []
    for key in keys:
        if key == CONTROL:
            continue
        value = objects.get(key)
        if value is None:
            raise RecoveryRequired("S3 inventory changed during backup; quiesce writers")
        decode_entry(key, value.body)
        entries.append(
            _Entry(
                key=key,
                sha256=sha256(value.body).hexdigest(),
                body_base64=base64.b64encode(value.body).decode("ascii"),
            )
        )
    # Recheck every body as well as inventory to detect concurrent changes during capture.
    verify(objects, tuple(entries))
    if read_control(objects) != control:
        raise RecoveryRequired("S3 prefix control changed during backup")
    wire = _Backup(entries=tuple(entries)).model_dump_json().encode()
    try:
        with destination.open("xb") as output:
            output.write(wire)
    except OSError:
        raise RecoveryRequired("S3 backup requires a new writable destination") from None


def verify(objects: Objects, entries: tuple[_Entry, ...]) -> None:
    if objects.keys() != tuple(sorted((CONTROL, *(entry.key for entry in entries)))):
        raise RecoveryRequired("S3 backup/restore inventory differs from complete manifest")
    for entry in entries:
        value = objects.get(entry.key)
        if value is None or sha256(value.body).hexdigest() != entry.sha256:
            raise RecoveryRequired("S3 backup/restore body differs from manifest")
        decode_entry(entry.key, value.body)


def restore(objects: Objects, source: Path) -> None:
    try:
        raw = source.read_bytes()
        manifest = _Backup.model_validate_json(raw)
        if len({entry.key for entry in manifest.entries}) != len(manifest.entries):
            raise ValueError("Duplicate backup stream")
        bodies = tuple(entry.body() for entry in manifest.entries)
    except (OSError, ValueError, TypeError):
        raise RecoveryRequired("Invalid full S3 backup; no restore writes attempted") from None
    # Reservation precedes the first stream body; failures intentionally retain RESTORING.
    ownership = reserve(objects, Mode.RESTORING, sha256(raw).hexdigest())
    try:
        for entry, body in zip(manifest.entries, bodies, strict=True):
            objects.put(entry.key, body)
        verify(objects, manifest.entries)
        if read_control(objects) != ownership:
            raise RecoveryRequired("S3 restore ownership changed")
        control = Control.model_validate_json(ownership.body).model_copy(
            update={"mode": Mode.READY}
        )
        objects.put(CONTROL, control.model_dump_json().encode(), ownership.etag)
    except (ConditionalFailure, UncertainWrite):
        raise ReconciliationRequired(
            "S3 restore incomplete or acknowledgement uncertain; inspect retained ownership"
        ) from None
    ready(objects)
