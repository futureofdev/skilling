"""Reentrant course locks for cooperating processes on a local filesystem.

The persistent lock file is never replaced or removed. Its existence is not ownership:
only the kernel lock is. Cooperators must not move/replace live course directories or
lock paths. Network filesystems, hostile path replacement and power loss are not covered.
"""

from __future__ import annotations

import errno
import math
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

from ._protocol import StoreBusy

if os.name == "posix":
    import fcntl
elif os.name == "nt":
    import msvcrt

DEFAULT_LOCK_TIMEOUT = 30.0
LOCK_POLL_INTERVAL = 0.05


class _Identity(NamedTuple):
    device: int
    inode: int


class _Ownership(threading.local):
    def __init__(self) -> None:
        self.descriptors: dict[_Identity, int] = {}


_REGISTRY_MUTEX = threading.Lock()
_LOCKS: dict[_Identity, threading.RLock] = {}
_OPEN_FDS: set[int] = set()
_OWNERSHIP = _Ownership()


def _before_fork() -> None:
    _REGISTRY_MUTEX.acquire()


def _after_fork_parent() -> None:
    _REGISTRY_MUTEX.release()


def _after_fork_child() -> None:
    global _REGISTRY_MUTEX, _LOCKS, _OPEN_FDS, _OWNERSHIP
    # Close inherited references, without unlocking the parent's shared open description.
    for fd in _OPEN_FDS:
        os.close(fd)
    _REGISTRY_MUTEX = threading.Lock()
    _LOCKS = {}
    _OPEN_FDS = set()
    _OWNERSHIP = _Ownership()


if os.name == "posix":
    os.register_at_fork(
        before=_before_fork, after_in_parent=_after_fork_parent, after_in_child=_after_fork_child
    )


def _kernel_lock(fd: int) -> None:
    if os.name == "posix":
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif os.name == "nt":
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        raise NotImplementedError(f"Course locking is unsupported on {os.name!r}")


def _kernel_unlock(fd: int) -> None:
    if os.name == "posix":
        fcntl.flock(fd, fcntl.LOCK_UN)
    elif os.name == "nt":
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        raise NotImplementedError(f"Course locking is unsupported on {os.name!r}")


def _close(fd: int) -> None:
    with _REGISTRY_MUTEX:
        try:
            os.close(fd)
        finally:
            _OPEN_FDS.remove(fd)


@contextmanager
def locked_course(directory: Path, *, timeout: float = DEFAULT_LOCK_TIMEOUT) -> Iterator[None]:
    """Lock an already checked existing directory, with one deadline for all waits."""
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("Lock timeout must be finite and nonnegative")
    deadline = time.monotonic() + timeout
    owner_pid = os.getpid()
    stat = directory.stat()
    identity = _Identity(stat.st_dev, stat.st_ino)
    with _REGISTRY_MUTEX:
        local_lock = _LOCKS.setdefault(identity, threading.RLock())
    if not local_lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
        raise StoreBusy(f"Timed out acquiring course lock: {directory}")
    try:
        if identity in _OWNERSHIP.descriptors:
            yield
            return
        with _REGISTRY_MUTEX:
            fd = os.open(directory / ".skilling.lock", os.O_RDWR | os.O_CREAT, 0o600)
            _OPEN_FDS.add(fd)
        try:
            # Seek failures are I/O failures, never mistaken for lock contention.
            os.lseek(fd, 0, os.SEEK_SET)
            while True:
                try:
                    _kernel_lock(fd)
                    break
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EINTR}:
                        raise
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise StoreBusy(f"Timed out acquiring course lock: {directory}") from exc
                    if exc.errno != errno.EINTR:
                        time.sleep(min(LOCK_POLL_INTERVAL, remaining))
            _OWNERSHIP.descriptors[identity] = fd
            try:
                yield
            finally:
                # A fork child's callback already closed inherited FDs and reset ownership.
                if os.getpid() == owner_pid:
                    try:
                        _kernel_unlock(fd)
                    finally:
                        del _OWNERSHIP.descriptors[identity]
        finally:
            if os.getpid() == owner_pid:
                _close(fd)
    finally:
        if os.getpid() == owner_pid:
            local_lock.release()
