"""SQLAlchemy adapter for the jobs application service."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select, text

from app.v2.common import audit, page, require_entity, serialize
from app.v2.domains.jobs.models import Job, Outbox
from app.v2.domains.monitoring.models import City, Station
from app.v2.shared.job_contracts import JobSpec
from app.v2.domains.jobs.service import JobRecord, JobSubmissionService


class SqlAlchemyJobSubmissionPort:
    def __init__(self, session: Session, owner_id: str | None = None) -> None:
        self.session = session
        self.owner_id = owner_id

    def find_existing(self, target_key: str, include_finished: bool = False) -> JobRecord | None:
        bind = self.session.bind
        if bind is not None and bind.dialect.name == "postgresql":
            self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                                 {"key": f"enqueue:{target_key}"})
        statement = select(Job).where(Job.target_key == target_key)
        if not include_finished:
            statement = statement.where(Job.status.in_(["queued", "running"]))
        return self.session.scalar(statement.order_by(Job.created_at.desc()))

    def create(self, spec: JobSpec) -> JobRecord:
        item = Job(kind=spec.kind, parameters=spec.parameters, owner_id=spec.owner_id,
                   target_key=spec.target_key)
        self.session.add(item)
        self.session.flush()
        self.session.add(Outbox(job_id=item.id))
        audit(self.session, spec.owner_id, "JOB_CREATED", "job", item.id, {"kind": spec.kind})
        return item

    def validate_targets(self, station_id: str | None, city_id: str | None) -> None:
        if station_id:
            require_entity(self.session, Station, station_id)
        if city_id:
            require_entity(self.session, City, city_id)


class SqlAlchemyJobReadPort:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _public(item: Job) -> dict[str, Any]:
        result = serialize(item)
        result["parameters"] = {k: v for k, v in result["parameters"].items() if k != "sha256"}
        result["result"] = {k: v for k, v in result["result"].items() if k != "sha256"}
        result["download_available"] = item.status in {"succeeded", "partial"} and bool(item.result.get("storage_key"))
        return result

    @staticmethod
    def _scope(statement: Any, owner_id: str | None, manager: bool) -> Any:
        return statement if manager else statement.where(Job.owner_id == owner_id)

    def list_jobs(self, status: str | None, owner_id: str | None, manager: bool, page_number: int, page_size: int) -> dict[str, Any]:
        statement = self._scope(select(Job), owner_id, manager)
        if status:
            statement = statement.where(Job.status == status)
        result = page(self.session, statement.order_by(Job.created_at.desc(), Job.id), page_number, page_size)
        result["items"] = [
            self._public(item)
            for item in (self.session.get(Job, row["id"]) for row in result["items"])
            if item is not None
        ]
        return result

    def get_job(self, identifier: str, owner_id: str | None, manager: bool) -> dict[str, Any] | None:
        item = self.session.scalar(self._scope(select(Job).where(Job.id == identifier), owner_id, manager))
        return self._public(item) if item else None

    def cancel_job(self, identifier: str, owner_id: str | None, manager: bool, actor_id: str) -> dict[str, Any] | None:
        item = self.session.scalar(self._scope(
            select(Job).where(Job.id == identifier).with_for_update(), owner_id, manager
        ))
        if item is None:
            return None
        if item.status not in {"queued", "running"}:
            return {"_conflict": True, "id": item.id, "status": item.status}
        item.status = "cancelled"
        item.progress_stage, item.progress_message = "cancelled", "任务已取消"
        audit(self.session, actor_id, "JOB_CANCELLED", "job", item.id)
        return self._public(item)

    def retry_job(self, identifier: str, owner_id: str | None, manager: bool, actor_id: str) -> dict[str, Any] | None:
        item = self.session.scalar(self._scope(
            select(Job).where(Job.id == identifier).with_for_update(), owner_id, manager
        ))
        if item is None:
            return None
        if item.status not in {"failed", "partial"}:
            return {"_conflict": True, "id": item.id, "status": item.status}
        if item.kind in {"collect", "train", "import"} and not manager:
            return {"_forbidden": True, "id": item.id, "status": item.status}
        spec = JobSpec(
            kind=item.kind,
            parameters=dict(item.parameters or {}),
            target_key=JobSubmissionService.fingerprint(item.kind, item.parameters or {}, actor_id),
            owner_id=actor_id,
        )
        new = SqlAlchemyJobSubmissionPort(self.session, actor_id).create(spec)
        return {"job_id": new.id, "status": new.status}

    def prepare_download(self, identifier: str, owner_id: str | None, manager: bool, regulator: bool) -> dict[str, Any] | None:
        item = self.session.scalar(self._scope(select(Job).where(Job.id == identifier), owner_id, manager))
        if item is None:
            return None
        if item.parameters.get("report") == "inspections" and not regulator:
            return {"_forbidden": True, "id": item.id}
        if item.status not in {"succeeded", "partial"} or not item.result.get("storage_key"):
            return {"_conflict": True, "id": item.id}
        audit(self.session, owner_id, "DOWNLOAD", "job", item.id)
        return {
            "id": item.id,
            "storage_key": item.result["storage_key"],
            "sha256": item.result["sha256"],
            "filename": item.result["filename"],
        }
