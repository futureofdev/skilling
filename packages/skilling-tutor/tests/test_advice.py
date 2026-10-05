import asyncio

import pytest
from installed_child import PolicyModel, policy_model
from pydantic_ai import Agent

from skilling_tutor import (
    AdviceIdentity,
    HomeworkAdvice,
    HomeworkAdviceContext,
    LearnerEvidence,
    ObjectiveAdvice,
    ObjectiveAdviceContext,
    SkillingCapability,
    SkillingRunDeps,
    SkillingRunner,
    TutorError,
    TutorErrorKind,
    TutorPurpose,
)


def objective_context(label="A"):
    return ObjectiveAdviceContext(
        (AdviceIdentity(label, f"Explain {label}"),),
        LearnerEvidence.from_text(f"Actual explanation {label}"),
        "revision",
    )


def homework_context(label="A"):
    return HomeworkAdviceContext(
        "Build",
        "Practice",
        (AdviceIdentity(label, "Required"),),
        (AdviceIdentity(f"stretch-{label}", "Optional"),),
        LearnerEvidence.from_text(f"Built {label}"),
        "rev",
    )


def item(identity):
    return {"id": identity, "verdict": "supported", "reason": "Actual evidence explains the result"}


def test_direct_and_runner_structured_advice():
    ctx = objective_context()
    model = policy_model(call_tools=[], custom_output_args={"objectives": [item("A")]})
    runner = SkillingRunner.create(model)
    direct = Agent(
        model,
        output_type=ObjectiveAdvice.output_type(),
        deps_type=SkillingRunDeps,
        capabilities=[SkillingCapability.for_context(TutorPurpose.OBJECTIVE_ADVICE)],
    )

    async def exercise():
        wire = await direct.run("turn", deps=SkillingRunDeps(ctx))
        assert (
            ObjectiveAdvice.from_output(wire.output, context=ctx)
            == (await runner.advise_objectives(ctx)).output
        )
        assert model.last_model_request_parameters is not None
        assert {tool.name for tool in model.last_model_request_parameters.function_tools} == {
            "load_capability",
            "read_skill_reference",
        }
        homework_model = policy_model(
            call_tools=[],
            custom_output_args={
                "requirements": [item("A")],
                "stretch_goals": [item("stretch-A")],
            },
        )
        hw = SkillingRunner.create(homework_model)
        homework_direct = Agent(
            homework_model,
            output_type=HomeworkAdvice.output_type(),
            deps_type=SkillingRunDeps,
            capabilities=[SkillingCapability.for_context(TutorPurpose.HOMEWORK_ADVICE)],
        )
        homework_wire = await homework_direct.run("turn", deps=SkillingRunDeps(homework_context()))
        result = await hw.advise_homework(homework_context())
        assert (
            HomeworkAdvice.from_output(homework_wire.output, context=homework_context())
            == result.output
        )
        assert result.output.requirements[0].id == "A"
        assert result.output.stretch_goals[0].id == "stretch-A"
        assert result.output.evidence_digest == homework_context().evidence.digest
        assert result.usage.requests == 2

    asyncio.run(exercise())


@pytest.mark.parametrize("ids", [[], ["unknown"], ["A", "A"], ["A", "unknown"]])
def test_identity_cardinality_refused(ids):
    wire = ObjectiveAdvice.output_type().model_validate({"objectives": [item(x) for x in ids]})
    with pytest.raises(TutorError) as error:
        ObjectiveAdvice.from_output(wire, context=objective_context())
    assert error.value.kind is TutorErrorKind.ADVICE


def test_required_and_stretch_separation():
    wire = HomeworkAdvice.output_type().model_validate(
        {"requirements": [item("stretch-A")], "stretch_goals": [item("A")]}
    )
    with pytest.raises(TutorError):
        HomeworkAdvice.from_output(wire, context=homework_context())


