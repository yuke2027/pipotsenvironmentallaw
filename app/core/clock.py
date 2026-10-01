"""Injectable clocks so lockout, tokens, and jobs do not read the wall clock directly."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

class Clock(Protocol):
    """Monotonic-enough UTC clock used by services."""

    def now(self) -> datetime: ...


class SystemClock:
    """Production clock. Returns timezone-aware UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FrozenClock:
    """Manually advanced clock for tests and deterministic replays."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None or instant.tzinfo.utcoffset(instant) is None:
            raise ValueError("clock instants must be timezone-aware")
        self._instant = instant.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._instant

    def advance(self, seconds: float) -> None:
        self._instant = self._instant + timedelta(seconds=seconds)
