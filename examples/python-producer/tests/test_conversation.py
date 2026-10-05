"""Automatic conversation advances only after rendering, with fresh bounded choices."""

import json
from pathlib import Path

import pytest
from journey import Browser, ChoosingTutor
from pydantic_ai.models.function import FunctionModel
from test_controller import to_beat

from skilling.workspace import import_local_course
from skilling_producer_example import ProducerController
from skilling_producer_example._tutor import BrowserConversationResult, BrowserTutor
from skilling_tutor import ConversationReply, TutorUsage

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
    browser.model.requests = ["next", None]
    browser.model.on_context = lambda: (
        (browser.controller._service().snapshot().beat.name.value == "concept")
        or pytest.fail("Tutor was called before the learner's current beat advanced")
    )
    browser.post("/api/chat", {"message": "Move on", "display_id": browser.state["display_id"]})
    assert browser.state["continuation"]
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


@pytest.fixture
def immediate_conversation(conversation):
    """Keep public session transitions real while inspecting the first tutor request."""
    browser = conversation
    original = browser.controller.runner
    assert isinstance(original, BrowserTutor)
    browser.request_beats = []

    class InspectingTutor(BrowserTutor):
        async def chat(self, message, context, *, history=()):
            actual = browser.controller._service().snapshot().beat.name
            assert str(actual) == str(context.teaching.beat)
            browser.request_beats.append(str(actual))
            return BrowserConversationResult(
                ConversationReply("Teach the fresh current material"),
                TutorUsage(1, 0, 0, 0),
                (),
            )

    browser.controller.runner = InspectingTutor(original.agent, original.reviews)
    return browser


@pytest.mark.parametrize(
    ("beat", "message", "next_beat"),
    [
        ("welcome", "continue", "objectives"),
        ("objectives", "Move on", "concept"),
        ("concept", "next please!", "gate-concept"),
        ("gate-concept", "Continue", "exercise"),
        ("exercise", "please continue", "gate-exercise"),
    ],
)
def test_explicit_painted_readiness_advances_before_tutor(
    immediate_conversation, beat, message, next_beat
):
    browser = immediate_conversation
    to_beat(browser, beat)
    body = {"message": message, "display_id": browser.state["display_id"]}
    browser.post("/api/chat", body)
    assert browser.request_beats == [next_beat]
    after = browser.controller._service().snapshot()
    browser.post("/api/chat", body)  # same captured choice has stable public action identity
    assert browser.controller._service().snapshot() == after
    assert browser.request_beats == [next_beat, next_beat]


@pytest.mark.parametrize("message", ["continue", "Can you continue explaining?", "I am stuck"])
def test_readiness_never_invents_exercise_attempt(immediate_conversation, message):
    browser = immediate_conversation
    to_beat(browser, "gate-exercise")
    before = browser.controller._service().snapshot()
    browser.post("/api/chat", {"message": message, "display_id": browser.state["display_id"]})
    assert browser.controller._service().snapshot() == before


@pytest.mark.parametrize("beat", ["gate-exercise", "quiz"])
def test_native_tutor_cannot_invent_attempt_or_answer_for_continue(conversation, beat):
    browser = conversation
    to_beat(browser, beat)
    before = browser.controller._service().snapshot()
    browser.model.requests = [browser.state["controls"][0]["id"]]
    browser.post("/api/chat", {"message": "continue", "display_id": browser.state["display_id"]})
    assert browser.controller._service().snapshot() == before
    assert browser.state["continuation"] is None
    assert browser.state["tutor_error"]


def test_explicit_quiz_choice_feedback_precedes_tutor_and_retry_is_safe(immediate_conversation):
    browser = immediate_conversation
    to_beat(browser, "quiz")
    option = browser.state["controls"][0]
    body = {"message": option["payload"], "display_id": browser.state["display_id"]}
    browser.post("/api/chat", body)
    assert browser.state["feedback"]
    assert browser.request_beats == []
    after = browser.controller._service().snapshot()
    browser.post("/api/chat", body)
    assert browser.controller._service().snapshot() == after
    assert browser.state["feedback"]
    browser.post("/api/chat", {"message": "continue", "display_id": browser.state["display_id"]})
    assert browser.controller._service().snapshot() == after


def test_explicit_readiness_refuses_stale_presentation(immediate_conversation):
    browser = immediate_conversation
    body = {"message": "continue", "display_id": browser.state["display_id"]}
    browser.action("next")
    before = browser.controller._service().snapshot()
    browser.post("/api/chat", body, status=409)
    assert browser.controller._service().snapshot() == before
    assert browser.request_beats == []


def test_followup_stops_at_gate_without_reteaching_or_inventing_readiness(conversation):
    browser = conversation
    browser.model.requests = ["next", "next", "next", "proceed"]
    browser.post("/api/chat", {"message": "Help me learn"})
    for _ in range(3):
        resume(browser)
    assert browser.state["snapshot"]["beat"]["name"] == "gate-concept"
    assert browser.state["continuation"] is None
    assert "tutor_error" not in browser.state
    assert browser.model.requests == ["proceed"]
    assert len([m for m in browser.state["messages"] if m["role"] == "tutor"]) == 3


def test_rendered_exercise_reaches_gate_without_second_tutor_reply(conversation):
    browser = conversation
    to_beat(browser, "gate-concept")
    browser.model.requests = ["next", "attempted"]
    browser.post("/api/chat", {"message": "Proceed", "display_id": browser.state["display_id"]})
    assert browser.state["snapshot"]["beat"]["name"] == "exercise"
    material = json.loads(browser.model.contexts[-1]["teaching"]["material"])
    assert material["body"]
    messages = browser.state["messages"]
    history = browser.controller.history
    requests = len(browser.model.contexts)
    token = browser.state["continuation"]["id"]
    resume(browser)  # the actual exercise reply has painted
    assert browser.state["snapshot"]["beat"]["name"] == "gate-exercise"
    assert browser.state["continuation"] is None
    assert browser.state["messages"] == messages
    assert browser.controller.history == history
    assert len(browser.model.contexts) == requests
    assert browser.model.requests == ["attempted"]
    browser.post("/api/continue", {"continuation_id": token})
    assert browser.state["messages"] == messages
    assert len(browser.model.contexts) == requests


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
