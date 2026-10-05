---
id: embed
slug: /embed
title: Embed a tutor
---

# Embed a tutor

Build a Python producer that owns identity, persistence, learner controls and model configuration.
Skilling supplies deterministic learning state; the optional `skilling-tutor` adapter supplies
shared tutoring policy and informal advice. The installable
[Welcome browser example](../examples/python-producer/README.md) connects these pieces.
This is experimental source documentation, not a claim that these changes are released.

## Choose the boundary

`FileSession` keeps the existing workspace/CLI workflow. `Session` uses the synchronous
`SessionStore` protocol and a trusted `SessionScope(namespace, learner_id, course_id)`.
SQLite needs no extra driver and is the default for configured producers. PostgreSQL and S3
are explicit alternatives. A remote failure never selects a different store.

Keep these responsibilities separate:

| Owner | Responsibility |
| --- | --- |
| Producer authentication | Resolve the authenticated principal, authorize its course, then construct the scope and permitted work root. |
| Session store | Durable record, scratch, receipts, pending feedback, homework and deletion generation. |
| Producer filesystem | Authored course source and separately authorized learner files. |
| Producer conversation | Transcript, displayed material, review evidence and transient handles, isolated per authorized scope and browser. |
| Tutor | Explain current material and offer informal feedback through copied safe contexts. |

A scope is an opaque identity, not authentication. Never construct it from model output or an
arbitrary browser learner ID. Resolve identity **before any state read**, including list/export.
The reference app's selector is labeled **local demo identity, not production authentication**.
A hosted application must replace that demo boundary with its own verified identity dependency;
keep the demo route disabled. Validate course permission and work-root permission together.

## Run the local reference producer

From the checkout, run `uv sync --frozen`. Create separate existing absolute work directories for
Alice and Bob and a state directory outside them. Use the canonical absolute checkout path for
Welcome; configuration rejects directory aliases and overlapping work roots. Save this TOML,
substituting your own absolute paths:

```toml
namespace = "local-learning-demo"

[backend]
# Omitted kind defaults to SQLite; this is an explicit persistent file.
path = "/absolute/demo/state/sessions.sqlite3"

[[courses]]
id = "welcome-skilling"
path = "/absolute/skilling/examples/welcome-skilling"

[[learners]]
selector = "alice"
label = "Alice (local demo)"
learner_id = "demo-learner-a"
work_root = "/absolute/demo/alice"
courses = ["welcome-skilling"]

[[learners]]
selector = "bob"
label = "Bob (local demo)"
learner_id = "demo-learner-b"
work_root = "/absolute/demo/bob"
courses = ["welcome-skilling"]
```

Install your selected model provider SDK in the producer environment and provide credentials
through its server environment. There is no default provider and no browser credential form.
For example, the supported tutor package accepts `pydantic-ai-slim[openai]>=2.52.0,<2.53.0`.
Adding a provider is a producer decision; synthetic tests never call paid providers.

```sh
.venv/bin/skilling-producer-example serve \
  --config /absolute/demo/producer.toml \
  --model openai:YOUR_MODEL --host 127.0.0.1 --port 8765
```

Open two separate browser profiles at `http://127.0.0.1:8765` and select different demo learners.
Cookies and CSRF tokens bind each browser independently. Selection discards its old conversation,
review and display handles. Progress persists, and each note stays in its permitted work root.
The app remains loopback-only. The existing `serve --workspace /absolute/workspace --model ...`
launch still uses `FileSession` and the same CLI-compatible workspace files.

For explicit file mode use `[backend] kind = "file"` and an absolute `path` for new state roots.
It creates namespace/learner-bound roots; it does not silently adopt another learner's legacy root.

For PostgreSQL install the core `postgres` extra and configure:

```toml
[backend]
kind = "postgres"
dsn_env = "DEMO_DATABASE_DSN"
schema_name = "skilling_demo"
```

Put the connection string in that server environment variable, not the TOML or chat. The app owns
a bounded synchronous pool, waits for startup and closes it on shutdown. Configure database roles,
TLS, backups and allowed schema privileges as part of deployment. The adapter refuses unsupported
or malformed schema/state instead of repairing it automatically.

For S3 install the core `s3` extra and configure:

