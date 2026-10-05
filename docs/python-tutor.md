# Conversational Python tutor

For a complete application integration, start with the
[Embed a tutor website guide](https://futureofdev.github.io/skilling/docs/embed) and
[React reference application](../examples/react-tutor/README.md). The public `Tutor` and
optional `skilling_tutor.fastapi.mount_tutor` combine the capability below with a trusted,
file-backed application controller and real streaming. This page documents the lower-level
conversation and capability interfaces, which remain useful for custom transports.

`skilling-tutor` 0.1.0 is an experimental optional adapter for a trusted Python producer.
Its matching core is `skilling>=0.8.0,<0.9.0`, the first allocated minor containing the public
session facade. This source change does not publish either distribution or execute a release.
The adapter supports `pydantic-ai-slim>=2.52.0,<2.53.0` and
`pydantic-ai-harness[skills]>=0.52.0,<0.53.0`; provider SDKs/extras are explicitly
selected and installed by the producer. The core remains LLM-free.

Use `SkillingRunner.chat` for ordinary learner messages. A single native conversational Agent
selects the applicable shared skill policy and replies with text and optional validated informal
objective/homework feedback. The application does not select a teaching mode. This shares the
bundled tutoring policy with Claude Code/Codex; synthetic tests do not establish identical real
model quality. Genuine provider/learner acceptance remains separate.

```python
from skilling_tutor import ConversationContext, SkillingRunner

runner = SkillingRunner.create(selected_model)
history = ()
# Refresh public state before each turn; context stays stable during that turn.
context = ConversationContext.from_snapshot(session.snapshot())
turn = await runner.chat(learner_message, context, history=history)
print(turn.output.text)
history = turn.history  # complete copied transcript, including previous turns
```

`ConversationContext.from_snapshot` copies the current beat, legal inputs, teaching/feedback,
revision and the public
snapshot's completed/total lesson counts. It adds no assumed streak, phase or other progress facts.
A manually created context can omit progress. Optional `objectives` and `homework` arguments are
existing safe advice contexts containing current scoped criteria and actual producer-selected
evidence. Objective advice must match the current snapshot/record revision. Homework slots have
a separate revision: pass a freshly read public `homework_check` alongside `homework` to
`from_snapshot`. The factory checks that slot's revision and active criteria against the supplied
safe review context, then copies only the slot revision. It retains no check, token or queued work.
A manually constructed conversation context must supply the separate current `homework_revision`;
never use an old advice context as its own freshness witness. Missing data leads to
clarification or a producer-refresh request. Scoped evidence remains distinct from the latest
learner utterance. The tutor may answer an ordinary question without assessing it even when
review context is available.

`ConversationReply` contains `text`, the selected `BundledSkill`, optional
`objectives`/`homework` advice, and an immutable
`refresh` tuple of `TutorRefresh` values. These bounded requests identify missing teaching,
progress, objective evidence or homework evidence. They authorize no controller action.
The producer can satisfy them with fresh public reads and actual evidence, then build a new
context for a subsequent turn. A gate snapshot may omit the previous teaching body: retain a
producer-owned copy tied to the course identity/version and coordinate, or ask the learner to
choose an available controller control. Supplement the current material with that matching body;
preserve the fresh gate, legal inputs and canonical pending feedback. Never reuse an old context
or its controls wholesale. Never translate a model refresh into `hint`, `advance`, acknowledgement,
file execution or submission. `hint` is a state transition and requires the learner's choice.
Only current `legal_inputs` authorize offered delivery controls; `None` means unknown and `()`
means none. Manual contexts may omit the beat and legal inputs; refresh before offering controls.
The conversational wire requires the model to declare its selected skill. Native output hooks
require that policy to have been activated before the model request that produced the reply.
Scoped feedback and refresh also require their corresponding policies. A known cold gate
snapshot requires `teaching` refresh. A selected progress/homework policy with no corresponding
current data requires its refresh request. Other missing-data classification remains a model
decision; absent objective/homework criteria still forbid feedback regardless of that decision.
No model refresh automatically reads or changes anything.
One combined retry identifies all missing requirements. A model that refuses them fails within
the producer's retry and usage limits. Loading a skill alongside final output is too late: the
model must receive its policy on a subsequent request before completing the reply.
Every emitted
feedback block must cover the supplied identities exactly once and is bound to that context's
actual evidence digest/revision. No feedback can be emitted for an absent review context.
`ConversationReply.output_type()` and `from_output` support equivalent direct native Agents;
producer Agents can retain their own output contract instead. `ConversationResult.history` is a
copied accumulated native transcript; store it per learner and pass it to the next call, or pass
`[]` to reset. The runner retains no transcript. Its conversational operation passes the actual
bounded latest learner message to `Agent.run`.

The producer owns identity/session binding, fresh trusted reads, transcript storage, model/provider,
UI, file inspection, permission/consent, presentation acknowledgement and every learning-state
mutation. Conversation, feedback and model recommendations cannot advance a gate, acknowledge
pending feedback, settle an objective or submit homework. Explicit learner controls remain separate.
The advanced purpose-specific methods below remain available for explicitly scoped integrations.

Copy the current session into a narrow context. Keep the session, Course, paths, credentials,
action event identities, feedback references and homework submission token in the controller.
`NarrationContext.from_snapshot` copies the beat, legal inputs, active material/persona/tone and canonical pending
feedback; it excludes learner identity, revision, future questions and receipt handles. An absent
authored persona stays absent.
`ObjectiveAdviceContext.from_objectives` copies objective ids, kinds and authored criteria.
`HomeworkAdviceContext.from_check` copies the active required/stretch lists, never queued work
or submission text/token. Requirements receive stable coordinate/category/ordinal identities,
so identical text still requires separate results. `LearnerEvidence.from_text` bounds actual
producer-selected learner evidence and binds its digest. Safe contexts are frozen and bounded.

```python
from dataclasses import dataclass
from pydantic_ai import Agent
from skilling_tutor import (
    ConversationContext, ConversationReply, SkillingCapability, TutorPurpose,
)

@dataclass(frozen=True)
class ProducerDeps:
    context: ConversationContext
    # Trusted application dependencies may also live here, but the getter returns only safe data.

def safe_context(deps: ProducerDeps) -> ConversationContext:
    return deps.context

capability = SkillingCapability.create(
    TutorPurpose.CONVERSATION, context_getter=safe_context,
)
# selected_model is a producer-configured Model or model identifier; no default provider.
agent = Agent(
    selected_model, deps_type=ProducerDeps, capabilities=[capability],
    output_type=ConversationReply.output_type(),
)
context = ConversationContext.from_snapshot(session.snapshot())
result = await agent.run(learner_message, deps=ProducerDeps(context), message_history=history)
reply = ConversationReply.from_output(result.output, context=context)
print(reply.text)
history = result.all_messages()  # producer-owned, isolated per learner
# Read-only refresh requests and presentation acknowledgement remain producer responsibilities.
```

The native capability shares the exact bundled `learn`, `progress` and `homework` skills with
Codex and Claude Code. Native Harness `Skills` exposes `load_capability`; one allowlisted
`read_skill_reference` tool returns the original packaged reference text. These are its only two
function tools. Current delivery references and scoped objective/homework review references are
also supplied verbatim through dynamic native instructions. Activated progress/homework policies
receive their references on every model request, including skills restored from retained history.
This guarantees current policy availability without relying on a model remembering a tool read;
additional references remain available through the reader. The transport purpose is fixed by the
producer's output contract: ordinary chat uses `CONVERSATION`; changing course beats and learner
requests select policy within that contract. `NARRATION` is an explicitly scoped text helper.
The package backend contains only the triad's policy bytes, works on every supported
platform, and grants no host filesystem, shell, state or run-workspace access. `upgrade-skilling`
is excluded. An always-on binding maps bundled CLI and host duties to the trusted producer:
course/state discovery and reads, file edits, processes, checks, consent, firsthand inspection,
provenance, objective settlement, presentation, submission and token retention. The tutor advises
from actual supplied safe evidence and requests producer refresh when facts are missing; it cannot
claim or promise those operations or infer unprovided counts, continuity, submission status or work.

The capability contributes no native tools or model/provider/settings/output-type overrides.
For a custom conversational output contract it requires an applicable canonical skill without
adding fields to that contract. Advanced scoped purposes require their corresponding skill.
The per-run guard retains only the policy IDs available to the latest model request, and never
keeps learner context or history on the shared capability.
Upstream may attach infrastructure such as tool search; structured output modes also use output
tools. The producer Agent retains its output contract and can compose trusted benign capabilities.
Producer-added tools/hooks are the producer's authority and responsibility; composition is no
security guarantee. Material, history and learner text are untrusted content. Neither prompt
instructions nor model output can authorize controller operations, settle objectives, submit work
or acknowledge feedback.

On pinned 2.52.0, IDs are `skilling-conversation`, `skilling-narration`, `skilling-objective-advice` and
`skilling-homework-advice`. Equivalent duplicate configuration is combined; different getters for
the same purpose refuse. Upstream per-run same-ID capabilities replace the agent registration
wholly. The adapter checks the public registered capability tree through `for_agent` and refuses
conflicting configurations before replacement. Equivalent replacements remain supported and
validate each run's purpose and context. Each capability has immutable configuration and retains
no run context/history/usage. Typed getters are trusted producer functions: keep them pure and
return only safe context, even when the producer deps also contain privileged objects.

```python
from skilling_tutor import LearnerEvidence, HomeworkAdviceContext, NarrationContext, SkillingRunner
from pydantic_ai.usage import UsageLimits

runner = SkillingRunner.create(selected_model, usage_limits=UsageLimits(request_limit=16))
context = NarrationContext.from_snapshot(session.snapshot())
turn = await runner.narrate(context, history=[])  # complete async turn
# Optional next-turn history is explicitly producer-owned:
next_turn = await runner.narrate(context, history=turn.new_messages)
check = session.homework_check()
advice_context = HomeworkAdviceContext.from_check(
    check, evidence=LearnerEvidence.from_text(actual_learner_work),
)
advice = await runner.advise_homework(advice_context)
```

The runner owns one primary conversational Agent plus three advanced purpose Agents sharing the
selected model/config and the same native capability.
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
to sixteen requests (previously eight): three skill activations, all eight sequential reference
reads and output use twelve, leaving bounded retry room. Normal turns can activate fewer skills
and read references in parallel. Explicit producer limits remain unchanged and may refuse
a turn before completion. The runner disables Agent instrumentation and emits no learner logs or
automatic tracing.
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
and exercises native activation, all original triad references, direct attachment, runner narration
and both advice operations, plus a retained multi-turn conversation switching learning, objective
review, current progress and homework review without caller-selected modes. A separate core-only
install proves that neither tutor nor framework is required by the core. CI retains the full source
matrix and runs matching installed artifacts on Linux/macOS/Windows at Python 3.11/3.14; local
results establish only the tested host/interpreter, never published artifacts or other platforms.

For a runnable local UI using these public APIs, see the [browser producer walkthrough](python-producer.md).
