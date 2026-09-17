"""Mechanical archive/slot transactions under the existing course lock."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, StrictBytes, field_validator

from ...course import HomeworkArchiveEntry, HomeworkSlot, Record
from .._io import _fsync_dir as _fsync_dir
from .._io import _write_bytes_atomic as _write_bytes_atomic
from .._paths import checked_path
from .._protocol import (
    Conflict,
    InvalidSubmissionToken,
    RecoveryRequired,
    SubmissionCommit,
    SubmissionCommitResult,
    SubmissionReceipt,
    SubmissionToken,
)


class Boundary(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    @field_validator("version", mode="before", check_fields=False)
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("submission journal version must be an integer")
        return value


class ReceiptData(Boundary):
    token: str
    learner_id: str
    course_id: str
    course_version: str
    coordinate: str
    instance_id: str
    archive: HomeworkArchiveEntry

    def value(self) -> SubmissionReceipt:
        return SubmissionReceipt.checked(
            SubmissionReceipt(
                self.token,
                self.learner_id,
                self.course_id,
                self.course_version,
                self.coordinate,
                self.instance_id,
                self.archive,
            ),
            self.token,
        )


class Receipt(Boundary):
    version: Literal[1]
    kind: Literal["receipt"]
    value: ReceiptData
    archive_path: str


class Prepared(Boundary):
    version: Literal[1]
    kind: Literal["prepared"]
    receipt: Receipt
    slot_before: StrictBytes
    slot_after: StrictBytes | None
    archive_after: StrictBytes


class Committed(Boundary):
    version: Literal[1]
    kind: Literal["committed"]
    receipt: Receipt


def dump(value: object) -> bytes:
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=100).encode("utf-8")


def revision(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest()[:16] if raw is not None else None


def receipt_name(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest() + ".yaml"


def receipt_data(value: SubmissionReceipt) -> ReceiptData:
    raw = asdict(value)
    raw["archive"] = value.archive.model_dump(mode="json")
    return ReceiptData.model_validate(raw)


def validate_submission_commit(commit: SubmissionCommit, root: Path) -> SubmissionCommit:
    """Validate supplied copies and paths before locking can create any state."""
    try:
        receipt = SubmissionReceipt.checked(commit.receipt, commit.receipt.token)
        token = SubmissionToken.parse(receipt.token)
        if commit.expected_slot_revision != token.slot_revision:
            raise ValueError("submission revision differs from checked token")
        slot = (
            HomeworkSlot.model_validate(commit.slot.model_dump(mode="json"))
            if commit.slot is not None
            else None
        )
        journal = SubmissionJournal(root, receipt.course_id)
        for parts in (
            ("record.yaml",),
            ("submission.yaml",),
            ("homework", "active.yaml"),
            ("homework", "archive"),
            ("submission-receipts", receipt_name(receipt.token)),
        ):
            journal.path(*parts)
        journal.path(
            "homework",
            "archive",
            f"{receipt.coordinate}-{receipt.archive.submitted_at.date()}.yaml",
        )
        return SubmissionCommit(receipt, token.slot_revision, slot)
    except (ValueError, TypeError, AttributeError, yaml.YAMLError) as exc:
        raise RecoveryRequired(f"Invalid submission input: {exc}") from exc


class SubmissionJournal:
    def __init__(self, root: Path, course_id: str) -> None:
        self.root, self.course_id = root, course_id

    def path(self, *parts: str) -> Path:
        return checked_path(self.root, self.course_id, *parts)

    def raw(self, *parts: str) -> bytes | None:
        path = self.path(*parts)
        if path.exists() and not path.is_file():
            raise ValueError("submission target must be a regular file")
        return path.read_bytes() if path.is_file() else None

    def validate_token_stream(self, token: SubmissionToken) -> None:
        """Refuse a wrong stream before recovery can alter any accepted operation."""
        raw = self.raw("record.yaml")
        if raw is None:
            raise Conflict("submission record stream", token.course_version, None)
        try:
            record = Record.model_validate(yaml.safe_load(raw))
        except (ValueError, TypeError, yaml.YAMLError) as exc:
            raise RecoveryRequired(f"Invalid submission record stream: {exc}") from exc
        if (record.learner_id, record.course_id, record.course_version) != (
            token.learner_id,
            token.course_id,
            token.course_version,
        ):
            raise InvalidSubmissionToken("Token belongs to a different record stream")

    def validate_receipt(self, value: Receipt, *, archive_required: bool) -> SubmissionReceipt:
        receipt = value.value.value()
        if receipt.course_id != self.course_id:
            raise ValueError("submission receipt course mismatch")
        raw_record = self.raw("record.yaml")
        if raw_record is None:
            raise ValueError("submission has no record stream")
        record = Record.model_validate(yaml.safe_load(raw_record))
        if (record.learner_id, record.course_id, record.course_version) != (
            receipt.learner_id,
            receipt.course_id,
            receipt.course_version,
        ):
            raise ValueError("submission record stream mismatch")
        base = f"{receipt.coordinate}-{receipt.archive.submitted_at.date()}"
        parts = value.archive_path.split("/")
        if len(parts) != 3 or parts[:2] != ["homework", "archive"]:
            raise ValueError("invalid submission archive path")
        name = parts[2]
        if name != base + ".yaml":
            suffix = name.removeprefix(base + "-").removesuffix(".yaml")
            if not suffix.isdecimal() or int(suffix) < 2 or name != f"{base}-{int(suffix)}.yaml":
                raise ValueError("invalid submission archive filename")
        self.path(*parts)
        self.path("submission-receipts", receipt_name(receipt.token))
        if archive_required and self.raw(*parts) != dump(receipt.archive.model_dump(mode="json")):
            raise ValueError("submission receipt archive bytes differ")
        return receipt

    def load_receipt(self, token: str) -> Receipt | None:
        raw = self.raw("submission-receipts", receipt_name(token))
        if raw is None:
            return None
        found = Receipt.model_validate(yaml.safe_load(raw))
        receipt = self.validate_receipt(found, archive_required=True)
        if receipt.token != token:
            raise ValueError("submission receipt token mismatch")
        return found

    def inspect(self) -> Prepared | Committed | None:
        raw = self.raw("submission.yaml")
        if raw is None:
            return None
        data = yaml.safe_load(raw)
        value = (
            Prepared.model_validate(data)
            if isinstance(data, dict) and data.get("kind") == "prepared"
            else Committed.model_validate(data)
        )
        if isinstance(value, Prepared):
            self.preflight(value)
        else:
            receipt = self.validate_receipt(value.receipt, archive_required=True)
            if self.load_receipt(receipt.token) != value.receipt:
                raise ValueError("committed submission receipt is missing or inconsistent")
        return value

    def preflight(self, value: Prepared) -> None:
        receipt = self.validate_receipt(value.receipt, archive_required=False)
        token = SubmissionToken.parse(receipt.token)
        before = HomeworkSlot.model_validate(yaml.safe_load(value.slot_before))
        expected_revision = revision(value.slot_before)
        assert expected_revision is not None
        if (
            SubmissionToken.for_slot(
                token.learner_id, token.course_id, token.course_version, before, expected_revision
            )
            != token
        ):
            raise ValueError("submission before-image differs from checked token")
        if (
            receipt.archive.coordinate,
            receipt.archive.title,
            receipt.archive.requirements,
            receipt.archive.stretch_goals,
        ) != (
            before.coordinate,
            before.title,
            before.requirements,
            before.stretch_goals,
        ):
            raise ValueError("submission archive differs from checked assignment")
        after = (
            HomeworkSlot.model_validate(yaml.safe_load(value.slot_after))
            if value.slot_after is not None
            else None
        )
        expected = (
            HomeworkSlot(**before.queued[0].model_dump(), queued=before.queued[1:])
            if before.queued
            else None
        )
        if after != expected:
            raise ValueError("submission must preserve and advance the checked queue once")
        if value.archive_after != dump(receipt.archive.model_dump(mode="json")):
            raise ValueError("submission archive after-image mismatch")
        if self.raw(*value.receipt.archive_path.split("/")) not in (None, value.archive_after):
            raise ValueError("unexpected submission archive bytes")
        if self.raw("homework", "active.yaml") not in (value.slot_before, value.slot_after):
            raise ValueError("unexpected submission slot bytes")
        raw_receipt = self.raw("submission-receipts", receipt_name(receipt.token))
        if raw_receipt not in (None, dump(value.receipt.model_dump(mode="json"))):
            raise ValueError("unexpected submission receipt bytes")

    def publish(self, value: Prepared | Committed) -> None:
        data = value.model_dump()
        data["receipt"] = value.receipt.model_dump(mode="json")
        _write_bytes_atomic(self.path("submission.yaml"), dump(data))

    def apply(self, value: Prepared) -> None:
        archive_parts = value.receipt.archive_path.split("/")
        if self.raw(*archive_parts) is None:
            _write_bytes_atomic(self.path(*archive_parts), value.archive_after)
        if self.raw("homework", "active.yaml") != value.slot_after:
            path = self.path("homework", "active.yaml")
            if value.slot_after is None:
                path.unlink()
                _fsync_dir(path.parent)
            else:
                _write_bytes_atomic(path, value.slot_after)
        token = value.receipt.value.token
        if self.raw("submission-receipts", receipt_name(token)) is None:
            _write_bytes_atomic(
                self.path("submission-receipts", receipt_name(token)),
                dump(value.receipt.model_dump(mode="json")),
            )
        self.publish(Committed(version=1, kind="committed", receipt=value.receipt))

    def commit(self, commit: SubmissionCommit) -> SubmissionCommitResult:
        receipt = commit.receipt
        found = self.load_receipt(receipt.token)
        if found is not None:
            return SubmissionCommitResult(found.value.value(), True)
        before = self.raw("homework", "active.yaml")
        actual = revision(before)
        if actual != commit.expected_slot_revision:
            raise Conflict("homework/active.yaml", commit.expected_slot_revision, actual)
        assert before is not None
        base = f"{receipt.coordinate}-{receipt.archive.submitted_at.date()}"
        name, suffix = base + ".yaml", 2
        while self.path("homework", "archive", name).exists():
            name = f"{base}-{suffix}.yaml"
            suffix += 1
        stored = Receipt(
            version=1,
            kind="receipt",
            value=receipt_data(receipt),
            archive_path="homework/archive/" + name,
        )
        prepared = Prepared(
            version=1,
            kind="prepared",
            receipt=stored,
            slot_before=before,
            slot_after=dump(commit.slot.model_dump(mode="json")) if commit.slot else None,
            archive_after=dump(receipt.archive.model_dump(mode="json")),
        )
        self.preflight(prepared)
        self.publish(prepared)
        self.apply(prepared)
        return SubmissionCommitResult(receipt, False)
