"""One ordered pass: collect, impute, compliance, risk, forecast, alert.

A failed step stops the pass. The next pass uses a new run id and starts at
collect again. Exceptions are sanitized before they are stored on the run.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.logging import sanitize_text
from app.scheduler.jobs import STEP_NAMES, JobResult, failure
from app.scheduler.locks import TargetLock


Step = Callable[[], JobResult]


@dataclass(frozen=True)
class PipelineRun:
    run_id: str
    executed: tuple[str, ...]
    failed_step: str | None
    status: str
    reason: str | None = None


class Pipeline:
    def __init__(
        self,
        steps: Mapping[str, Step],
        *,
        locks: TargetLock | None = None,
        target: str = "pipeline",
    ) -> None:
        missing = [name for name in STEP_NAMES if name not in steps]
        if missing:
            raise ValueError("pipeline is missing steps")
        self._steps = dict(steps)
        self._locks = locks if locks is not None else TargetLock()
        self._target = target
        self.runs: list[PipelineRun] = []

    def run_once(self) -> PipelineRun:
        run_id = str(uuid4())
        if not self._locks.acquire(self._target):
            outcome = PipelineRun(run_id, (), None, "FAILED", "locked")
            self.runs.append(outcome)
            return outcome
        executed: list[str] = []
        failed: str | None = None
        reason: str | None = None
        status = "SUCCESS"
        try:
            for name in STEP_NAMES:
                executed.append(name)
                try:
                    result = self._steps[name]()
                except Exception as exc:
                    result = failure(sanitize_text(str(exc)))
                if result.status != "SUCCESS":
                    failed = name
                    status = "FAILED"
                    reason = result.reason
                    break
        finally:
            self._locks.release(self._target)
        outcome = PipelineRun(run_id, tuple(executed), failed, status, reason)
        self.runs.append(outcome)
        return outcome


def build_scheduler(pipeline: Pipeline, interval_seconds: int) -> BackgroundScheduler:
    """Register the pipeline on an interval. The scheduler is not started here."""

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        pipeline.run_once,
        "interval",
        seconds=interval_seconds,
        id="supervision-pipeline",
        replace_existing=True,
    )
    return scheduler
