"""Exact-byte atomic writes and platform-aware directory durability."""

import errno
import os
import tempfile
from pathlib import Path


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _fsync_dir(directory: Path) -> None:
    # Windows has no usable directory descriptor through this standard-library path.
    # File flush/fsync and atomic replacement still run; this is not a power-loss promise.
    if os.name == "nt":
        return
    fd: int | None = None
    try:
        fd = os.open(directory, os.O_RDONLY)
        os.fsync(fd)
    except OSError as exc:
        if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
            raise
    finally:
        if fd is not None:
            os.close(fd)
