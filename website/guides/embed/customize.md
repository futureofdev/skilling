---
title: Make the tutor yours
sidebar_label: Customize and chat
description: Give Tutor your PydanticAI Agent, then chat through its streaming API or FastAPI mount.
---

# Make the tutor yours

Give `Tutor` your text-output Agent. Keep your model, instructions and tools; Skilling handles
course flow and learner progress.

```python
import os
from pathlib import Path

from pydantic_ai import Agent
from skilling_tutor import Tutor

agent = Agent(
    os.environ["TUTOR_MODEL"],
    instructions="Keep replies concise. Use examples from our product.",
)

@agent.tool_plain
def product_glossary(term: str) -> str:
    """Look up an approved product definition."""
    return {"workspace": "A shared area for a team's projects."}.get(
        term.casefold(), "No glossary entry."
    )

tutor = Tutor(
    agent=agent,
    courses={"onboarding": Path("./courses/onboarding")},
    state_dir=Path("./data/learning"),
)
```

## Chat with it

From your existing async chat handler, stream events for the authenticated learner:

```python
async def chat(user_id: str, message: str, display_id: str, request_id: str):
    session = tutor.session(learner_id=user_id, course="onboarding")
    async for event in session.stream(
        message,
        display_id=display_id,
        request_id=request_id,
    ):
        yield event
```

Get the initial display from `await session.state()`. Use a new request ID for each message
and reuse it for an exact retry. Render `text-delta`, discard drafts on `text-reset`, reconcile
the accepted `state`, and show `error` without acknowledging it.
[Acknowledge completed renders](react.md#acknowledge-what-was-actually-shown)
to continue teaching; gates still wait for the learner.

## Put it in a web app

For FastAPI, the mount handles that streaming endpoint for you:

```python
from fastapi import FastAPI
from my_app.auth import current_user  # Returns the authenticated user's stable ID.
from skilling_tutor.fastapi import mount_tutor

app = FastAPI()
mount_tutor(app, tutor, current_user=current_user)
# Connect your chat to POST /api/learn/onboarding/chat.
```

Use the [React reference app](quickstart.md) for the complete chat UI, or follow the
[React event handling](react.md) and [FastAPI authentication](fastapi.md) guides.

For account-scoped tools, pass `deps_factory=lambda user_id, course: AppDeps(user_id, course)`
alongside an Agent configured with `deps_type=AppDeps`. For work reviews, supply an async
`evidence_provider(user_id, course, snapshot)` returning `Evidence` from your actual storage;
see the [working example](https://github.com/futureofdev/skilling/blob/main/examples/react-tutor/app.py).
If your Agent has output validators, use a separate `review_agent` without them for structured reviews.
