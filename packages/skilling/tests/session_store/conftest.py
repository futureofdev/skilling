"""Explicit backend selection; a requested unavailable service must fail closed."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from skilling.store import FileSessionStore, SessionScope, SessionStore, SQLiteSessionStore

StoreFactory = Callable[[SessionScope], SessionStore]


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("session persistence")
    group.addoption("--store-profile", choices=("file", "sqlite", "postgres", "aws", "seaweed"))
    group.addoption(
        "--store-config", help="Private JSON configuration for an explicit service profile"
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "store_profile" in metafunc.fixturenames:
        selected = metafunc.config.getoption("--store-profile", default=None)
        metafunc.parametrize("store_profile", [selected] if selected else ["file", "sqlite"])


def pytest_report_header() -> str:
    return f"Native SQLite library: {sqlite3.sqlite_version}"


@pytest.fixture
def store_factory(
    store_profile: str, tmp_path: Path, request: pytest.FixtureRequest
) -> StoreFactory:
    if store_profile == "postgres":
        from .backends.postgres._support import postgres_fixture

        fixture = postgres_fixture(request)
        return lambda scope: fixture.store
    if store_profile == "sqlite":
        database = tmp_path / "sessions.db"
        return lambda scope: SQLiteSessionStore.open(database)
    if store_profile != "file":
        pytest.fail(
            f"Explicit {store_profile} session profile is not available in this implementation"
        )

    def open_store(scope: SessionScope) -> SessionStore:
        identity = (scope.namespace + "\0" + scope.learner_id).encode()
        root = tmp_path / "stores" / hashlib.sha256(identity).hexdigest()
        return FileSessionStore.open(root, namespace=scope.namespace, learner_id=scope.learner_id)

    return open_store