def test_reused_all_purpose_agents_capture_concurrent_and_sequential_isolation():
    import json

    from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    from skilling_tutor import NarrationContext

    captures = []

    async def generate(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        await asyncio.sleep(0)
        assert info.instructions is not None
        data = json.JSONDecoder().raw_decode(
            info.instructions.split("SAFE CONTEXT (data):\n", 1)[1]
        )[0]
        captures.append((data, messages, info.function_tools))
        assert {tool.name for tool in info.function_tools} == {
            "load_capability",
            "read_skill_reference",
        }
        if not info.output_tools:
            return ModelResponse(parts=[TextPart(data["material"])])
        if "objectives" in data:
            output = {"objectives": [item(x["id"]) for x in data["objectives"]]}
        else:
            output = {
                "requirements": [item(x["id"]) for x in data["requirements"]],
                "stretch_goals": [item(x["id"]) for x in data["stretch_goals"]],
            }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    runner = SkillingRunner.create(PolicyModel(FunctionModel(generate)))

    async def exercise():
        for _ in range(2):
            (
                objective_a,
                objective_b,
                homework_a,
                homework_b,
                narration_a,
                narration_b,
            ) = await asyncio.gather(
                runner.advise_objectives(objective_context("A")),
                runner.advise_objectives(objective_context("B")),
                runner.advise_homework(homework_context("A")),
                runner.advise_homework(homework_context("B")),
                runner.narrate(NarrationContext("Course", "1.1", "Persona A", (), "Material A")),
                runner.narrate(NarrationContext("Course", "1.1", "Persona B", (), "Material B")),
            )
            assert objective_a.output.objectives[0].id == "A"
            assert objective_b.output.objectives[0].id == "B"
            assert homework_a.output.requirements[0].id == "A"
            assert homework_b.output.requirements[0].id == "B"
            assert narration_a.output == "Material A" and narration_b.output == "Material B"
            for result_a, result_b in ((objective_a, objective_b), (homework_a, homework_b)):
                assert "Actual explanation B" not in repr(result_a.new_messages)
                assert "Actual explanation A" not in repr(result_b.new_messages)
                assert "Built B" not in repr(result_a.new_messages)
                assert "Built A" not in repr(result_b.new_messages)

    asyncio.run(exercise())
    assert len(captures) == 12


@pytest.mark.parametrize("mode", ["native", "prompted"])
def test_supported_direct_output_modes_preserve_producer_contract(mode):
    import json

    from pydantic_ai import NativeOutput, PromptedOutput
    from pydantic_ai.profiles import ModelProfile

    output_type = (
        NativeOutput(ObjectiveAdvice.output_type())
        if mode == "native"
        else PromptedOutput(ObjectiveAdvice.output_type())
    )
    model = policy_model(
        call_tools=[],
        custom_output_text=json.dumps({"objectives": [item("A")]}),
        profile=ModelProfile(supports_json_schema_output=True),
    )
    agent = Agent(
        model,
        deps_type=SkillingRunDeps,
        output_type=output_type,
        capabilities=[SkillingCapability.for_context(TutorPurpose.OBJECTIVE_ADVICE)],
    )
    result = asyncio.run(agent.run("turn", deps=SkillingRunDeps(objective_context())))
    advice = ObjectiveAdvice.from_output(result.output, context=objective_context())
    assert advice.objectives[0].id == "A"
    assert model.last_model_request_parameters is not None
    assert {tool.name for tool in model.last_model_request_parameters.function_tools} == {
        "load_capability",
        "read_skill_reference",
    }


def test_objective_and_homework_producer_histories_retained_and_cleared():
    import json
    from dataclasses import replace

    from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    captures = []

    async def generate(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert info.instructions is not None
        data = json.JSONDecoder().raw_decode(
            info.instructions.split("SAFE CONTEXT (data):\n", 1)[1]
        )[0]
        captures.append((data, repr(messages), len(messages)))
        if "objectives" in data:
            output = {"objectives": [item(x["id"]) for x in data["objectives"]]}
        else:
            output = {
                "requirements": [item(x["id"]) for x in data["requirements"]],
                "stretch_goals": [item(x["id"]) for x in data["stretch_goals"]],
            }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    runner = SkillingRunner.create(PolicyModel(FunctionModel(generate)))

    async def exercise():
        for purpose in ("objectives", "homework"):
            if purpose == "objectives":
                first = await runner.advise_objectives(objective_context("A"))
                original_history = repr(first.new_messages)
                updated = replace(
                    objective_context("A"),
                    evidence=LearnerEvidence.from_text("Updated proof A"),
                    revision="revision2",
                )
                await runner.advise_objectives(updated, history=first.new_messages)
                await runner.advise_objectives(objective_context("B"), history=[])
            else:
                first = await runner.advise_homework(homework_context("A"))
                original_history = repr(first.new_messages)
                updated = replace(
                    homework_context("A"),
                    evidence=LearnerEvidence.from_text("Updated proof A"),
                    revision="revision2",
                )
                await runner.advise_homework(updated, history=first.new_messages)
                await runner.advise_homework(homework_context("B"), history=[])
            assert repr(first.new_messages) == original_history
            assert captures[-2][0]["evidence"]["text"] == "Updated proof A"
            assert captures[-2][0]["revision"] == "revision2"
            assert captures[-2][2] > captures[-1][2] == 3
            assert "'id': 'A'" in captures[-2][1]
            assert "'id': 'A'" not in captures[-1][1]
            assert "Actual explanation A" not in json.dumps(captures[-1][0])
            assert "Built A" not in json.dumps(captures[-1][0])

    asyncio.run(exercise())
