"""The single-learner file backend.

The layout is specified rather than incidental (spec/runtime.md#the-file-layout) so that
any runtime can read any learner's local state. That is what makes local progress portable
between tools instead of trapped in one.

Revisions are content hashes, so they cost nothing to compute and survive a process that
forgets everything. Writes go through a temporary file and an atomic rename, with fsync
before acknowledging, because the specification requires that an acknowledged completion
survives a crash of the runtime, the store, or both.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import yaml
from pydantic import BaseModel

from ..course import CompletionEntry, HomeworkArchiveEntry, HomeworkSlot, Record
from ._io import _fsync_dir, _write_bytes_atomic
from ._journal import (
    Journal,
    RuntimeSnapshot,
    SubmissionJournal,
    TransitionCommit,
    TransitionIdentity,
    TransitionJournal,
    TransitionResult,
    recover_journals,
    validate_commit,
    validate_submission_commit,
    validate_transition_commit,
)
from ._locking import DEFAULT_LOCK_TIMEOUT as DEFAULT_LOCK_TIMEOUT
from ._locking import locked_course
from ._paths import canonical_root, checked_path
from ._protocol import (
    CompletionCommit,
    CompletionCommitResult,
    CompletionReceipt,
    Conflict,
    InvalidSubmissionToken,
    RecoveryRequired,
    Revision,
    StatePathError,
    SubmissionCommit,
    SubmissionCommitResult,
    SubmissionReceipt,
    SubmissionToken,
)

RECORD_NAME = "record.yaml"
LOG_NAME = "completed.yaml"
HOMEWORK_DIR = "homework"
HOMEWORK_ACTIVE = "active.yaml"
HOMEWORK_ARCHIVE = "archive"

LOCAL_LEARNER = "local"
"""A file state root serves exactly one learner, so the id is implicit."""


def _revision(data: bytes) -> Revision:
    return hashlib.sha256(data).hexdigest()[:16]


def _dump(model: BaseModel) -> str:
    return yaml.safe_dump(
        model.model_dump(mode="json"), sort_keys=False, allow_unicode=True, width=100
    )


def _dump_list(models: Sequence[BaseModel]) -> str:
    return yaml.safe_dump(
        [m.model_dump(mode="json") for m in models],
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )


def _write_atomic(path: Path, text: str) -> None:
    _write_bytes_atomic(path, text.encode("utf-8"))


class FileProgressStore:
    """A conforming store over a directory tree. One learner per ``state_root``."""

    def __init__(self, state_root: Path | str, learner_id: str = LOCAL_LEARNER) -> None:
        self.state_root = canonical_root(state_root)
        self.learner_id = learner_id

    # ------------------------------------------------------------------------- paths

    def checked_path(self, course_id: str, *parts: str) -> Path:
        """Check every descendant before access, without creating the state root."""
        return checked_path(self.state_root, course_id, *parts)

    def course_dir(self, course_id: str) -> Path:
        return self.checked_path(course_id)

    def ensure_course_paths(self, course_id: str) -> None:
        """Read-only preflight before a session can initialize learner state."""
        directory = self.course_dir(course_id)
        self._record_path(course_id)
        self._log_path(course_id)
        self._homework_path(course_id)
        self.checked_path(course_id, "scratch.yaml")
        self.checked_path(course_id, "completion.yaml")
        self.checked_path(course_id, "transition.yaml")
        self.checked_path(course_id, "submission.yaml")
        receipts = self.checked_path(course_id, "transition-receipts")
        if receipts.is_dir():
            for child in receipts.iterdir():
                self.checked_path(course_id, "transition-receipts", child.name)
        submitted = self.checked_path(course_id, "submission-receipts")
        if submitted.is_dir():
            for child in submitted.iterdir():
                self.checked_path(course_id, "submission-receipts", child.name)
        archive = self._archive_dir(course_id)
        if archive.is_dir():
            for child in archive.iterdir():
                self.checked_path(course_id, HOMEWORK_DIR, HOMEWORK_ARCHIVE, child.name)
        if directory.is_dir():
            for child in directory.iterdir():
                if child.name.startswith("."):
                    self.checked_path(course_id, child.name)

    def _record_path(self, course_id: str) -> Path:
        return self.checked_path(course_id, RECORD_NAME)

    def _log_path(self, course_id: str) -> Path:
        return self.checked_path(course_id, LOG_NAME)

    def _homework_path(self, course_id: str) -> Path:
        return self.checked_path(course_id, HOMEWORK_DIR, HOMEWORK_ACTIVE)

    def _archive_dir(self, course_id: str) -> Path:
        return self.checked_path(course_id, HOMEWORK_DIR, HOMEWORK_ARCHIVE)

    @contextmanager
    def _locked_course(
        self, course_id: str, *, submission: SubmissionToken | None = None
    ) -> Iterator[None]:
        """Shared exclusion seam for every read and write of an existing course."""
        directory = self.course_dir(course_id)
        self.checked_path(course_id, ".skilling.lock")
        directory.mkdir(parents=True, exist_ok=True)
        with locked_course(directory, timeout=DEFAULT_LOCK_TIMEOUT):
            if submission is not None:
                SubmissionJournal(self.state_root, course_id).validate_token_stream(submission)
            recover_journals(self.state_root, course_id)
            yield

    # ------------------------------------------------------------------------ record

    def get_record(self, learner_id: str, course_id: str) -> tuple[Record, Revision] | None:
        path = self._record_path(course_id)
        if not self.course_dir(course_id).is_dir():
            return None
        with self._locked_course(course_id):
            if not path.is_file():
                return None
            raw = path.read_bytes()
            record = Record.model_validate(yaml.safe_load(raw.decode("utf-8")))
            if record.course_id != course_id:
                raise StatePathError(
                    f"Record course id {record.course_id!r} does not match directory {course_id!r}"
                )
            return record, _revision(raw)

    def put_record(self, record: Record, expected_revision: Revision | None) -> Revision:
        path = self._record_path(record.course_id)
        with self._locked_course(record.course_id):
            actual = _revision(path.read_bytes()) if path.is_file() else None
            if actual != expected_revision:
                raise Conflict(RECORD_NAME, expected_revision, actual)
            text = _dump(record)
            _write_atomic(self._record_path(record.course_id), text)
            return _revision(text.encode("utf-8"))

    # --------------------------------------------------------------------------- log

    def get_log(self, learner_id: str, course_id: str) -> list[CompletionEntry]:
        path = self._log_path(course_id)
        if not self.course_dir(course_id).is_dir():
            return []
        with self._locked_course(course_id):
            if not path.is_file():
                return []
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            return [CompletionEntry.model_validate(item) for item in data]

    def append_completion(self, learner_id: str, course_id: str, entry: CompletionEntry) -> None:
        self._log_path(course_id)
        with self._locked_course(course_id):
            entries = self.get_log(learner_id, course_id)
            entries.append(entry)
            _write_atomic(self._log_path(course_id), _dump_list(entries))

    # ---------------------------------------------------------------------- homework

    def get_homework(
        self, learner_id: str, course_id: str
    ) -> tuple[HomeworkSlot | None, Revision | None]:
        path = self._homework_path(course_id)
        if not self.course_dir(course_id).is_dir():
            return (None, None)
        with self._locked_course(course_id):
            if not path.is_file():
                return None, None
            raw = path.read_bytes()
            slot = HomeworkSlot.model_validate(yaml.safe_load(raw.decode("utf-8")))
            return slot, _revision(raw)

    def put_homework(
        self,
        learner_id: str,
        course_id: str,
        slot: HomeworkSlot | None,
        expected_revision: Revision | None,
    ) -> Revision | None:
        path = self._homework_path(course_id)
        with self._locked_course(course_id):
            actual = _revision(path.read_bytes()) if path.is_file() else None
            if actual != expected_revision:
                raise Conflict(HOMEWORK_ACTIVE, expected_revision, actual)
            if slot is None:
                if path.is_file():
                    self._homework_path(course_id).unlink()
                    _fsync_dir(path.parent)
                return None
            text = _dump(slot)
            _write_atomic(self._homework_path(course_id), text)
            return _revision(text.encode("utf-8"))

    def append_homework_archive(
        self, learner_id: str, course_id: str, entry: HomeworkArchiveEntry
    ) -> None:
        self._archive_dir(course_id)
        if re.fullmatch(r"[0-9]+\.[0-9]+", entry.coordinate) is None:
            raise StatePathError(f"Invalid archive coordinate: {entry.coordinate!r}")
        directory = self._archive_dir(course_id)
        if directory.is_dir():
            for child in directory.iterdir():
                self.checked_path(course_id, HOMEWORK_DIR, HOMEWORK_ARCHIVE, child.name)
        with self._locked_course(course_id):
            stamp = entry.submitted_at.date().isoformat()
            name = f"{entry.coordinate}-{stamp}.yaml"
            path = self.checked_path(course_id, HOMEWORK_DIR, HOMEWORK_ARCHIVE, name)
            # Archives are immutable, so a same-day resubmission of a different instance gets a
            # suffix rather than overwriting what is already there.
            suffix = 2
            while path.exists():
                name = f"{entry.coordinate}-{stamp}-{suffix}.yaml"
                path = self.checked_path(course_id, HOMEWORK_DIR, HOMEWORK_ARCHIVE, name)
                suffix += 1
            _write_atomic(
                self.checked_path(course_id, HOMEWORK_DIR, HOMEWORK_ARCHIVE, name), _dump(entry)
            )

    def get_homework_archive(self, learner_id: str, course_id: str) -> list[HomeworkArchiveEntry]:
        directory = self._archive_dir(course_id)
        if directory.is_dir():
            for child in directory.glob("*.yaml"):
                self.checked_path(course_id, HOMEWORK_DIR, HOMEWORK_ARCHIVE, child.name)
        if not self.course_dir(course_id).is_dir():
            return []
        with self._locked_course(course_id):
            if not directory.is_dir():
                return []
            entries = []
            for child in sorted(directory.glob("*.yaml")):
                path = self.checked_path(course_id, HOMEWORK_DIR, HOMEWORK_ARCHIVE, child.name)
                entries.append(
                    HomeworkArchiveEntry.model_validate(
                        yaml.safe_load(path.read_text(encoding="utf-8"))
                    )
                )
            return sorted(entries, key=lambda e: e.submitted_at)

    # ------------------------------------------------------------------ enumeration

    def list_records(self, course_id: str) -> list[tuple[str, Record]]:
        """Optional for file backends. A state root holds one learner, so this returns at
        most one row — which is still more useful than refusing."""
        found = self.get_record(self.learner_id, course_id)
        return [(self.learner_id, found[0])] if found else []

    def get_completion_receipt(self, learner_id: str, course_id: str) -> CompletionReceipt | None:
        self.checked_path(course_id, "completion.yaml")
        if not self.course_dir(course_id).is_dir():
            return None
        with self._locked_course(course_id):
            return Journal(self.state_root, course_id).receipt()

    def commit_completion(self, commit: CompletionCommit) -> CompletionCommitResult:
        validated = validate_commit(commit, self.state_root)
        with self._locked_course(validated.receipt.course_id):
            return Journal(self.state_root, validated.receipt.course_id).commit(validated)

    def read_runtime_state(self, course_id: str) -> bytes:
        path = self.checked_path(course_id, "scratch.yaml")
        if not self.course_dir(course_id).is_dir():
            return b""
        with self._locked_course(course_id):
            return path.read_bytes() if path.is_file() else b""

    def write_runtime_state(
        self, course_id: str, data: bytes, expected_record_revision: Revision
    ) -> None:
        self.checked_path(course_id, "scratch.yaml")
        path = self._record_path(course_id)
        with self._locked_course(course_id):
            actual = _revision(path.read_bytes()) if path.is_file() else None
            if actual != expected_record_revision:
                raise Conflict(RECORD_NAME, expected_record_revision, actual)
            _write_bytes_atomic(self.checked_path(course_id, "scratch.yaml"), data)

    def read_runtime_snapshot(self, learner_id: str, course_id: str) -> RuntimeSnapshot | None:
        self.ensure_course_paths(course_id)
        if not self.course_dir(course_id).is_dir():
            return None
        with self._locked_course(course_id):
            try:
                return TransitionJournal(self.state_root, course_id).snapshot(learner_id)
            except (ValueError, TypeError, yaml.YAMLError) as exc:
                raise RecoveryRequired(f"Invalid runtime snapshot: {exc}") from exc

    def get_transition_identity(
        self, learner_id: str, course_id: str, key: str
    ) -> TransitionIdentity | None:
        self.ensure_course_paths(course_id)
        if not self.course_dir(course_id).is_dir():
            return None
        with self._locked_course(course_id):
            try:
                return TransitionJournal(self.state_root, course_id).identity(learner_id, key)
            except (ValueError, TypeError, yaml.YAMLError) as exc:
                raise RecoveryRequired(f"Invalid transition receipt: {exc}") from exc

    def commit_transition(self, commit: TransitionCommit) -> TransitionResult:
        validated = validate_transition_commit(commit, self.state_root)
        with self._locked_course(validated.identity.course_id):
            try:
                return TransitionJournal(self.state_root, validated.identity.course_id).commit(
                    validated
                )
            except (ValueError, TypeError, yaml.YAMLError) as exc:
                raise RecoveryRequired(f"Invalid transition intent: {exc}") from exc

    def get_submission_receipt(
        self, learner_id: str, course_id: str, token: str
    ) -> SubmissionReceipt | None:
        identity = SubmissionToken.parse(token)
        if (identity.learner_id, identity.course_id) != (learner_id, course_id):
            raise InvalidSubmissionToken("Token belongs to a different learner/course stream")
        self.ensure_course_paths(course_id)
        if not self.course_dir(course_id).is_dir():
            return None
        with self._locked_course(course_id, submission=identity):
            try:
                found = SubmissionJournal(self.state_root, course_id).load_receipt(token)
                return found.value.value() if found is not None else None
            except (ValueError, TypeError, yaml.YAMLError) as exc:
                raise RecoveryRequired(f"Invalid submission receipt: {exc}") from exc

    def commit_submission(self, commit: SubmissionCommit) -> SubmissionCommitResult:
        validated = validate_submission_commit(commit, self.state_root)
        self.ensure_course_paths(validated.receipt.course_id)
        identity = SubmissionToken.parse(validated.receipt.token)
        if not self.course_dir(validated.receipt.course_id).is_dir():
            raise Conflict("submission record stream", identity.course_version, None)
        with self._locked_course(validated.receipt.course_id, submission=identity):
            try:
                return SubmissionJournal(self.state_root, validated.receipt.course_id).commit(
                    validated
                )
            except (ValueError, TypeError, yaml.YAMLError) as exc:
                raise RecoveryRequired(f"Invalid submission intent: {exc}") from exc
