"""Shared retry and minimum-interval gate for provider and notification calls.

The first attempt plus at most three retries are allowed. Retry waits follow
1x, 2x, and 4x the base delay, plus optional bounded jitter. Every attempt,
including a retry, passes through the rate limiter.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Protocol, TypeVar

T = TypeVar("T")
MAX_RETRIES = 3


class PacingClock(Protocol):
    def time(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


@dataclass
class StepClock:
    """Test clock whose sleep moves time forward and records the delays."""

    now: float = 0.0
    sleeps: list[float] | None = None

    def __post_init__(self) -> None:
        if self.sleeps is None:
            self.sleeps = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("sleep seconds must be non-negative")
        assert self.sleeps is not None
        self.sleeps.append(seconds)
        self.now += seconds


@dataclass
class CallTrace:
    starts: list[float]
    sleeps: list[float]


class RetryExhausted(Exception):
    """The initial call and the allowed retries all failed. The message is sanitized."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ExternalCaller:
    def __init__(
        self,
        clock: PacingClock,
        *,
        min_interval_seconds: float,
        base_delay_seconds: float = 1.0,
        max_retries: int = MAX_RETRIES,
        max_jitter_seconds: float = 0.0,
        rng: random.Random | None = None,
    ) -> None:
        if min_interval_seconds < 0 or base_delay_seconds < 0 or max_jitter_seconds < 0:
            raise ValueError("intervals must be non-negative")
        if max_retries < 0 or max_retries > MAX_RETRIES:
            raise ValueError("retries cannot exceed 3")
        self._clock = clock
        self._min_interval = min_interval_seconds
        self._base_delay = base_delay_seconds
        self._max_retries = max_retries
        self._max_jitter = max_jitter_seconds
        self._rng = rng if rng is not None else random.Random(0)
        self._last_start: float | None = None
        self.starts: list[float] = []
        self.backoff_sleeps: list[float] = []

    def execute(self, operation: Callable[[], T]) -> T:
        """Run ``operation`` until it returns or the retry budget is spent."""

        failures = 0
        last_error = "external call failed"
        while True:
            self._acquire()
            try:
                return operation()
            except Exception as exc:
                last_error = type(exc).__name__
                if failures >= self._max_retries:
                    raise RetryExhausted(last_error) from None
                failures += 1
                delay = self._base_delay * (2 ** (failures - 1))
                if self._max_jitter:
                    delay += self._rng.random() * self._max_jitter
                self.backoff_sleeps.append(delay)
                self._clock.sleep(delay)

    def _acquire(self) -> None:
        now = self._clock.time()
        if self._last_start is not None:
            gap = now - self._last_start
            if gap < self._min_interval:
                self._clock.sleep(self._min_interval - gap)
                now = self._clock.time()
        self._last_start = now
        self.starts.append(now)
