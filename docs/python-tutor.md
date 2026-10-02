# Optional Python tutor

`skilling-tutor` 0.1.0 is an experimental optional adapter for a trusted Python producer.
Its matching core is `skilling>=0.8.0,<0.9.0`, the first allocated minor containing the public
session facade. This source change does not publish either distribution or execute a release.
The adapter supports `pydantic-ai-slim>=2.52.0,<2.53.0`; provider SDKs/extras are explicitly
selected and installed by the producer. The core remains LLM-free.

Copy the current session into a narrow context. Keep the session, Course, paths, credentials,
action event identities, feedback references and homework submission token in the controller.
`NarrationContext.from_snapshot` copies only active material/persona/tone and canonical pending
feedback; it excludes learner identity, revision, future questions and receipt handles.
`ObjectiveAdviceContext.from_objectives` copies objective ids, kinds and authored criteria.
`HomeworkAdviceContext.from_check` copies the active required/stretch lists, never queued work
or submission text/token. Requirements receive stable coordinate/category/ordinal identities,
so identical text still requires separate results. `LearnerEvidence.from_text` bounds actual
producer-selected learner evidence and binds its digest. Safe contexts are frozen and bounded.

```python
from dataclasses import dataclass
from pydantic_ai import Agent
from skilling_tutor import NarrationContext, SkillingCapability, TutorPurpose

@dataclass(frozen=True)
class ProducerDeps:
    teaching: NarrationContext
    # Trusted application dependencies may also live here, but the getter returns only teaching.

def teaching_context(deps: ProducerDeps) -> NarrationContext:
    return deps.teaching

capability = SkillingCapability.create(
    TutorPurpose.NARRATION, context_getter=teaching_context,
)
# selected_model is a producer-configured Model or model identifier; no default provider.
agent = Agent(selected_model, deps_type=ProducerDeps, capabilities=[capability])
context = NarrationContext.from_snapshot(session.snapshot())
result = await agent.run("Teach the active turn", deps=ProducerDeps(context))
# Present result.output successfully before the controller acknowledges presentation.
```

The native capability contributes dynamic instructions and validation only, zero function or
native tools, workspace, model/provider/settings override or output-type override. Upstream
may attach its own infrastructure such as tool search; structured output modes also use output
tools. These are distinct from Skilling mutation tools. The producer Agent retains its output
contract and can compose trusted benign capabilities without an adapter registry. Producer-added
tools/hooks are the producer's authority and responsibility; composition is no security guarantee.
Material, history and learner text are untrusted content. Neither prompt instructions nor model
output can authorize a controller operation, settle objectives, submit work or acknowledge feedback.

On pinned 2.52.0, IDs are `skilling-narration`, `skilling-objective-advice` and
`skilling-homework-advice`. Equivalent duplicate configuration is combined; different getters for
the same purpose refuse. Upstream per-run same-ID capabilities replace the agent registration
wholly. The adapter checks the public registered capability tree through `for_agent` and refuses
conflicting configurations before replacement. Equivalent replacements remain supported and
validate each run's purpose and context. Each capability has immutable configuration and retains
no run context/history/usage. Typed getters are trusted producer functions: keep them pure and
return only safe context, even when the producer deps also contain privileged objects.

```python
from skilling_tutor import LearnerEvidence, HomeworkAdviceContext, SkillingRunner
from pydantic_ai.usage import UsageLimits

runner = SkillingRunner.create(selected_model, usage_limits=UsageLimits(request_limit=3))
turn = await runner.narrate(context, history=[])  # complete async turn
# Optional next-turn history is explicitly producer-owned:
next_turn = await runner.narrate(context, history=turn.new_messages)
check = session.homework_check()
advice_context = HomeworkAdviceContext.from_check(
    check, evidence=LearnerEvidence.from_text(actual_learner_work),
)
advice = await runner.advise_homework(advice_context)
```

The runner owns three Agents sharing the selected model/config and the same native capability.
Narration returns text. Objective/homework advice returns frozen informal advice with exactly one
bounded reason/verdict per required identity, separate stretch results, evidence digest and revision.
Missing, unknown or duplicate identities refuse. `ObjectiveAdvice.output_type()` and
`HomeworkAdvice.output_type()` expose the adapter wire boundary for direct producer Agents;
call `from_output(wire, context=...)` to enforce full identity/cardinality before displaying advice.
Default structured output uses Pydantic tool output; direct producers may choose its standard
native/prompted wrappers when their selected model supports them. The capability leaves these
output choices intact. Same-model advice is informal feedback, never independent grading or
certification. Actual learner confirmation and trusted evidence remain separate controller steps.

`TutorResult` separates output/status from frozen copied usage and adapter-specific new messages.
Framework messages are mutable producer-owned objects, copied on runner input/output; the runner
never retains them. Keep histories isolated by learner/purpose, redact before selecting them,
and pass no history or `[]` to clear it. A producer-configured Model must itself support safe
concurrent use. Settings/limits are copied and usage starts afresh each run. The runner defaults
to three requests, disables Agent instrumentation, and emits no learner logs or automatic tracing.
Explicit producer instrumentation of a selected Model remains producer-owned.

`TutorError.kind` distinguishes invalid context/configuration, usage limit, model failure and
invalid advice. Missing optional provider SDK/configuration produces an actionable adapter
configuration error; an incompatible core import asks for matching artifacts. Ordinary provider
failures are mapped without placing exception text/credentials in the model prompt. Async
cancellation propagates. Failure/cancellation never acknowledges feedback, mutates progression
or implies rollback of an earlier controller commit. Retry narration of the same canonical pending
feedback; controller mutations require their own public session retry/reconciliation rules.

Build and verify matching local artifacts before using the adapter:

```sh
uv build --package skilling --out-dir dist/core
uv build --package skilling-tutor --out-dir dist/tutor
task package:tutor:smoke
```

The smoke creates fresh environments outside the checkout, installs local wheel and sdist pairs
in the same resolver operation, disables real model requests, inspects metadata/license/typing,
and exercises direct attachment, runner narration and both advice operations. A separate core-only
install proves that neither tutor nor framework is required by the core. CI retains the full source
matrix and runs matching installed artifacts on Linux/macOS/Windows at Python 3.11/3.14; local
results establish only the tested host/interpreter, never published artifacts or other platforms.
