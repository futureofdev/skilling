"""The built launcher uses the same storage environment and course as development."""

import sys

from fastapi.testclient import TestClient
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from skilling_react_example import cli


def test_built_launcher_preserves_environment_and_custom_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("TUTOR_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TUTOR_CONFIG", raising=False)
    monkeypatch.delenv("TUTOR_COURSE_DIR", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["skilling-react-example", "serve", "--model", "test", "--port", "8129"]
    )
    monkeypatch.setattr(cli, "Agent", lambda model: Agent(TestModel()))
    served = []

    def serve(app, **options):
        assert options["host"] == "127.0.0.1" and options["port"] == 8129
        with TestClient(app, base_url="http://127.0.0.1:8129") as client:
            assert client.get("/").status_code == 200
            assert client.get("/api/learn/welcome/state").status_code == 200
            response = client.put(
                "/api/work",
                json={"text": "My own note"},
                headers={"Origin": "http://127.0.0.1:8129"},
            )
            assert response.status_code == 200, response.text
            served.append(True)

    # Use an isolated static fixture so source tests need no Node build.
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>Test UI</title>")
    monkeypatch.setattr(cli, "__file__", str(tmp_path / "cli.py"))
    monkeypatch.setattr(cli.uvicorn, "run", serve)
    cli.main()
    assert served and (tmp_path / "progress.sqlite3").is_file()
    assert (tmp_path / "workspace/showcase/welcome-skilling/goal.md").read_text() == "My own note"
