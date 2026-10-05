"""One learner-authored file, bounded inspection, and descriptor-relative custody."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

NOTE_PATH = "showcase/welcome-skilling/goal.md"
MAX_NOTE_BYTES = 24_000


@dataclass(frozen=True)
class NoteObservation:
    path: str
    text: str
    digest: str
    regular_file: bool = True
    file_identity: str = ""

    @property
    def meaningful(self) -> bool:
        for label in ("Goal", "Takeaway", "Next action"):
            pattern = rf"(?i)^[ \t]*(?:[-*][ \t]*)?(?:\*\*)?{label}"
            pattern += r"(?::(?:\*\*)?|(?:\*\*)?:)[ \t]*(\S.*)$"
            values = (re.match(pattern, line) for line in self.text.splitlines())
            if not any(match and len(match.group(1).strip()) >= 3 for match in values):
                return False
        return True


@dataclass(frozen=True)
class GoalNote:
    workspace: Path

    @classmethod
    def open(cls, workspace: Path) -> GoalNote:
        return cls(workspace.resolve(strict=True))

    def _check(self, *, create: bool = False) -> Path:
        parent = self.workspace
        for name in ("showcase", "welcome-skilling"):
            parent /= name
            if parent.is_symlink():
                raise ValueError("note parents must not be symlinks")
            if create:
                parent.mkdir(exist_ok=True)
            if not parent.is_dir():
                raise FileNotFoundError("note parent does not exist")
        target = parent / "goal.md"
        if target.is_symlink():
            raise ValueError("note must not be a symlink")
        if target.exists() and not stat.S_ISREG(target.lstat().st_mode):
            raise ValueError("note must be a regular file")
        if not target.resolve().is_relative_to(self.workspace):
            raise ValueError("note is outside workspace")
        return target

    @contextmanager
    def _parent(self, *, create: bool = False) -> Iterator[int | None]:
        self._check(create=create)
        if os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
            yield None
            return
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open(self.workspace, flags)
        try:
            for name in ("showcase", "welcome-skilling"):
                next_descriptor = os.open(name, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            yield descriptor
        finally:
            os.close(descriptor)

    def inspect(self) -> NoteObservation:
        with self._parent() as descriptor:
            target = self._check()
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            fd = os.open("goal.md" if descriptor is not None else target, flags, dir_fd=descriptor)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError("note must be a regular file")
                data = stream.read(MAX_NOTE_BYTES + 1)
                after = os.fstat(stream.fileno())
            current = self._check().stat()
            if (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) != (
                after.st_ino,
                after.st_dev,
                after.st_size,
                after.st_mtime_ns,
            ) or (current.st_ino, current.st_dev) != (before.st_ino, before.st_dev):
                raise ValueError("note changed during inspection")
        if len(data) > MAX_NOTE_BYTES:
            raise ValueError("note is too large")
        text = data.decode("utf-8", errors="strict")
        identity = f"{before.st_dev}:{before.st_ino}:{before.st_size}:{before.st_mtime_ns}"
        return NoteObservation(NOTE_PATH, text, hashlib.sha256(data).hexdigest(), True, identity)

    @staticmethod
    def _open_leaf(path: str | Path, flags: int, *, dir_fd: int | None) -> int:
        if os.name != "nt":
            return os.open(path, flags, 0o600, dir_fd=dir_fd)
        import ctypes
        import msvcrt

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
        ]
        create.restype = ctypes.c_void_p
        close = kernel.CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close.restype = ctypes.c_int
        # CRT O_EXCL can follow a broken Windows symlink; open the reparse point itself.
        disposition = 1 if flags & os.O_CREAT else 3  # CREATE_NEW / OPEN_EXISTING
        handle = create(str(path), 0x40000000, 1, None, disposition, 0x00200000, None)
        if handle is None or handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
        except BaseException:
            close(handle)
            raise

    def save(self, text: str) -> NoteObservation:
        data = text.encode("utf-8", errors="strict")
        if len(data) > MAX_NOTE_BYTES:
            raise ValueError("note is too large")
        with self._parent(create=True) as descriptor:
            target = self._check()
            flags = os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            if not target.exists():
                flags |= os.O_CREAT | os.O_EXCL
            fd = self._open_leaf(
                "goal.md" if descriptor is not None else target, flags, dir_fd=descriptor
            )
            temporary = ".goal-" + secrets.token_hex(16) + ".tmp"
            staging = temporary if descriptor is not None else target.with_name(temporary)
            published = False
            try:
                # Open the old leaf only for custody checks; never truncate its shared inode.
                with os.fdopen(fd, "wb") as guard:
                    info = os.fstat(guard.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise ValueError("note must be a regular file with one link")
                    current = self._check().stat()
                    if (current.st_ino, current.st_dev) != (info.st_ino, info.st_dev):
                        raise ValueError("note changed before save")
                    staged_fd = os.open(
                        staging, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=descriptor
                    )
                    with os.fdopen(staged_fd, "wb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    current = self._check().stat()
                    if (current.st_ino, current.st_dev, current.st_nlink) != (
                        info.st_ino,
                        info.st_dev,
                        1,
                    ):
                        raise ValueError("note changed before publication")
                # Closing the guard permits Windows replacement. Both writers publish whole
                # private files; a concurrent winner can never create a mixed-byte note.
                os.replace(
                    staging,
                    "goal.md" if descriptor is not None else target,
                    src_dir_fd=descriptor,
                    dst_dir_fd=descriptor,
                )
                published = True
                if descriptor is not None:
                    os.fsync(descriptor)
            finally:
                if not published:
                    with suppress(FileNotFoundError):
                        os.unlink(staging, dir_fd=descriptor)
        return self.inspect()
