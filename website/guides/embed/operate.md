---
title: Persistence and recovery
sidebar_label: Operate and recover
description: Understand durable learning state, presentation receipts, retries and the file-backed deployment boundary.
---

# Persistence and recovery

The mounted tutor is a single-process, file-backed integration. Put its `state_dir` on durable
writable storage and run one application worker. Scope authentication and course access in
your application before the tutor resolves a learner session.

## What survives a restart

| Resource | Owner and lifetime |
|---|---|
| Committed learning record and pending canonical quiz feedback | Skilling file session; durable in `state_dir` |
| Chat transcript | Tutor process; lost on restart |
| Display acknowledgements and pending continuations | Tutor process; refresh after restart |
| Unconfirmed informal reviews | Tutor process; obtain a fresh review after restart |
| Actual learner files, notes and evidence | Your application and its durable work storage |
| Course source | Your application; preserve the exact registered version |

Losing a transcript does not erase course progress. It also does not establish that a learner
previously supplied evidence or saw a particular reply. Rebuild the interface from fresh state
and obtain fresh evidence for reviews.

The session registry is bounded. Configure `max_sessions`, `lock_timeout`, `turn_timeout` and
PydanticAI `UsageLimits` for your workload. Capacity and timeout failures should be visible to
the user; do not silently share one learner's session with another.
The default registry allows 256 distinct learner/course sessions, with no automatic eviction.
Each session retains at most 1,024 request IDs. Reaching either limit returns 503 until the
process is restarted; choose a different session backend before scaling beyond this boundary.

The in-process transcript retains the latest 64 entries, including structured quiz questions
and feedback. When the model's tool trace reaches its limit, the tutor rebuilds context from
accepted dialogue instead of clearing the conversation. Older dialogue may eventually fall
outside these bounds; the state includes a history notice when it has been omitted. Store a
durable transcript in your application if your product needs long-term conversation recall.

## Retry the operation the learner actually requested

Keep the same request ID when retrying one request. Generate a new ID for a new learner message
or action. If a durable action committed before the model failed, the failure does not roll
the action back. Reload the current state and retry narration without issuing a second
learning action. Within one process, retry the exact original payload, including its original
display or continuation ID. Substituting a refreshed ID while keeping the old request ID is a
conflict. After a process restart, old receipts are gone: read fresh state and start a new
narration request without a control. Never blindly replay the earlier learner choice.

An interrupted stream has not proved delivery of the complete teaching turn. Do not acknowledge
partial or failed responses. A completed response must be rendered before acknowledging its
display; canonical quiz feedback must likewise be shown before continuation.

## Deploy behind your existing application boundary

Keep model credentials on the server. Preserve authentication, course authorization and the
adapter's origin checks through your reverse proxy. Use explicit allowed browser origins when
your frontend is served separately. The local reference app's demo identity is for loopback
development; replace it with your application's authentication before deployment.

The file-backed integration does not provide distributed session locks or shared chat history.
Do not increase Uvicorn workers or deploy replicas against the same state directory and assume
that in-memory receipts are coordinated. SQLite, PostgreSQL and S3 session support are separate
planned work, not configuration switches on this adapter.

Back up course versions, learner state and application work together. Stop writers for a
consistent filesystem copy. Pin registered course versions. The mounted adapter has no course
migration endpoint; the local CLI's learner identity differs from these scoped records, so its
upgrade command does not migrate them. Plan a producer-owned migration integration with core
primitives before changing an existing enrollment's course version.

## Model quality and observability

Choose provider settings in your Agent and pass `usage_limits=UsageLimits(...)` to `Tutor`.
Any tracing or telemetry is your
application's choice; review what course content and learner evidence it sends off the host.
Exercise your actual model against your course: deterministic protocol tests establish the
software flow, not the quality of the teaching.
