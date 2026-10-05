"""Automatic conversation advances only after rendering, with fresh bounded choices."""

import json
from pathlib import Path

import pytest
from journey import Browser, ChoosingTutor
from pydantic_ai.models.function import FunctionModel
from test_controller import to_beat

from skilling.workspace import import_local_course
from skilling_producer_example import ProducerController
from skilling_producer_example._tutor import BrowserTutor

COURSE = Path(__file__).resolve().parents[2] / "welcome-skilling"


@pytest.fixture
def conversation(tmp_path):
    workspace = tmp_path / "learner"
    import_local_course(workspace, COURSE)
    model = ChoosingTutor()
    tutor = BrowserTutor.create(FunctionModel(model.respond))
    controller = ProducerController.open(workspace, tutor)
    browser = Browser(controller)
    browser.model = model
    yield browser
    browser.client.close()


def resume(browser):
    return browser.post("/api/continue", {"continuation_id": browser.state["continuation"]["id"]})


def test_readiness_automatically_teaches_new_material_after_presentation(conversation):
    browser = conversation
    to_beat(browser, "objectives")
    before = browser.controller._service().snapshot()
    browser.model.requests = ["next", "next", None]
    browser.post("/api/chat", {"message": "Move on"})
    assert browser.controller._service().snapshot() == before
    assert browser.state["continuation"]
    resume(browser)  # browser has rendered the objectives turn
    assert browser.state["snapshot"]["beat"]["name"] == "concept"
    assert browser.model.contexts[-1]["teaching"]["beat"] == "concept"
    material = json.loads(browser.model.contexts[-1]["teaching"]["material"])
    assert material["body"]
    assert material["presented_material"][-1]["beat"] == "objectives"
    assert material["presented_material"][-1]["objectives"]
    resume(browser)  # browser has rendered the actual concept turn
    assert browser.state["snapshot"]["beat"]["name"] == "gate-concept"
    assert browser.state["continuation"] is None
    assert len([m for m in browser.state["messages"] if m["role"] == "learner"]) == 1
    assert "requestable_controls" in browser.model.contexts[-1]["teaching"]["material"]


def test_deeper_question_does_not_advance_gate(conversation):
    browser = conversation
    to_beat(browser, "gate-concept")
    before = browser.controller._service().snapshot()
    browser.post("/api/chat", {"message": "Explain that more slowly; I do not understand yet"})
    assert browser.controller._service().snapshot() == before
    assert browser.state["continuation"] is None


def test_followup_cannot_invent_readiness_or_exceed_four_model_turns(conversation):
    browser = conversation
    browser.model.requests = ["next", "next", "next", "proceed"]
    browser.post("/api/chat", {"message": "Help me learn"})
    for _ in range(3):
        resume(browser)
    assert browser.state["snapshot"]["beat"]["name"] == "gate-concept"
    assert browser.state["continuation"] is None
    assert browser.state["tutor_error"]
    assert browser.model.requests == []


def test_quiz_choice_commits_once_and_stops_for_canonical_feedback(conversation):
    browser = conversation
    to_beat(browser, "quiz")
    option = browser.state["controls"][0]
    before = browser.controller._service().snapshot()
    browser.model.requests = [option["id"], "next"]
    browser.post("/api/chat", {"message": f"My answer is {option['payload']}"})
    token = browser.state["continuation"]["id"]
    assert browser.controller._service().snapshot() == before
    resume(browser)
    feedback = browser.state["feedback"]
    after = browser.controller._service().snapshot()
    assert feedback and browser.state["controls"] == []
    assert browser.model.requests == ["next"]
    browser.post("/api/continue", {"continuation_id": token})
    assert browser.controller._service().snapshot() == after
    assert {k: v for k, v in browser.state["feedback"].items() if k != "display_id"} == {
        k: v for k, v in feedback.items() if k != "display_id"
    }


def test_new_chat_and_restart_expire_unpresented_continuations(conversation):
    browser = conversation
    before = browser.controller._service().snapshot()
    browser.model.requests = ["next", None, "next"]
    browser.post("/api/chat", {"message": "Help me learn"})
    old = browser.state["continuation"]["id"]
    browser.post("/api/chat", {"message": "Wait, I have a question"})
    browser.post("/api/continue", {"continuation_id": old}, status=409)
    assert browser.controller._service().snapshot() == before
    browser.post("/api/chat", {"message": "Continue"})
    token = browser.state["continuation"]["id"]
    restarted = Browser(
        ProducerController.open(browser.controller.workspace, browser.controller.runner)
    )
    restarted.post("/api/continue", {"continuation_id": token}, status=409)
    assert restarted.controller._service().snapshot() == before
    restarted.client.close()


def test_provider_failure_after_presented_step_preserves_current_material(conversation):
    browser = conversation
    browser.model.requests = ["next"]
    browser.post("/api/chat", {"message": "Help me learn"})
    browser.model.fail = True
    resume(browser)
    assert browser.state["snapshot"]["beat"]["name"] == "objectives"
    assert browser.state["snapshot"]["beat"]["objectives"]
    assert browser.state["tutor_error"]
    assert browser.state["continuation"] is None


def test_history_keeps_complete_native_tool_pairs(conversation):
    browser = conversation
    browser.post("/api/chat", {"message": "Teach me"})
    result = browser.controller.history
    assert result
    # A provider history longer than128 messages is retained as whole turns.
    from skilling_producer_example._tutor import BrowserConversationResult
    from skilling_tutor import ConversationReply, TutorUsage

    history = result * 65
    original = browser.controller.runner
    assert isinstance(original, BrowserTutor)

    class LongHistoryTutor(BrowserTutor):
        async def chat(self, *args, **kwargs):
            return BrowserConversationResult(
                ConversationReply("Explain the current material"),
                TutorUsage(1, 0, 0, 0),
                history,
            )

    browser.controller.runner = LongHistoryTutor(original.agent, original.reviews)
    browser.post("/api/chat", {"message": "Another question"})
    assert browser.controller.history == history
    assert len(history) > 128
