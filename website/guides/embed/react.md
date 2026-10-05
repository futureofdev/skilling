---
title: A streaming React interface
sidebar_label: React and streaming
description: Stream teaching, reconcile saved state, and acknowledge only content the learner actually saw.
---

# A streaming React interface

The [reference app](https://github.com/futureofdev/skilling/tree/main/examples/react-tutor)
uses React, TypeScript, Tailwind and Vercel AI SDK. It pairs a streaming conversation with
course progress, structured quiz feedback and a learner work area. Fonts are bundled locally. Run it with the [quickstart](quickstart.md),
then replace its components with your product's own design.

## Connect your chat

Use `useChat` with `DefaultChatTransport` pointed at the mounted course route. Keep only the
latest user message in the request: the server maintains the trusted conversation history.

```tsx
import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai';

const transport = new DefaultChatTransport({
  api: '/api/learn/onboarding/chat',
  prepareSendMessagesRequest: ({ messages, body }) => ({
    body: { ...body, messages: messages.slice(-1) },
  }),
});

function TutorChat() {
  const { messages, sendMessage, status, stop } = useChat({ transport });
  // Include current state when sending: sendMessage({ text }, {
  //   body: { display_id: state.display_id, request_id: crypto.randomUUID() },
  // });
  // Preserve that body if retrying the same operation.
  // Offer stop() while status is 'streaming' or 'submitted'.
  // Add the state and acknowledgement handling described below.
}
```

This connects text streaming. The reference app also supplies the current `display_id`, handles
structured course events, and manages rendering acknowledgement and continuation. Reuse that
flow to deliver the whole course; a chat component alone does not implement presentation.

## Render text and learning state together

The response is the Vercel AI SDK UI message SSE protocol. Text deltas arrive from the model
as they are generated; Skilling does not simulate streaming by splitting a completed answer.
The server also emits `data-skilling` parts:

| Data type | What your interface should do |
|---|---|
| `state` with `state` | Reconcile the course display and accepted transcript from the server |
| `text-reset` | Discard the superseded provisional text from this turn |
| `error` with `code`, `message`, and optional `state` | Show the failure and any fresh saved state; do not acknowledge a failed reply |

Streamed text is provisional until the run succeeds. A model validator can retry a response,
so a reset must remove the earlier attempt rather than displaying both as accepted teaching.
Use the server's final `messages` to reconcile the displayed transcript.

Canonical quiz feedback comes from the server, not the tutor's prose. Render its correctness
and explanation faithfully. Keep structured questions and feedback from `state.messages` in
their chronological position alongside the learner's answers; `state.feedback` identifies the
current feedback awaiting display acknowledgement. Quiz option controls come from current
server state; send the selected control ID instead of inferring the answer from generated text.
Historical question cards are read-only and must not offer old answer controls.

## Acknowledge what was actually shown

After the complete accepted teaching or canonical feedback is committed to the visible UI,
POST its `display_id` to `/api/learn/onboarding/ack`. Receiving tokens or fetching state does
not count. Hidden tabs, an unmounted component, cancelled streams and failed responses must
not acknowledge a completed display.

The reference app waits for a visible paint opportunity and cancels stale acknowledgement
callbacks. The acknowledgement response can contain a server-issued `continuation.id`.
Submit that through the chat endpoint with a fresh `request_id` and `continuation_id`; do not
invent learner text to trigger continuation. Keep that request separate from a learner choice.

The server bounds automatic continuation. Gates and quiz answers still require the learner.
Retain the same request ID and payload when retrying a failed request, including any display
or continuation ID. A new learner message needs a new ID.

## HTTP surface

All routes below are relative to `/api/learn/{course}` and use the same authenticated user.

| Route | Request |
|---|---|
| `GET /state` | Read current course state |
| `POST /chat` | Latest Vercel user message, or `message` plus `request_id`; optional `display_id` |
| `POST /chat` | Explicit `control`, `display_id`, `request_id` for a learner action |
| `POST /chat` | Server-issued `continuation_id` plus `request_id` |
| `POST /ack` | `display_id` after completed rendering |
| `POST /review` | `kind` (`objectives` or `homework`) and learner `explanation` |
| `POST /review/ack` | `review_id` after displaying the review |
| `POST /review/confirm` | `review_id`, and `objective_id` when confirming one objective |

Writes use JSON. Serve the browser and API at the same origin, or configure the adapter's
exact `allowed_origins` and your application's CORS middleware. Keep provider keys out of
frontend environment variables and bundles.

For framework details, see the official [AI SDK transport documentation](https://ai-sdk.dev/docs/ai-sdk-ui/transport)
and [stream protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol). The example's lockfile
pins the actual versions used; Skilling's state and acknowledgement contract sits alongside
that protocol.

## Make failures and access needs part of the interface

Keep the last accepted state visible while a reply streams. Announce busy and error states
without moving keyboard focus on every token. Label the composer and every quiz choice; make
all actions reachable with a keyboard. Provide a stop control, a clear recovery action, and
readable focus indicators in both color modes. Respect reduced-motion preferences.

Do not render model or course Markdown as executable HTML. The reference app disables raw HTML
and uses safe external-link attributes. A historical quiz is part of the transcript, not an
active form: only current server controls can submit an answer. On authentication changes,
discard the old learner's local transcript and transient handles before loading fresh state.

For a compact screen, preserve access to the conversation, course outline and current learning
material without making side panels prerequisites for answering. Exercise the actual interface
with keyboard navigation and a screen reader; automated component tests alone do not establish
accessibility or teaching quality.
