"""Exclusive runtime locking and composed local store."""

from __future__ import annotations

import fcntl
import os
from dataclasses import dataclass
from pathlib import Path

from ..errors import LockError
from .artifact import ArtifactStore


class RunLock:
    def __init__(self, target_repository: Path) -> None:
        self.path = Path(target_repository).resolve() / ".ai-harness" / "run.lock"
        self._descriptor: int | None = None

    def acquire(self) -> "RunLock":
        if self._descriptor is not None:
            raise LockError("run lock is already held by this object")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(descriptor, 0)
            os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
        except BlockingIOError as exc:
            os.close(descriptor)
            raise LockError("another harness run holds the repository lock") from exc
        self._descriptor = descriptor
        return self

    def release(self) -> None:
        if self._descriptor is None:
            return
        fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        os.close(self._descriptor)
        self._descriptor = None

    def __enter__(self) -> "RunLock":
        return self.acquire()

    def __exit__(self, *_: object) -> None:
        self.release()


@dataclass(slots=True)
class LocalRuntimeStore:
    artifacts: object
    state: object
    knowledge: object
    lock: RunLock
