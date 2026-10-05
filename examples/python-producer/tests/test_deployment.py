"""Configured identities exercise real stores and HTTP custody without real providers."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from journey import BASE, NOTE, SyntheticTutor

from skilling.store import SessionScope
from skilling_producer_example import Deployment, ProducerConfig, create_app

COURSE = Path(__file__).resolve().parents[2] / "welcome-skilling"


def configuration(tmp_path, kind="sqlite", namespace="demo"):
    roots = [tmp_path / name for name in ("alice", "bob")]
    for root in roots:
        root.mkdir(exist_ok=True)
    return ProducerConfig.model_validate(
        {
            "namespace": namespace,
            "backend": {"kind": kind, "path": str(tmp_path / "state")},
            "courses": [{"id": "welcome-skilling", "path": str(COURSE)}],
            "learners": [
                {
                    "selector": name,
                    "label": name.title(),
                    "learner_id": f"opaque/{name}",
                    "work_root": str(root),
                    "courses": ["welcome-skilling"],
                }
                for name, root in zip(("alice", "bob"), roots, strict=True)
            ],
        }
    )


def post(client, state, path, body):
    return client.post(
        path, json=body, headers={"Origin": BASE, "X-CSRF-Token": state["csrf_token"]}
    )


def select(client, selector):
    state = client.get("/api/state").json()
    result = post(
        client, state, "/api/demo/select", {"selector": selector, "course_id": "welcome-skilling"}
    )
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.parametrize("kind", ["sqlite", "file"])
def test_two_browsers_scope_handles_notes_and_restart(tmp_path, kind):
    config = configuration(tmp_path, kind)
    deployment = Deployment.configure(config, SyntheticTutor().runner)
    app = create_app(deployment)
    bob = TestClient(app, base_url=BASE)
    with TestClient(app, base_url=BASE) as alice:
        unselected = alice.get("/api/state").json()
        assert unselected["snapshot"] is None
        assert deployment.backend is not None
        absent = deployment.backend.for_scope(
            SessionScope("demo", "opaque/alice", "welcome-skilling")
        ).read(SessionScope("demo", "opaque/alice", "welcome-skilling"))
        assert absent.state is None
        assert (
            post(
                alice,
                unselected,
                "/api/demo/select",
                {"selector": "opaque/alice", "course_id": "welcome-skilling"},
            ).status_code
            == 403
        )
        a, b = select(alice, "alice"), select(bob, "bob")
        assert a["csrf_token"] != b["csrf_token"]
        assert alice.cookies != bob.cookies
        assert post(bob, a, "/api/note/save", {"text": NOTE}).status_code == 403
        a = post(alice, a, "/api/note/save", {"text": NOTE}).json()
        assert bob.get("/api/state").json()["note"] is None
        assert (
            post(
                bob,
                b,
                "/api/actions/next",
                {"display_id": a["display_id"], "event_id": "cross-browser"},
            ).status_code
            == 409
        )
        control = a["controls"][0]["id"]
        advanced = post(
            alice,
            a,
            f"/api/actions/{control}",
            {"display_id": a["display_id"], "event_id": "alice-next"},
        )
        assert advanced.status_code == 200, advanced.text
        a = advanced.json()
        assert a["demo"]["selected"] == "Alice"
        assert bob.get("/api/state").json()["snapshot"] == b["snapshot"]
        switch = post(
            alice, a, "/api/demo/select", {"selector": "bob", "course_id": "welcome-skilling"}
        )
        assert switch.status_code == 200, switch.text
        switched = switch.json()
        assert switched["note"] is None and switched["messages"] == []
        assert switched["csrf_token"] != a["csrf_token"]
        assert (
            post(
                alice,
                switched,
                "/api/actions/next",
                {"display_id": a["display_id"], "event_id": "copied"},
            ).status_code
            == 409
        )
        a = select(alice, "alice")
        persisted = a["snapshot"]
        assert a["note"]["text"] == NOTE
    bob.close()
    assert deployment.backend is None and deployment.bindings == {}
    reopened = Deployment.configure(config, SyntheticTutor().runner)
    with TestClient(create_app(reopened), base_url=BASE) as client:
        state = select(client, "alice")
        assert state["snapshot"] == persisted
        assert state["note"]["text"] == NOTE
        assert state["messages"] == [] and state["review"] is None
        assert "fresh evidence" in state["history_notice"]


def test_namespace_cookie_and_state_isolation(tmp_path):
    config = configuration(tmp_path)
    first = Deployment.configure(config, SyntheticTutor().runner)
    other_root = tmp_path / "other-namespace"
    other_root.mkdir()
    other = configuration(other_root, namespace="other")
    second = Deployment.configure(
        other.model_copy(update={"backend": config.backend}), SyntheticTutor().runner
    )
    with (
        TestClient(create_app(first), base_url=BASE) as a,
        TestClient(create_app(second), base_url=BASE) as b,
    ):
        left, right = select(a, "alice"), select(b, "alice")
        assert set(a.cookies.keys()).isdisjoint(b.cookies.keys())
        assert post(b, left, "/api/note/save", {"text": NOTE}).status_code == 403
        left = post(a, left, "/api/note/save", {"text": NOTE}).json()
        assert b.get("/api/state").json()["note"] is None
        control = left["controls"][0]["id"]
        changed = post(
            a,
            left,
            f"/api/actions/{control}",
            {"display_id": left["display_id"], "event_id": "advance"},
        )
        assert changed.status_code == 200, changed.text
        assert b.get("/api/state").json()["snapshot"] == right["snapshot"]


def test_configuration_rejects_overlap_and_request_paths(tmp_path):
    config = configuration(tmp_path)
    bad = config.model_dump()
    bad["learners"][1]["work_root"] = bad["learners"][0]["work_root"]
    with pytest.raises(ValueError, match="overlap"):
        Deployment.configure(ProducerConfig.model_validate(bad), SyntheticTutor().runner)
    app = create_app(Deployment.configure(config, SyntheticTutor().runner))
    with TestClient(app, base_url=BASE) as client:
        state = client.get("/api/state").json()
        result = post(
            client,
            state,
            "/api/demo/select",
            {
                "selector": "alice",
                "course_id": "welcome-skilling",
                "learner_id": "victim",
                "work_root": "/",
            },
        )
        assert result.status_code == 400
        assert (
            post(
                client, state, "/api/demo/select", {"selector": "alice", "course_id": "unknown"}
            ).status_code
            == 403
        )


def test_configured_canonical_feedback_restart_and_review_staleness(tmp_path):
    from skilling.course import parse_lesson, parse_quiz
    from skilling.session import Session, load_course

    config = configuration(tmp_path)
    model = SyntheticTutor()
    deployment = Deployment.configure(config, model.runner)
    with TestClient(create_app(deployment), base_url=BASE) as client:
        state = select(client, "alice")
        state = post(client, state, "/api/note/save", {"text": NOTE}).json()
        wrong = False
        for _ in range(30):
            snapshot = state["snapshot"]
            beat = snapshot["beat"]["name"]
            if state["feedback"]:
                if wrong:
                    original = state["feedback"]
                    break
                state = post(
                    client, state, "/api/feedback/ack", {"display_id": state["display_id"]}
                ).json()
                continue
            if beat == "gate-exercise":
                state = post(
                    client,
                    state,
                    "/api/review/objectives",
                    {
                        "evidence": "Synthetic fixture evidence: I explained saved progress "
                        "and wrote my goal note."
                    },
                ).json()
                review = state["review"]
                assert review is not None
                post(client, state, "/api/review/ack", {"review_id": review["id"]})
                changed = post(
                    client, state, "/api/note/save", {"text": NOTE + "Edited since review\n"}
                ).json()
                assert changed["review"] is None
                assert (
                    post(
                        client,
                        changed,
                        "/api/review/confirm",
                        {"review_id": review["id"], "objective_id": review["objective_ids"][0]},
                    ).status_code
                    == 409
                )
                state = changed
            if beat == "quiz":
                course = load_course(COURSE)
                lesson = course.lesson_at(
                    f"{snapshot['position']['phase']}.{snapshot['position']['lesson']}"
                )
                assert lesson is not None
                quiz = parse_lesson(lesson.path).section("quiz")
                assert quiz is not None
                answer = parse_quiz(quiz.body, quiz.line)[
                    snapshot["beat"]["number"] - 1
                ].answer_label
                label = next(
                    option["label"]
                    for option in snapshot["beat"]["options"]
                    if option["label"] != answer
                )
                control = f"answer-{label}"
                wrong = True
            else:
                choices = [item["id"] for item in state["controls"]]
                control = next(
                    (
                        item
                        for item in ("proceed", "attempted", "continue", "next")
                        if item in choices
                    ),
                    choices[0],
                )
            response = post(
                client,
                state,
                f"/api/actions/{control}",
                {"display_id": state["display_id"], "event_id": f"fixture-{_}"},
            )
            assert response.status_code == 200, response.text
            state = response.json()
        else:
            raise AssertionError("quiz not reached")
        # Safe tutor projection contains no scope or persistence handle.
        assert model.contexts
        import json

        projected = json.dumps(model.contexts)
        for secret in ("opaque/alice", str(tmp_path), "session_revision", "submission_token"):
            assert secret not in projected
    reopened = Deployment.configure(config, SyntheticTutor().runner)
    with TestClient(create_app(reopened), base_url=BASE) as client:
        state = select(client, "alice")
        assert state["feedback"]["reason"] == original["reason"]
        assert state["controls"] == [] and state["messages"] == []
        binding = next(iter(reopened.bindings.values()))
        assert binding.controller is not None
        assert isinstance(binding.controller.session, Session)
        pending = binding.controller.session.pending_feedback()
        assert pending is not None
        response = post(client, state, "/api/feedback/ack", {"display_id": state["display_id"]})
        assert response.status_code == 200, response.text
        assert binding.controller.session.pending_feedback() is None


@pytest.mark.parametrize(
    "setting", ['dsn_env = "SENTINEL:secret"', 'dsn_env = "DB_DSN"\npassword = "SENTINEL-secret"']
)
def test_cli_configuration_diagnostics_hide_secret_values(tmp_path, setting):
    import subprocess
    import sys

    from pydantic import ValidationError

    from skilling_producer_example._deployment import BackendConfig

    with pytest.raises(ValidationError) as invalid:
        BackendConfig.model_validate({"kind": "postgres", "dsn_env": "SENTINEL:secret"})
    assert "SENTINEL" not in str(invalid.value)
    config = tmp_path / "invalid.toml"
    config.write_text('[backend]\nkind = "postgres"\n' + setting + "\n")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from skilling_producer_example._cli import main; main()",
            "serve",
            "--config",
            str(config),
            "--model",
            "test",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 2
    assert "SENTINEL" not in result.stdout + result.stderr
    assert "validation" in result.stderr.lower()


def test_overlapping_same_learner_saves_publish_only_complete_utf8(tmp_path, monkeypatch):
    import os
    import stat
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from skilling_producer_example._controller._note import GoalNote

    if os.name == "nt":
        pytest.skip("Win32 leaf guard refuses a second writer before the POSIX overlap barrier")
    note_a, note_b = GoalNote.open(tmp_path), GoalNote.open(tmp_path)
    note_a.save("original")
    barrier = Barrier(2)
    real_fsync = os.fsync

    def overlapping(fd):
        real_fsync(fd)
        if stat.S_ISREG(os.fstat(fd).st_mode):
            barrier.wait(timeout=10)

    monkeypatch.setattr(os, "fsync", overlapping)
    texts = ("星" * 3, "B" * 100)

    def save(pair):
        note, text = pair
        try:
            return note.save(text).text
        except ValueError:
            return None  # A concurrent publication can invalidate the observed leaf.

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(save, zip((note_a, note_b), texts, strict=True)))
    assert any(result in texts for result in results)
    assert note_a.inspect().text in texts
    assert list((tmp_path / "showcase/welcome-skilling").glob(".goal-*.tmp")) == []
