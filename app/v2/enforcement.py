"""Human-reviewed leads and an optimistic-concurrency inspection workflow."""
from datetime import date
from pathlib import PurePath
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi import Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.v2.shared.http_errors import ErrorCode
from app.v2.auth import authorize, get_user
from app.v2.common import MANAGERS, REGULATORS, fail
from app.v2.domains.auth.models import User
from app.v2.contracts import Page, EnterpriseView, LeadView, InspectionView, AttachmentView
from app.v2.domains.enforcement.repository import SqlAlchemyEnforcementReadPort, SqlAlchemyEnforcementWritePort, notify, scope
from app.v2.domains.enforcement.service import EnforcementReadService, EnforcementWriteService, ListFilter

router = APIRouter(tags=["执法监督"], dependencies=[Depends(authorize(*REGULATORS))])


def _reads(request: Request, session: Any, user: Any = None) -> EnforcementReadService:
    return EnforcementReadService(SqlAlchemyEnforcementReadPort(session, user))


def _writes(request: Request, session: Any) -> EnforcementWriteService:
    return EnforcementWriteService(SqlAlchemyEnforcementWritePort(session, request.app.state.store, request.app.state.db))


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EnterpriseBody(Body):
    name: str = Field(min_length=2, max_length=200)
    credit_code: str | None = Field(None, pattern=r"^[0-9A-Z]{18}$")
    industry: str = Field("", max_length=100)
    address: str = Field("", max_length=1000)
    contact: str = Field("", max_length=200)
    version: int = 1


@router.get("/enterprises", response_model=Page[EnterpriseView])
def enterprises(request: Request, q: str = "", page_number: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _reads(request, session).list_enterprises(ListFilter(query=q, page_number=page_number, page_size=page_size))


@router.post("/enterprises", status_code=201)
def create_enterprise(body: EnterpriseBody, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        return _writes(request, session).create_enterprise(body.model_dump(exclude={"version"}), user.id)


@router.get("/enterprises/{identifier}", response_model=EnterpriseView)
def enterprise_detail(identifier: str, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _writes(request, session).enterprise_detail(identifier, user)


@router.put("/enterprises/{identifier}")
def update_enterprise(identifier: str, body: EnterpriseBody, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        return _writes(request, session).update_enterprise(identifier, body.model_dump(), user.id)


class RecordBody(Body):
    kind: Literal["outlet", "permit"]
    name: str = Field(min_length=1, max_length=200)
    details: dict[str, Any] = Field(default_factory=dict)


@router.post("/enterprises/{identifier}/records", status_code=201)
def enterprise_record(identifier: str, body: RecordBody, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        return _writes(request, session).add_enterprise_record(identifier, body.model_dump(), user.id)


class LeadBody(Body):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=5, max_length=20000)
    station_id: str | None = None
    enterprise_id: str | None = None
    evaluation_id: str | None = None
    priority: Literal["normal", "high", "urgent"] = "normal"


@router.get("/leads", response_model=Page[LeadView])
def leads(request: Request, status: str | None = None, q: str = "", page_number: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _reads(request, session).list_leads(ListFilter(query=q, status=status, page_number=page_number, page_size=page_size))


@router.post("/leads", status_code=201)
def create_lead(body: LeadBody, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        return _writes(request, session).create_lead(body.model_dump(), user.id)


class AssignBody(Body):
    assignee_id: str
    collaborators: list[str] = Field(default_factory=list, max_length=20)
    enterprise_id: str | None = None
    due_date: date
    note: str = Field(min_length=2, max_length=4000)


@router.post("/leads/{identifier}/assign", status_code=201)
def assign(identifier: str, body: AssignBody, request: Request, user: User = Depends(authorize(*MANAGERS))) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        return _writes(request, session).assign_lead(identifier, body.model_dump(), user.id)


class ReasonBody(Body):
    reason: str = Field(min_length=5, max_length=4000)


@router.post("/leads/{identifier}/claim")
def claim_lead(identifier: str, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        return _writes(request, session).claim_lead(identifier, user.id)


@router.post("/leads/{identifier}/reject")
def reject_lead(identifier: str, body: ReasonBody, request: Request, user: User = Depends(authorize(*MANAGERS))) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        return _writes(request, session).reject_lead(identifier, body.reason, user.id)


@router.get("/inspections", response_model=Page[InspectionView])
def inspections(request: Request, status: str | None = None, q: str = "", page_number: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200), user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _reads(request, session, user).list_inspections(ListFilter(query=q, status=status, page_number=page_number, page_size=page_size))


@router.get("/inspections/{identifier}", response_model=InspectionView)
def inspection_detail(identifier: str, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _writes(request, session).inspection_detail(identifier, user)


class InspectionBody(Body):
    version: int = Field(ge=1)
    facts: str = Field(max_length=50000)
    legal_references: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


@router.put("/inspections/{identifier}")
def save_inspection(identifier: str, body: InspectionBody, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    values = body.model_dump(); values["user"] = user
    with request.app.state.db.transaction() as session:
        return _writes(request, session).save_inspection(identifier, values, user.id)


class TransitionBody(Body):
    version: int = Field(ge=1)
    action: Literal["start", "rectify", "submit_rectification", "reinspect", "submit_review", "no_rectification", "approve", "return", "reopen"]
    note: str = Field(min_length=5, max_length=10000)


@router.post("/inspections/{identifier}/transition")
def transition(identifier: str, body: TransitionBody, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    values = body.model_dump(); values["user"] = user
    with request.app.state.db.transaction() as session:
        return _writes(request, session).transition(identifier, values, user.id, user.role in MANAGERS)


class RectificationBody(Body):
    requirement: str = Field(min_length=5, max_length=10000)
    due_date: date
    version: int = Field(ge=1)


@router.post("/inspections/{identifier}/rectifications", status_code=201)
def add_rectification(identifier: str, body: RectificationBody, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    values = body.model_dump(); values["user"] = user
    with request.app.state.db.transaction() as session:
        return _writes(request, session).add_rectification(identifier, values, user.id)


class RectificationUpdate(Body):
    response: str = Field(min_length=5, max_length=10000)
    review_note: str = Field("", max_length=10000)
    verified: bool = False
    version: int = Field(ge=1)


@router.put("/inspections/{identifier}/rectifications/{rectification_id}")
def update_rectification(identifier: str, rectification_id: str, body: RectificationUpdate, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    values = body.model_dump(); values["user"] = user
    with request.app.state.db.transaction() as session:
        return _writes(request, session).update_rectification(identifier, rectification_id, values, user.id)


@router.post("/attachments", status_code=201, response_model=AttachmentView)
async def upload_attachment(request: Request, file: UploadFile = File(...), inspection_id: str | None = Form(None), enterprise_id: str | None = Form(None), replaces_id: str | None = Form(None), user: User = Depends(get_user)) -> dict[str, Any]:
    content = await file.read(request.app.state.settings.max_upload_bytes + 1)
    if not content or len(content) > request.app.state.settings.max_upload_bytes:
        fail("附件为空或超过 50MB")
    with request.app.state.db.transaction() as session:
        return _writes(request, session).upload_attachment(content, PurePath((file.filename or "attachment").replace("\\", "/")).name, inspection_id, enterprise_id, replaces_id, user.id)


@router.get("/attachments/{identifier}/download")
def download_attachment(identifier: str, request: Request, user: User = Depends(get_user)) -> Response:
    with request.app.state.db.transaction() as session:
        result = _writes(request, session).prepare_attachment_download(identifier, user)
        return FileResponse(result["path"], filename=result["filename"], media_type="application/octet-stream", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
