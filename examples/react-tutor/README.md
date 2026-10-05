# A learning workspace you can make your own

A real React + TypeScript application using Tailwind CSS v4, Vercel AI SDK `useChat`, and
Skilling’s public `Tutor` / `mount_tutor` APIs. It runs the Welcome course with an
application-owned Pydantic AI Agent. Model output streams live; course material, quiz
feedback, progress and learner decisions stay structured.

This example uses the APIs in this checkout. It does not imply a published package release.

## Run it

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 22.12+, and a model provider
account. Choose a model that supports text generation and structured tool output for reviews.
Install that provider’s `pydantic-ai-slim` extra explicitly.

Use a checkout containing this integration. Until PR #135 merges, select it explicitly after
cloning the repository: `git fetch origin pull/135/head`, then `git switch --detach FETCH_HEAD`.
After merge, use `main`. Keep the core, tutor and application at the same revision.

From the repository root, install the Python server (OpenAI provider example):

```sh
uv sync --frozen
uv pip install --python .venv/bin/python -e './packages/skilling-tutor[fastapi]' \
  'pydantic-ai-slim[openai]>=2.52.0,<2.53.0'
```

Set `TUTOR_MODEL` to your provider-qualified model name (for example `openai:YOUR_MODEL`)
and set the provider credential, such as `OPENAI_API_KEY`, through your server environment
before starting Python. Never commit credentials or put them in frontend variables.
A later `uv sync` may remove separately installed provider extras; use `--no-sync` for launch.
On Windows, the environment Python is `.venv/Scripts/python.exe`. Then start the backend:

```sh
uv run --no-sync uvicorn app:local_app --factory --app-dir examples/react-tutor \
  --host 127.0.0.1 --port 8000
```

In another terminal, from the repository root:

```sh
cd examples/react-tutor
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. Vite proxies `/api` to port 8000. API keys stay on the Python
server; do not put them in `VITE_` variables. The example is restricted to loopback and trusted
local origins. Its default demo identity and optional learner selector are not production
authentication. Use your own application identity and course authorization for a hosted product.

This Welcome reference app uses the course alias `welcome`. When building your own application,
register your courses with `Tutor` and point the frontend at the matching alias with `VITE_COURSE`.
Adapt the Welcome-specific learner work and evidence flow for the new course.
`TUTOR_DATA_DIR` changes both launchers’ default storage directory (default: `.data` relative to
the directory where Python starts). The default store is SQLite at `.data/progress.sqlite3`; learner
work is stored separately. Run **one application worker**, including with PostgreSQL or S3.
Course progress survives restarts; chat, render receipts and outstanding informal reviews
are temporary. Two browsers using the same learner share that learner/course conversation.

## Serve a built app or install an artifact

Build the frontend from this directory:

```sh
npm ci
npm run build
```

The build typechecks the app, writes `dist/`, and stages the same assets under
`src/skilling_react_example/static/` for Python packaging. Those outputs are ignored by Git;
build them before packaging. From the repository root:

```sh
uv run --no-sync skilling-react-example serve --model "$TUTOR_MODEL" \
  --host 127.0.0.1 --port 8000
# To create installable artifacts after the frontend build:
uv build --package skilling-react-example
```

Open `http://127.0.0.1:8000` for the built app; no Vite server is needed. Both the wheel and
sdist include the staged frontend assets. An installed deployment must also supply the Welcome
course with `--course /absolute/path/welcome-skilling` (or `TUTOR_COURSE_DIR`) and explicitly install its chosen
model-provider SDK. The source checkout can locate its bundled Welcome course automatically.
Building artifacts does not publish them or establish release readiness.

Both launch paths default to `.data` relative to the directory where Python starts. The CLI
reads `TUTOR_CONFIG`, `TUTOR_DATA_DIR` and `TUTOR_COURSE_DIR`; explicit `--config`, `--data-dir`
and `--course` flags override those defaults. When a TOML configuration is selected, its backend,
course and learner paths determine storage. The CLI still requires `--model`; the ASGI factory
reads `TUTOR_MODEL`. Supported launcher hosts are `127.0.0.1` and `localhost`.

## Configure persistence and local learner identities

Set `TUTOR_CONFIG` to an absolute TOML path, or pass `--config /absolute/path/producer.toml`
to the launcher. The [session integration reference](../../docs/embedding-a-tutor.md)
contains the complete two-learner configuration and file, SQLite, PostgreSQL and S3 settings.
Course sources and separate learner work directories must already exist at canonical absolute
paths. Keep the state directory outside learner work roots.

For the default SQLite setup, use `--data-dir /absolute/path/data` or `TUTOR_DATA_DIR`.
The configured backend is explicit: connection failures never fall back to local storage.
Optional backend SDKs must be installed in the same application environment; credentials come
from server-side environment variables or the SDK credential chain, never the browser.

