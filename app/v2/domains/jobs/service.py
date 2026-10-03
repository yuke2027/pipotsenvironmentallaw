"""Application service for submitting jobs.

The service owns the job fingerprint and idempotency rules.  It deliberately
knows nothing about FastAPI or SQLAlchemy; persistence is supplied by a small
port implemented by the HTTP adapter.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from app.v2.shared.job_contracts import JobSpec


class JobRecord(Protocol):
    id: Any
    status: Any


class JobSubmissionPort(Protocol):
    def find_existing(self, target_key: str, include_finished: bool) -> JobRecord | None: ...

    def create(self, spec: JobSpec) -> JobRecord: ...

    def validate_targets(self, station_id: str | None, city_id: str | None) -> None: ...


class JobSubmissionService:
    """Validate and submit a job through an injected persistence adapter."""

    def __init__(self, port: JobSubmissionPort):
        self.port = port

    @staticmethod
    def fingerprint(kind: str, parameters: dict[str, Any], owner_id: str | None,
                    idempotency_key: str | None = None) -> str:
        if idempotency_key:
            return idempotency_key
        payload = json.dumps([kind, parameters, owner_id], sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def submit(self, kind: str, parameters: dict[str, Any], owner_id: str | None = None,
               idempotency_key: str | None = None) -> JobRecord:
        target_key = self.fingerprint(kind, parameters, owner_id, idempotency_key)
        spec = JobSpec(kind=kind, parameters=parameters, target_key=target_key,
                       owner_id=owner_id, idempotency_key=idempotency_key)
        existing = self.port.find_existing(target_key, include_finished=bool(idempotency_key))
        return existing or self.port.create(spec)

    def validate_targets(self, station_id: str | None, city_id: str | None) -> None:
        validator = getattr(self.port, "validate_targets", None)
        if validator is not None:
            validator(station_id, city_id)


class JobReadPort(Protocol):
    def list_jobs(self, status: str | None, owner_id: str, manager: bool,
                  page_number: int, page_size: int) -> dict[str, Any]: ...

    def get_job(self, identifier: str, owner_id: str, manager: bool) -> dict[str, Any] | None: ...

    def cancel_job(self, identifier: str, owner_id: str, manager: bool,
                   actor_id: str) -> dict[str, Any] | None: ...

    def retry_job(self, identifier: str, owner_id: str, manager: bool,
                  actor_id: str) -> dict[str, Any] | None: ...

    def prepare_download(self, identifier: str, owner_id: str, manager: bool,
                         regulator: bool) -> dict[str, Any] | None: ...


class JobReadService:
    """Read and lifecycle use cases for owner-scoped jobs."""

    def __init__(self, port: JobReadPort):
        self.port = port

    def list_jobs(self, status: str | None, owner_id: str, manager: bool,
                  page_number: int, page_size: int) -> dict[str, Any]:
        return self.port.list_jobs(status, owner_id, manager, page_number, page_size)

    def get_job(self, identifier: str, owner_id: str, manager: bool) -> dict[str, Any] | None:
        return self.port.get_job(identifier, owner_id, manager)

    def cancel_job(self, identifier: str, owner_id: str, manager: bool,
                   actor_id: str) -> dict[str, Any] | None:
        return self.port.cancel_job(identifier, owner_id, manager, actor_id)

    def retry_job(self, identifier: str, owner_id: str, manager: bool,
                  actor_id: str) -> dict[str, Any] | None:
        return self.port.retry_job(identifier, owner_id, manager, actor_id)

    def prepare_download(self, identifier: str, owner_id: str, manager: bool,
                         regulator: bool) -> dict[str, Any] | None:
        return self.port.prepare_download(identifier, owner_id, manager, regulator)
