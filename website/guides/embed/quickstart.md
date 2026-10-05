---
title: Run the React tutor
sidebar_label: Run the example
description: Start a React and Tailwind tutor backed by FastAPI, PydanticAI and the Welcome course.
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
# Until PR #135 merges, select its source integration:
git fetch origin pull/135/head
git switch --detach FETCH_HEAD
uv sync --frozen
uv pip install --python .venv/bin/python \
  -e './packages/skilling-tutor[fastapi]' \
  'pydantic-ai-slim[openai]>=2.52.0,<2.53.0'
```

After PR #135 merges, `main` contains the integration and the two PR-checkout commands can be
omitted. Keep core, tutor and example app on the same checkout.

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

In a second terminal, from the same repository root:

```bash
cd examples/react-tutor
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

The development server stores its SQLite database (`progress.sqlite3`) and learner work under
`.data` in the directory where Python starts (the repository root in these commands).
Set `TUTOR_DATA_DIR` in the server environment to use another persistent directory.
For multiple demo learners or another backend, set `TUTOR_CONFIG` to an absolute TOML file;
follow the [complete configuration example](/reference/embedding-a-tutor#run-the-local-reference-producer).
Use separate browser profiles when testing independent learner identities.

Stop and restart the backend with the same state location. Committed progress survives;
conversation history and unconfirmed reviews start fresh. See [what persists](operate.md).

## Make it your application

Keep the Python integration and replace the React components, or keep the branded UI and
register your own course in your application-owned `Tutor`. The Welcome demo has course-specific
work and evidence handling; adapt those too when changing courses. The [FastAPI guide](fastapi.md) shows the small application setup;
the [React guide](react.md) explains stream events, acknowledgements and controls.

## Build and troubleshoot

`npm run build` in `examples/react-tutor` typechecks the frontend and generates production
assets. The [application README](https://github.com/futureofdev/skilling/blob/main/examples/react-tutor/README.md)
describes how the packaged launcher serves those assets and how to build matched source artifacts.
A production frontend build does not make the demo authentication suitable for public hosting;
follow [deployment and recovery](operate.md) when integrating it into your product.

| Symptom | Next step |
|---|---|
| Backend asks for `TUTOR_MODEL` | Set a provider-qualified model name in the terminal starting Python. |
| Provider import or credential error | Install that provider's extra into the same Python environment and configure its server credentials. |
| Vite loads but API requests fail | Check that the Python server is listening on loopback port 8000 and use the Vite URL. |
| Existing course state refuses to open | Restore the original course source/version; do not delete progress to hide a version mismatch. |
| Restart loses notes or progress | Confirm the same persistent data/config path and authorized identity are in use. |
| An action reports a stale display | Refresh state and make a new choice from the current controls. |

## Serve the built interface from Python

After `npm run build`, return to the repository root and start the source-installed launcher:

```bash
uv run --no-sync skilling-react-example serve \
  --model "$TUTOR_MODEL" --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. This serves the built React assets and API from one origin;
you do not need the Vite development server. Use `--config /absolute/path/producer.toml`
for configured identities and persistence, `--data-dir /absolute/path/data` for default SQLite
storage, or `--course /absolute/path/welcome-skilling` for an explicit Welcome course source. The launcher
requires built frontend assets. `npm run build` stages them in both `dist/` and the Python
package so `uv build --package skilling-react-example` can include them in its wheel and sdist. It enforces
loopback hosting (`127.0.0.1` or `localhost`) and does not add a production login system.

The launcher shares the development server's `.data` default and reads `TUTOR_CONFIG`,
`TUTOR_DATA_DIR` and `TUTOR_COURSE_DIR`; explicit flags override those environment defaults.
With a TOML configuration selected, its backend, course and learner paths take precedence.
Keep `--model` explicit for this CLI; the ASGI development factory reads `TUTOR_MODEL`.
