# Disposable persistence services

The small Compose file provides **SeaweedFS 4.48 S3** and **PostgreSQL 17.11**,
pinned by image digest. It publishes only loopback ports and retains data in
project-owned volumes. These are local test services; SeaweedFS permits anonymous
local access and the manual PostgreSQL default is a test-only password.

Start S3 directly, without Python dependencies:

```sh
docker compose -f packages/skilling/tests/backends/compose.yaml -p skilling-local --profile seaweed up -d
docker compose -f packages/skilling/tests/backends/compose.yaml -p skilling-local port seaweed 8333
```

Use the reported `http://127.0.0.1:PORT` as the S3 endpoint, region `us-east-1`,
path-style addressing, and any nonempty local test access/secret keys. Create a
bucket before using it. The endpoint provides S3-compatible storage, not proof
of AWS behavior. Filer metadata and object volumes both survive service restarts.

For repeatable automated verification, the controller assigns a unique project,
generates private PostgreSQL credentials, bounds startup, checks the actual
server version, creates the bucket on its owned local SeaweedFS service, and writes
a private configuration file:

```sh
python packages/skilling/tests/backends/services.py start --profile seaweed --config-out /absolute/private/seaweed.json
python packages/skilling/tests/backends/services.py start --profile postgres --config-out /absolute/private/postgres.json
python packages/skilling/tests/backends/services.py stop --profile seaweed --config /absolute/private/seaweed.json
python packages/skilling/tests/backends/services.py stop --profile postgres --config /absolute/private/postgres.json
```

Restart an owned fixture with `services.py restart --profile seaweed --config /absolute/private/seaweed.json`
(or `--profile postgres`). Reload its private configuration afterwards: Docker Desktop
may assign a different ephemeral loopback port on restart. The volume identity is unchanged.

The parent directory must exist. Configuration files contain test credentials;
do not commit or upload them. Stop uses the recorded ownership identity and
removes only that project's containers and volumes. Keep the file if a failed
Docker operation needs retry. For manual `skilling-local` setup, remove its test
data only when finished with that project:

```sh
docker compose -f packages/skilling/tests/backends/compose.yaml -p skilling-local --profile seaweed down --volumes
```
