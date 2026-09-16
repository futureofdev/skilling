"""Cache containment and plain-file checks; no hostile concurrent replacement guarantee."""

import os
import shutil
import stat
from collections.abc import Callable
from pathlib import Path

from ._errors import CacheInvalid


def plain(path: Path, *, directory: bool) -> None:
    try:
        info = path.lstat()
    except OSError:
        raise CacheInvalid("cache path is missing or unreadable; use a separate cache") from None
    if (
        stat.S_ISLNK(info.st_mode)
        or (info.st_file_attributes & 0x400 if os.name == "nt" else False)
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
    ):
        raise CacheInvalid("cache content must use plain files/directories, never aliases")


def root_path(cache: Path) -> Path:
    try:
        root = cache.resolve()
        if root.exists():
            plain(root, directory=True)
        return root
    except (OSError, ValueError, RuntimeError):
        raise CacheInvalid("cannot resolve cache root") from None


def child(root: Path, name: str, *, directory: bool = False) -> Path:
    if not name or name in {".", ".."} or any(c in name for c in "/\\:\0"):
        raise CacheInvalid("invalid cache path component")
    path = root / name
    if path.exists() or path.is_symlink():
        plain(path, directory=directory)
    return path


def remove_tree(path: Path) -> None:
    """Remove task-owned scratch, including Windows read-only Git object files."""
    if not path.exists():
        return

    def writable(operation: Callable[..., object], filename: str, error: object) -> None:
        item = Path(filename)
        plain(item, directory=False)
        item.chmod(item.stat().st_mode | stat.S_IWRITE)
        operation(filename)

    shutil.rmtree(path, onerror=writable)


def fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    import errno

    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
            raise
    finally:
        os.close(fd)
