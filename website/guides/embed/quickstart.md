---
title: Run the React tutor
sidebar_label: Run the example
description: Start a branded React and Tailwind tutor backed by FastAPI, PydanticAI and the Welcome course.
---

# Run the React tutor

Start with the included Welcome course, a local FastAPI server and the React interface.
You need Python 3.11 or later, [uv](https://docs.astral.sh/uv/getting-started/installation/),
Node 22.12 or later, and access to a model provider supported by PydanticAI.

This is a source-checkout quickstart. The optional tutor and matching core must come from
the same checkout; these instructions do not assume a public package release.

## Install the Python application

From a checkout containing the integration:

```bash
git clone https://github.com/futureofdev/skilling.git
cd skilling
uv sync --frozen
uv pip install --python .venv/bin/python \
  -e './packages/skilling-tutor[fastapi]' \
  'pydantic-ai-slim[openai]>=2.52.0,<2.53.0'
```

The provider extra above is for OpenAI. Replace it with the extra required by your chosen
provider. On Windows use `.venv/Scripts/python.exe` as the environment's Python path.
Keep the frozen source environment and selected provider installation: a later `uv sync`
can remove dependencies you installed separately.

Set `TUTOR_MODEL` to the provider-qualified model you want to use, and configure that provider's
credentials in the **server** environment. For example, an OpenAI model uses an `openai:` model
identifier and `OPENAI_API_KEY`. Never put the key in a `VITE_` variable or the browser chat.

The reference application's [README](https://github.com/futureofdev/skilling/blob/main/examples/react-tutor/README.md)
is the canonical command reference for its environment settings and launch commands.

## Start the backend and frontend

From the repository root, start the server:

```bash
uv run --no-sync uvicorn app:local_app --factory --app-dir examples/react-tutor \
  --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd skilling/examples/react-tutor
npm ci
npm run dev
```

Open the local address printed by Vite. The browser talks to `/api` through Vite's development
proxy, and the Python server owns all model requests. The example uses a local demo identity
and loopback guards. To embed it in your deployed application, replace that identity with
[your authentication dependency](fastapi.md).

## Take a real learning step

Start the conversation, choose a topic you want to learn, and respond to the tutor. Ask for
a different explanation or example when it helps. The course outline and progress display
come from saved state. Quiz choices are your answers; authored feedback appears before the
next teaching step.

Use the work area for the learner note and supply your own explanation when requesting a
review. Read the feedback before confirming an objective or homework submission. A positive
model review does not itself mark work complete.

The demo stores learning state and learner work under `examples/react-tutor/.data` by default.
Set `TUTOR_DATA_DIR` in the server environment to use another persistent directory.
Stop and restart the backend with the same state location. Committed progress survives;
conversation history and unconfirmed reviews start fresh. See [what persists](operate.md).

## Make it your application

Keep the Python integration and replace the React components, or keep the branded UI and
register your own course. The [FastAPI guide](fastapi.md) shows the small application setup;
the [React guide](react.md) explains stream events, acknowledgements and controls.
