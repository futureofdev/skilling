"""Custom browser output retains native canonical-policy timing and refresh assurances."""

import asyncio
from copy import deepcopy

import pytest
from pydantic_ai import models
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel

from skilling_producer_example._tutor import BrowserConversationResult, BrowserTurn, BrowserTutor
from skilling_tutor import ConversationContext, NarrationContext

models.ALLOW_MODEL_REQUESTS = False


def context():
    return ConversationContext(NarrationContext("Welcome", "1.1", None, (), "Current concept"), "r")


def returns(messages):
    return [
        part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


def retries(messages):
    return [
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]


@pytest.mark.parametrize("same_response", [False, True])
def test_declared_learn_requires_policy_before_response_even_if_progress_loaded(same_response):
    captures = []

    async def respond(messages, info):
        captures.append(deepcopy(messages))
        output = ToolCallPart(
            info.output_tools[0].name, {"text": "Explain current material", "skill": "learn"}
        )
        if len(captures) == 1:
            return ModelResponse(parts=[ToolCallPart("load_capability", {"id": "progress"})])
        if len(captures) == 2:
            parts = (
                [ToolCallPart("load_capability", {"id": "learn"}), output]
                if same_response
                else [output]
            )
            return ModelResponse(parts=parts)
        assert any("activate learn" in retry for retry in retries(messages))
        if not same_response and len(captures) == 3:
            return ModelResponse(parts=[ToolCallPart("load_capability", {"id": "learn"})])
        assert any(
            part.tool_name == "load_capability"
            and isinstance(part.content, dict)
            and "# Skill: learn" in part.content.get("instructions", "")
            for part in returns(messages)
        )
        return ModelResponse(parts=[output])

    tutor = BrowserTutor.create(FunctionModel(respond))
    result = asyncio.run(tutor.chat("Explain this", context()))
    assert isinstance(result, BrowserConversationResult)
    assert result.output.skill.value == "learn"
    assert result.requested_control is None
    assert result.usage.requests == (3 if same_response else 4)
    assert BrowserTurn.model_fields["requested_control"].default is None
    assert "objectives" not in BrowserTurn.model_fields


@pytest.mark.parametrize(
    "skill, handoff", [("homework", "homework-evidence"), ("progress", "progress")]
)
def test_missing_data_requires_refresh_before_custom_browser_output(skill, handoff):
    captures = []

    async def respond(messages, info):
        captures.append(deepcopy(messages))
        if len(captures) == 1:
            return ModelResponse(parts=[ToolCallPart("load_capability", {"id": skill})])
        refresh = [] if len(captures) == 2 else [handoff]
        if refresh:
            assert any(f"include {handoff} in refresh" in retry for retry in retries(messages))
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {"text": "Please supply current evidence", "skill": skill, "refresh": refresh},
                )
            ]
        )

    result = asyncio.run(
        BrowserTutor.create(FunctionModel(respond)).chat("Review my current work", context())
    )
    assert isinstance(result, BrowserConversationResult)
    assert result.usage.requests == 3
    assert [value.value for value in result.output.refresh] == [handoff]
    assert result.requested_control is None


@pytest.mark.parametrize(
    "handoff, required",
    [("teaching", "learn"), ("objective-evidence", "learn"), ("homework-evidence", "homework")],
)
def test_refresh_requires_its_own_policy_even_with_another_policy_active(handoff, required):
    captures = []

    async def respond(messages, info):
        captures.append(deepcopy(messages))
        if len(captures) == 1:
            return ModelResponse(parts=[ToolCallPart("load_capability", {"id": "progress"})])
        if len(captures) == 3:
            assert any(f"activate {required}" in retry for retry in retries(messages))
            return ModelResponse(parts=[ToolCallPart("load_capability", {"id": required})])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "text": "Refresh actual current data",
                        "skill": "progress",
                        "refresh": ["progress", handoff],
                    },
                )
            ]
        )

    result = asyncio.run(
        BrowserTutor.create(FunctionModel(respond)).chat("Current data?", context())
    )
    assert result.usage.requests == 4
    assert [value.value for value in result.output.refresh] == ["progress", handoff]


def test_reused_browser_agent_does_not_retain_guard_policy_state_between_runs():
    async def respond(messages, info):
        parts = returns(messages)
        if not parts:
            return ModelResponse(parts=[ToolCallPart("load_capability", {"id": "progress"})])
        loaded = any(
            part.tool_name == "load_capability"
            and isinstance(part.content, dict)
            and "# Skill: learn" in part.content.get("instructions", "")
            for part in parts
        )
        if retries(messages) and not loaded:
            return ModelResponse(parts=[ToolCallPart("load_capability", {"id": "learn"})])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name, {"text": "Fresh teaching reply", "skill": "learn"}
                )
            ]
        )

    tutor = BrowserTutor.create(FunctionModel(respond))

    async def exercise():
        first, second = await asyncio.gather(
            tutor.chat("First learner", context()), tutor.chat("Second learner", context())
        )
        assert first.usage.requests == second.usage.requests == 4

    asyncio.run(exercise())
