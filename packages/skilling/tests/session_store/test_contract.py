"""Shared scope, coherent-CAS and deletion checks against real persistence."""

from __future__ import annotations

import pytest

from skilling.course import Course, Record
from skilling.store import (
    Conflict,
    DeleteSession,
    InitializeSession,
    MutateSession,
    RecordMutationKind,
    SessionDeleted,
    SessionReadKind,
    SessionScope,
    StoreError,
    TransitionCommit,
    TransitionIdentity,
    TransitionSession,
    TransitionVerb,
)

from .conftest import StoreFactory


def test_c01_same_learner_course_is_independent_in_each_namespace(
    clean: Course, store_factory: StoreFactory
) -> None:
    scopes = (
        SessionScope("producer-a", "same", clean.id),
        SessionScope("producer-b", "same", clean.id),
        SessionScope("producer-a", "other", clean.id),
    )
    for scope in scopes:
        store = store_factory(scope)
        assert store.read(scope).kind == SessionReadKind.ABSENT
        store.commit(InitializeSession(scope, None, Record.new(clean, scope.learner_id)))
    original = [store_factory(scope).read(scope) for scope in scopes]
    first = original[0]
    assert first.state is not None and first.session_revision is not None
    store_factory(scopes[0]).commit(DeleteSession(scopes[0], first.session_revision))
    for scope, before in zip(scopes[1:], original[1:], strict=True):
        assert store_factory(scope).read(scope) == before
        assert all(
            record.learner_id == scope.learner_id
            for record in store_factory(scope).list_records(scope.namespace, scope.course_id)
        )


def test_c04_scratch_only_commit_invalidates_whole_session_expectation(
    clean: Course, store_factory: StoreFactory
) -> None:
    scope = SessionScope("producer", "local", clean.id)
    store = store_factory(scope)
    store.commit(InitializeSession(scope, None, Record.new(clean, "local")))
    before = store.read(scope)
    assert before.state is not None and before.session_revision is not None
    state = before.state
    identity = TransitionIdentity(
        "local", clean.id, clean.version, "0.1", TransitionVerb.ADVANCE, "next", None
    )
    store.commit(
        TransitionSession(
            scope,
            before.session_revision,
            TransitionCommit(
                identity, state.record_revision, state.scratch, state.record, b"wrong_count: 1\n"
            ),
        )
    )
    changed = store.read(scope)
    assert changed.state is not None
    assert changed.session_revision != before.session_revision
    assert changed.state.record_revision == state.record_revision
    with pytest.raises(Conflict):
        store.commit(
            MutateSession(
                scope,
                before.session_revision,
                state.record,
                state.record_revision,
                RecordMutationKind.RECORD,
            )
        )
    assert store.read(scope) == changed


def test_c05_delete_survives_reopen_and_refuses_stale_mutations(
    clean: Course, store_factory: StoreFactory
) -> None:
    scope = SessionScope("producer", "local", clean.id)
    store = store_factory(scope)
    initialize = InitializeSession(scope, None, Record.new(clean, "local"))
    store.commit(initialize)
    before = store.read(scope)
    assert before.state is not None and before.session_revision is not None
    stale = MutateSession(
        scope,
        before.session_revision,
        before.state.record,
        before.state.record_revision,
        RecordMutationKind.OBJECTIVE,
    )
    store.commit(DeleteSession(scope, before.session_revision))
    reopened = store_factory(scope)
    tombstone = reopened.read(scope)
    assert tombstone.kind == SessionReadKind.DELETED and tombstone.state is None
    for command in (initialize, stale):
        with pytest.raises(SessionDeleted):
            reopened.commit(command)
        assert reopened.read(scope) == tombstone
    assert reopened.export_progress(scope) is None
    assert reopened.list_records(scope.namespace, scope.course_id) == ()


def test_c06_mismatched_record_never_initializes(
    clean: Course, store_factory: StoreFactory
) -> None:
    scope = SessionScope("producer", "local", clean.id)
    store = store_factory(scope)
    with pytest.raises(StoreError):
        store.commit(InitializeSession(scope, None, Record.new(clean, "foreign")))
    assert store.read(scope).kind == SessionReadKind.ABSENT
