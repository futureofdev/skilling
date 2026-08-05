"""Store selection: URI parsing plus entry-point discovery for third-party backends.

The seam has three destinations for a URI: no scheme (or ``file:``) resolves to the file
backend; any other scheme is looked up in the ``skilling.stores`` entry-point group and
the whole URI is handed to the discovered factory; an unregistered scheme fails with a
message actionable enough to register one.
"""

from __future__ import annotations

import importlib.metadata

import pytest

from skilling.store import FileProgressStore, UnknownScheme, default_state_root, open_store


def test_default_is_the_file_backend_at_the_default_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILLING_STATE_ROOT", str(tmp_path / "state"))
    store = open_store(None)
    assert isinstance(store, FileProgressStore)
    assert default_state_root() == tmp_path / "state"


def test_explicit_file_uri_and_bare_path_select_the_file_backend(tmp_path):
    for uri in (f"file:{tmp_path}", str(tmp_path)):
        assert isinstance(open_store(uri), FileProgressStore)


def test_unknown_scheme_fails_actionably(tmp_path):
    with pytest.raises(UnknownScheme, match="postgres.*skilling.stores"):
        open_store("postgres://example/db")


def test_entry_point_backend_is_discovered(monkeypatch):
    class Dummy:  # satisfies ProgressStore structurally where used
        def __init__(self, uri):
            self.uri = uri

    ep = importlib.metadata.EntryPoint(name="dummy", value="x:y", group="skilling.stores")
    monkeypatch.setattr(ep.__class__, "load", lambda self: lambda uri: Dummy(uri))
    monkeypatch.setattr("skilling.store._select._entry_points", lambda: [ep])
    store = open_store("dummy://anything")
    assert isinstance(store, Dummy) and store.uri == "dummy://anything"
