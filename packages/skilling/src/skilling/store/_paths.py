"""Checked paths for local state, without filesystem creation.

The caller-selected root may be an alias. Descendants may not: even an alias within the
root could redirect a write into another course. This protects against pre-existing aliases,
not hostile concurrent replacement or hardlinks on a shared filesystem.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from functools import cache
from pathlib import Path

from ..course import is_course_id
from ._protocol import StatePathError


def canonical_root(root: Path | str) -> Path:
    try:
        resolved = Path(root).resolve(strict=False)
        # Non-strict resolution may suppress a cycle/error; check every existing ancestor.
        for path in (resolved, *resolved.parents):
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            if path.resolve(strict=True) != path:
                raise StatePathError(f"Cannot resolve state root alias: {root}")
        return resolved
    except (OSError, RuntimeError, ValueError) as exc:
        raise StatePathError(f"Cannot resolve state root: {exc}") from exc


_WINDOWS_DEVICES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CONIN$",
    "CONOUT$",
    *(f"COM{n}" for n in "123456789¹²³"),
    *(f"LPT{n}" for n in "123456789¹²³"),
}


@cache
def _windows_api() -> ctypes.CDLL:
    if os.name != "nt":
        raise NotImplementedError("Windows path metadata is Windows-only")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.FindFirstFileW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.WIN32_FIND_DATAW)]
    api.FindFirstFileW.restype = wintypes.HANDLE
    api.FindClose.argtypes = [wintypes.HANDLE]
    api.FindClose.restype = wintypes.BOOL
    return api


def _check_windows_component(candidate: Path) -> None:
    """Inspect directory metadata without opening a target that another owner may replace.

    CPython resolve/lstat can open a Windows target with share mode zero, which denies
    another cooperating writer's rename even before this caller acquires the course lock.
    FindFirstFileW returns the long filename and reparse attributes without that target
    handle. Reject short-name aliases and every descendant reparse point conservatively;
    the selected root is already canonicalized separately.
    """
    if os.name != "nt":
        raise NotImplementedError("Windows path metadata is Windows-only")
    name = candidate.name
    if (
        name.endswith((".", " "))
        or any(ord(char) < 32 or char in '"*<>?|' for char in name)
        or name.partition(".")[0].rstrip(" ").upper() in _WINDOWS_DEVICES
    ):
        raise StatePathError(f"Invalid Windows state path component: {name!r}")
    data = wintypes.WIN32_FIND_DATAW()
    api = _windows_api()
    handle = api.FindFirstFileW(str(candidate), ctypes.byref(data))
    if handle == ctypes.c_void_p(-1).value:
        error = ctypes.get_last_error()
        if error in {2, 3}:  # ERROR_FILE_NOT_FOUND / ERROR_PATH_NOT_FOUND
            return
        raise ctypes.WinError(error)
    try:
        if data.cFileName.lower() != name.lower() or data.dwFileAttributes & 0x400:
            raise StatePathError(f"State descendant must not be an alias: {candidate}")
    finally:
        if not api.FindClose(handle):
            raise ctypes.WinError(ctypes.get_last_error())


def checked_path(root: Path, course_id: str, *parts: str) -> Path:
    if not is_course_id(course_id):
        raise StatePathError(f"Invalid state course id: {course_id!r}")
    candidate = root
    for part in (course_id, *parts):
        if not part or part in (".", "..") or any(c in part for c in "/\\:\0"):
            raise StatePathError(f"Invalid state path component: {part!r}")
        candidate = candidate / part
        try:
            if os.name == "nt":
                _check_windows_component(candidate)
                continue
            if candidate.is_symlink():
                raise StatePathError(f"State descendant must not be an alias: {candidate}")
            try:
                candidate.lstat()
            except FileNotFoundError:
                resolved = candidate.resolve(strict=False)
            else:
                # Existing junctions must resolve strictly: cycles and broken targets refuse.
                try:
                    resolved = candidate.resolve(strict=True)
                except FileNotFoundError:
                    # A cooperating store may have deleted this file since lstat.
                    # An entry still present (e.g. a broken junction) must still refuse.
                    try:
                        candidate.lstat()
                    except FileNotFoundError:
                        resolved = candidate.resolve(strict=False)
                    else:
                        raise
            if not resolved.is_relative_to(root) or resolved != candidate:
                raise StatePathError(f"State descendant must not be an alias: {candidate}")
        except (OSError, RuntimeError, ValueError) as exc:
            raise StatePathError(f"Cannot resolve state path {candidate}: {exc}") from exc
    return candidate
