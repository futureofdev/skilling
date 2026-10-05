# PostgreSQL session persistence

`PostgresSessionStore` stores a complete scoped learning session in one PostgreSQL
row. This experimental adapter shares SQLite's versioned aggregate codec and
mechanical commit evaluator. It does not store course files, learner work or chat
history. A normalized progress export is for inspection; it cannot restore a
session's pending feedback or retry receipts.

Install the optional driver with `skilling[postgres]`. Core file/SQLite imports do
not import Psycopg. The tested service fixture selects PostgreSQL **17.11**;
locked development drivers are Psycopg **3.3.6** and psycopg-pool **3.3.3**.

```python
import os
from psycopg_pool import ConnectionPool
from skilling.store import PostgresSessionStore

with ConnectionPool(
    os.environ["SKILLING_DATABASE_URL"],
    min_size=1,
    max_size=4,
    timeout=5,
    kwargs={"connect_timeout": 5},
) as pool:
    pool.wait(timeout=5)
    store = PostgresSessionStore.open(
        pool, schema="skilling", timeout=5, statement_timeout=10
    )
    # Supply this store to Session.open with a server-authorized SessionScope.
    # Offload synchronous calls from an asynchronous request handler.
    store.close()
```

The producer owns and closes the pool; `store.close()` only disables that adapter.
`timeout` bounds pool checkout and database lock waits. `statement_timeout` bounds
each database statement. Configure connection establishment on the producer's
pool. Both adapter timeouts accept positive values up to 60 seconds. A transaction
ends before a call returns; it never spans model narration or a human wait.

Use a dedicated lowercase schema. Provision the database and role separately;
the role needs schema creation rights on first installation, or a precreated empty
schema it owns. Adapter initialization takes a transaction-scoped advisory lock,
then creates only its dedicated schema tables. Existing unknown layouts or schema
versions refuse; there is no implicit migration. `public`, `information_schema`
and PostgreSQL-reserved schema names are refused. Unrelated application schemas
remain untouched.

Existing streams use `SELECT ... FOR UPDATE`; concurrent absent-stream insertion
uses composite uniqueness and `ON CONFLICT DO NOTHING`, then reads the winner
under its row lock. Every update includes namespace, learner and course. Scratch,
original outcomes, completion/homework effects and receipts commit together.
Administrative deletion clears the payload and retains a tombstone, so stale
creation or replay cannot restore the stream. Administrative enumeration is scoped
to one namespace/course and excludes deleted streams.

Lock/statement contention raises `StoreBusy`. A connection failure during a write
raises `ReconciliationRequired`, because loss of the response does not establish
rollback. Reopen/read using the original scope and retry only a receipt-bearing
original command; its exact accepted identity returns its original outcome.
Objective/artifact mutations without such receipts need read/reconcile. Adapter
exceptions omit the DSN and server error strings. Configure the producer's own
pool logging to avoid sensitive connection diagnostics.

## Native full backup and restore

Stop writers before backup and keep the producer stopped during restore. Use
`pg_dump` and `pg_restore` from the server's major version. Retain the complete
schema, including schema metadata, aggregate payloads and deleted rows. Supply
credentials through a protected `PGPASSFILE` or libpq environment, never command
arguments or public evidence. For example:

```sh
pg_dump --format=custom --schema=skilling --file=skilling.dump
pg_restore --list skilling.dump > skilling.inventory
```

Record the archive SHA-256, storage schema version, logical namespaces, stream
count and tombstone count in a backup manifest. Verify that the dump completed
successfully. Record course/work/history backups separately. Keep the archive and
inventory private: stored records may contain learner information.

Provision a **new, empty, stopped database**. Refuse restoration over any existing
application table, view, materialized view or sequence. Verify the archive checksum
and inventory before the first write, and retain the same schema and logical
namespace. Restore atomically:

```sh
pg_restore --single-transaction --exit-on-error --no-owner --no-privileges \
  --dbname=empty_restore_database skilling.dump
```

Before serving traffic, open the adapter in the restored schema, enumerate the
manifest's namespace/course scopes and compare the complete stream/tombstone
inventory. Read the restored states to validate schema, embedded identities and
receipt references. Recover a known pending feedback item and replay known
completion/submission/action receipts without changing their original results.
Leave any failed or unverified destination stopped. This is a same-backend restore,
not a live merge or cross-backend import.

The disposable test procedure runs real `pg_dump --format=custom` and
`pg_restore --single-transaction` from the pinned container. It verifies pending
feedback, an accepted homework receipt, exact action replay and tombstones after
restore, and refuses a wrong checksum or nonempty target. Process tests kill a
worker immediately before and after server commit for completion, submission,
answer and acknowledgement; they are process-crash evidence, not power-loss proof.

## Running the selected service checks

```sh
uv sync --frozen --all-packages --all-extras
python packages/skilling/tests/backends/services.py start --profile postgres \
  --config-out /absolute/private/postgres.json
uv run --all-packages --all-extras pytest packages/skilling/tests/session_store \
  --store-profile=postgres --store-config=/absolute/private/postgres.json -q
python packages/skilling/tests/backends/services.py stop --profile postgres \
  --config=/absolute/private/postgres.json
```

An explicitly selected PostgreSQL profile without its service, private config or
driver fails its prerequisite. Default service-free tests do not connect to a
remote database. Do not upload the private fixture configuration.

Transaction/pool behavior follows the [Psycopg pool documentation](https://www.psycopg.org/psycopg3/docs/advanced/pool.html)
and [transaction documentation](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).
