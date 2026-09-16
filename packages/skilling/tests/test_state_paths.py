"""File-store containment, with fixed-date models suitable for native Windows."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from skilling.course import HomeworkArchiveEntry
from skilling.store import FileProgressStore, StatePathError

from .test_store import COURSE, LEARNER, a_record, a_slot, an_entry


def archive_entry(coordinate: str = "0.2") -> HomeworkArchiveEntry:
    return HomeworkArchiveEntry(
        coordinate=coordinate,
        title="Assignment",
        requirements=a_slot().requirements,
        submitted_at=an_entry("0.2").completed_at,
    )


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def directory_alias(link: Path, target: Path) -> None:
    """Windows junctions need no symlink privilege; directory coverage must not skip."""
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        link.symlink_to(target, target_is_directory=True)


def file_alias(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except OSError as exc:
        if os.name == "nt" and exc.winerror == 1314:
            pytest.skip("Windows file-symlink privilege unavailable; junction cases still run")
        raise


def operation(store: FileProgressStore, name: str, course_id: str) -> object:
    if name == "course-dir":
        return store.course_dir(course_id)
    if name == "record-get":
        return store.get_record(LEARNER, course_id)
    if name == "record-put":
        # A copied model can bypass serialization validation; the file boundary must defend itself.
        return store.put_record(a_record().model_copy(update={"course_id": course_id}), None)
    if name == "log-get":
        return store.get_log(LEARNER, course_id)
    if name == "log-append":
        return store.append_completion(LEARNER, course_id, an_entry("0.1"))
    if name == "homework-get":
        return store.get_homework(LEARNER, course_id)
    if name == "homework-put":
        return store.put_homework(LEARNER, course_id, a_slot(), None)
    if name == "homework-delete":
        return store.put_homework(LEARNER, course_id, None, None)
    if name == "archive-get":
        return store.get_homework_archive(LEARNER, course_id)
    if name == "archive-append":
        return store.append_homework_archive(LEARNER, course_id, archive_entry())
    if name == "list-records":
        return store.list_records(course_id)
    raise AssertionError(name)


OPERATIONS = [
    "course-dir",
    "record-get",
    "record-put",
    "log-get",
    "log-append",
    "homework-get",
    "homework-put",
    "homework-delete",
    "archive-get",
    "archive-append",
    "list-records",
]


@pytest.mark.parametrize("name", OPERATIONS)
@pytest.mark.parametrize("invalid", ["../escaped", "absolute", "a/b", "a\\b", "", "valid\n"])
@pytest.mark.parametrize("existing", [False, True])
def test_invalid_ids_leave_all_bytes_unchanged(
    tmp_path: Path,
    name: str,
    invalid: str,
    existing: bool,
) -> None:
    state = tmp_path / "state"
    if existing:
        FileProgressStore(state).put_record(a_record(), None)
    (tmp_path / "sentinel").write_bytes(b"outside sentinel")
    if invalid == "absolute":
        invalid = str(tmp_path / "escaped")
    before = snapshot(tmp_path)
    with pytest.raises(StatePathError):
        operation(FileProgressStore(state), name, invalid)
    assert snapshot(tmp_path) == before
    assert state.exists() == existing


@pytest.mark.parametrize(
    "coordinate", ["../escape", "0/2", "0\\2", "/absolute", "0.2\n", "0:2", ""]
)
def test_archive_coordinate_is_checked_before_any_write(tmp_path: Path, coordinate: str) -> None:
    store = FileProgressStore(tmp_path / "state")
    (tmp_path / "sentinel").write_bytes(b"untouched")
    before = snapshot(tmp_path)
    with pytest.raises(StatePathError):
        store.append_homework_archive(LEARNER, COURSE, archive_entry(coordinate))
    assert snapshot(tmp_path) == before
    assert not store.state_root.exists()


@pytest.mark.parametrize("name", OPERATIONS)
@pytest.mark.parametrize("inside", [False, True])
def test_course_directory_alias_is_never_followed(
    tmp_path: Path,
    name: str,
    inside: bool,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    target = (state if inside else tmp_path) / "other-course"
    target.mkdir()
    (target / "sentinel").write_bytes(b"preserve me")
    directory_alias(state / COURSE, target)
    before = snapshot(target)
    with pytest.raises(StatePathError):
        operation(FileProgressStore(state), name, COURSE)
    assert snapshot(target) == before


@pytest.mark.parametrize(
    "parts,directory",
    [
        (("record.yaml",), False),
        (("completed.yaml",), False),
        (("homework",), True),
        (("homework", "active.yaml"), False),
        (("homework", "archive"), True),
        (("homework", "archive", "0.2-2026-08-03.yaml"), False),
        (("scratch.yaml",), False),
        ((".skilling.lock",), False),
    ],
)
def test_preflight_refuses_every_aliased_descendant(
    tmp_path: Path,
    parts: tuple[str, ...],
    directory: bool,
) -> None:
    store = FileProgressStore(tmp_path / "state")
    link = store.state_root / COURSE / Path(*parts)
    link.parent.mkdir(parents=True)
    target = tmp_path / "target"
    if directory:
        target.mkdir()
        (target / "sentinel").write_bytes(b"unchanged")
        directory_alias(link, target)
    else:
        target.write_bytes(b"unchanged")
        file_alias(link, target)
    before = snapshot(tmp_path)
    with pytest.raises(StatePathError):
        store.ensure_course_paths(COURSE)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("kind", ["broken", "cycle"])
def test_unresolvable_course_alias_fails_closed(tmp_path: Path, kind: str) -> None:
    state = tmp_path / "state"
    state.mkdir()
    link = state / COURSE
    file_alias(link, tmp_path / "missing" if kind == "broken" else link)
    with pytest.raises(StatePathError):
        FileProgressStore(state).get_record(LEARNER, COURSE)


def test_selected_root_alias_is_supported_and_canonical(tmp_path: Path) -> None:
    target = tmp_path / "real-state"
    target.mkdir()
    link = tmp_path / "alias"
    directory_alias(link, target)
    store = FileProgressStore(link)
    assert store.state_root == target.resolve()
    store.put_record(a_record(), None)
    store.put_homework(LEARNER, COURSE, a_slot(), None)
    store.append_homework_archive(LEARNER, COURSE, archive_entry())
    assert FileProgressStore(target).get_record(LEARNER, COURSE) == store.get_record(
        LEARNER, COURSE
    )
    assert len(store.get_homework_archive(LEARNER, COURSE)) == 1


def test_relative_root_keeps_constructor_time_meaning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    store = FileProgressStore("state")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    store.put_record(a_record(), None)
    assert (tmp_path / "state" / COURSE / "record.yaml").is_file()
    assert not (elsewhere / "state").exists()


def test_record_identity_mismatch_is_refused_without_repair(tmp_path: Path) -> None:
    store = FileProgressStore(tmp_path / "state")
    store.put_record(a_record(), None)
    path = store.state_root / COURSE / "record.yaml"
    data = yaml.safe_load(path.read_text())
    data["course_id"] = "other-course"
    path.write_text(yaml.safe_dump(data))
    before = snapshot(tmp_path)
    with pytest.raises(StatePathError):
        store.get_record(LEARNER, COURSE)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "parts", [("",), (".",), ("..",), ("a/b",), ("a\\b",), ("C:stream",), ("nul\0",)]
)
def test_invalid_internal_components_never_create_state(
    tmp_path: Path, parts: tuple[str, ...]
) -> None:
    store = FileProgressStore(tmp_path / "state")
    with pytest.raises(StatePathError):
        store.checked_path(COURSE, *parts)
    assert not store.state_root.exists()


@pytest.mark.parametrize("kind", ["self", "two-node", "ancestor"])
def test_root_cycles_are_controlled(tmp_path: Path, kind: str) -> None:
    link = tmp_path / "root"
    if kind == "two-node":
        other = tmp_path / "other"
        directory_alias(link, other)
        directory_alias(other, link)
    else:
        directory_alias(link, link)
    root = link / "child" if kind == "ancestor" else link
    with pytest.raises(StatePathError):
        FileProgressStore(root)
    assert sorted(p.name for p in tmp_path.iterdir()) == (
        ["other", "root"] if kind == "two-node" else ["root"]
    )


@pytest.mark.parametrize(
    "name,parts",
    [
        ("record-get", ("record.yaml",)),
        ("record-put", ("record.yaml",)),
        ("log-get", ("completed.yaml",)),
        ("log-append", ("completed.yaml",)),
        ("homework-get", ("homework", "active.yaml")),
        ("homework-put", ("homework", "active.yaml")),
        ("homework-delete", ("homework", "active.yaml")),
        ("archive-get", ("homework", "archive", "0.2-2026-08-03.yaml")),
        ("archive-append", ("homework", "archive", "0.2-2026-08-03.yaml")),
        ("list-records", ("record.yaml",)),
    ],
)
def test_direct_operations_refuse_leaf_aliases(
    tmp_path: Path,
    name: str,
    parts: tuple[str, ...],
) -> None:
    store = FileProgressStore(tmp_path / "state")
    link = store.state_root / COURSE / Path(*parts)
    link.parent.mkdir(parents=True)
    target = tmp_path / "sentinel"
    target.write_bytes(b"must not read or overwrite this")
    file_alias(link, target)
    before = snapshot(tmp_path)
    with pytest.raises(StatePathError):
        operation(store, name, COURSE)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("parts", [("homework",), ("homework", "archive")])
def test_missing_leaf_under_directory_alias_is_refused(
    tmp_path: Path, parts: tuple[str, ...]
) -> None:
    store = FileProgressStore(tmp_path / "state")
    link = store.state_root / COURSE / Path(*parts)
    link.parent.mkdir(parents=True)
    target = tmp_path / "outside"
    target.mkdir()
    directory_alias(link, target)
    with pytest.raises(StatePathError):
        store.checked_path(COURSE, *parts, "missing.yaml")
    assert list(target.iterdir()) == []


def test_absent_preflight_is_read_only(tmp_path: Path) -> None:
    store = FileProgressStore(tmp_path / "state")
    store.ensure_course_paths(COURSE)
    assert store.checked_path(COURSE, "scratch.yaml").is_absolute()
    assert not store.state_root.exists()


@pytest.mark.parametrize("name", OPERATIONS)
@pytest.mark.parametrize("kind", ["self", "two-node", "broken"])
def test_unresolvable_directory_aliases_are_refused(
    tmp_path: Path,
    name: str,
    kind: str,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    link = state / COURSE
    if kind == "two-node":
        other = state / "other-course"
        directory_alias(link, other)
        directory_alias(other, link)
    else:
        directory_alias(link, link if kind == "self" else tmp_path / "missing")
    with pytest.raises(StatePathError):
        operation(FileProgressStore(state), name, COURSE)
    assert sorted(p.name for p in state.iterdir()) == (
        [COURSE, "other-course"] if kind == "two-node" else [COURSE]
    )
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize(
    "requested,actual,attributes,refused",
    [
        ("record.yaml", "record.yaml", 0, False),
        ("RECORD.YAML", "record.yaml", 0, False),
        ("literal~name.yaml", "literal~name.yaml", 0, False),
        ("RECORD~1.YAM", "record-long-name.yaml", 0, True),
        ("SHORT", "long-directory-name", 0x10, True),
        ("record.yaml", "record.yaml", 0x400, True),
        ("homework", "homework", 0x410, True),
    ],
)
def test_windows_metadata_checks_canonical_names_and_reparse_points(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    requested: str,
    actual: str,
    attributes: int,
    refused: bool,
) -> None:
    """The same metadata interpretation runs on all hosts; Windows CI uses real API too."""
    import ctypes
    from ctypes import wintypes
    from types import SimpleNamespace

    from skilling.store import _paths

    closed: list[int] = []
    queried: list[str] = []

    def find(path, pointer):
        queried.append(path)
        data = ctypes.cast(pointer, ctypes.POINTER(wintypes.WIN32_FIND_DATAW)).contents
        data.cFileName = actual
        data.dwFileAttributes = attributes
        return 42

    def close(handle):
        closed.append(handle)
        return 1

    monkeypatch.setattr(_paths, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        _paths, "_windows_api", lambda: SimpleNamespace(FindFirstFileW=find, FindClose=close)
    )
    target = tmp_path / requested
    if refused:
        with pytest.raises(StatePathError, match="alias"):
            _paths._check_windows_component(target)
    else:
        _paths._check_windows_component(target)
    assert queried == [str(target)]
    assert closed == [42], "successful lookup handles close even on alias refusal"


@pytest.mark.parametrize("error", [2, 3, 5, 123])
def test_windows_metadata_missing_and_io_errors_are_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: int
) -> None:
    import ctypes
    from types import SimpleNamespace

    from skilling.store import _paths

    def find(*args):
        return ctypes.c_void_p(-1).value

    def close(*args):
        raise AssertionError("an invalid search handle must not be closed")

    monkeypatch.setattr(_paths, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        _paths, "_windows_api", lambda: SimpleNamespace(FindFirstFileW=find, FindClose=close)
    )
    monkeypatch.setattr(ctypes, "get_last_error", lambda: error, raising=False)
    failure = OSError(error, "metadata lookup failed")
    monkeypatch.setattr(ctypes, "WinError", lambda code: failure, raising=False)
    if error in {2, 3}:
        _paths._check_windows_component(tmp_path / "record.yaml")
    else:
        with pytest.raises(OSError) as caught:
            _paths._check_windows_component(tmp_path / "record.yaml")
        assert caught.value is failure


@pytest.mark.parametrize(
    "name",
    [
        "record.",
        "record ",
        "record?",
        "record*",
        "record\x01",
        "NUL",
        "nul.txt",
        "CONOUT$",
        "COM1",
        "LPT².txt",
    ],
)
def test_windows_nonliteral_or_device_components_refuse_before_metadata_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    from types import SimpleNamespace

    from skilling.store import _paths

    def unexpected():
        raise AssertionError("unsafe names must fail before even a directory query")

    monkeypatch.setattr(_paths, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(_paths, "_windows_api", unexpected)
    with pytest.raises(StatePathError, match="Invalid Windows"):
        _paths._check_windows_component(tmp_path / name)


def test_windows_metadata_close_failure_is_not_suppressed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ctypes
    from ctypes import wintypes
    from types import SimpleNamespace

    from skilling.store import _paths

    def find(path, pointer):
        data = ctypes.cast(pointer, ctypes.POINTER(wintypes.WIN32_FIND_DATAW)).contents
        data.cFileName = "record.yaml"
        return 42

    monkeypatch.setattr(_paths, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        _paths,
        "_windows_api",
        lambda: SimpleNamespace(FindFirstFileW=find, FindClose=lambda handle: 0),
    )
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    failure = OSError(5, "search handle close failed")
    monkeypatch.setattr(ctypes, "WinError", lambda code: failure, raising=False)
    with pytest.raises(OSError) as caught:
        _paths._check_windows_component(tmp_path / "record.yaml")
    assert caught.value is failure
