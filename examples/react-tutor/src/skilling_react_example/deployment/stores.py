"""Explicit synchronous backend lifecycle owned by the producer lifespan."""

from __future__ import annotations

import hashlib
import os
from contextlib import ExitStack
from pathlib import Path

from skilling.store import (
    FileSessionStore,
    SessionScope,
    SessionStore,
    SQLiteSessionStore,
    StoreError,
)

from .config import BackendConfig


class BackendLease:
    def __init__(self, config: BackendConfig) -> None:
        self.config = config
        self._resources = ExitStack()
        self._store: SessionStore | None = None

    @classmethod
    def open(cls, config: BackendConfig) -> BackendLease:
        lease = cls(config)
        try:
            if config.kind == "sqlite":
                assert config.path is not None
                store = SQLiteSessionStore.open(Path(config.path))
                lease._resources.callback(store.close)
                lease._store = store
            elif config.kind == "postgres":
                from psycopg_pool import ConnectionPool

                from skilling.store import PostgresSessionStore

                assert config.dsn_env is not None
                dsn = os.environ.get(config.dsn_env)
                if not dsn:
                    raise StoreError("Selected PostgreSQL credential environment is unavailable")
                pool = ConnectionPool(
                    dsn,
                    min_size=1,
                    max_size=4,
                    timeout=5,
                    kwargs={"connect_timeout": 5},
                    open=False,
                )
                lease._resources.callback(pool.close)
                pool.open(wait=True, timeout=5)
                lease._store = PostgresSessionStore.open(pool, schema=config.schema_name)
            elif config.kind == "s3":
                from boto3.session import Session
                from botocore.config import Config

                from skilling.store import S3SessionStore

                profile = os.environ.get(config.profile_env) if config.profile_env else None
                if config.profile_env and not profile:
                    raise StoreError("Selected AWS profile environment is unavailable")
                client = Session(profile_name=profile).client(
                    "s3",
                    region_name=config.region,
                    endpoint_url=config.endpoint_url,
                    config=Config(
                        connect_timeout=5,
                        read_timeout=10,
                        retries={"total_max_attempts": 1, "mode": "standard"},
                        s3={"addressing_style": "path"},
                    ),
                )
                lease._resources.callback(client.close)
                assert config.bucket is not None and config.prefix is not None
                lease._store = S3SessionStore.open(client, config.bucket, config.prefix)
            return lease
        except Exception:
            lease.close()
            raise StoreError(
                "Selected persistence backend could not be opened; no fallback"
            ) from None

    def for_scope(self, scope: SessionScope) -> SessionStore:
        if self.config.kind == "file":
            assert self.config.path is not None
            key = hashlib.sha256((scope.namespace + "\0" + scope.learner_id).encode()).hexdigest()
            return FileSessionStore.open(
                Path(self.config.path) / key, namespace=scope.namespace, learner_id=scope.learner_id
            )
        if self._store is None:
            raise StoreError("Persistence backend is not running")
        return self._store

    def close(self) -> None:
        self._resources.close()
        self._store = None
