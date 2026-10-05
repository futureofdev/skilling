"""Standalone synthetic installed-app journey: real native tutor, never real providers."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic_ai import models
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from skilling.session import FileSession, load_course
from skilling.workspace import import_local_course, load_manifest
from skilling_producer_example import ProducerController, create_app
from skilling_producer_example._controller import ReviewKind
from skilling_producer_example._tutor import BrowserTutor
from skilling_tutor import SkillingRunner

models.ALLOW_MODEL_REQUESTS = False
BASE = "http://127.0.0.1:8765"
NOTE = (
    "Goal: Learn stellar spectra\nTakeaway: Saved position survives chats\n"
    "Next action: Explain absorption lines\n"
)


class SyntheticTutor:
    """Native skill loading and complete advice derived from actual copied contexts."""

    def __init__(self):
        self.contexts: list[dict] = []
        self.verdict = "supported"
        self.fail = False
        self.cancel = False
        self.on_context: Callable[[], None] | None = None

    async def respond(self, messages, info: AgentInfo) -> ModelResponse:
        if self.cancel:
            import asyncio

            raise asyncio.CancelledError()
        if self.fail:
            raise RuntimeError("PRIVATE_CREDENTIAL_SENTINEL")
        assert info.instructions is not None
        context = json.JSONDecoder().raw_decode(
            info.instructions.split("SAFE CONTEXT (data):\n", 1)[1]
        )[0]
        self.contexts.append(context)
        if self.on_context is not None:
            callback, self.on_context = self.on_context, None
            callback()
        assert {tool.name for tool in info.function_tools} == {
            "load_capability",
            "read_skill_reference",
        }
        skill = "homework" if context["homework"] else "learn"
        returns = [
            part
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        if not any(
            part.tool_name == "load_capability"
            and isinstance(part.content, dict)
            and f"# Skill: {skill}" in part.content.get("instructions", "")
            for part in returns
        ):
            return ModelResponse(parts=[ToolCallPart("load_capability", {"id": skill})])
        output: dict[str, object] = {
            "text": "Synthetic tutor explains the current material and actual supplied evidence.",
            "skill": skill,
        }

        def item(identity):
            return {
                "id": identity["id"],
                "verdict": self.verdict,
                "reason": f"Synthetic review of authored criterion: {identity['text']}",
            }

        if context["objectives"]:
            output["objectives"] = {
                "objectives": [item(i) for i in context["objectives"]["objectives"]]
            }
        if context["homework"]:
            output["homework"] = {
                name: [item(i) for i in context["homework"][name]]
                for name in ("requirements", "stretch_goals")
            }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    def runner(self) -> SkillingRunner:
        return SkillingRunner.create(FunctionModel(self.respond))


class ChoosingTutor(SyntheticTutor):
    def __init__(self):
        super().__init__()
        self.requests: list[str | None] = []

    async def respond(self, messages, info):
        result = await super().respond(messages, info)
        for part in result.parts:
            if isinstance(part, ToolCallPart) and part.tool_name == info.output_tools[0].name:
                args = part.args_as_dict()
                args["requested_control"] = self.requests.pop(0) if self.requests else None
                return ModelResponse(parts=[ToolCallPart(part.tool_name, args)])
        return result


class Browser:
    model: SyntheticTutor

    def __init__(self, controller: ProducerController):
        self.controller = controller
        self.client = TestClient(create_app(controller), base_url=BASE)
        self.state = self.client.get("/api/state").json()

    def post(self, path: str, body: dict, *, status: int = 200) -> dict:
        response = self.client.post(
            path, json=body, headers={"Origin": BASE, "X-CSRF-Token": self.state["csrf_token"]}
        )
        assert response.status_code == status, response.text
        result = response.json()
        if status == 200:
            self.state = result
        return result

    def refresh(self):
        response = self.client.get("/api/state")
        assert response.status_code == 200, response.text
        self.state = response.json()

    def action(self, control: str, *, status: int = 200):
        return self.post(
            f"/api/actions/{control}",
            {"display_id": self.state["display_id"], "event_id": secrets.token_urlsafe(16)},
            status=status,
        )

    def ack(self):
        return self.post("/api/feedback/ack", {"display_id": self.state["feedback"]["display_id"]})

    def review(self, kind: str):
        return self.post(
            f"/api/review/{kind}",
            {
                "evidence": "I chose stellar spectra; explained "
                "absorption in my own words and requested a slower example. "
                "Completion saves position; submission separately archives reviewed homework."
            },
        )

    def confirm(self, objective_id: str | None = None):
        review_id = self.state["review"]["id"]
        self.post("/api/review/ack", {"review_id": review_id})
        return self.post(
            "/api/review/confirm", {"review_id": review_id, "objective_id": objective_id}
        )


def conversational_journey(workspace: Path, course_source: Path) -> dict[str, object]:
    import_local_course(workspace, course_source.resolve())
    model = ChoosingTutor()
    controller = ProducerController.open(
        workspace, BrowserTutor.create(FunctionModel(model.respond))
    )
    browser = Browser(controller)
    model.requests = ["next", "next", "next", None]
    before = controller._service().snapshot()
    browser.post("/api/chat", {"message": "Help me to learn"})
    assert controller._service().snapshot() == before
    steps = []
    for _ in range(3):
        browser.post("/api/continue", {"continuation_id": browser.state["continuation"]["id"]})
        steps.append(browser.state["snapshot"]["beat"]["name"])
    assert steps == ["objectives", "concept", "gate-concept"]
    assert browser.state["continuation"] is None
    gate = controller._service().snapshot()
    browser.post("/api/chat", {"message": "I have a deeper question, do not continue yet"})
    assert controller._service().snapshot() == gate
    browser.client.close()
    return {"steps": steps, "render_ack_required": True, "gate_question_read_only": True}


def synthetic_journey(workspace: Path, course_source: Path) -> dict[str, object]:
    import_local_course(workspace, course_source.resolve())
    model = SyntheticTutor()
    controller = ProducerController.open(workspace, model.runner())
    browser = Browser(controller)
    browser.post("/api/note/save", {"text": NOTE})
    assert (workspace / "showcase/welcome-skilling/goal.md").read_bytes() == NOTE.encode()
    wrong_once = False
    reopened = False
    settled = set()
    for _ in range(80):
        state = browser.state
        snapshot = state["snapshot"]
        beat = snapshot["beat"]["name"]
        if state["feedback"]:
            if state["feedback"]["question_number"] == 3 and not reopened:
                original = state["feedback"]
                fresh = ProducerController.open(workspace, model.runner())
                browser = Browser(fresh)
                assert not fresh.history
                assert browser.state["feedback"]["reason"] == original["reason"]
                assert browser.state["controls"] == []
                reopened = True
            browser.ack()
        elif beat == "done":
            break
        elif beat == "gate-exercise":
            for objective in state["objectives"]:
                if objective["id"] not in settled:
                    browser.review("objectives")
                    browser.confirm(objective["id"])
                    settled.add(objective["id"])
            browser.action("attempted")
        elif beat == "gate-concept":
            revision = snapshot["revision"]
            browser.post("/api/chat", {"message": "Explain this more slowly, with a new example."})
            assert browser.state["snapshot"]["revision"] == revision
            assert model.contexts[-1]["teaching"]["material"]
            browser.action("proceed")
        elif beat == "quiz":
            # Fixture-only authored labels are synthetic probes, never authentic learner proof.
            entry = load_manifest(workspace).course("welcome-skilling")
            assert entry is not None
            course = load_course(workspace / ".skilling" / entry.path)
            lesson = course.lesson_at(
                f"{snapshot['position']['phase']}.{snapshot['position']['lesson']}"
            )
            assert lesson is not None
            from skilling.course import parse_lesson

            parsed = parse_lesson(lesson.path)
            number = snapshot["beat"]["number"]
            quiz = parsed.section("quiz")
            assert quiz is not None
            from skilling.course import parse_quiz

            label = parse_quiz(quiz.body, quiz.line)[number - 1].answer_label
            if not wrong_once:
                label = next(o["label"] for o in snapshot["beat"]["options"] if o["label"] != label)
                wrong_once = True
            browser.action(f"answer-{label}")
        else:
            ids = [c["id"] for c in state["controls"]]
            browser.action("continue" if "continue" in ids else ids[0])
    else:
        raise AssertionError("journey did not complete")
    assert browser.state["snapshot"]["completed_count"] == 2
    assert browser.state["homework"]["active"]["title"] == "Try the method"
    updated = NOTE + "Review: The slower example linked line absorption to electron transitions.\n"
    browser.post("/api/note/save", {"text": updated})
    review_service = browser.controller.session
    assert review_service is not None
    active_before = review_service.homework_check()
    model.verdict = "partial"
    browser.review("homework")
    partial_id = browser.state["review"]["id"]
    browser.post("/api/review/ack", {"review_id": partial_id})
    browser.post("/api/review/confirm", {"review_id": partial_id}, status=409)
    assert review_service.homework_check() == active_before
    model.verdict = "supported"
    model.cancel = True
    import asyncio

    try:
        asyncio.run(
            browser.controller.review_work(ReviewKind.HOMEWORK, "Actual synthetic learner evidence")
        )
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancelled review unexpectedly returned")
    assert browser.controller.review is None
    assert review_service.homework_check() == active_before
    model.cancel = False
    browser.refresh()
    browser.review("homework")
    assert len(browser.state["review"]["advice"]["requirements"]) == 3
    confirmed_id = browser.state["review"]["id"]
    browser.confirm()
    original_archive = browser.state["archive"]
    browser.post("/api/review/confirm", {"review_id": confirmed_id})
    assert browser.state["archive"] == original_archive
    assert browser.state["homework"]["active"] is None
    assert all(r["verdict"] is None for r in browser.state["archive"]["requirements"])
    browser.post("/api/artifact", {"title": "My next stellar-spectra step"})
    service = browser.controller.session
    assert service is not None
    before = service.progress()
    assert service.artifacts()[0].path == "showcase/welcome-skilling/goal.md"
    browser.client.close()
    relocated = workspace.with_name(workspace.name + "-relocated")
    assert not relocated.exists()
    shutil.move(str(workspace), str(relocated))
    resumed = ProducerController.open(relocated, model.runner())
    assert resumed.session is not None
    assert resumed.session.progress() == before
    assert resumed.session.homework_check().active is None
    assert resumed.session.artifacts()[0].path == "showcase/welcome-skilling/goal.md"
    assert (relocated / "showcase/welcome-skilling/goal.md").read_bytes() == updated.encode()
    nested = relocated / "showcase/welcome-skilling"
    cli_results = []
    for argv in (
        ["progress", "--course", "welcome-skilling"],
        ["next", "--course", "welcome-skilling"],
        ["homework", "check", "--course", "welcome-skilling"],
    ):
        result = subprocess.run(
            [
                str(
                    Path(sys.executable).parent
                    / ("skilling.exe" if os.name == "nt" else "skilling")
                ),
                *argv,
            ],
            cwd=nested,
            capture_output=True,
            text=True,
            check=True,
        )
        cli_results.append(json.loads(result.stdout))
    assert cli_results[0]["percent_complete"] == 100.0
    assert cli_results[1]["beat"]["name"] == "done"
    assert cli_results[2]["active"] is None
    assert (
        FileSession.pending_feedback_at(
            state_root=relocated / ".skilling/state",
            learner_id="local",
            course_id="welcome-skilling",
        )
        is None
    )
    return {
        "completed_count": 2,
        "homework_active": None,
        "canonical_reopen": reopened,
        "wrong_remediation": wrong_once,
        "settled_objectives": sorted(settled),
        "model_context_count": len(model.contexts),
        "relocated_workspace": str(relocated),
        "conversation": conversational_journey(
            workspace.with_name(workspace.name + "-chat"), course_source
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--course-source", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(synthetic_journey(args.workspace, args.course_source), sort_keys=True))
