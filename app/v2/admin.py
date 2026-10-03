from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from app.core.errors import ErrorCode
from app.v2.auth import authorize, get_user, hasher
from app.v2.common import MANAGERS, REGULATORS, fail
from app.v2.domains.admin.repository import SqlAlchemyAdminReadPort, SqlAlchemyAdminWritePort, SqlAlchemyUserAdministrationPort
from app.v2.domains.admin.service import AdminReadService, AdminWriteService, NewAccount, UserAdministrationService
from app.v2.domains.admin.legacy_adapter import LegacyUserAdministrationAdapter
from app.v2.shared.errors import DomainError
from app.v2.domains.auth.models import User

router = APIRouter(tags=["系统管理"], dependencies=[Depends(get_user)])
from app.v2.contracts import Page, StandardView, LawView, UserView, ModelView


def _user_administration(request: Request, session: Any) -> UserAdministrationService | LegacyUserAdministrationAdapter:
    if not request.app.state.settings.user_administration_service_enabled:
        return LegacyUserAdministrationAdapter(session)
    return UserAdministrationService(SqlAlchemyUserAdministrationPort(session))


def _admin_reads(request: Request, session: Any) -> AdminReadService | LegacyUserAdministrationAdapter:
    if not request.app.state.settings.admin_read_service_enabled:
        return LegacyUserAdministrationAdapter(session)
    return AdminReadService(SqlAlchemyAdminReadPort(session))


def _admin_writes(request: Request, session: Any) -> AdminWriteService:
    return AdminWriteService(SqlAlchemyAdminWritePort(session, request.app.state.store))


@router.get("/people")
def people(request: Request, user: User = Depends(authorize(*REGULATORS))) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _user_administration(request, session).list_people()


@router.get("/standards", response_model=Page[StandardView])
def standards(request: Request) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _admin_reads(request, session).list_standards()


@router.get("/laws", response_model=Page[LawView])
def laws(request: Request) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _admin_reads(request, session).list_laws()


