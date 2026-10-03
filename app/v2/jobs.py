"""Transactional job submission and owner-scoped job results."""

from typing import Any

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi import Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.core.errors import ErrorCode
from app.v2.auth import authorize, get_user
from app.v2.common import MANAGERS, REGULATORS, fail, serialize
from app.v2.domains.auth.models import User
from app.v2.contracts import Page, JobView, Accepted
from app.v2.shared.job_contracts import JobSpec
from app.v2.shared.job_contracts import JobState
from app.v2.domains.jobs.repository import SqlAlchemyJobReadPort, SqlAlchemyJobSubmissionPort
from app.v2.domains.jobs.service import JobReadService, JobSubmissionService

router = APIRouter(tags=["后台任务"], dependencies=[Depends(get_user)])
MODEL_JOBS = {"train", "forecast", "impute"}


class JobBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["collect", "evaluate", "export", "train", "forecast", "impute"]
    start: date
    end: date
    station_id: str | None = None
    city_id: str | None = None
    pollutant: Literal["PM2.5", "PM10", "SO2", "NO2", "O3", "CO", "AQI"] | None = None
    task: Literal["forecast", "imputation"] = "forecast"
    algorithm: Literal["seasonal", "lightgbm", "interpolation", "SAITS", "BRITS"] = "seasonal"
    format: Literal["csv", "xlsx"] = "csv"
    report: Literal["observations", "inspections"] = "observations"
    seed: int = Field(42, ge=0, le=2147483647)

    @model_validator(mode="after")
    def validate_range(self) -> "JobBody":
        if self.end < self.start or (self.end - self.start).days > 731:
            raise ValueError("任务时间范围应在 732 天以内")
        if self.kind == "train":
            allowed = {"seasonal", "lightgbm"} if self.task == "forecast" else {"interpolation", "SAITS", "BRITS"}
            if self.algorithm not in allowed: raise ValueError("模型算法与任务不匹配")
        return self


def public_job(item: Any) -> dict[str, Any]:
    result = serialize(item)
    result["parameters"] = {k: v for k, v in result["parameters"].items() if k != "sha256"}
    result["result"] = {k: v for k, v in result["result"].items() if k != "sha256"}
    result["download_available"] = item.status in {"succeeded", "partial"} and bool(item.result.get("storage_key"))
    return result


def enqueue(session: Any, kind: str, parameters: dict[str, Any], owner_id: str | None = None, dedupe: str | None = None) -> Any:
    """Compatibility facade for callers that still submit through ``app.v2.jobs``."""
    service = JobSubmissionService(SqlAlchemyJobSubmissionPort(session, owner_id))
    return service.submit(kind, parameters, owner_id, idempotency_key=dedupe)


@router.post("/jobs", status_code=202, response_model=Accepted)
def create_job(body: JobBody, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    if body.kind in {"collect", "train"} and user.role != "管理员": fail("仅管理员可以执行采集与训练", ErrorCode.FORBIDDEN)
    if body.kind == "export" and body.report == "inspections" and user.role not in REGULATORS: fail("无权导出监管业务", ErrorCode.FORBIDDEN)
    settings = request.app.state.settings
    if body.kind == "collect" and settings.environment == "production" and not settings.source_license_ready():
        fail("持续业务使用的来源许可尚未确认", ErrorCode.CONFIGURATION_ERROR)
    with request.app.state.db.transaction() as session:
        idempotency_key = request.headers.get("Idempotency-Key")
        submission = JobSubmissionService(SqlAlchemyJobSubmissionPort(session, user.id))
        submission.validate_targets(body.station_id, body.city_id)
        item = submission.submit(body.kind, body.model_dump(mode="json", exclude={"kind"}), user.id,
                                 idempotency_key=idempotency_key)
        return {"job_id": item.id, "status": item.status}


@router.post("/imports", status_code=202)
async def upload_import(request: Request, file: UploadFile = File(...), kind: Literal["all", "extra", "enterprises"] = Form(...),
                        user: User = Depends(authorize(*MANAGERS))) -> dict[str, Any]:
    content = await file.read(request.app.state.settings.max_upload_bytes + 1)
    if not content or len(content) > request.app.state.settings.max_upload_bytes: fail("文件为空或超过 50MB")
    if not (file.filename or "").lower().endswith(".csv"): fail("请上传 UTF-8 CSV 文件")
    key, hashed = request.app.state.store.put(content, "uploads", ".csv")
    with request.app.state.db.transaction() as session:
        item = enqueue(session, "import", {"kind": kind, "storage_key": key, "sha256": hashed}, user.id,
                       dedupe=request.headers.get("Idempotency-Key"))
        return {"job_id": item.id, "status": item.status}


@router.get("/jobs", response_model=Page[JobView])
def jobs(request: Request, status: str | None = None, page_number: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200), user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return JobReadService(SqlAlchemyJobReadPort(session)).list_jobs(
            status, user.id, user.role in MANAGERS, page_number, page_size
        )

@router.get("/jobs/{identifier}")
def job_detail(identifier: str, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        item = JobReadService(SqlAlchemyJobReadPort(session)).get_job(
            identifier, user.id, user.role in MANAGERS
        )
        if item is None:
            fail("任务不存在", ErrorCode.NOT_FOUND)
        return item

@router.post("/jobs/{identifier}/retry", status_code=202)
def retry_job(identifier: str, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        result = JobReadService(SqlAlchemyJobReadPort(session)).retry_job(
            identifier, user.id, user.role in MANAGERS, user.id
        )
        if result is None:
            fail("任务不存在", ErrorCode.NOT_FOUND)
        if result.pop("_forbidden", False):
            fail("无权重试该任务", ErrorCode.FORBIDDEN)
        if result.pop("_conflict", False):
            fail("任务当前状态不允许重试", ErrorCode.CONFLICT)
        return result


@router.post("/jobs/{identifier}/cancel")
def cancel_job(identifier: str, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        item = JobReadService(SqlAlchemyJobReadPort(session)).cancel_job(
            identifier, user.id, user.role in MANAGERS, user.id
        )
        if item is None:
            fail("任务不存在", ErrorCode.NOT_FOUND)
        if item.pop("_conflict", False):
            fail("任务当前状态不允许取消", ErrorCode.CONFLICT)
        return {"job_id": item["id"], "status": item["status"]}

@router.get("/jobs/{identifier}/download")
def download(identifier: str, request: Request, user: User = Depends(get_user)) -> Response:
    with request.app.state.db.transaction() as session:
        result = JobReadService(SqlAlchemyJobReadPort(session)).prepare_download(
            identifier, user.id, user.role in MANAGERS, user.role in REGULATORS
        )
        if result is None:
            fail("任务不存在", ErrorCode.NOT_FOUND)
        if result.pop("_forbidden", False):
            fail("无权下载该任务结果", ErrorCode.FORBIDDEN)
        if result.pop("_conflict", False):
            fail("任务结果尚未生成", ErrorCode.CONFLICT)
        path = request.app.state.store.verify(result["storage_key"], result["sha256"])
        return FileResponse(path, filename=result["filename"], headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
