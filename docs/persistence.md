# Complete session persistence

`SQLiteSessionStore` is the service-free, synchronous store for producer-owned multi-user
sessions. The legacy CLI still uses its file workspace by default. Database state does not
include the course files, learner note/artifact bytes, authentication, or optional chat history.
Keep those resources in a separate backup inventory.

```python
from pathlib import Path
from skilling.store import SQLiteSessionStore

with SQLiteSessionStore.open(Path("/absolute/producer/sessions.db")) as store:
    # Pass the store and a server-authorized SessionScope to Session.open(...).
    ...
```

The parent directory must already exist. There is no URI discovery, fallback database,
automatic directory creation, or optional database SDK requirement. Core-only installations
need only Python's standard `sqlite3` module. Producer authentication must resolve the opaque
namespace, learner ID and course ID before constructing a scope or trusted action handle;
the scope is not an authentication credential.

## Transactions and deployment

Every operation creates and closes its own connection. Writes use `BEGIN IMMEDIATE`, bound
parameters, explicit commit/rollback, DELETE journal mode and `synchronous=EXTRA`. Each write
reads one complete aggregate under the write transaction and compares its captured session
revision. The default busy wait is five seconds; `open(path, timeout=...)` accepts zero through
60 seconds. Contention raises `StoreBusy`. No transaction spans narration or a learner wait.
Async producers must offload the synchronous call to a worker thread.

Deploy on one host with a local filesystem and cooperating SQLite processes. Network
filesystem/WAL coordination, distributed workers, clustered storage and physical power-loss
survival are not asserted. `sqlite3.sqlite_version` identifies the host library; record it
alongside operational test evidence. Process interruption tests establish atomic old-or-new
state under the tested SQLite/OS version.

Each `(namespace, learner_id, course_id)` row contains the complete learning state, independent
record/homework revisions, canonical pending feedback, completion log, homework archive,
original action/completion/submission receipts, lifetime key reservations, explicit upgrade
metadata and source digest. Every mutation changes the whole-session revision, including a
feedback acknowledgement that leaves the record revision unchanged. Revisions are opaque.
Do not derive new actions by interpreting or rebasing them.

An exact keyed retry returns the original outcome together with the current snapshot, even
after another action. A changed identity for an accepted key raises an idempotency conflict.
If acknowledgement of a commit is uncertain, reconcile the original identity after reopening.
An unkeyed record/objective/artifact mutation requires reading and reconciling the state;
automatically inventing another action can apply an effect twice. Database recovery does not
emit learner hooks or imply that canonical feedback was displayed.

## Schema and failures

Storage schema version 1 is distinct from the course, format and package versions. An empty
database is initialized transactionally; a recognized version-one layout opens unchanged.
Unknown layouts, foreign tables, extra schema objects or another version refuse before
migration or repair. There is currently no supported migration command. Any future migration
requires a named tested upgrade and a verified complete backup.

Corrupt schema, aggregate identity, receipts or feedback references refuse without fallback.
`SessionSchemaError` identifies an unsupported layout, `RecoveryRequired` invalid durable
state or a failed database operation, and `ReconciliationRequired` an uncertain commit
acknowledgement. Error messages do not interpolate arbitrary SQL or configuration values.
`close()` refuses future calls; connections from completed calls are already closed.

## Inspection, deletion and full recovery

`store.list_records(namespace, course_id)` is an administrative scope-constrained enumeration
of live progress records. `store.export_progress(scope)` returns a normalized `Record` (or
`None` for absence/deletion). This export omits runtime scratch and receipts and **cannot
restore a session**. It is for reporting and inspection, not cross-backend migration.

Administrative deletion is `store.commit(DeleteSession(scope, captured_session_revision))`.
It clears the payload and preserves a minimal identity/generation tombstone. Stale actions,
acknowledgements, retries and initialization cannot resurrect the stream. Other streams and
learner-owned files are untouched. Deletion does not promise forensic erasure from SQLite
free pages, operating-system snapshots or previous backups; retention remains producer-owned.

Stop writers before your operational backup/restore procedure. Native backup uses
`Connection.backup`, checks the exact schema, SQLite integrity and every aggregate/tombstone,
then publishes the validated file without replacing an existing destination. Restore accepts
only an existing backup and a new destination. The destination's parent must exist. A partial
staging copy is never served as the destination.

```python
from pathlib import Path
from skilling.store import SQLiteSessionStore

source = Path("/absolute/producer/sessions.db")
backup = Path("/absolute/backups/sessions-2026-10-05.db")
restored = Path("/absolute/restored/sessions.db")
with SQLiteSessionStore.open(source) as store:
    store.backup(backup)
with SQLiteSessionStore.restore(backup, restored) as store:
    # Inspect authorized scopes, recover pending feedback and retry an old action.
    ...
```

Full backup preserves original scopes, source identities, all receipts, original timestamps,
pending feedback, homework and tombstones. Restore never merges into a live database or
changes logical namespaces. Keep the old deployment stopped when switching the producer to
the new database; restoring an older backup necessarily restores its older logical history.
Restore course resources, durable learner work directories and optional histories separately.
File workspace backups retain their existing recovery-preserving procedure.

PostgreSQL and S3 support have separate adapters and real-service acceptance requirements;
SQLite results alone establish no compatibility claim for those services.
