"""Preserved filesystem custody regression cases from the prior reference producer."""

import os
import sys
from contextlib import contextmanager

import pytest

from skilling_react_example.deployment.note import GoalNote

NOTE = "Goal: Learn Python\nTakeaway: Save work\nNext action: Build a script"


@pytest.mark.parametrize("existing", [False, True])
def test_note_fallback_leaf_substitution_does_not_create_outside(tmp_path, monkeypatch, existing):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    note = GoalNote.open(workspace)
    target = workspace / "showcase/welcome-skilling/goal.md"
    target.parent.mkdir(parents=True)
    if existing:
        target.write_text("Original learner words")
    external = tmp_path / "outside-missing"
    real_open_leaf = GoalNote._open_leaf

    @contextmanager
    def fallback(self, *, create=False):
        self._check(create=create)
        yield None

    def substitute(path, flags, *, dir_fd=None):
        assert path == target
        assert bool(flags & os.O_CREAT) is not existing
        if not existing:
            assert flags & os.O_EXCL
        if existing:
            target.unlink()
        try:
            target.symlink_to(external)
        except OSError:
            pytest.skip("symlinks unavailable on this host")
        # Simulate the platform fallback without POSIX O_NOFOLLOW's separate protection.
        return real_open_leaf(path, flags & ~getattr(os, "O_NOFOLLOW", 0), dir_fd=dir_fd)

    monkeypatch.setattr(GoalNote, "_parent", fallback)
    monkeypatch.setattr(GoalNote, "_open_leaf", staticmethod(substitute))
    with pytest.raises((OSError, ValueError)):
        note.save(NOTE)
    assert not external.exists()


def test_note_leaf_existing_external_substitution_preserves_bytes(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    note = GoalNote.open(workspace)
    note.save(NOTE)
    target = workspace / "showcase/welcome-skilling/goal.md"
    external = tmp_path / "external-existing"
    external.write_bytes(b"External bytes must remain unchanged\r\n")
    before = external.read_bytes()
    real_open_leaf = GoalNote._open_leaf

    def substitute(path, flags, *, dir_fd=None):
        target.unlink()
        try:
            target.symlink_to(external)
        except OSError:
            pytest.skip("symlinks unavailable on this host")
        return real_open_leaf(path, flags & ~getattr(os, "O_NOFOLLOW", 0), dir_fd=dir_fd)

    monkeypatch.setattr(GoalNote, "_open_leaf", staticmethod(substitute))
    with pytest.raises((OSError, ValueError)):
        note.save("Replacement learner text")
    assert external.read_bytes() == before


@pytest.mark.parametrize("creating", [False, True])
def test_note_windows_leaf_uses_native_no_follow_and_owned_binary_handle(
    tmp_path, monkeypatch, creating
):
    import ctypes
    from types import ModuleType
    from unittest.mock import Mock

    path = tmp_path / "goal.md"
    flags = os.O_WRONLY | (os.O_CREAT | os.O_EXCL if creating else 0)
    create = Mock(return_value=123)
    close = Mock()
    kernel = Mock(CreateFileW=create, CloseHandle=close)
    convert = Mock(return_value=9)
    native = ModuleType("msvcrt")
    monkeypatch.setattr(native, "open_osfhandle", convert, raising=False)
    with monkeypatch.context() as patch:
        patch.setattr(os, "name", "nt")
        patch.setattr(os, "O_BINARY", 0x8000, raising=False)
        patch.setattr(ctypes, "WinDLL", Mock(return_value=kernel), raising=False)
        patch.setitem(sys.modules, "msvcrt", native)
        assert GoalNote._open_leaf(path, flags, dir_fd=None) == 9
    assert create.call_args.args == (
        str(path),
        0x40000000,
        1,
        None,
        1 if creating else 3,
        0x00200000,
        None,
    )
    convert.assert_called_once_with(123, os.O_WRONLY | 0x8000)
    close.assert_not_called()


def test_note_windows_leaf_closes_handle_if_descriptor_conversion_fails(tmp_path, monkeypatch):
    import ctypes
    from types import ModuleType
    from unittest.mock import Mock

    path = tmp_path / "goal.md"
    close = Mock()
    kernel = Mock(CreateFileW=Mock(return_value=123), CloseHandle=close)
    native = ModuleType("msvcrt")
    monkeypatch.setattr(
        native,
        "open_osfhandle",
        Mock(side_effect=OSError("descriptor conversion refused")),
        raising=False,
    )
    with monkeypatch.context() as patch:
        patch.setattr(os, "name", "nt")
        patch.setattr(os, "O_BINARY", 0x8000, raising=False)
        patch.setattr(ctypes, "WinDLL", Mock(return_value=kernel), raising=False)
        patch.setitem(sys.modules, "msvcrt", native)
        with pytest.raises(OSError, match="descriptor conversion refused"):
            GoalNote._open_leaf(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, dir_fd=None)
    close.assert_called_once_with(123)


def test_overlapping_same_learner_saves_publish_only_complete_utf8(tmp_path, monkeypatch):
    import os
    import stat
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    if os.name == "nt":
        pytest.skip("Win32 leaf guard refuses a second writer before the POSIX overlap barrier")
    note_a, note_b = GoalNote.open(tmp_path), GoalNote.open(tmp_path)
    note_a.save("original")
    barrier = Barrier(2)
    real_fsync = os.fsync

    def overlapping(fd):
        real_fsync(fd)
        if stat.S_ISREG(os.fstat(fd).st_mode):
            barrier.wait(timeout=10)

    monkeypatch.setattr(os, "fsync", overlapping)
    texts = ("星" * 3, "B" * 100)

    def save(pair):
        note, text = pair
        try:
            return note.save(text).text
        except ValueError:
            return None  # A concurrent publication can invalidate the observed leaf.

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(save, zip((note_a, note_b), texts, strict=True)))
    assert any(result in texts for result in results)
    assert note_a.inspect().text in texts
    assert list((tmp_path / "showcase/welcome-skilling").glob(".goal-*.tmp")) == []