```toml
[backend]
kind = "s3"
bucket = "your-private-bucket"
prefix = "skilling-demo/"
region = "your-region"
# Optional: environment variable naming an SDK profile.
# profile_env = "DEMO_AWS_PROFILE"
# Optional explicit compatible service endpoint; HTTPS except loopback test services.
# endpoint_url = "http://127.0.0.1:8333"
```

The producer owns the SDK client. This app uses one total SDK attempt and bounded connection/read
timeouts. The backend conditionally replaces one complete aggregate object per scoped stream;
confirmed conflicts differ from ambiguous transport failures. Reconcile ambiguous outcomes using
the same captured command identity. Supply credentials through the SDK's server-side credential
chain. Restrict access to the dedicated bucket/prefix; backup and restore require their documented
inventory permissions. See [S3 persistence](persistence-s3.md) and
[database persistence](persistence.md) for operational limits.

## Open a scoped session

This example uses real public constructors. The application has already authenticated the learner
and checked the course and work directory permissions before this function is called:

```python
from pathlib import Path
from skilling.session import Session
from skilling.store import SessionScope, SQLiteSessionStore

store = SQLiteSessionStore.open(Path("/absolute/state/sessions.sqlite3"))
scope = SessionScope("your-product", "verified-principal-id", "welcome-skilling")
session = Session.open(
    Path("/absolute/courses/welcome-skilling"),
    store=store, scope=scope, work_root=Path("/absolute/work/learner-a"),
)
snapshot = session.snapshot()
# Keep store alive for requests; close it at producer shutdown.
```

Store operations are synchronous. FastAPI synchronous endpoints use the framework worker pool;
in async code use `await asyncio.to_thread(session.snapshot)` or an equivalent bounded executor.
Do not hold a database transaction or source lock across model calls or human waits. The reference
app creates/closes stores in its ASGI lifespan and offloads initialization and shutdown too.

Capture controls from the exact displayed snapshot. Treat revisions as opaque equality tokens,
including aggregate revisions that change for scratch-only operations. Do not parse their format.

```python
from skilling.session import ActionOperation

# Only after the learner chooses a currently offered control:
action = session.capture_action(
    snapshot, event_id="producer-generated-stable-event-id",
    operation=ActionOperation.ADVANCE, payload="next",
)
result = session.act(action)
```

Retain the same captured handle for an uncertain retry. Exact replay returns the original outcome;
a reused event key with changed intent refuses. A stale aggregate or a handle copied across scopes
refuses before effects. Refresh after conflicts and ask for a new choice when the display changed.
Session source identity is pinned: same-version source edits refuse; explicitly upgrade validated
new versions. Pending feedback must be presented before upgrade. Existing unknown legacy source
provenance is attached explicitly on first neutral session open, not retroactively asserted.

`pending_feedback()` returns canonical feedback and a scoped acknowledgement handle. Render all
canonical fields, wait for an actual paint, and only then call `acknowledge_feedback(handle)`.
Do not acknowledge on receipt from the server or on model narration. Restart restores pending
canonical feedback even though conversation is gone. The browser example retains its existing
DOM cancellation and failed-render safeguards.

## Choose a tutor integration

The shared runner loads the packaged learning, progress and homework policies. It retains no
conversation itself; keep the returned transcript per authorized learner and browser:

```python
from skilling_tutor import ConversationContext, SkillingRunner

runner = SkillingRunner.create(selected_model)
context = ConversationContext.from_snapshot(snapshot)
turn = await runner.chat(learner_message, context, history=history)
history = turn.history
reply = turn.output.text
```

If you already own a native Agent, attach the same capability directly:

```python
from dataclasses import dataclass
from pydantic_ai import Agent
from skilling_tutor import (
    ConversationContext, ConversationReply, SkillingCapability, TutorPurpose,
)

@dataclass(frozen=True)
class ProducerDeps:
    context: ConversationContext

def safe_context(deps: ProducerDeps) -> ConversationContext:
    return deps.context

agent = Agent(
    selected_model,
    deps_type=ProducerDeps,
    capabilities=[SkillingCapability.create(
        TutorPurpose.CONVERSATION, context_getter=safe_context,
    )],
    output_type=ConversationReply.output_type(),
)
result = await agent.run(
    learner_message, deps=ProducerDeps(context), message_history=history,
)
reply = ConversationReply.from_output(result.output, context=context)
history = result.all_messages()
```

