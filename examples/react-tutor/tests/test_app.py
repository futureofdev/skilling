"""The local demo's identity boundary and application-owned practice evidence."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest
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
def client(tmp_path: Path) -> TestClient:
    agent = Agent(TestModel(custom_output_text="Let's explore this together."))
    return TestClient(app_module.create_app(agent=agent, data_dir=tmp_path))


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
    with pytest.raises(ValueError, match="regular file"):
        work.save("overwrite")
    assert outside.read_text() == "preserve"
