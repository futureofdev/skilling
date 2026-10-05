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

From the repository root, start the Python server (OpenAI example):

```sh
uv sync --frozen
uv pip install --python .venv/bin/python -e './packages/skilling-tutor[fastapi]' \
  'pydantic-ai-slim[openai]>=2.52.0,<2.53.0'
export TUTOR_MODEL='openai:gpt-4.1-mini'
export OPENAI_API_KEY='your-key'
uv run --no-sync uvicorn app:local_app --factory --app-dir examples/react-tutor --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd examples/react-tutor
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. Vite proxies `/api` to port 8000. API keys stay on the Python
server; do not put them in `VITE_` variables. The example’s fixed identity is restricted to
loopback and trusted local origins. It is a single-user demo, not a deployment authentication
system. Do not expose it through a public tunnel.

The course alias defaults to `welcome`. `VITE_COURSE` selects another alias when adapting
`app.py` to register your own courses. `TUTOR_DATA_DIR` changes the storage directory (default:
`examples/react-tutor/.data`). Run **one application worker** for this file-backed Tutor.
Course progress survives restarts; chat, render receipts and outstanding informal reviews
are temporary. The UI displays this distinction.

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
   `.data/workspace/showcase/welcome-skilling/goal.md`. Its evidence hook reads those bytes,
   checks the entries exist and hashes the content. Model advice reviews meaning; the app’s
   file check is not a claim that the work is correct or original.
5. Complete the lesson separately from reviewing and submitting the unlocked homework.
   Edit your note to include the homework reflection, request fresh advice, and confirm
   submission only after reading every requirement’s feedback.

## Integration map

| File                  | Responsibility                                                                    |
| --------------------- | --------------------------------------------------------------------------------- |
| `app.py`              | Your Agent, course registration, identity dependency and application work storage |
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

For your production application, replace `current_user` with your authentication dependency,
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
