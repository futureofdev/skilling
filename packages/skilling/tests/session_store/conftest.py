"""Explicit backend selection; a requested unavailable service must fail closed."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from skilling.store import FileSessionStore, SessionScope, SessionStore

StoreFactory = Callable[[SessionScope], SessionStore]


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("session persistence")
    group.addoption("--store-profile", choices=("file", "sqlite", "postgres", "aws", "seaweed"))
    group.addoption(
        "--store-config", help="Private JSON configuration for an explicit service profile"
    )


@pytest.fixture
def store_factory(request: pytest.FixtureRequest, tmp_path: Path) -> StoreFactory:
    profile = request.config.getoption("--store-profile", default=None) or "file"
    if profile != "file":
        pytest.fail(f"Explicit {profile} session profile is not available in this implementation")

    def open_store(scope: SessionScope) -> SessionStore:
        identity = (scope.namespace + "\0" + scope.learner_id).encode()
        root = tmp_path / "stores" / hashlib.sha256(identity).hexdigest()
        return FileSessionStore.open(root, namespace=scope.namespace, learner_id=scope.learner_id)

    return open_store
