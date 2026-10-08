"""At-least-once delivery with transactional outbox and PostgreSQL target locks."""
import logging
import threading
from datetime import date
from typing import Any, cast

from celery import Celery  # type: ignore[import-untyped]
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.v2.shared.sensitive_logging import install_sensitive_data_filter
from app.v2.config import Settings
from app.v2.db import Database
from app.v2.domains.jobs.models import Job
from app.v2.shared.persistence import now
from app.v2.storage import FileStore
from app.v2.shared.job_contracts import ArtifactRef, JobKind, JobProgress, JobResult, JobSpec, JobState

settings = Settings()
celery_app = Celery("environmental-platform", broker=settings.redis_url)
celery_app.conf.update(task_default_queue="io", task_acks_late=True, task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, broker_transport_options={"visibility_timeout": 3600},
    task_serializer="json", accept_content=["json"], result_serializer="json", timezone="Asia/Shanghai",
    task_ignore_result=True, broker_connection_retry_on_startup=True)
logger = logging.getLogger(__name__)
install_sensitive_data_filter(logger)


def artifact_references(job_kind: str, result: dict[str, Any]) -> list[ArtifactRef]:
    """Translate adapter output into the stable artifact registry contract."""
    key = result.get("artifact_key") or result.get("storage_key")
    digest = result.get("artifact_sha256") or result.get("sha256")
    if not key or not digest:
        return []
    return [ArtifactRef(
        kind=result.get("artifact_kind") or job_kind,
        key=key,
        sha256=digest,
        media_type=result.get("artifact_media_type"),
    )]


def dispatch(db: Database, store: FileStore, configuration: Settings, job: Job, progress: Any) -> dict[str, Any]:
    p = job.parameters
    start = date.fromisoformat(p["start"]) if "start" in p else None
    end = date.fromisoformat(p["end"]) if "end" in p else None
    if job.kind == "collect":
        from app.v2.domains.collection.adapters import LegacyCollectionAdapter
        from app.v2.domains.collection.service import CollectionService
        from app.v2.evaluation import evaluate_range
        if start is None or end is None:
            raise ValueError("采集任务缺少日期范围")
        result = CollectionService(LegacyCollectionAdapter(db, store, configuration)).collect(start, end, job.id, progress)
        result["evaluation"] = evaluate_range(db, start, end, job.id, lambda _: None)
        return result
    if job.kind == "import":
        from app.v2.domains.collection.adapters import LegacyCollectionAdapter
        from app.v2.domains.collection.service import CollectionService
        from app.v2.exports import import_enterprises
        from app.v2.evaluation import evaluate_range
        content = store.verify(p["storage_key"], p["sha256"]).read_bytes()
        if p["kind"] == "enterprises": return import_enterprises(db, content, job.owner_id)
        result = CollectionService(LegacyCollectionAdapter(db, store, configuration)).import_file(content, p["kind"])
        day = date.fromisoformat(result["date"])
        result["evaluation"] = evaluate_range(db, day, day, job.id, progress)
        return result
    if job.kind == "evaluate":
        from app.v2.evaluation import evaluate_range
        if start is None or end is None:
            raise ValueError("评估任务缺少日期范围")
        return evaluate_range(db, start, end, job.id, progress, p.get("station_id"))
    if job.kind == "export":
        from app.v2.exports import export_job
        return export_job(db, store, p, job.owner_id, progress)
    if job.kind in {"train", "forecast", "impute"}:
        if configuration.ml_service_enabled:
            from app.v2.domains.ml.adapters import LegacyModelExecutionAdapter
            from app.v2.domains.ml.service import ModelExecutionService
            return ModelExecutionService(LegacyModelExecutionAdapter()).execute(
                db, store, configuration, job, progress
            )
        from app.v2.ml import model_job
        return model_job(db, store, configuration, job, progress)
    raise ValueError("不支持的任务类型")


