# S3-compatible complete sessions

Install `skilling[s3]` and supply a producer-owned Boto3 client. The core import
has no SDK import or network side effect. The producer owns credentials, region,
endpoint, bucket provisioning, client closure and access policy. Run synchronous
store calls in a worker thread when embedding in an async application.

```python
import boto3
from botocore.config import Config
from skilling.store import S3SessionStore

client = boto3.client(
    "s3",
    region_name="us-east-1",
    # endpoint_url="http://127.0.0.1:8333",  # your compatible endpoint
    config=Config(
        retries={"total_max_attempts": 1},
        connect_timeout=5,
        read_timeout=10,
    ),
)
store = S3SessionStore.open(client, "producer-bucket", "deployment/session-state")
```

Credentials use the SDK provider chain; keep credentials out of browser/model
inputs and diagnostics. Select a dedicated nonempty prefix; the adapter neither
creates buckets nor enumerates outside that prefix. Require scoped GetObject,
PutObject and ListBucket permissions. Normal operation does not need DeleteObject.
All cooperating clients must use this adapter and its prefix control protocol;
unconditional external writes or lifecycle deletion invalidate its guarantees.

A stream is one complete JSON aggregate under SHA-256 namespace/course/learner
path components. The full scope is validated inside each body. The returned ETag
is an opaque conditional token, not an integrity checksum. Create uses
`IfNoneMatch="*"`; each later mutation, including deletion, uses the ETag captured
with the full body in `IfMatch`. There is one SDK write attempt, no multipart or
blind overwrite, and no automatic retry with a new expectation. Scratch-only
changes invalidate the whole-session revision. Record/homework revisions retain
their separate meanings.

Every aggregate is bounded to 16 MiB of serialized bytes. Lifetime receipts and
key reservations are retained; approaching capacity requires producer planning.
`SessionCapacity` refuses an oversized write before publication. This design is
for bounded course histories; it does not promise unlimited stream growth.
Unknown schema, malformed scope or corrupt recovery data refuse without repair.

After a timeout or connection loss, the adapter reads again and recovers an exact
durable keyed outcome when available, including after later accepted actions.
A 409/412/404 conditional refusal never authorizes rebasing. An uncertain mutation
without a recoverable durable identity raises `ReconciliationRequired`; inspect
current state and recollect any needed learner consent. Do not blindly retry an
objective/artifact edit as a fresh action. SDK response text is not included in
public storage errors.

## Backup and restore

`store.export_progress(scope)` returns normalized progress for inspection. It
excludes scratch and recovery receipts and is not a restore format. Stop all
writers before `store.backup(new_absolute_path)`. The full JSON backup contains
every scoped body, tombstone, key and SHA-256 checksum. Inventory/body rechecks
detect changes during capture, but do not replace producer-enforced quiescence.
Keep backups private: they contain learner/session data.

Restore only into a new empty prefix in a stopped deployment:

```python
from pathlib import Path

store.backup(Path("/private/backups/sessions.json"))
restored = S3SessionStore.restore(
    client, "producer-bucket", "restored/session-state",
    Path("/private/backups/sessions.json"),
)
```

Restore validates the complete manifest, embedded scopes and checksums before any
write. It reserves `_skilling.json` as RESTORING with a unique owner and manifest
hash before writing the first stream. Initialization and restore compete for the
same create-if-absent control object. Only a verified inventory and body checksum
set permits the conditional transition to READY. Ordinary open/read/write refuse
RESTORING. A live initialized prefix, corrupt control or unexplained nonempty
prefix cannot be adopted or overwritten.

An interrupted restore retains RESTORING, its owner/hash and any complete bodies.
There is no automatic resume or cleanup API. Preserve this evidence, stop every
client, inspect the matching backup, and restore to another new empty prefix.
Cleanup of the failed prefix requires an explicit operator decision and strictly
scoped object/version deletion. Never change RESTORING to READY manually merely
to make partial state visible.

Deletion replaces the aggregate with a minimal scope/generation tombstone;
stale creation and retries cannot resurrect it. Bucket versions, backups, work
files and optional conversation histories are producer retention responsibilities.
Logical deletion does not promise physical erasure. Disable lifecycle expiry of
live aggregates, control objects and tombstones. There are no independently
published payload generations requiring orphan garbage collection.

Back up course source, learner work/artifact bytes and optional history separately.
Restoration preserves the same logical namespaces and does not provide a
cross-backend import or live migration mechanism.

The selected compatibility targets are AWS S3 general-purpose buckets and
single-node SeaweedFS 4.48. Explicit `--store-profile=aws` or `seaweed` tests require
private service configuration and fail if unavailable. Local/stub tests do not
establish AWS compatibility; AWS proof is a separate pending gate. No clustered
SeaweedFS or universal S3-compatible endpoint guarantee is made.

## Trusted AWS verification

`Trusted AWS persistence verification` is a manual workflow, separate from PR CI.
A maintainer must review the complete candidate commit before dispatching its full
40-character SHA and approving the `persistence-aws` environment. Precreate that environment with required reviewers and restrict who can approve it;
a name in workflow YAML alone does not protect it. Configure its environment secrets
and variables with the `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optional
`AWS_SESSION_TOKEN` secrets, and the `AWS_TEST_BUCKET`, `AWS_TEST_REGION`, and
`AWS_TEST_PREFIX` variables. Use a disposable existing bucket and restrict the
credentials to the allowed test prefix. The workflow neither provisions a bucket
nor enumerates unrelated production prefixes. Each run adds a unique child prefix;
the tests remove their own objects. Versioned buckets can retain old versions and
require the operator's lifecycle policy.

Environment approval authorizes executing the reviewed candidate with those
credentials. Never dispatch untrusted candidate code. No credentials are attached
to PR CI. The uploaded manifest contains the exact source SHA, SDK/Python versions,
run identity and test exit status; the private configuration is not uploaded.
A configured workflow is not evidence of a successful AWS run.
