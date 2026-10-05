---
title: Make the tutor yours
sidebar_label: Agent and evidence
description: Extend your PydanticAI Agent, supply application dependencies, and review real learner evidence.
---

# Make the tutor yours

The high-level `Tutor` accepts your existing PydanticAI **text-output Agent**. Its model,
instructions, tools and configuration remain yours. Skilling attaches its teaching capability
for each run with a fresh, narrow copy of the current course state.

```python
import os
from pydantic_ai import Agent

agent = Agent(
    os.environ["TUTOR_MODEL"],
    instructions=(
        "Teach with examples from our product. Keep explanations concise, "
        "and ask the learner before moving past a readiness gate."
    ),
)

@agent.tool_plain
def product_glossary(term: str) -> str:
    """Explain a product term using the application's approved glossary."""
    return {"workspace": "A shared area for a team's projects."}.get(
        term.casefold(), "No glossary entry is available for that term."
    )
```

Pass this Agent to `Tutor` as in the [FastAPI integration](fastapi.md). You can use another
provider supported by your installed PydanticAI version. Install that provider's SDK and keep
credentials in the server environment. No model or provider is selected by Skilling.

## Keep application dependencies native

Use the Agent's normal typed dependencies for account-scoped tools. A `deps_factory` on `Tutor`
receives the trusted learner ID and registered course alias for each run. It returns the
dependency object expected by your Agent. Scope any data-access tools to that authenticated
learner; a prompt is not an authorization check.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class AppDeps:
    learner_id: str
    course: str

agent = Agent(os.environ["TUTOR_MODEL"], deps_type=AppDeps)
# Supply this alongside agent, courses and state_dir in Tutor(...):
# deps_factory=lambda learner_id, course: AppDeps(learner_id, course)
```

The safe context sent to the tutoring capability contains current teaching and public progress.
Raw course objects, filesystem paths, credentials, future quiz material and confirmation tokens
stay outside it. Your additional tools remain your application's responsibility.

## Review actual work

Teaching conversation and assessment evidence serve different purposes. To review practical
work, supply an `evidence_provider` that reads the relevant learner work from your application's
trusted storage and returns the observed text plus a stable revision. A learner saying they
saved or tested a file does not prove the file exists or a check passed.

Reviews are informal. Present the review, then ask for the learner's explicit confirmation.
The runtime calls the evidence provider again before confirmation so an edit cannot reuse a
stale positive review. The async hook signature is
`evidence_provider(learner_id, course_alias, snapshot) -> Evidence | None`; see
[`WorkStore.evidence` in the reference app](https://github.com/futureofdev/skilling/blob/main/examples/react-tutor/app.py).
Homework submission also requires its own confirmation. Keep file editing and work storage
in your application; the tutor does not gain shell or filesystem access by being mounted.

The public `Evidence` value has `text` and `revision`, plus optional `checked` and
`attested_by` provenance. Practice confirmation requires actual producer inspection with
that provenance. Never copy browser-supplied claims into those fields. The reference app's
saved work editor demonstrates a narrow evidence provider for the Welcome note.

Reviews use structured model output. If your conversational Agent has output validators,
provide a separate `review_agent` without output validators, with the same dependency type and
appropriate provider configuration. PydanticAI forbids overriding output type when any output
validator is installed. The adapter does not silently remove your validators.

## Structured-output Agents and lower-level integrations

The streaming chat integration uses text output. If your Agent has a structured output contract,
use the existing native `SkillingCapability` with your own controller rather than changing that
contract implicitly. The [Python tutor API guide](https://github.com/futureofdev/skilling/blob/main/docs/python-tutor.md)
shows direct capability composition, safe context construction, `ConversationReply` and
`SkillingRunner`.

The [session facade](https://github.com/futureofdev/skilling/blob/main/docs/python-session.md)
remains available to applications implementing another transport. `SkillingRunner.chat` itself
provides read-only conversation; the mounted `Tutor` adds the trusted application flow around it.
