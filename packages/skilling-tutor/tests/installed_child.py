"""Synthetic installed-public-API proof; copied into an outside-checkout stage."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

from pydantic_ai import Agent, models
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

import skilling
import skilling_tutor
from skilling.skills import ROOT, skill_files
from skilling_tutor import (
    AdviceIdentity,
    HomeworkAdviceContext,
    LearnerEvidence,
    NarrationContext,
    ObjectiveAdviceContext,
    SkillingCapability,
    SkillingRunDeps,
    SkillingRunner,
    TutorPurpose,
)

models.ALLOW_MODEL_REQUESTS = False


async def main() -> None:
    prefix = Path(sys.prefix).resolve()
    for module in (skilling, skilling_tutor):
        assert module.__file__ is not None
        assert Path(module.__file__).resolve().is_relative_to(prefix)
    assert skilling.__version__ == sys.argv[1] and skilling_tutor.__version__ == sys.argv[2]
    assert importlib.metadata.version("pydantic-ai-slim") == "2.52.0"
    assert importlib.metadata.version("pydantic-ai-harness") == "0.52.0"
    bodies = {}
    references = {}
    digests = {}
    for skill in ("learn", "progress", "homework"):
        for path in skill_files(skill):
            assert path.resolve().is_relative_to(prefix)
            relative = path.relative_to(ROOT / skill).as_posix()
            content = path.read_bytes()
            digests[f"{skill}/{relative}"] = hashlib.sha256(content).hexdigest()
            if relative == "SKILL.md":
                body = "\n".join(content.decode("utf-8").splitlines()).split("---", 2)[2].strip()
                bodies[skill] = f"# Skill: {skill}\n\n{body}"
            else:
                references[(skill, relative)] = content.decode("utf-8")
    assert len(bodies) == 3 and len(references) == 8
    captures = []

    def response(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captures.append(messages)
        assert {tool.name for tool in info.function_tools} == {
            "load_capability",
            "read_skill_reference",
        }
        returns = [
            part
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        missing_skills = [
            skill
            for skill, body in bodies.items()
            if not any(
                part.tool_name == "load_capability"
                and isinstance(part.content, dict)
                and part.content.get("instructions") == body
                for part in returns
            )
        ]
        if missing_skills:
            return ModelResponse(
                parts=[ToolCallPart("load_capability", {"id": skill}) for skill in missing_skills]
            )
        missing_refs = [
            (skill, relative)
            for (skill, relative), text in references.items()
            if not any(
                part.tool_name == "read_skill_reference" and part.content == text
                for part in returns
            )
        ]
        if missing_refs:
            return ModelResponse(
                parts=[
                    ToolCallPart("read_skill_reference", {"skill": skill, "reference": relative})
                    for skill, relative in missing_refs
                ]
            )
        return ModelResponse(parts=[TextPart("narrated")])

    context = NarrationContext("Course", "1.1", "Tutor", (), "Active material")
    cap = SkillingCapability.for_context(TutorPurpose.NARRATION)
    direct = Agent(
        FunctionModel(response),
        capabilities=[cap],
        deps_type=SkillingRunDeps,
    )
    assert (await direct.run("turn", deps=SkillingRunDeps(context))).output == "narrated"
    assert cap.get_toolset() is None and cap.get_native_tools() == []
    assert (
        await SkillingRunner.create(FunctionModel(response)).narrate(context)
    ).output == "narrated"
    assert len(captures) == 6  # three requests each for native Agent and shared runner
    assert str(ROOT) not in repr(captures)
    evidence = LearnerEvidence.from_text("Actual learner proof")
    identity = AdviceIdentity("required", "Explain the result")
    item = {"id": "required", "verdict": "supported", "reason": "Actual proof explains the result"}
    objective = ObjectiveAdviceContext((identity,), evidence, "revision")
    advice = await SkillingRunner.create(
        TestModel(call_tools=[], custom_output_args={"objectives": [item]})
    ).advise_objectives(objective)
    assert advice.output.evidence_digest == evidence.digest
    homework = HomeworkAdviceContext("Work", "Practice", (identity,), (), evidence, "revision")
    result = await SkillingRunner.create(
        TestModel(call_tools=[], custom_output_args={"requirements": [item], "stretch_goals": []})
    ).advise_homework(homework)
    assert result.output.requirements[0].id == "required"
    print(
        json.dumps(
            {
                "status": "PASS",
                "python": sys.version,
                "core": skilling.__version__,
                "tutor": skilling_tutor.__version__,
                "core_origin": skilling.__file__,
                "tutor_origin": skilling_tutor.__file__,
                "real_requests": False,
                "harness": importlib.metadata.version("pydantic-ai-harness"),
                "policy_resources": digests,
                "native_activation_requests": len(captures),
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
