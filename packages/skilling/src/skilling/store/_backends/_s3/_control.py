"""Strict prefix ownership shared by initialization and stopped-prefix restoration."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..._protocol import ReconciliationRequired, RecoveryRequired, SessionSchemaError
from ._objects import ConditionalFailure, Objects, ObjectValue, UncertainWrite

CONTROL = "_skilling.json"


class Mode(StrEnum):
    READY = "READY"
    RESTORING = "RESTORING"


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    mode: Mode
    owner: str = Field(min_length=1)
    manifest_sha256: str | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_schema(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Schema must be integer")
        return value


def read_control(objects: Objects) -> ObjectValue | None:
    value = objects.get(CONTROL)
    if value is not None:
        try:
            Control.model_validate_json(value.body)
        except ValueError:
            raise SessionSchemaError("Invalid S3 prefix control; no automatic migration") from None
    return value


def ready(objects: Objects) -> None:
    value = read_control(objects)
    if value is None or Control.model_validate_json(value.body).mode != Mode.READY:
        raise RecoveryRequired("S3 prefix is not READY; stopped restore needs operator recovery")


def reserve(objects: Objects, mode: Mode, manifest: str | None = None) -> ObjectValue:
    if objects.keys():
        raise RecoveryRequired("S3 initialization or restore requires an empty prefix")
    control = Control(mode=mode, owner=uuid4().hex, manifest_sha256=manifest)
    raw = control.model_dump_json().encode()
    try:
        objects.put(CONTROL, raw)
    except ConditionalFailure:
        raise RecoveryRequired("S3 prefix was reserved by another initializer or restore") from None
    except UncertainWrite:
        raise ReconciliationRequired("S3 prefix reservation acknowledgement uncertain") from None
    value = read_control(objects)
    if value is None or value.body != raw:
        raise RecoveryRequired("S3 prefix reservation ownership changed")
    return value