Pass safe copied contexts, never `Session`, store clients, namespace/learner identity, course paths,
credentials, scoped handles or submission tokens. Producer-added tools are separate authority;
the capability is not a sandbox. See [the tutor API](python-tutor.md) for bounded context factories,
scoped evidence, native skills and refresh requests.

Advice does not settle objectives or submit homework. Inspect actual permitted learner files,
bind the evidence digest and current record/homework/aggregate revisions, render complete advice,
and obtain a separate learner confirmation. Recheck the file digest and all revisions immediately
before the confirmed mutation. Use the captured `HomeworkCheck.submission` handle for neutral
submission, and the captured snapshot for objective settlement. A changed file or scratch-only
state change invalidates the review. Never invent learner work, attestations or history.

## Restart, deletion and operations

Restart loses in-memory transcripts, displays and informal reviews. Tell the learner, preserve
committed progress, show pending canonical feedback, and request fresh evidence. Durable records
are not proof of a lost conversation. Work files and provider logs have separate retention policies.

`DeleteSession(scope, expected_revision)` requires an exact current aggregate revision. Deletion
removes the active aggregate and leaves a tombstone; a stale action cannot recreate it. A new
explicit initialization uses that tombstone revision. Exported progress is not a complete backup:
receipts, pending feedback and submission state belong to the full aggregate. Restores use an empty
destination and preserve retry identities. SQLite uses its database backup API; PostgreSQL and S3
have backend-specific inventory and consistency requirements. Quiesce writers according to the
backend guide. For S3 restore use a sibling prefix, not a child of a live prefix.

The reference app does not persist conversation. If your producer does, isolate transcripts and
provider identifiers by the same authorized scope and apply your deletion policy to those systems
and learner work independently. Namespace filtering is a query boundary, not row-level authorization.

## Verify your producer

Run `task check` for source and canonical DOM regressions. The existing installed smoke manager
builds matched core/tutor/app wheels and sdists outside the checkout. Explicit backend profiles
exercise full aggregate backup/restore and a stale delete race; selected unavailable services fail
rather than skip. Use disposable dedicated service targets, never a live learner database/prefix.
Synthetic models establish protocol behavior, not real-model quality or authentic learner proof.
The focused human/provider acceptance run remains separate; do not claim it from synthetic output.

The installed manager defaults to SQLite. Add `--check-backend-extras` to verify both optional
SDKs and the binary PostgreSQL driver in each installed artifact environment without contacting
services. The existing installed-package CI matrix uses this flag on Linux, macOS and Windows;
those import checks are distinct from the explicit service profiles below. From the checkout:

```sh
task package:tutor:smoke -- --store-profile sqlite --evidence /absolute/evidence/sqlite
task package:tutor:smoke -- --store-profile file --evidence /absolute/evidence/file
task package:tutor:smoke -- --store-profile postgres \
  --store-config /absolute/private/postgres.json --evidence /absolute/evidence/postgres
task package:tutor:smoke -- --store-profile s3 \
  --store-config /absolute/private/s3.json --evidence /absolute/evidence/s3
```

These JSON files configure the test harness, not the app. PostgreSQL requires two distinct
throwaway databases and a native client matching the server major version:

```json
{
  "disposable": true,
  "dsn_env": "PROBE_DATABASE_DSN",
  "restore_dsn_env": "PROBE_RESTORE_DSN",
  "native_command": ["docker", "exec", "-i", "YOUR_OWNED_POSTGRES_CONTAINER"],
  "native_database": "probe_source",
  "native_restore_database": "probe_restore"
}
```

An empty `native_command` uses local `pg_dump`/`pg_restore`. The configured environment supplies
libpq credentials; passwords never enter command arguments. Each run creates a random dedicated
schema. Confirm the supplied container and databases are yours and disposable. Retain evidence,
then dispose of those databases using your service lifecycle.

The S3 profile requires an existing disposable bucket and an explicit dedicated prefix:

```json
{
  "disposable": true,
  "bucket": "your-disposable-bucket",
  "prefix": "installed-probes/",
  "region": "us-east-1",
  "endpoint_url": "http://127.0.0.1:8333"
}
```

Omit `endpoint_url` for AWS and use the SDK credential environment. The probe creates random
sibling source/restore prefixes and a separate app prefix below the dedicated prefix; it does
not delete your bucket. Dispose of this test prefix after retaining evidence. A local compatible
service result does not establish AWS behavior; run an explicitly authorized AWS profile separately.
