"""The local demo's identity boundary and application-owned practice evidence."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

MODULE_PATH = Path(__file__).resolve().parents[1] / "app.py"
SPEC = importlib.util.spec_from_file_location("react_tutor_app", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
app_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = app_module
SPEC.loader.exec_module(app_module)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    agent = Agent(TestModel(custom_output_text="Let's explore this together."))
    with TestClient(app_module.create_app(agent=agent, data_dir=tmp_path)) as client:
        yield client


def test_local_identity_rejects_remote_host_and_origin(client: TestClient) -> None:
    assert client.get("/api/work").status_code == 200
    assert client.get("/api/work", headers={"Host": "attacker.example"}).status_code == 403
    assert (
        client.get("/api/work", headers={"Origin": "https://attacker.example"}).status_code == 403
    )
    assert (
        client.put(
            "/api/work", json={"text": "hello"}, headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )


def test_note_is_saved_verbatim_at_fixed_path(client: TestClient, tmp_path: Path) -> None:
    text = "Goal: Learn Python\nTakeaway: I own my progress\nNext action: Write a script\n"
    assert client.put("/api/work", json={"text": text}).status_code == 200
    assert client.get("/api/work").json()["text"] == text
    assert (tmp_path / "workspace/showcase/welcome-skilling/goal.md").read_text() == text
    assert client.put("/api/work", json={"text": text, "path": "../escape"}).status_code == 422
    assert client.put("/api/work", json={"text": " "}).status_code == 422


def test_evidence_inspects_bytes_and_changes_revision(tmp_path: Path) -> None:
    asyncio.run(_evidence_inspects_bytes_and_changes_revision(tmp_path))


async def _evidence_inspects_bytes_and_changes_revision(tmp_path: Path) -> None:
    work = app_module.WorkStore(tmp_path)
    assert await work.evidence("local-demo-learner", "welcome", None) is None
    work.save("Goal: Learn Python\nTakeaway: Save my work\nNext action: Build a script")
    first = await work.evidence("local-demo-learner", "welcome", None)
    assert first is not None and first.checked and first.attested_by
    work.save("Goal: Learn Python\nTakeaway: Save my work\nNext action: Build another script")
    second = await work.evidence("local-demo-learner", "welcome", None)
    assert second is not None and first.revision != second.revision
    assert await work.evidence("another-user", "welcome", None) is None
    work.save("Goal:\nTakeaway: Save my work\nNext action: Build a script")
    empty_goal = await work.evidence("local-demo-learner", "welcome", None)
    assert empty_goal is not None and empty_goal.checked is None
    work.save("An unstructured note")
    incomplete = await work.evidence("local-demo-learner", "welcome", None)
    assert incomplete is not None and incomplete.checked is None and incomplete.attested_by is None


def test_note_symlink_is_rejected(tmp_path: Path) -> None:
    work = app_module.WorkStore(tmp_path / "workspace")
    target = work.target()
    outside = tmp_path / "outside.txt"
    outside.write_text("preserve")
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is unavailable")
    with pytest.raises(ValueError, match="symlink"):
        work.save("overwrite")
    assert outside.read_text() == "preserve"


@pytest.mark.parametrize("kind", ["sqlite", "file"])
def test_configured_learners_keep_scoped_progress_notes_and_feedback_after_restart(tmp_path, kind):
    from skilling.session import Session
    from skilling_react_example.deployment import ProducerConfig

    course = Path(__file__).resolve().parents[2] / "welcome-skilling"
    for name in ("alice", "bob"):
        (tmp_path / name).mkdir()
    config = ProducerConfig.model_validate(
        {
            "namespace": "react-test",
            "backend": {"kind": kind, "path": str(tmp_path / "state")},
            "courses": [{"id": "welcome-skilling", "path": str(course)}],
            "learners": [
                {
                    "selector": name,
                    "label": name.title(),
                    "learner_id": "opaque/" + name,
                    "work_root": str(tmp_path / name),
                    "courses": ["welcome-skilling"],
                }
                for name in ("alice", "bob")
            ],
        }
    )

    def make_app():
        return app_module.create_app(agent=Agent(TestModel()), config=config)

    app = make_app()
    with TestClient(app) as alice:
        bob = TestClient(app)
        assert alice.get("/api/learn/welcome/state").status_code == 401
        assert alice.get("/api/demo").json()["selected"] is None
        bob.get("/api/demo")
        assert alice.cookies != bob.cookies
        assert alice.post("/api/demo/select", json={"selector": "opaque/alice"}).status_code == 403
        assert alice.post("/api/demo/select", json={"selector": "alice"}).status_code == 200
        assert bob.post("/api/demo/select", json={"selector": "bob"}).status_code == 200
        text = "Goal: Learn Python\nTakeaway: Save work\nNext action: Build a script"
        assert alice.put("/api/work", json={"text": text}).status_code == 200
        assert bob.get("/api/work").json()["text"] == ""
        first = alice.get("/api/learn/welcome/state").json()
        assert (
            bob.post("/api/learn/welcome/ack", json={"display_id": first["display_id"]}).status_code
            == 409
        )
        session = app.state.tutor.session(learner_id="opaque/alice", course="welcome")
        assert isinstance(session.service, Session)

        async def reach_feedback():
            for index in range(30):
                state = await session.state()
                if state["feedback"]:
                    return state
                assert state["controls"]
                choice = next(
                    (
                        item
                        for item in state["controls"]
                        if item["id"] in ("next", "proceed", "attempted", "continue")
                    ),
                    state["controls"][0],
                )
                session._action(choice["id"], state["display_id"], str(index))
            raise AssertionError("No quiz feedback reached")

        pending = asyncio.run(reach_feedback())
        bob_state = bob.get("/api/learn/welcome/state").json()
        assert bob_state["feedback"] is None
        assert bob_state["snapshot"]["beat"] == first["snapshot"]["beat"]
    reopened = make_app()
    with TestClient(reopened) as alice:
        alice.get("/api/demo")
        alice.post("/api/demo/select", json={"selector": "alice"})
        assert alice.get("/api/work").json()["text"] == text
        state = alice.get("/api/learn/welcome/state").json()
        assert state["feedback"] is not None
        assert {k: v for k, v in state["feedback"].items() if k != "display_id"} == {
            k: v for k, v in pending["feedback"].items() if k != "display_id"
        }
        assert (
            alice.post(
                "/api/learn/welcome/ack", json={"display_id": pending["display_id"]}
            ).status_code
            == 409
        )
        result = alice.post("/api/learn/welcome/ack", json={"display_id": state["display_id"]})
        assert result.status_code == 200, result.text
        assert result.json()["feedback"] is None


def test_work_identity_revision_changes_when_same_bytes_are_replaced(tmp_path):
    async def check():
        work = app_module.WorkStore(tmp_path)
        text = "Goal: Learn Python\nTakeaway: Save my work\nNext action: Build a script"
        work.save(text)
        first = await work.evidence("local-demo-learner", "welcome", None)
        work.save(text)
        second = await work.evidence("local-demo-learner", "welcome", None)
        assert first.revision != second.revision

    asyncio.run(check())


def test_hardlinked_note_is_not_overwritten(tmp_path):
    import os

    work = app_module.WorkStore(tmp_path / "workspace")
    target = work.target()
    outside = tmp_path / "outside.txt"
    outside.write_text("preserve")
    os.link(outside, target)
    with pytest.raises(ValueError, match="one link"):
        work.save("overwrite")
    assert outside.read_text() == "preserve"


def test_authenticated_dependency_disables_demo_selection_and_unknown_ids(tmp_path):
    async def identity(request: Request) -> str:
        # A controlled fake auth dependency; production must verify its own credentials.
        return request.headers.get("x-test-identity", "unknown")

    app = app_module.create_app(
        agent=Agent(TestModel()), data_dir=tmp_path, identity_dependency=identity
    )
    with TestClient(app) as client:
        assert client.get("/api/demo").json() == {"enabled": False}
        assert client.post("/api/demo/select", json={"selector": "local"}).status_code == 404
        assert client.get("/api/learn/welcome/state").status_code == 403
        assert client.get("/api/work").status_code == 403
        headers = {"x-test-identity": "local-demo-learner"}
        assert client.get("/api/learn/welcome/state", headers=headers).status_code == 200
        assert (
            client.put(
                "/api/work",
                json={"text": "mine"},
                headers=headers | {"Origin": "https://attacker.example"},
            ).status_code
            == 403
        )


def test_local_demo_supports_explicit_cli_origin_and_rejects_unlisted_origin(tmp_path):
    app = app_module.create_app(
        agent=Agent(TestModel()),
        data_dir=tmp_path,
        allowed_origins=("http://localhost:8123",),
    )
    with TestClient(app, base_url="http://localhost:8123") as client:
        assert (
            client.put(
                "/api/work", json={"text": "mine"}, headers={"Origin": "http://localhost:8123"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/api/work", json={"text": "mine"}, headers={"Origin": "http://localhost:8124"}
            ).status_code
            == 403
        )
