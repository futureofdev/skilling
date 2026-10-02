"""Synthetic installed-public-API proof; copied into an outside-checkout stage."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import sys
from pathlib import Path

from pydantic_ai import Agent, models
from pydantic_ai.models.test import TestModel

import skilling
import skilling_tutor
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
    context = NarrationContext("Course", "1.1", "Tutor", (), "Active material")
    cap = SkillingCapability.for_context(TutorPurpose.NARRATION)
    direct = Agent(
        TestModel(custom_output_text="narrated"), capabilities=[cap], deps_type=SkillingRunDeps
    )
    assert (await direct.run("turn", deps=SkillingRunDeps(context))).output == "narrated"
    assert cap.get_toolset() is None and cap.get_native_tools() == []
    assert (
        await SkillingRunner.create(TestModel(custom_output_text="narrated")).narrate(context)
    ).output == "narrated"
    evidence = LearnerEvidence.from_text("Actual learner proof")
    identity = AdviceIdentity("required", "Explain the result")
    item = {"id": "required", "verdict": "supported", "reason": "Actual proof explains the result"}
    objective = ObjectiveAdviceContext((identity,), evidence, "revision")
    advice = await SkillingRunner.create(
        TestModel(custom_output_args={"objectives": [item]})
    ).advise_objectives(objective)
    assert advice.output.evidence_digest == evidence.digest
    homework = HomeworkAdviceContext("Work", "Practice", (identity,), (), evidence, "revision")
    result = await SkillingRunner.create(
        TestModel(custom_output_args={"requirements": [item], "stretch_goals": []})
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
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
