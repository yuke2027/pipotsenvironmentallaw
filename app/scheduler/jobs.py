"""Pipeline step names and the result each step returns."""

from __future__ import annotations

from dataclasses import dataclass

STEP_NAMES: tuple[str, ...] = (
    "collect",
    "impute",
    "compliance",
    "risk",
    "forecast",
    "alert",
)


@dataclass(frozen=True)
class JobResult:
    status: str
    no_op: bool = False
    reason: str | None = None


def success(*, no_op: bool = False, reason: str | None = None) -> JobResult:
    return JobResult(status="SUCCESS", no_op=no_op, reason=reason)


def failure(reason: str) -> JobResult:
    return JobResult(status="FAILED", no_op=False, reason=reason)