Open separate browser profiles and select different demo learners to verify isolation. An
HttpOnly, SameSite=strict cookie, JSON requests and same-origin checks protect the loopback
boundary. Switching learner clears the browser view; returning can restore that learner's
in-process conversation. Restart discards conversations and reviews while preserving committed
progress, pending canonical feedback and files in durable work storage.

Use [deployment and recovery](https://futureofdev.github.io/skilling/docs/embed/operate)
for backup, restore, identity, retry and single-worker requirements. A shared backend alone
does not coordinate the tutor's in-memory locks or presentation handles across replicas.

## What to try

1. Ask your tutor to walk through the first idea. Watch the response stream. Ask for another
   example or change the pace. Ordinary teaching continues after completed material renders;
   explicit choices and quiz answers remain learner actions.
2. Work through an exercise in conversation, then choose **Attempted** or explicitly report
   that you tried it. Asking to keep the same pace does not report an attempt. Answer the quiz
   using a button or your own message. Questions and canonical feedback stay in the conversation
   beside each answer. A stopped or failed draft does not acknowledge learning material.
3. Open **Your practice & reflection**. Explain what you understand and request a learning
   review. Read the advice, then explicitly confirm each supported objective you authored.
4. In the second lesson, save a note with meaningful **Goal:**, **Takeaway:** and
   **Next action:** entries. The app saves your exact words at
   the authorized learner work root under `showcase/welcome-skilling/goal.md`. Its evidence hook reads those bytes,
   checks the entries exist and hashes the content. Model advice reviews meaning; the app’s
   file check is not a claim that the work is correct or original.
5. Complete the lesson separately from reviewing and submitting the unlocked homework.
   Edit your note to include the homework reflection, request fresh advice, and confirm
   submission only after reading every requirement’s feedback.

## Integration map

| File                  | Responsibility                                                                    |
| --------------------- | --------------------------------------------------------------------------------- |
| `app.py` | Source-checkout ASGI entry point |
| `src/skilling_react_example/` | Agent, identity, scoped persistence, work storage and packaged CLI |
| `src/App.tsx`         | `useChat`, bounded transport requests, streaming lifecycle and learning workspace |
| `src/Workbench.tsx`   | Saved work, evidence review and explicit learner confirmations                    |
| `src/presentation.ts` | Visible paint checks before acknowledging committed content                       |
| `src/types.ts`        | Copied JSON presentation types; no hidden grading answers                         |
| `src/styles.css`      | Tailwind theme, component utilities and responsive layout                         |

The frontend uses the standard AI SDK UI message stream. Custom `data-skilling` parts carry
canonical states, narration resets and errors. Streamed drafts are provisional: rejected
narration is removed on `text-reset`, and final `state.messages` replaces the draft.
`prepareSendMessagesRequest` sends the latest request only because the server owns history.
Retries reuse the same request ID and body; the server prevents repeating committed actions.
Stop cancels the transport; refresh recovers the current durable state.

Render acknowledgement means “this completed presentation had a visible paint opportunity.”
It is not learner consent, proof of reading or a completion decision. Hidden tabs, removed
components, partial streams and failed turns do not receive acknowledgement. Reviews require
their own render receipt and a separate learner confirmation. Changing saved work invalidates
the old review. Canonical quiz questions and feedback remain in chronological transcript order
when the next teaching turn arrives. Only the current server controls can advance learning.

For your production application, supply your verified identity dependency and disable demo selection,
register your course, and implement your own storage-backed `Evidence` provider. Keep
`checked` and `attested_by` server-owned. Preserve origin protections, course authorization,
request limits and stable learner identity. The core package remains independent of React,
FastAPI, Pydantic AI and the model provider.

## Brand and accessibility

The mark (`public/skilling-mark.svg`) and tokens (`src/brand/tokens.css`) are unmodified source
assets copied from **skilling-brand-assets-v2.0**, provided in `skilling-strategy` on
2026-10-05. Created by Future of Dev. No generated raster derivatives are included.

The Cut is Ink on a light field. Geometry has zero radius. Archivo and Inter are bundled from
Fontsource rather than fetched from a third-party font service. Build lime denotes learner
actions and completed progress; Signal denotes navigation and system actions. The layout
supports narrow screens, keyboard navigation, focus outlines, reduced motion, safe Markdown,
and polite status announcements without announcing every streamed token.

## Verify

```sh
# From this directory
npm test
npm run build

# From the repository root
uv run pytest examples/react-tutor/tests
```

The tests exercise actual AI SDK streaming transport with deterministic HTTP/SSE fixtures,
canonical content, visible render receipts, local identity protection and saved evidence.
They do not claim a live model-provider run.

Implementation references: [AI SDK transport](https://ai-sdk.dev/docs/ai-sdk-ui/transport),
[custom streaming data](https://ai-sdk.dev/docs/ai-sdk-ui/streaming-data),
[Tailwind’s Vite integration](https://tailwindcss.com/docs/installation/using-vite).