def run_job(job_id: str, configuration: Settings | None = None) -> dict[str, Any]:
    configuration = configuration or settings
    configuration.prepare()
    db, store = Database(configuration), FileStore(configuration.storage_root)
    stop = threading.Event()
    thread = None
    def progress(percent: float, stage: str | None = None, message: str | None = None) -> None:
        snapshot = JobProgress(state=JobState.RUNNING, percent=max(0, min(int(percent), 99)),
                               stage=stage, message=message)
        with db.transaction() as session:
            item = session.get(Job, job_id)
            if item is None or item.status == JobState.CANCELLED.value:
                return
            item.progress = max(item.progress, snapshot.percent)
            item.progress_stage = snapshot.stage
            item.progress_message = snapshot.message
            item.heartbeat_at = now()
    def heartbeat() -> None:
        while not stop.wait(20):
            try:
                with db.transaction() as session:
                    item = session.get(Job, job_id)
                    if item is not None:
                        item.heartbeat_at = now()
            except Exception:
                logger.warning("Unable to update job heartbeat %s", job_id)
    try:
        # Session advisory lock survives transaction commits; connection close releases it on a crash.
        with db.engine.connect() as lock:
            acquired = lock.scalar(text("SELECT pg_try_advisory_lock(hashtext(:key))"), {"key": f"job:{job_id}"})
            if not acquired: return {"status": "duplicate"}
            try:
                with db.transaction() as session:
                    job = session.get(Job, job_id)
                    if job is None or job.status in {"succeeded", "partial", "failed", "cancelled"}:
                        return {"status": "already_finished"}
                    # Validate the cross-process job envelope before executing
                    # a legacy algorithm. This catches malformed persisted jobs
                    # without changing the public database schema.
                    JobSpec(kind=cast(JobKind, job.kind), parameters=job.parameters, target_key=job.target_key,
                            owner_id=job.owner_id)
                    job.status, job.started_at, job.heartbeat_at = JobState.RUNNING.value, now(), now()
                    job.progress_stage, job.progress_message = "starting", "任务已开始"
                    job.attempts += 1
                    job.error = None
                thread = threading.Thread(target=heartbeat, daemon=True)
                thread.start()
                try:
                    result = dispatch(db, store, configuration, job, progress)
                    if not isinstance(result, dict):
                        raise ValueError("任务结果必须是对象")
                    state = JobState.PARTIAL if result.get("failures") else JobState.SUCCEEDED
                    artifacts = artifact_references(job.kind, result)
                    source_hashes = list(result.get("source_hashes") or [])
                    if not source_hashes and result.get("snapshot_hash"):
                        source_hashes = [result["snapshot_hash"]]
                    contract = JobResult(state=state, artifacts=artifacts, result=result,
                                         source_hashes=source_hashes)
                    with db.transaction() as session:
                        item = session.get(Job, job_id)
                        if item is None:
                            raise ValueError("任务记录在执行过程中被删除")
                        item.result = {**result, "_contract": contract.model_dump(mode="json")}
                        item.progress, item.finished_at = 100, now()
                        item.progress_stage, item.progress_message = "completed", "任务已完成"
                        item.status = state.value
                    return {"status": "completed"}
                except Exception as exc:
                    logger.exception("Job %s failed: %s", job_id, exc)
                    with db.transaction() as session:
                        item = session.get(Job, job_id)
                        if item is not None:
                            # Expected validation messages are useful; unexpected exceptions never expose paths or SQL.
                            item.error = str(exc)[:600] if isinstance(exc, ValueError) else f"任务执行失败（{type(exc).__name__}），请联系管理员并提供任务编号"
                            failed = JobResult(state=JobState.FAILED, error_code=type(exc).__name__,
                                               error_message=str(exc)[:600])
                            item.result = {"_contract": failed.model_dump(mode="json")}
                            item.status, item.finished_at = JobState.FAILED.value, now()
                            item.progress_stage, item.progress_message = "failed", "任务执行失败"
                    return {"status": "failed"}
                finally:
                    stop.set()
                    if thread: thread.join(timeout=2)
            finally:
                lock.execute(text("SELECT pg_advisory_unlock(hashtext(:key))"), {"key": f"job:{job_id}"})
    finally:
        db.engine.dispose()


@celery_app.task(name="platform.run_job")
def execute_job(job_id: str) -> dict[str, Any]:
    return run_job(job_id)
