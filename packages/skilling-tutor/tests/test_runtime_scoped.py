"""Scoped persistence uses captured handles and drains in-flight commits on cancellation."""

import asyncio
import threading

import pytest
import test_runtime as journeys

from skilling.session import Session
from skilling.store import FileSessionStore, SessionScope, SQLiteSessionStore
from skilling_tutor import Tutor, TutorSessionError


@pytest.mark.parametrize("kind", ["sqlite", "file"])
@pytest.mark.parametrize(
    "journey",
    [
        journeys.test_one_displayed_review_can_confirm_each_objective_once,
        journeys.test_homework_review_requires_inspected_evidence_and_explicit_submission,
    ],
)
def test_scoped_reviews_and_submission_use_bound_handles(tmp_path, monkeypatch, kind, journey):
    original = journeys.tutor_at
    sqlite = SQLiteSessionStore.open(tmp_path / "state.sqlite3") if kind == "sqlite" else None

    def factory(directory, **kwargs):
        tutor = original(directory, **kwargs)

        def session(learner, alias, course):
            work = directory / "work" / learner
            work.mkdir(parents=True, exist_ok=True)
            scope = SessionScope("runtime-test", learner, course.id)
            store = sqlite or FileSessionStore.open(
                directory / "state" / learner, namespace=scope.namespace, learner_id=learner
            )
            return Session.open(course.root, store=store, scope=scope, work_root=work)

        return Tutor(
            agent=tutor.agent,
            courses={key: value.root for key, value in tutor.courses.items()},
            session_factory=session,
            evidence_provider=tutor.evidence_provider,
            review_agent=tutor.review_agent,
        )

    monkeypatch.setattr(journeys, "tutor_at", factory)
    try:
        journey(tmp_path)
    finally:
        if sqlite:
            sqlite.close()


def test_cancelled_worker_keeps_session_lock_until_commit_finishes(tmp_path):
    async def run():
        session = journeys.tutor_at(tmp_path, lock_timeout=0.02).session(
            learner_id="a", course="welcome"
        )
        started, release = threading.Event(), threading.Event()
        committed = []

        def commit():
            started.set()
            assert release.wait(timeout=3)
            committed.append("durable")

        async def mutation():
            async with session._locked():
                await session._io(commit)

        pending = asyncio.create_task(mutation())
        try:
            assert await asyncio.to_thread(started.wait, 1)
            # The loop continues while the store worker blocks.
            await asyncio.sleep(0)
            pending.cancel()
            await asyncio.sleep(0)
            pending.cancel()
            with pytest.raises(TutorSessionError, match="still running"):
                await session.state()
            assert not pending.done() and committed == []
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert committed == ["durable"]
        assert await session.state()

    asyncio.run(run())
