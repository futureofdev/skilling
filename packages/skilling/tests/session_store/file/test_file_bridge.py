"""Legacy bytes, immutable root ownership and stopped relocation remain compatible."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from skilling.course import Course, Record
from skilling.store import (
    FileProgressStore,
    FileSessionStore,
    InitializeSession,
    SessionReadKind,
    SessionScope,
    StoreError,
)

from ...test_session import snapshot


def test_binding_is_immutable_before_foreign_recovery(tmp_path: Path) -> None:
    root = tmp_path / "state"
    FileSessionStore.open(root, namespace="producer-a", learner_id="same-learner")
    before = snapshot(root)
    for namespace, learner in (("producer-b", "same-learner"), ("producer-a", "different")):
        with pytest.raises(StoreError):
            FileSessionStore.open(root, namespace=namespace, learner_id=learner, bind_existing=True)
        assert snapshot(root) == before


def test_nonempty_legacy_root_needs_explicit_attachment(clean: Course, tmp_path: Path) -> None:
    root = tmp_path / "state"
    legacy = FileProgressStore(root)
    original = Record.new(clean, "local")
    legacy.put_record(original, None)
    before = snapshot(root)
    with pytest.raises(StoreError):
        FileSessionStore.open(root, namespace="producer", learner_id="local")
    assert snapshot(root) == before
    store = FileSessionStore.open(
        root, namespace="producer", learner_id="local", bind_existing=True
    )
    read = store.read(SessionScope("producer", "local", clean.id))
    assert read.kind == SessionReadKind.LIVE and read.state is not None
    assert read.state.record == original
    for path, raw in before.items():
        assert snapshot(root)[path] == raw


def test_legacy_attachment_checks_existing_learner(clean: Course, tmp_path: Path) -> None:
    root = tmp_path / "state"
    FileProgressStore(root).put_record(Record.new(clean, "original"), None)
    before = snapshot(root)
    with pytest.raises(StoreError):
        FileSessionStore.open(root, namespace="producer", learner_id="other", bind_existing=True)
    assert snapshot(root) == before


def test_stopped_relocation_preserves_scope_and_record(clean: Course, tmp_path: Path) -> None:
    root = tmp_path / "state"
    scope = SessionScope("producer", "local", clean.id)
    store = FileSessionStore.open(root, namespace=scope.namespace, learner_id=scope.learner_id)
    store.commit(InitializeSession(scope, None, Record.new(clean, "local")))
    before = store.read(scope)
    destination = tmp_path / "relocated"
    shutil.move(root, destination)
    reopened = FileSessionStore.open(destination, namespace=scope.namespace, learner_id="local")
    assert reopened.read(scope) == before
    with pytest.raises(StoreError):
        FileSessionStore.open(destination, namespace="other", learner_id="local")


def test_conflicting_first_attachment_has_one_winner(tmp_path: Path) -> None:
    root = tmp_path / "contested"
    workers = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "packages.skilling.tests.session_store.file.worker",
                str(root),
                namespace,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for namespace in ("producer-a", "producer-b")
    ]
    try:
        for process in workers:
            assert process.stdout is not None
            assert process.stdout.readline().strip() == "ready"
        for process in workers:
            assert process.stdin is not None
            process.stdin.write("go\n")
            process.stdin.flush()
        outcomes = []
        for process in workers:
            out, err = process.communicate(timeout=20)
            assert process.returncode == 0, err
            outcomes.append(out.strip())
        assert sorted(outcomes) == ["bound", "refused"]
    finally:
        for process in workers:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


def test_foreign_scope_is_refused_before_access(clean: Course, tmp_path: Path) -> None:
    root = tmp_path / "state"
    scope = SessionScope("producer", "local", clean.id)
    store = FileSessionStore.open(root, namespace="producer", learner_id="local")
    store.commit(InitializeSession(scope, None, Record.new(clean, "local")))
    before = snapshot(root)
    with pytest.raises(StoreError):
        store.read(SessionScope("other", "local", clean.id))
    assert snapshot(root) == before
