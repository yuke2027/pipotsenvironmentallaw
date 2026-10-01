"""Non-blocking locks so one target cannot run two pipeline passes at once."""

from __future__ import annotations

import threading


class TargetLock:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def acquire(self, target: str) -> bool:
        with self._guard:
            lock = self._locks.setdefault(target, threading.Lock())
        return lock.acquire(blocking=False)

    def release(self, target: str) -> None:
        with self._guard:
            lock = self._locks.get(target)
        if lock is not None and lock.locked():
            lock.release()
