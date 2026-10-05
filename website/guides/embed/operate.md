---
title: Deploy, recover and grow
sidebar_label: Deploy and recover
description: Choose durable storage, preserve learner progress through failures, and operate the single-worker tutor safely.
---

# Deploy, recover and grow

The React application separates durable learning state from a temporary conversation. Choose
your persistence backend, integrate your authentication, and keep one application worker.
A shared database does **not** make this tutor runtime safe to run across multiple workers:
its conversations, locks, display receipts and review handles still live in one process.

## Choose where progress lives

| Integration | Default | Alternatives |
|---|---|---|
| React reference application | SQLite at `TUTOR_DATA_DIR/progress.sqlite3` | Explicit TOML configuration for file, PostgreSQL or S3 |
| `Tutor(..., state_dir=...)` | File-backed sessions | Supply `session_factory` instead for producer-owned `Session` storage |
| Existing CLI workspace | Files under `.skilling/` | No automatic adoption of application-scoped database records |

The React app reads `TUTOR_CONFIG` when you supply an absolute TOML path. Its
[configuration reference](/reference/embedding-a-tutor#run-the-local-reference-producer)
includes a complete two-learner example and the backend settings. A selected backend that
fails never falls back to another store. Your application must resolve identity and course
permission before opening a scoped session.

Read the guide for the backend you actually deploy:

- [SQLite](/reference/persistence): a local filesystem on one host, no additional driver.
- [PostgreSQL](/reference/persistence-postgres): an application-owned bounded pool, TLS and database roles.
- [S3](/reference/persistence-s3): a private bucket/prefix, conditional writes and explicit reconciliation of uncertain commits.

For local development, the repository includes a small
[Docker Compose setup for PostgreSQL and SeaweedFS](https://github.com/futureofdev/skilling/blob/main/packages/skilling/tests/backends/README.md).
SeaweedFS provides a local S3-compatible endpoint; testing it does not establish AWS compatibility.

These adapters persist the full session aggregate, including pending feedback, receipts and
deletion generations. A progress export is useful for reporting; it is **not** a complete backup.
Backend source support and tested service compatibility are different claims. Validate your
actual database or object-storage service using the documented acceptance profile.

## What survives a restart

| Resource | Where it belongs | Restart behavior |
|---|---|---|
| Committed progress, homework and pending canonical feedback | Selected session store | Preserved |
| Chat transcript | Tutor process | Lost; explain this to the learner |
| Display acknowledgements and continuation handles | Tutor process | Discard; fetch fresh state |
| Unconfirmed informal reviews | Tutor process | Discard; inspect work and request a fresh review |
| Learner notes and artifacts | Authorized application work storage | Preserved only if you make that storage durable |
| Course source | Versioned application content | Preserve the exact registered version |

The in-process registry is scoped by authorized learner and course. Two browsers using the same
learner share that conversation; switching the demo selector clears the browser view but does
not erase the server conversation. Use separate demo learners when testing isolation.

Recover the interface from fresh server state. Display pending canonical feedback completely
before acknowledging it. A saved record does not prove that a lost reply was shown, or that a
learner supplied evidence in a lost conversation.

Keep course versions pinned. Same-version source edits can be refused, and the mounted adapter
has no course migration endpoint. Application-scoped records use a different identity from
local CLI records: the CLI upgrade command does not migrate those enrollments. Implement and
verify an explicit producer-owned upgrade before changing an enrolled course's version.

## Retry without repeating the learner's action

Create one request ID per learner operation. Within a running process, retry the **exact same
payload and ID**, including the original display or continuation ID. Reusing an ID with a
changed payload is a conflict, even if the replacement ID came from a refreshed display.

If an action commits and the model then fails, the action remains committed. Refresh the saved
state and recover narration without issuing the action again. After a restart, the HTTP runtime's
in-memory request receipts are gone: start from fresh state with a new narration request and
no replayed control. Durable store receipts have a longer lifetime, but are not a replacement
for the lost browser handle.

For an ambiguous backend commit, retain the original captured command identity and follow the
backend's reconciliation procedure. Do not generate a new mutation to guess whether the first
one succeeded. A definite conflict requires refreshed state and, when the choice changed, a
new learner decision.

Interrupted streams, hidden tabs and failed renders are not presentation receipts. The
[React guide](react.md#acknowledge-what-was-actually-shown) explains when acknowledgement and
automatic continuation are valid.

## Prepare your hosted application

The shipped example is a **loopback demo**, even with PostgreSQL or S3 configured. Its learner
selector demonstrates scoped storage; it does not authenticate people. For a hosted product:

1. Mount the tutor in your own application with verified identity and course authorization.
   Keep demo selection disabled and authorize learner work paths separately.
2. Keep model credentials, database DSNs and storage credentials on the server. Give backend
   credentials only the permissions required by the selected adapter.
3. Use HTTPS and your application's session protections. Preserve the adapter's origin checks
   through your proxy; allow exact trusted origins when the frontend is hosted separately.
4. Run **one worker**, with durable storage for both state and learner work. PostgreSQL or S3
   changes the persistence backend, not the runtime's process-coordination contract.
5. Configure provider limits and application timeouts. Stream SSE without proxy buffering;
   ensure the proxy timeout permits your configured turn duration and surfaces disconnections.
6. Verify backup restoration, a backend outage, a stale browser action, a cancelled stream and
   restart with pending quiz feedback before enrolling real learners.

The application owns store and provider clients. Open and close them in its lifespan; offload
synchronous storage work to a bounded worker pool. Do not hold a transaction across a model
call or a human wait. The reference app opens and closes its configured store in its lifespan.
The [FastAPI guide](fastapi.md) shows the integration boundary.

## Back up the whole learning experience

Inventory the session store, exact course sources and actual learner work. Include separately
persisted transcripts or provider identifiers if your product keeps them. Stop writers as
required by the backend guide; restore to an empty destination and validate it before switching
the application over. Keep the previous deployment stopped during that switch.

SQLite uses the database backup API; PostgreSQL and S3 have their own inventory and consistency
requirements. For S3, restore to a sibling prefix, never a child of the live prefix. Preserve
original scopes, receipts and deletion tombstones. Restoring an older backup restores its older
logical history; a progress-only export cannot rebuild retry safety or pending feedback.

Deletion of a scoped session does not delete learner files, model-provider logs or old backups.
Apply your retention policy to each system. Stale actions must not recreate a deleted session;
new initialization requires the current tombstone generation.

## Capacity and model quality

Configure `max_sessions`, `lock_timeout`, `turn_timeout` and PydanticAI `UsageLimits` for your
workload. The default process registry holds 256 sessions with no automatic eviction; each
session retains up to 1,024 request IDs. Exhaustion returns 503 until restart. Changing the
storage backend does not remove those bounds. Plan an application lifecycle and a coordinated
runtime design before scaling beyond them.

The transcript retains the latest 64 entries, including structured questions and feedback.
The tutor can rebuild model context from accepted dialogue when its tool trace is full;
state includes a history notice when older dialogue has been omitted. Durable conversation
history, if needed, is a separate application feature with its own retention policy.

Synthetic tests establish protocol behavior. Evaluate teaching quality, costs and evidence
review with your actual model and courses. Tracing is opt-in application policy: inspect what
course content and learner evidence it sends to third parties.
