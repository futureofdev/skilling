"""Synthetic installed-public-API proof; copied into an outside-checkout stage."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import sys
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path

from pydantic_ai import Agent, models
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

import skilling
import skilling_tutor
from skilling.delivery import Beat, Input
from skilling.skills import ROOT, skill_files
from skilling_tutor import (
    AdviceIdentity,
    BundledSkill,
    ConversationContext,
    HomeworkAdviceContext,
    LearnerEvidence,
    NarrationContext,
    ObjectiveAdviceContext,
    ProgressContext,
    SkillingCapability,
    SkillingRunDeps,
    SkillingRunner,
    TutorPurpose,
    TutorRefresh,
)

models.ALLOW_MODEL_REQUESTS = False


class PolicyModel(WrapperModel):
    """Synthetic successful models first consume a real native skill activation."""

    def __init__(self, model: Model, skill: BundledSkill | None = None):
        super().__init__(model)
        self.skill = skill

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        schemas = [tool.parameters_json_schema for tool in model_request_parameters.output_tools]
        if model_request_parameters.output_object is not None:
            schemas.append(model_request_parameters.output_object.json_schema)
        skill = self.skill or (
            BundledSkill.HOMEWORK
            if any("requirements" in schema.get("properties", {}) for schema in schemas)
            else BundledSkill.LEARN
        )
        if not any(
            part.tool_name == "load_capability"
            and isinstance(part.content, dict)
            and f"# Skill: {skill.value}" in part.content.get("instructions", "")
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ):
            return ModelResponse(parts=[ToolCallPart("load_capability", {"id": skill.value})])
        return await self.wrapped.request(messages, model_settings, model_request_parameters)


def policy_model(
    *, call_tools=None, custom_output_args=None, custom_output_text=None, profile=None
):
    args = dict(custom_output_args) if custom_output_args is not None else None
    skill = BundledSkill.LEARN
    if args is not None:
        if "requirements" in args or "homework" in args:
            skill = BundledSkill.HOMEWORK
        if "progress" in args.get("refresh", ()):
            skill = BundledSkill.PROGRESS
        if "text" in args:
            args.setdefault("skill", skill.value)
    return PolicyModel(
        TestModel(
            call_tools=call_tools or [],
            custom_output_args=args,
            custom_output_text=custom_output_text,
            profile=profile,
        ),
        skill,
    )


@dataclass
class ConversationJourney:
    captures: list[tuple[list[ModelMessage], AgentInfo]]
    skills: list[str]

    @classmethod
    def create(cls) -> ConversationJourney:
        return cls([], [])

    async def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        await asyncio.sleep(0)
        self.captures.append((deepcopy(messages), info))
        assert {tool.name for tool in info.function_tools} == {
            "load_capability",
            "read_skill_reference",
        }
        assert info.instructions is not None
        data = json.JSONDecoder().raw_decode(
            info.instructions.split("SAFE CONTEXT (data):\n", 1)[1]
        )[0]
        for kind, skill, reference in (
            ("objectives", "learn", "objectives.md"),
            ("homework", "homework", "workflows.md"),
        ):
            if data[kind] is not None:
                assert (ROOT / skill / "references" / reference).read_text() in info.instructions
        latest = next(
            part.content
            for message in reversed(messages)
            if isinstance(message, ModelRequest)
            for part in reversed(message.parts)
            if isinstance(part, UserPromptPart)
        )
        assert isinstance(latest, str)
        skill = (
            "progress" if "progress" in latest else "homework" if "homework" in latest else "learn"
        )
        reference = {
            "progress": "references/reading-progress.md",
            "homework": "references/workflows.md",
            "learn": "references/objectives.md"
            if "objectives" in latest
            else "references/delivery-loop.md",
        }[skill]
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
            self.skills.append(skill)
            return ModelResponse(parts=[ToolCallPart("load_capability", {"id": skill})])
        reference_text = (ROOT / skill / reference).read_bytes().decode("utf-8")
        if not any(
            part.tool_name == "read_skill_reference" and part.content == reference_text
            for part in returns
        ):
            return ModelResponse(
                parts=[
                    ToolCallPart("read_skill_reference", {"skill": skill, "reference": reference})
                ]
            )
        output: dict[str, object] = {
            "text": f"{latest}: {data['teaching']['material']}",
            "skill": skill,
        }
        if skill == "progress":
            progress = data["progress"]
            output["text"] = (
                f"Current progress: {progress['completed_count']}/{progress['lesson_count']}"
                if progress
                else "Please ask the producer to refresh current progress"
            )
            if progress is None:
                output["refresh"] = ["progress"]

        def item(identity, evidence):
            return {
                "id": identity["id"],
                "verdict": "partial",
                "reason": f"Actual supplied evidence: {evidence['text']}",
            }

        if "objectives" in latest:
            review = data["objectives"]
            if review is None:
                output["text"] = "Please supply current objective criteria and actual evidence"
                output["refresh"] = ["objective-evidence"]
            else:
                output["objectives"] = {
                    "objectives": [
                        item(identity, review["evidence"]) for identity in review["objectives"]
                    ]
                }
        if skill == "homework":
            review = data["homework"]
            if review is None:
                output["text"] = "Please supply current homework criteria and actual evidence"
                output["refresh"] = ["homework-evidence"]
            else:
                output["homework"] = {
                    "requirements": [
                        item(identity, review["evidence"]) for identity in review["requirements"]
                    ],
                    "stretch_goals": [
                        item(identity, review["evidence"]) for identity in review["stretch_goals"]
                    ],
                }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    async def run(self) -> tuple[ModelMessage, ...]:
        runner = SkillingRunner.create(FunctionModel(self.respond))
        context = ConversationContext(
            NarrationContext("Course", "1.1", None, (), "Initial material"),
            "r1",
            ProgressContext(0, 2),
        )
        history: tuple[ModelMessage, ...] = ()
        for message in ("Explain this material", "Give me a hint", "Here is my reasoning"):
            result = await runner.chat(message, context, history=history)
            assert message in result.output.text
            assert result.output.objectives is None and result.output.homework is None
            assert len(result.history) > len(history)
            history = result.history
        evidence = LearnerEvidence.from_text("Current actual objective reasoning")
        objective = ObjectiveAdviceContext(
            (AdviceIdentity("objective", "Explain the result"),), evidence, "r2"
        )
        context = replace(
            context,
            teaching=replace(context.teaching, material="Refreshed material"),
            revision="r2",
            progress=ProgressContext(1, 2),
            objectives=objective,
        )
        original = repr(history)
        review = await runner.chat("Review my objectives", context, history=history)
        assert review.output.objectives is not None
        assert review.output.objectives.evidence_digest == evidence.digest
        assert review.output.objectives.revision == "r2"
        assert "Refreshed material" in review.output.text and repr(history) == original
        updated_evidence = LearnerEvidence.from_text("Updated actual objective reasoning")
        context = replace(
            context,
            revision="r3",
            objectives=replace(objective, evidence=updated_evidence, revision="r3"),
        )
        refreshed_review = await runner.chat(
            "Review my objectives again", context, history=review.history
        )
        assert refreshed_review.output.objectives is not None
        assert refreshed_review.output.objectives.evidence_digest == updated_evidence.digest
        assert refreshed_review.output.objectives.revision == "r3"
        assert (
            "Updated actual objective reasoning"
            in refreshed_review.output.objectives.objectives[0].reason
        )
        assert (
            "Current actual objective reasoning"
            not in refreshed_review.output.objectives.objectives[0].reason
        )
        assert "Updated actual objective reasoning" not in refreshed_review.output.text
        progress = await runner.chat(
            "What is my progress?", context, history=refreshed_review.history
        )
        assert progress.output.text == "Current progress: 1/2"
        homework_evidence = LearnerEvidence.from_text("Current actual homework work")
        homework = HomeworkAdviceContext(
            "Work",
            "Practice",
            (AdviceIdentity("required", "Do the work"),),
            (AdviceIdentity("stretch", "Extend the work"),),
            homework_evidence,
            "homework-slot",
        )
        result = await runner.chat(
            "Review my homework",
            replace(context, homework=homework, homework_revision="homework-slot"),
            history=progress.history,
        )
        assert result.output.homework is not None
        assert result.output.homework.evidence_digest == homework_evidence.digest
        assert result.output.homework.requirements[0].id == "required"
        assert result.output.homework.stretch_goals[0].id == "stretch"
        assert {"learn", "progress", "homework"} == set(self.skills)
        assert str(ROOT) not in repr(self.captures)
        return result.history


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
        policy_model(call_tools=[], custom_output_args={"objectives": [item]})
    ).advise_objectives(objective)
    assert advice.output.evidence_digest == evidence.digest
    homework = HomeworkAdviceContext("Work", "Practice", (identity,), (), evidence, "revision")
    result = await SkillingRunner.create(
        policy_model(
            call_tools=[], custom_output_args={"requirements": [item], "stretch_goals": []}
        )
    ).advise_homework(homework)
    assert result.output.requirements[0].id == "required"
    conversation = ConversationJourney.create()
    transcript = await conversation.run()
    cold = ConversationContext(
        NarrationContext(
            "Course",
            "1.1",
            None,
            (),
            '{"beat":"gate-exercise"}',
            Beat.GATE_EXERCISE,
            (Input.HINT, Input.ATTEMPTED),
        ),
        "r",
    )
    refreshed = await SkillingRunner.create(
        policy_model(
            call_tools=[],
            custom_output_args={"text": "Please refresh teaching", "refresh": ["teaching"]},
        )
    ).chat("Bring back the exercise", cold)
    assert refreshed.output.refresh == (TutorRefresh.TEACHING,)
    assert '"legal_inputs": ["hint", "attempted"]' in repr(refreshed.history)
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
                "conversation_turns": 7,
                "conversation_messages": len(transcript),
                "conversation_skills": conversation.skills,
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
