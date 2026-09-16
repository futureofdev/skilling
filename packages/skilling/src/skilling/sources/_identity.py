"""Versioned private cache metadata and platform-independent Git payload identity."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..course import is_course_id, is_semver
from ._errors import CacheInvalid, UnknownRef
from ._paths import plain

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def course_key(course_id: str, version: str) -> str:
    if not (is_course_id(course_id) and is_semver(version)):
        raise CacheInvalid("invalid cached course id/version")
    return f"{course_id}@{version}"


def validate_key(key: str) -> str:
    course_id, _, version = key.partition("@")
    if course_key(course_id, version) != key:
        raise ValueError("invalid course key")
    return key


def ref_digest(ref: str) -> str:
    return hashlib.sha256(ref.encode("utf-8")).hexdigest()


def safe_source_ref(ref: str) -> str:
    """Display provenance only: exact cache lookup identity is separately hashed.

    HTTP userinfo and all URL query/fragment values are omitted. SSH usernames remain;
    passwords do not. This does not rewrite the exact-input ResolvedSource.ref interface.
    """
    if ref.startswith("gh:"):
        return "gh:source (redacted)" if "?" in ref else ref
    try:
        parts = urlsplit(ref.removeprefix("git+"))
        host = parts.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        if parts.port is not None:
            host += f":{parts.port}"
        if parts.scheme == "ssh" and parts.username:
            host = f"{parts.username}@{host}"
        return urlunsplit(
            (parts.scheme.lower(), host, parts.path, "redacted" if parts.query else "", "")
        )
    except ValueError:
        return "remote URL (redacted)"


def relative_name(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or path.as_posix() != value
        or any(p in {".", "..", ".git"} for p in path.parts)
        or any(c in value for c in "\\:\0")
    ):
        raise ValueError("unsafe payload-relative path")
    return value


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Provenance(Metadata):
    transport: str = Field(pattern=r"^[a-z][a-z0-9+.-]*$")
    source: str
    pin: str | None = None
    subdirectory: str | None = None
    commit: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

    @field_validator("pin")
    @classmethod
    def safe_pin(cls, value: str | None) -> str | None:
        if value is not None and "?" in value:
            raise ValueError("Git pin cannot carry query parameters")
        return value

    @field_validator("source")
    @classmethod
    def sanitized(cls, value: str) -> str:
        if safe_source_ref(value) != value:
            raise ValueError("unsanitized source provenance")
        return value

    @field_validator("subdirectory")
    @classmethod
    def relative(cls, value: str | None) -> str | None:
        return relative_name(value) if value is not None else None

    @model_validator(mode="after")
    def coherent(self) -> Provenance:
        if self.source.startswith("gh:"):
            body, _, subdirectory = self.source.removeprefix("gh:").partition("#")
            repository, _, pin = body.partition("@")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
                raise ValueError("invalid GitHub source provenance")
            expected = ("https", pin or None, subdirectory or None)
        else:
            expected = (urlsplit(self.source).scheme, None, None)
        if (self.transport, self.pin, self.subdirectory) != expected:
            raise ValueError("source provenance fields disagree")
        return self


class Payload(Metadata):
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    executables: tuple[str, ...] = ()

    @field_validator("executables")
    @classmethod
    def paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("executable paths must be unique and sorted")
        return tuple(relative_name(v) for v in values)


class Entry(Metadata):
    key: str
    source: Provenance

    @field_validator("key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        return validate_key(value)


class Index(Metadata):
    version: Literal[1] = 1
    entries: dict[str, Entry] = Field(default_factory=dict)
    contents: dict[str, Payload] = Field(default_factory=dict)
    pending: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def coherent(self) -> Index:
        for digest in (*self.entries, *self.pending):
            if not _DIGEST.fullmatch(digest):
                raise ValueError("invalid source digest")
        for key in (*self.contents, *self.pending.values()):
            validate_key(key)
        if self.entries.keys() & self.pending.keys():
            raise ValueError("source cannot be both verified and pending")
        if any(entry.key not in self.contents for entry in self.entries.values()):
            raise ValueError("verified source lacks content identity")
        return self


def payload_paths(root: Path) -> tuple[Path, ...]:
    plain(root, directory=True)
    found: list[Path] = []

    def walk(directory: Path) -> None:
        for path in sorted(directory.iterdir()):
            if path.name == ".git":
                continue
            relative_name(path.relative_to(root).as_posix())
            info = path.lstat()
            directory_entry = stat.S_ISDIR(info.st_mode)
            plain(path, directory=directory_entry)
            found.append(path)
            if directory_entry:
                walk(path)

    try:
        walk(root)
    except (OSError, ValueError):
        raise CacheInvalid("cannot safely inspect course payload") from None
    return tuple(sorted(found, key=lambda p: p.relative_to(root).as_posix()))


def inspect_payload(root: Path, executables: tuple[str, ...]) -> Payload:
    digest = hashlib.sha256(b"skilling-payload-v1\0")
    executable_set = set(executables)
    regular: set[str] = set()
    for path in payload_paths(root):
        name = path.relative_to(root).as_posix()
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big") + encoded)
        if path.is_dir():
            digest.update(b"directory\0")
            continue
        regular.add(name)
        executable = name in executable_set
        if os.name == "posix" and bool(path.stat().st_mode & 0o111) != executable:
            raise CacheInvalid("course executable intent changed; use a separate cache")
        digest.update(b"executable\0" if executable else b"file\0")
        content = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    content.update(chunk)
        except OSError:
            raise CacheInvalid("cannot read course payload; preserve it and retry") from None
        digest.update(content.digest())
    if not executable_set <= regular:
        raise CacheInvalid("executable intent references absent course files")
    return Payload(digest=digest.hexdigest(), executables=executables)


def check_subdirectory(subdirectory: str | None) -> None:
    if subdirectory is not None:
        try:
            relative_name(subdirectory)
        except ValueError:
            raise UnknownRef("GitHub course subdirectory must stay inside the repository") from None
