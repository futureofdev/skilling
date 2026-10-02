import asyncio

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import UsageLimits

from skilling_tutor import NarrationContext, SkillingRunner, TutorError, TutorErrorKind


def context():
    return NarrationContext("Course", "1.1", "Tutor", (), "Canonical reason/remediation")


def test_usage_limit_and_missing_provider():
    runner = SkillingRunner.create(
        TestModel(custom_output_text="ok"), usage_limits=UsageLimits(request_limit=0)
    )
    with pytest.raises(TutorError) as error:
        asyncio.run(runner.narrate(context()))
    assert error.value.kind is TutorErrorKind.USAGE
    with pytest.raises(TutorError) as error:
        SkillingRunner.create("openai:gpt-5")
    assert error.value.kind is TutorErrorKind.CONFIGURATION
    assert "provider extra" in str(error.value)
    with pytest.raises(TutorError) as error:
        SkillingRunner.create("bogus:model")
    assert error.value.kind is TutorErrorKind.CONFIGURATION


def test_failure_cancellation_and_safe_narration_retry():
    requests = []

    async def fail(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        requests.append(info.instructions)
        raise RuntimeError("CREDENTIAL_SENTINEL")

    runner = SkillingRunner.create(FunctionModel(fail))
    with pytest.raises(TutorError) as error:
        asyncio.run(runner.narrate(context()))
    assert error.value.kind is TutorErrorKind.MODEL
    assert "CREDENTIAL_SENTINEL" not in str(error.value)

    async def cancelled(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(SkillingRunner.create(FunctionModel(cancelled)).narrate(context()))

    async def retry(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        requests.append(info.instructions)
        return ModelResponse(parts=[TextPart("Rendered feedback")])

    success = asyncio.run(SkillingRunner.create(FunctionModel(retry)).narrate(context()))
    assert requests[0] == requests[1]
    assert success.output == "Rendered feedback"


def test_actual_committed_feedback_and_advice_leave_durable_bytes_untouched(tmp_path):
    from pathlib import Path

    from skilling.course import Course
    from skilling.delivery import Beat, Input
    from skilling.session import ActionOperation, FileSession, TrustedAction
    from skilling_tutor import AdviceIdentity, LearnerEvidence, ObjectiveAdviceContext

    course = Course.load(Path(__file__).resolve().parents[3] / "examples/hello-skilling")
    session = FileSession.open(course, state_root=tmp_path / "state", learner_id="learner")
    for _ in range(20):
        snapshot = session.snapshot()
        if snapshot.beat.name is Beat.QUIZ:
            break
        for choice in (Input.NEXT, Input.PROCEED, Input.ATTEMPTED):
            if choice in snapshot.legal_inputs:
                session.advance(choice)
                break
        else:
            raise AssertionError(snapshot.beat)
    snapshot = session.snapshot()
    assert snapshot.beat.question is not None
    action = TrustedAction.create(
        snapshot,
        event_id="CONTROLLER_TOKEN_SENTINEL",
        operation=ActionOperation.ANSWER,
        payload=snapshot.beat.question.options[0].label,
    )
    result = session.act(action)
    context = NarrationContext.from_snapshot(result.snapshot)
    assert result.snapshot.pending_feedback is not None
    assert result.snapshot.pending_feedback.reason in context.material

    def durable():
        return {
            str(path.relative_to(tmp_path)): path.read_bytes()
            for path in tmp_path.rglob("*")
            if path.is_file()
        }

    before = durable()
    runner = SkillingRunner.create(
        TestModel(custom_output_text="arbitrary prose cannot acknowledge")
    )

    async def exercise():
        first = await runner.narrate(context)
        retry = await runner.narrate(context)
        assert first.output == retry.output
        assert "CONTROLLER_TOKEN_SENTINEL" not in repr(first.new_messages)

        async def failure(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise RuntimeError("Model failed after controller commit")

        with pytest.raises(TutorError):
            await SkillingRunner.create(FunctionModel(failure)).narrate(context)

        async def cancellation(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await SkillingRunner.create(FunctionModel(cancellation)).narrate(context)
        advice_runner = SkillingRunner.create(
            TestModel(
                custom_output_args={
                    "objectives": [
                        {
                            "id": "o",
                            "verdict": "not-yet",
                            "reason": "Actual evidence is insufficient",
                        }
                    ]
                }
            )
        )
        await advice_runner.advise_objectives(
            ObjectiveAdviceContext(
                (AdviceIdentity("o", "Explain"),), LearnerEvidence.from_text("I tried"), "revision"
            )
        )

    asyncio.run(exercise())
    assert durable() == before
    assert session.snapshot().pending_feedback == result.snapshot.pending_feedback


def test_native_application_cancellation_propagates():
    from pydantic_ai.exceptions import RunCancelled

    async def cancel(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise RunCancelled("Application cancelled the turn")

    runner = SkillingRunner.create(FunctionModel(cancel))
    with pytest.raises(RunCancelled):
        asyncio.run(runner.narrate(context()))
