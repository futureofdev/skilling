"""Installed public runtime/HTTP proof, copied outside the source checkout."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import Agent, models
from pydantic_ai.messages import ModelRequest, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

import skilling_tutor
from skilling_tutor import Tutor
from skilling_tutor.fastapi import mount_tutor

models.ALLOW_MODEL_REQUESTS = False


async def streaming_policy(messages, info):
    loaded = any(
        isinstance(part, ToolReturnPart) and part.tool_name == "load_capability"
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )
    if not loaded:
        yield {0: DeltaToolCall(name="load_capability", json_args='{"id":"learn"}')}
    else:
        yield "Installed "
        yield "stream works."


def main() -> None:
    assert skilling_tutor.__file__ is not None
    assert Path(skilling_tutor.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    course = Path(sys.argv[1]).resolve()
    state_dir = Path(sys.argv[2]).resolve()
    tutor = Tutor(
        agent=Agent(FunctionModel(stream_function=streaming_policy)),
        courses={"course": course},
        state_dir=state_dir,
    )
    app = FastAPI()
    mount_tutor(app, tutor, current_user=lambda: "installed-learner")
    with TestClient(app) as client:
        initial = client.get("/api/learn/course/state")
        assert initial.status_code == 200, initial.text
        response = client.post(
            "/api/learn/course/chat",
            json={"message": "Teach me the current material", "request_id": "installed-turn"},
        )
        assert response.status_code == 200
        assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
        frames = [
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        assert not any(frame["type"] == "error" for frame in frames), frames
        assert (
            "".join(frame["delta"] for frame in frames if frame["type"] == "text-delta")
            == "Installed stream works."
        )
        state = next(
            frame["data"]["state"]
            for frame in reversed(frames)
            if frame["type"] == "data-skilling" and frame["data"]["type"] == "state"
        )
        acknowledged = client.post(
            "/api/learn/course/ack", json={"display_id": state["display_id"]}
        )
        assert acknowledged.status_code == 200, acknowledged.text
    print("installed Tutor + FastAPI + native model delta stream PASS")


if __name__ == "__main__":
    main()