@router.get("/notifications")
def notifications(request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _admin_reads(request, session).list_notifications(user.id)


@router.post("/notifications/{identifier}/read")
def mark_read(identifier: str, request: Request, user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        item = _admin_writes(request, session).mark_notification_read(identifier, user.id)
        if item is None:
            fail("通知不存在", ErrorCode.NOT_FOUND)
        return item



class UserBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=80)
    role: Literal["管理员", "监管主管", "执法人员", "研究者"]
    password: str = Field(min_length=12, max_length=200)


@router.get("/admin/users", response_model=Page[UserView])
def users(request: Request, user: User = Depends(authorize("管理员"))) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _user_administration(request, session).list_users()


@router.post("/admin/users", status_code=201)
def create_user(body: UserBody, request: Request, user: User = Depends(authorize("管理员"))) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        account = NewAccount(**body.model_dump(exclude={"password"}), password_hash=hasher.hash(body.password))
        return _user_administration(request, session).create_user(user.id, account)


class UserUpdate(BaseModel):
    role: Literal["管理员", "监管主管", "执法人员", "研究者"]
    active: bool


@router.patch("/admin/users/{identifier}")
def update_user(identifier: str, body: UserUpdate, request: Request, user: User = Depends(authorize("管理员"))) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        try:
            return _user_administration(request, session).update_user(
                user.id, identifier, body.role, body.active
            )
        except DomainError as exc:
            fail(exc.message, ErrorCode(exc.code))


@router.get("/admin/audits")
def audits(request: Request, page_number: int = Query(1, ge=1), user: User = Depends(authorize("管理员"))) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _user_administration(request, session).list_audits(page_number)


@router.get("/admin/sources")
def sources(request: Request, user: User = Depends(authorize("管理员"))) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _admin_reads(request, session).list_sources(request.app.state.settings.source_license_ready())


@router.get("/models", response_model=Page[ModelView])
def models(request: Request) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _admin_reads(request, session).list_models()


@router.post("/models/{identifier}/activate")
def activate(identifier: str, request: Request, user: User = Depends(authorize(MANAGERS[0]))) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        result = _admin_writes(request, session).activate_model(identifier, user.id)
        if result.pop("_conflict", False):
            fail("模型未通过验证或已处于当前激活状态", ErrorCode.CONFLICT)
        return result



@router.post("/models/{task}/rollback")
def rollback(task: str, request: Request, user: User = Depends(authorize(MANAGERS[0]))) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        result = _admin_writes(request, session).rollback_model(task, user.id)
        if result.pop("_conflict", False):
            fail("没有可回滚的模型版本", ErrorCode.CONFLICT)
        return result



class LawBody(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    region: str = Field(min_length=2, max_length=80)
    effective_from: date
    effective_to: date | None = None
    source_url: str = Field(pattern=r"^https://")
    summary: str = Field(min_length=5, max_length=10000)


@router.post("/admin/laws", status_code=201)
def add_law(body: LawBody, request: Request, user: User = Depends(authorize(MANAGERS[0]))) -> dict[str, Any]:
    if body.effective_to and body.effective_to < body.effective_from:
        fail("失效日期不能早于生效日期")
    with request.app.state.db.transaction() as session:
        return _admin_writes(request, session).add_law(body.model_dump(), user.id)



class StationBody(BaseModel):
    city_id: str
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    active: bool = True


@router.put("/admin/stations/{identifier}")
def update_station(identifier: str, body: StationBody, request: Request, user: User = Depends(authorize(MANAGERS[0]))) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        return _admin_writes(request, session).update_station(identifier, body.model_dump(), user.id)



class AliasBody(BaseModel):
    external_name: str = Field(min_length=1, max_length=100)
    valid_from: date
    valid_to: date | None = None


@router.post("/admin/stations/{identifier}/aliases")
def add_alias(identifier: str, body: AliasBody, request: Request, user: User = Depends(authorize(MANAGERS[0]))) -> dict[str, Any]:
    if body.valid_to and body.valid_to < body.valid_from:
        fail("别名失效日期不能早于生效日期")
    with request.app.state.db.transaction() as session:
        result = _admin_writes(request, session).add_alias(identifier, body.model_dump(), user.id)
        if result.pop("_conflict", False):
            fail("该别名在有效期内已被使用", ErrorCode.CONFLICT)
        return result



@router.get("/admin/channels")
def channels(request: Request, user: User = Depends(authorize("管理员"))) -> dict[str, Any]:
    with request.app.state.db.sessions() as session:
        return _admin_reads(request, session).list_channels()


class ChannelBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: Literal["email", "webhook"]
    config: dict[str, Any]
    credential_ref: str | None = Field(None, pattern=r"^ESP_NOTIFY_[A-Z0-9_]+$")
    enabled: bool = False


@router.post("/admin/channels", status_code=201)
def add_channel(body: ChannelBody, request: Request, user: User = Depends(authorize(MANAGERS[0]))) -> dict[str, Any]:
    from app.v2.notifications import validate_channel
    try:
        validate_channel(body.kind, body.config)
    except ValueError as exc:
        fail(str(exc))
    if any(k.lower() in {"password", "token", "secret", "authorization"} for k in body.config):
        fail("敏感凭据必须通过 credential_ref 引用环境变量")
    with request.app.state.db.transaction() as session:
        return _admin_writes(request, session).add_channel(body.model_dump(), user.id)



class ChannelToggle(BaseModel):
    enabled: bool


@router.patch("/admin/channels/{identifier}")
def toggle_channel(identifier: str, body: ChannelToggle, request: Request, user: User = Depends(authorize(MANAGERS[0]))) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        return _admin_writes(request, session).toggle_channel(identifier, body.enabled, user.id)



class StandardBody(BaseModel):
    code: str = Field(min_length=3, max_length=80)
    pollutant: Literal["PM2.5", "PM10", "SO2", "NO2", "O3", "CO"]
    basis: Literal["daily_mean", "daily_max_8h"]
    grade: Literal["一级", "二级"] = "二级"
    region: str = "全国"
    limit_value: float = Field(gt=0)
    unit: str
    min_points: int = Field(ge=1, le=24)
    effective_from: date
    effective_to: date | None = None
    source_url: str = Field(pattern=r"^https://")
    article: str = Field(min_length=1)


class ReferenceEnd(BaseModel):
    effective_to: date
    reason: str = Field(min_length=5, max_length=1000)


@router.patch("/admin/standards/{identifier}/end")
def end_standard(identifier: str, body: ReferenceEnd, request: Request, user: User = Depends(authorize(MANAGERS[0]))) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        result = _admin_writes(request, session).end_standard(identifier, body.model_dump(), user.id)
        if result.pop("_validation", False):
            fail("标准版本结束日期不能早于生效日期")
        if result.pop("_conflict", False):
            fail("标准版本结束日期不能晚于已有失效日期")
        return result



@router.patch("/admin/laws/{identifier}/end")
def end_law(identifier: str, body: ReferenceEnd, request: Request, user: User = Depends(authorize(MANAGERS[0]))) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        result = _admin_writes(request, session).end_law(identifier, body.model_dump(), user.id)
        if result.pop("_validation", False):
            fail("法规版本结束日期不能早于生效日期")
        return result



@router.post("/admin/standards", status_code=201)
def add_standard(body: StandardBody, request: Request, user: User = Depends(authorize(MANAGERS[0]))) -> dict[str, Any]:
    from app.v2.common import UNITS
    if body.unit != UNITS[body.pollutant]:
        fail("污染物单位不符合标准")
    if body.effective_to and body.effective_to < body.effective_from:
        fail("失效日期不能早于生效日期")
    if (body.pollutant == "O3") != (body.basis == "daily_max_8h"):
        fail("臭氧必须使用日最大 8 小时口径，其他污染物使用日均值口径")
    with request.app.state.db.transaction() as session:
        result = _admin_writes(request, session).add_standard(body.model_dump(), user.id)
        if result.pop("_conflict", False):
            fail("相同地区、等级和指标的标准有效期不能重叠", ErrorCode.CONFLICT)
        return result

