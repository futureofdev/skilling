"""Paired CLI/API roots prove envelope and exact record/scratch behavior agree."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skilling.cli import app
from skilling.session import FileSession, SessionRefusal, SessionSnapshot, load_course

from .test_state_paths import snapshot

runner = CliRunner()
NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


def envelope(view: SessionSnapshot, verb: str) -> dict[str, object]:
    position = view.position
    result: dict[str, object] = {
        "ok": True,
        "verb": verb,
        "course": {
            "id": view.course.id,
            "version": view.course.version,
            "title": view.course.title,
        },
        "position": {
            "phase": position.phase,
            "lesson": position.lesson,
            "beat": position.beat,
            "question_index": position.question_index,
        },
        "beat": {"name": view.beat.name, "content": view.beat.content()},
        "legal_inputs": list(view.legal_inputs),
        "revision": view.revision,
        "completed_count": view.completed_count,
        "lesson_count": view.lesson_count,
    }
    if view.tutor is not None:
        result["tutor"] = {"persona": view.tutor.persona, "tone": list(view.tutor.tone)}
    return result


@pytest.mark.parametrize("fixture", ["clean", "welcome"])
def test_full_teaching_quiz_resume_and_done_equivalence(
    clean_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixture: str,
) -> None:
    source = (
        clean_dir
        if fixture == "clean"
        else Path(__file__).resolve().parents[3] / "examples/welcome-skilling"
    )
    api_course, cli_course = tmp_path / "api-course", tmp_path / "cli-course"
    shutil.copytree(source, api_course)
    shutil.copytree(source, cli_course)
    api_state, cli_state = tmp_path / "api-state", tmp_path / "cli-state"
    monkeypatch.setenv("SKILLING_NOW", NOW.isoformat())
    monkeypatch.setattr("skilling.course._clock.utc_now", lambda: NOW)
    service = FileSession.open(
        load_course(api_course), state_root=api_state, learner_id="local", now=NOW
    )

    def cli(*args: str) -> dict:
        result = runner.invoke(
            app,
            [*args, "--course", str(cli_course), "--state", str(cli_state)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
        return json.loads(result.stdout)

    def same() -> None:
        assert snapshot(api_state) == snapshot(cli_state)
        assert envelope(service.snapshot(), "next") == cli("next")

    assert envelope(service.snapshot(), "next") == cli("next")
    same()
    completed = 0
    revisited = False
    iterations = 0
    while service.snapshot().beat.name != "done":
        iterations += 1
        assert iterations < 150
        beat = service.snapshot().beat.name
        if beat == "complete":
            # B owns completion. The same established CLI completes both paired roots.
            result = runner.invoke(
                app,
                ["complete", "--course", str(api_course), "--state", str(api_state)],
                catch_exceptions=False,
            )
            assert result.exit_code == 0, result.output
            assert json.loads(result.stdout) == cli("complete")
            completed += 1
        elif beat == "quiz":
            question = service.question()
            assert cli("quiz", "next") == {
                "ok": True,
                "question": {
                    "number": question.number,
                    "text": question.text,
                    "options": {o.label: o.text for o in question.options},
                },
            }
            # Deliberately wrong choices exercise remediation for every authored question.
            feedback = service.answer(" d ")
            assert cli("answer", " d ") == {
                "ok": True,
                "correct": feedback.correct,
                "reason": feedback.reason,
                "remediation": {
                    "offered": feedback.offered,
                    "objectives": list(feedback.objectives),
                },
            }
        else:
            legal = service.snapshot().legal_inputs
            if beat == "gate-concept":
                deeper = service.advance("go-deeper")
                assert envelope(deeper.snapshot, "advance") == cli(
                    "advance", "--input", "go-deeper"
                )
                same()
                delivered = service.advance("next")
                assert envelope(delivered.snapshot, "advance") == cli("advance", "--input", "next")
                given = "proceed"
            elif beat == "gate-exercise":
                hinted = service.advance("hint")
                assert envelope(hinted.snapshot, "advance") == cli("advance", "--input", "hint")
                delivered = service.advance("next")
                assert envelope(delivered.snapshot, "advance") == cli("advance", "--input", "next")
                given = "attempted"
            elif beat == "remediate" and "revisit-concept" in legal and not revisited:
                given = "revisit-concept"
                revisited = True
            else:
                given = str(legal[0])
            result = service.advance(given)
            assert envelope(result.snapshot, "advance") == cli("advance", "--input", given)
        same()
        # History/cached Python state is disposable between all operations.
        service = FileSession.open(
            load_course(api_course), state_root=api_state, learner_id="local", now=NOW
        )
    assert completed == service.snapshot().lesson_count


def test_correct_answers_and_keyed_replay_equivalence(
    clean_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_state, cli_state = tmp_path / "api-state", tmp_path / "cli-state"
    monkeypatch.setenv("SKILLING_NOW", NOW.isoformat())
    monkeypatch.setattr("skilling.course._clock.utc_now", lambda: NOW)
    service = FileSession.open(
        load_course(clean_dir), state_root=api_state, learner_id="local", now=NOW
    )

    def cli(*args: str):
        return runner.invoke(
            app,
            [*args, "--course", str(clean_dir), "--state", str(cli_state)],
            catch_exceptions=False,
        )

    for index, given in enumerate(["next", "next", "next", "proceed", "next", "attempted"]):
        key = f"event-{index}"
        result = service.advance(given, event_id=key)
        expected = envelope(result.snapshot, "advance") | {"replayed": result.replayed}
        assert expected == json.loads(cli("advance", "--input", given, "--key", key).stdout)
        assert snapshot(api_state) == snapshot(cli_state)
    result = service.advance("next", event_id="event-0")
    assert envelope(result.snapshot, "advance") | {"replayed": True} == json.loads(
        cli("advance", "--input", "next", "--key", "event-0").stdout
    )
    for label in ("b", "a", "c"):
        feedback = service.answer(label)
        assert feedback.correct
        assert {
            "ok": True,
            "correct": True,
            "reason": feedback.reason,
            "remediation": {"offered": False, "objectives": []},
        } == json.loads(cli("answer", label).stdout)
        assert snapshot(api_state) == snapshot(cli_state)
    before_api, before_cli = snapshot(api_state), snapshot(cli_state)
    with pytest.raises(SessionRefusal) as refusal:
        service.advance("next")
    refused = cli("advance", "--input", "next")
    assert refused.exit_code == 4
    assert json.loads(refused.stdout)["error"] == {
        "code": refusal.value.code,
        "message": str(refusal.value),
    }
    assert snapshot(api_state) == before_api and snapshot(cli_state) == before_cli


def test_cached_upgrade_hint_is_cli_owned_and_preserves_learner_bytes(
    clean_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from .test_cli_runtime import _add_to_workspace

    workspace = tmp_path / "workspace"
    course = _add_to_workspace(workspace, clean_dir, "clean-course")
    # Hint detection intentionally reads only cached version directory names, without a fetch.
    (course.parent / "clean-course@1.0.1").mkdir()
    state = workspace / ".skilling/state"
    monkeypatch.chdir(workspace)
    service = FileSession.open(load_course(course), state_root=state, learner_id="local")
    before = snapshot(state)
    result = runner.invoke(
        app, ["next", "--course", "clean-course", "--state", str(state)], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    expected = envelope(service.snapshot(), "next") | {
        "upgrade": {
            "available": "1.0.1",
            "level": "patch",
            "command": "skilling upgrade --course clean-course",
        }
    }
    assert json.loads(result.stdout) == expected
    assert snapshot(state) == before
