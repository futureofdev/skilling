"""Private disposable fixture inputs and owned schema cleanup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field

from skilling.store._backends._postgres import PostgresSessionStore

if TYPE_CHECKING:
    from psycopg import Connection
    from psycopg_pool import ConnectionPool


class ServiceConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    profile: str
    port: int = Field(gt=0, lt=65536)
    password: str = Field(min_length=1, repr=False)
    project: str = Field(pattern=r"^skilling-persistence-[0-9a-f]{24}$")


@dataclass
class PostgresFixture:
    pool: ConnectionPool[Connection[tuple[object, ...]]]
    store: PostgresSessionStore
    config: ServiceConfig

    def close(self) -> None:
        from psycopg import sql

        try:
            with self.pool.connection() as connection:
                connection.execute(
                    sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.store.schema))
                )
        finally:
            self.store.close()
            self.pool.close()


def postgres_fixture(request: pytest.FixtureRequest) -> PostgresFixture:
    if request.config.getoption("--store-profile", default=None) != "postgres":
        pytest.skip("Real PostgreSQL checks require explicit --store-profile=postgres")
    path = request.config.getoption("--store-config", default=None)
    if not path:
        pytest.fail("Selected PostgreSQL profile requires a private --store-config")
    try:
        from psycopg_pool import ConnectionPool

        config = ServiceConfig.model_validate_json(Path(path).read_bytes())
        if config.profile != "postgres":
            pytest.fail("Selected configuration is not PostgreSQL")
        pool: ConnectionPool[Connection[tuple[object, ...]]] = ConnectionPool(
            kwargs={
                "host": "127.0.0.1",
                "port": config.port,
                "user": "skilling_test",
                "dbname": "skilling_test",
                "password": config.password,
                "connect_timeout": 5,
            },
            min_size=1,
            max_size=4,
            timeout=5,
            open=True,
        )
        pool.wait(timeout=5)
        try:
            store = PostgresSessionStore.open(pool, schema="test_" + uuid4().hex)
        except Exception:
            pool.close()
            raise
    except Exception:
        pytest.fail(
            "Selected PostgreSQL fixture could not be opened; inspect private configuration",
            pytrace=False,
        )
    value = PostgresFixture(pool, store, config)
    request.addfinalizer(value.close)
    return value
