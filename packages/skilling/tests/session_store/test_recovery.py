"""Refusals never publish a partial repair or bypass explicit version upgrade."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from skilling.course import Course, Record
from skilling.store import (
    FileSessionStore,
    InitializeSession,
    MutateSession,
    RecordMutationKind,
    RecoveryRequired,
    SessionScope,
)
from skilling.store._protocol._file_source import Initialization


def test_record_mutation_cannot_change_version(clean: Course, tmp_path: Path) -> None:
    scope = SessionScope("producer", "local", clean.id)
    store = FileSessionStore.open(
        tmp_path / "state", namespace=scope.namespace, learner_id=scope.learner_id
    )
    store.commit(InitializeSession(scope, None, Record.new(clean, "local"), "a" * 64))
    before = store.read(scope)
    assert before.state is not None and before.session_revision is not None
    changed = before.state.record.model_copy(update={"course_version": "9.9.9"})
    for kind in RecordMutationKind:
        with pytest.raises(RecoveryRequired):
            store.commit(
                MutateSession(
                    scope, before.session_revision, changed, before.state.record_revision, kind
                )
            )
        assert store.read(scope) == before


def test_corrupt_source_is_typed_and_does_not_repair(clean: Course, tmp_path: Path) -> None:
    scope = SessionScope("producer", "local", clean.id)
    root = tmp_path / "state"
    store = FileSessionStore.open(root, namespace=scope.namespace, learner_id=scope.learner_id)
    store.commit(InitializeSession(scope, None, Record.new(clean, "local")))
    metadata = root / clean.id / "session-source.json"
    metadata.write_bytes(b"{}")
    with pytest.raises(RecoveryRequired):
        store.read(scope)
    assert metadata.read_bytes() == b"{}"


@pytest.mark.parametrize(
    "sibling, raw",
    [
        ("completion.yaml", b"kind: invalid"),
        ("scratch.yaml", b"wrong_count: invalid\n"),
        ("completed.yaml", b"[]"),
    ],
)
def test_corrupt_journal_prevents_initialization_recovery(
    clean: Course, tmp_path: Path, sibling: str, raw: bytes
) -> None:
    scope = SessionScope("producer", "local", clean.id)
    root = tmp_path / "state"
    store = FileSessionStore.open(root, namespace=scope.namespace, learner_id=scope.learner_id)
    directory = root / clean.id
    directory.mkdir()
    intent = directory / "session-initialize.json"
    intent.write_bytes(
        Initialization(
            version=1,
            source=None,
            record_yaml=yaml.safe_dump(Record.new(clean, "local").model_dump(mode="json")),
        )
        .model_dump_json()
        .encode()
    )
    (directory / sibling).write_bytes(raw)
    original = intent.read_bytes()
    with pytest.raises(RecoveryRequired):
        store.read(scope)
    assert intent.read_bytes() == original
    assert not (directory / "record.yaml").exists()


def test_initialization_recovers_published_source_and_unpublished_temp(
    clean: Course, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from skilling.store import ReconciliationRequired
    from skilling.store._protocol import _file_source

    root = tmp_path / "state"
    scope = SessionScope("producer", "local", clean.id)
    store = FileSessionStore.open(root, namespace=scope.namespace, learner_id=scope.learner_id)
    write = _file_source._write_bytes_atomic

    def lose_response(path: Path, raw: bytes) -> None:
        write(path, raw)
        if path.name == _file_source.SOURCE:
            raise OSError("simulated interruption after source publication")

    monkeypatch.setattr(_file_source, "_write_bytes_atomic", lose_response)
    with pytest.raises(ReconciliationRequired):
        store.commit(InitializeSession(scope, None, Record.new(clean, "local"), "a" * 64))
    directory = root / clean.id
    assert (directory / _file_source.INTENT).exists()
    assert not (directory / "record.yaml").exists()
    (directory / ".record.yaml.unpublished.tmp").write_bytes(b"unfinished")
    monkeypatch.setattr(_file_source, "_write_bytes_atomic", write)
    recovered = store.read(scope)
    assert recovered.state is not None and recovered.state.source_digest == "a" * 64
    assert not (directory / _file_source.INTENT).exists()


def test_boolean_file_schema_version_is_not_integer() -> None:
    from pydantic import ValidationError

    from skilling.store._protocol._file_delete import Tombstone
    from skilling.store._protocol._file_session import RootBinding
    from skilling.store._protocol._file_source import SourceBinding

    with pytest.raises(ValidationError):
        RootBinding.model_validate({"version": True, "namespace": "p", "learner_id": "l"})
    for boundary in (SourceBinding, Tombstone):
        with pytest.raises(ValidationError):
            boundary.model_validate(
                {
                    "version": True,
                    "namespace": "p",
                    "learner_id": "l",
                    "course_id": "test",
                    **(
                        {"course_version": "1.0.0", "digest": "a" * 64}
                        if boundary is SourceBinding
                        else {"generation": "g"}
                    ),
                }
            )


def test_same_version_source_change_cannot_be_accepted_as_noop_upgrade(
    clean_dir: Path, tmp_path: Path
) -> None:
    from skilling.session import Session, SessionRefusal

    course = Course.load(clean_dir)
    scope = SessionScope("producer", "local", course.id)
    store = FileSessionStore.open(
        tmp_path / "state", namespace=scope.namespace, learner_id=scope.learner_id
    )
    work = tmp_path / "work"
    work.mkdir()
    session = Session.open(clean_dir, store=store, scope=scope, work_root=work)
    before = store.read(scope)
    manifest = clean_dir / "course.yaml"
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    with pytest.raises(SessionRefusal, match="same-version"):
        session.upgrade()
    with pytest.raises(SessionRefusal, match="same-version"):
        Session.upgrade_at(clean_dir, store=store, scope=scope)
    assert store.read(scope) == before
