"""Core-only installed SQLite create/restart/feedback/backup probe, outside checkout."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


def probe(fixture: Path, case: Path, tool_dir: Path, checkout_sentinel: Path) -> None:
    import skilling
    from skilling.course import Course, parse_lesson, parse_quiz
    from skilling.session import Session
    from skilling.store import ActionOperation, SessionScope, SQLiteSessionStore

    assert not checkout_sentinel.exists(), checkout_sentinel
    imported = Path(skilling.__file__).resolve()
    assert imported.is_relative_to(Path(sys.prefix).resolve()), imported
    assert Path(sys.prefix).resolve().is_relative_to(tool_dir.resolve()), sys.prefix
    for dependency in ("pydantic_ai", "skilling_tutor", "psycopg", "psycopg_pool", "boto3"):
        assert importlib.util.find_spec(dependency) is None, dependency
    case.mkdir()
    course = Course.load(fixture)
    scope = SessionScope("installed-probe", "synthetic-learner", course.id)
    path = case / "sessions.db"
    work = case / "work"
    work.mkdir()
    store = SQLiteSessionStore.open(path)
    session = Session.open(fixture, store=store, scope=scope, work_root=work)
    for step in range(40):
        snapshot = session.snapshot()
        if snapshot.beat.name == "quiz":
            break
        payload = {"gate-concept": "proceed", "gate-exercise": "attempted"}.get(
            snapshot.beat.name, "next"
        )
        session.act(
            session.capture_action(
                snapshot,
                event_id=f"installed-advance-{step}",
                operation=ActionOperation.ADVANCE,
                payload=payload,
            )
        )
    else:
        raise AssertionError("Installed fixture did not reach a quiz")
    question = session.question()
    lesson = course.lesson_at(snapshot.position.coordinate)
    assert lesson
    section = parse_lesson(lesson.path).section("quiz")
    assert section
    authored = next(
        q for q in parse_quiz(section.body, section.body_line) if q.number == question.number
    )
    wrong = next(
        option.label for option in authored.options if option.label != authored.answer_label
    )
    action = session.capture_action(
        snapshot, event_id="installed-answer", operation=ActionOperation.ANSWER, payload=wrong
    )
    accepted = session.act(action)
    original_feedback = session.pending_feedback()
    assert original_feedback and not original_feedback.outcome.correct
    accepted_state = store.read(scope)
    store.close()
    reopened = SQLiteSessionStore.open(path)
    feedback = Session.pending_feedback_at(store=reopened, scope=scope)
    assert feedback and feedback.outcome == original_feedback.outcome
    backup = case / "backup.db"
    reopened.backup(backup)
    with SQLiteSessionStore.restore(backup, case / "restored.db") as restored:
        assert restored.read(scope) == accepted_state
        resumed = Session.open(fixture, store=restored, scope=scope, work_root=work)
        replay = resumed.act(action)
        assert replay.replayed and replay.original_outcome == accepted.original_outcome
        resumed.acknowledge_feedback(feedback.feedback_id)
        acknowledged = restored.read(scope)
        assert acknowledged.state
        assert acknowledged.state.record_revision == feedback.revision
        assert acknowledged.session_revision != accepted_state.session_revision
        assert resumed.pending_feedback() is None
    reopened.close()
    print(
        json.dumps(
            {
                "import": str(imported),
                "python": sys.version,
                "sqlite": sqlite3.sqlite_version,
                "core_only": True,
                "restart_feedback": True,
                "native_backup_restore": True,
                "old_key_replay": True,
                "independent_ack_revision": True,
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--tool-dir", required=True, type=Path)
    parser.add_argument("--checkout-sentinel", required=True, type=Path)
    args = parser.parse_args()
    probe(
        args.fixture.resolve(),
        args.case.resolve(),
        args.tool_dir.resolve(),
        args.checkout_sentinel.resolve(),
    )


if __name__ == "__main__":
    main()
