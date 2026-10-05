"""Installed reference app proof; synthetic learner/model evidence, no paid provider."""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from skilling_react_example.app import create_app
from skilling_react_example.deployment import ProducerConfig

NOTE = "Goal: Learn Python\nTakeaway: Save my own work\nNext action: Write a small script\n"
BASE = "http://127.0.0.1:8000"


def configured_journey(
    workspace: Path, course_source: Path, profile: str, config_path: Path | None
) -> dict[str, object]:
    workspace.mkdir(parents=True, exist_ok=False)
    for name in ("alice", "bob"):
        (workspace / name).mkdir()
    settings = json.loads(config_path.read_text()) if config_path else {}
    if profile in ("file", "sqlite"):
        backend = {"kind": profile, "path": str(workspace / "state")}
    elif profile == "postgres":
        backend = {
            "kind": profile,
            "dsn_env": settings["dsn_env"],
            "schema_name": "app_" + secrets.token_hex(12),
        }
    else:
        backend = {
            "kind": profile,
            "bucket": settings["bucket"],
            "prefix": settings["prefix"].rstrip("/") + "/app-" + secrets.token_hex(12) + "/",
            "region": settings["region"],
            "endpoint_url": settings.get("endpoint_url"),
            "profile_env": settings.get("profile_env"),
        }
    config = ProducerConfig.model_validate(
        {
            "namespace": "installed-react",
            "backend": backend,
            "courses": [{"id": "welcome-skilling", "path": str(course_source)}],
            "learners": [
                {
                    "selector": name,
                    "label": name.title(),
                    "learner_id": "opaque/" + name,
                    "work_root": str(workspace / name),
                    "courses": ["welcome-skilling"],
                }
                for name in ("alice", "bob")
            ],
        }
    )

    async def stream(messages, info):
        loaded = any(
            isinstance(part, ToolReturnPart) and part.tool_name == "load_capability"
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
        )
        if not loaded:
            yield {0: DeltaToolCall(name="load_capability", json_args='{"id":"learn"}')}
        else:
            yield "Synthetic teaching."

    def app():
        return create_app(agent=Agent(FunctionModel(stream_function=stream)), config=config)

    def select(client: TestClient, name: str) -> dict:
        assert client.get("/api/demo").status_code == 200
        result = client.post("/api/demo/select", json={"selector": name})
        assert result.status_code == 200, result.text
        result = client.get("/api/learn/welcome/state")
        assert result.status_code == 200, result.text
        return result.json()

    application = app()
    with TestClient(application, base_url=BASE) as alice:
        bob = TestClient(application, base_url=BASE)
        try:
            state = select(alice, "alice")
            bob_state = select(bob, "bob")
            assert alice.cookies != bob.cookies
            assert alice.put("/api/work", json={"text": NOTE}).status_code == 200
            assert bob.get("/api/work").json()["text"] == ""
            assert (
                bob.post(
                    "/api/learn/welcome/ack", json={"display_id": state["display_id"]}
                ).status_code
                == 409
            )
            for index in range(30):
                if state["feedback"]:
                    break
                control = next(
                    (
                        item
                        for item in state["controls"]
                        if item["id"] in ("next", "proceed", "attempted", "continue")
                    ),
                    state["controls"][0],
                )
                response = alice.post(
                    "/api/learn/welcome/chat",
                    json={
                        "request_id": f"installed-{index}",
                        "message": control["label"],
                        "control": control["id"],
                        "display_id": state["display_id"],
                    },
                )
                assert response.status_code == 200, response.text
                assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
                assert '"type":"error"' not in response.text, response.text
                state = alice.get("/api/learn/welcome/state").json()
            assert state["feedback"] is not None
            assert bob.get("/api/learn/welcome/state").json()["snapshot"] == bob_state["snapshot"]
            persisted = state["snapshot"]
        finally:
            bob.close()
    with TestClient(app(), base_url=BASE) as alice:
        resumed = select(alice, "alice")
        assert resumed["snapshot"] == persisted
        assert resumed["feedback"] is not None
        assert alice.get("/api/work").json()["text"] == NOTE
        assert resumed["review"] is None
        assert (
            alice.post(
                "/api/learn/welcome/ack", json={"display_id": state["display_id"]}
            ).status_code
            == 409
        )
        acknowledged = alice.post(
            "/api/learn/welcome/ack", json={"display_id": resumed["display_id"]}
        )
        assert acknowledged.status_code == 200, acknowledged.text
        assert acknowledged.json()["feedback"] is None
    return {
        "profile": profile,
        "two_browser_isolation": True,
        "restart": True,
        "canonical_feedback": True,
        "synthetic": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--course-source", type=Path, required=True)
    parser.add_argument(
        "--store-profile", choices=("file", "sqlite", "postgres", "s3"), default="sqlite"
    )
    parser.add_argument("--store-config", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            configured_journey(
                args.workspace, args.course_source, args.store_profile, args.store_config
            ),
            sort_keys=True,
        )
    )
