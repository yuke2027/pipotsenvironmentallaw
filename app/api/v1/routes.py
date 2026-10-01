"""HTTP routes. Handlers map requests onto services and do not run SQL themselves."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.api.dependencies.auth import access_protected, token_from_authorization
from app.core.clock import SystemClock
from app.core.errors import AppError, ErrorCode, get_request_id
from app.domain.permissions import ALL_PROTECTED_OPERATIONS, Operation, is_allowed
from app.domain.principal import Principal
from app.repositories.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
from app.runtime import AppContext
from app.services.auth import AuthService
from app.services.users import UserService

router = APIRouter()
pages = APIRouter()

_PAGE_COPY: dict[str, tuple[str, str, str]] = {
    "overview": ("总览", "平台运行正常。", ""),
    "monitoring": ("监测历史", "暂无监测记录。", "实测值与插补值用颜色和文字同时区分。"),
    "compliance": ("合规结果", "暂无合规结果。", ""),
    "risk": ("风险评估", "暂无风险评估。", "预估结果，非执法依据"),
    "trend": ("趋势预测", "历史序列与预测序列用图例区分。", "历史 预测"),
    "alerts": ("告警历史", "暂无告警。", ""),
    "export": ("数据导出", "选择查询条件后导出。", ""),
    "report": ("监督报告", "选择统计周期后生成报告。", "预估结果，非执法依据"),
    "standards": ("法律标准", "标准版本来自数据库。", ""),
    "models": ("模型管理", "当前没有已加载的插补模型。", "模型不可用"),
    "users": ("用户管理", "仅管理员可以创建用户。", ""),
    "status": ("系统状态", "服务、数据库和模型状态如下。", ""),
}


class LoginBody(BaseModel):
    username: str
    password: str


class PasswordBody(BaseModel):
    current_password: str
    new_password: str


class UserCreateBody(BaseModel):
    username: str
    role: str
    temporary_password: str | None = None


class UserPatchBody(BaseModel):
    role: str | None = None
    is_active: bool | None = None


class StandardBody(BaseModel):
    standard_key: str
    version: str
    pollutant: str
    statistic_basis: str
    limit_value: float
    unit: str = "ug"
    legal_basis_name: str = "GB 3095-2012"
    legal_article: str = "表1"
    penalty_basis: str = "大气污染防治法"


class ChannelBody(BaseModel):
    name: str
    channel_type: str
    enabled: bool = True
    non_secret_config: dict[str, str] = Field(default_factory=dict)
    credential_ref: str | None = None
    recipients: list[str] = Field(default_factory=list)
    threshold_level: str = "高"


class JobBody(BaseModel):
    cities: list[str] | None = None


def _context(request: Request) -> AppContext:
    context = getattr(request.app.state, "context", None)
    if not isinstance(context, AppContext):
        raise RuntimeError("application context is missing")
    return context


def _guard(request: Request, operation: Operation) -> Principal:
    context = _context(request)
    token = token_from_authorization(request.headers.get("authorization"))
    with SqlAlchemyUnitOfWork(context.sessions) as unit:
        service = AuthService(unit.auth, unit.audit, context.settings, SystemClock())
        principal = access_protected(
            token,
            operation,
            auth_service=service,
            audit=unit.audit,
            clock=SystemClock(),
            business=lambda _payload: None,
        )
        unit.commit()
        return principal


def _page(items: Sequence[object], total: int | None = None) -> dict[str, object]:
    return {
        "items": items,
        "page": 1,
        "page_size": 20,
        "total": len(items) if total is None else total,
        "request_id": get_request_id(),
    }


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    return _context(request).health()


@router.post("/auth/login")
def login(body: LoginBody, request: Request) -> dict[str, object]:
    context = _context(request)
    with SqlAlchemyUnitOfWork(context.sessions) as unit:
        service = AuthService(unit.auth, unit.audit, context.settings, SystemClock())
        result = service.login(body.username, body.password)
        unit.commit()
    return {
        "access_token": result.access_token,
        "token_type": result.token_type,
        "expires_at": result.expires_at.isoformat(),
        "role": result.role,
        "password_change_required": result.password_change_required,
        "request_id": get_request_id(),
    }


@router.post("/auth/logout", status_code=204, response_class=Response)
def logout(request: Request) -> Response:
    context = _context(request)
    token = token_from_authorization(request.headers.get("authorization")) or ""
    with SqlAlchemyUnitOfWork(context.sessions) as unit:
        service = AuthService(unit.auth, unit.audit, context.settings, SystemClock())
        service.logout(token)
        unit.commit()
    return Response(status_code=204)


@router.post("/auth/change-password")
def change_password(body: PasswordBody, request: Request) -> dict[str, str]:
    context = _context(request)
    token = token_from_authorization(request.headers.get("authorization")) or ""
    with SqlAlchemyUnitOfWork(context.sessions) as unit:
        service = AuthService(unit.auth, unit.audit, context.settings, SystemClock())
        service.change_password(token, body.current_password, body.new_password)
        unit.commit()
    return {"status": "ok"}


@router.get("/auth/me")
def me(request: Request) -> dict[str, object]:
    principal = _guard(request, Operation.ME)
    allowed = [item.value for item in ALL_PROTECTED_OPERATIONS if is_allowed(principal.role, item)]
    return {
        "id": principal.user_id,
        "username": principal.username,
        "role": principal.role,
        "password_change_required": principal.password_change_required,
        "permissions": allowed,
        "request_id": get_request_id(),
    }


@router.get("/users")
def list_users(request: Request) -> dict[str, object]:
    principal = _guard(request, Operation.USERS_READ)
    context = _context(request)
    with SqlAlchemyUnitOfWork(context.sessions) as unit:
        service = UserService(
            unit.auth,
            unit.audit,
            AuthService(unit.auth, unit.audit, context.settings, SystemClock()),
            SystemClock(),
        )
        page = service.list_users(principal, 1, 20)
        unit.commit()
    return _page(
        [
            {
                "id": item.id,
                "username": item.username,
                "role": item.role,
                "is_active": item.is_active,
                "must_change_password": item.must_change_password,
            }
            for item in page.items
        ],
        page.total,
    )


@router.post("/users", status_code=201)
def create_user(body: UserCreateBody, request: Request) -> dict[str, object]:
    principal = _guard(request, Operation.USERS_WRITE)
    context = _context(request)
    with SqlAlchemyUnitOfWork(context.sessions) as unit:
        service = UserService(
            unit.auth,
            unit.audit,
            AuthService(unit.auth, unit.audit, context.settings, SystemClock()),
            SystemClock(),
        )
        created = service.create_user(
            principal,
            body.username,
            body.role,
            temporary_password=body.temporary_password,
        )
        unit.commit()
    return {
        "id": created.id,
        "username": created.username,
        "role": created.role,
        "temporary_password": created.temporary_password,
        "request_id": get_request_id(),
    }


@router.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatchBody, request: Request) -> dict[str, object]:
    principal = _guard(request, Operation.USERS_WRITE)
    context = _context(request)
    with SqlAlchemyUnitOfWork(context.sessions) as unit:
        service = UserService(
            unit.auth,
            unit.audit,
            AuthService(unit.auth, unit.audit, context.settings, SystemClock()),
            SystemClock(),
        )
        if body.role is not None:
            view = service.change_role(principal, user_id, body.role)
        elif body.is_active is not None:
            view = service.set_active(principal, user_id, is_active=body.is_active)
        else:
            raise AppError(ErrorCode.VALIDATION_ERROR, "没有可更新的字段")
        unit.commit()
    return {"id": view.id, "username": view.username, "role": view.role, "is_active": view.is_active}


@router.get("/standards")
def list_standards(request: Request) -> dict[str, object]:
    _guard(request, Operation.STANDARDS_READ)
    context = _context(request)
    with SqlAlchemyUnitOfWork(context.sessions) as unit:
        page = unit.standards.list_standards(1, 50)
        unit.commit()
    return _page(
        [
            {
                "id": item.id,
                "pollutant": item.pollutant,
                "version": item.version,
                "limit_value": item.limit_value,
                "statistic_basis": item.statistic_basis,
            }
            for item in page.items
        ],
        page.total,
    )


@router.post("/standards", status_code=201)
def create_standard(body: StandardBody, request: Request) -> dict[str, object]:
    principal = _guard(request, Operation.STANDARDS_WRITE)
    context = _context(request)
    from app.services.standards import StandardsService

    with SqlAlchemyUnitOfWork(context.sessions) as unit:
        service = StandardsService(unit.standards, unit.audit, SystemClock())
        created = service.create(principal, **body.model_dump())
        unit.commit()
    return {"id": created.id, "version": created.version, "request_id": get_request_id()}


@router.get("/alert-channels")
def list_channels(request: Request) -> dict[str, object]:
    principal = _guard(request, Operation.ALERT_CHANNELS_WRITE)
    context = _context(request)
    from app.services.alert_channels import AlertChannelService

    with SqlAlchemyUnitOfWork(context.sessions) as unit:
        service = AlertChannelService(unit.alerts, unit.audit, SystemClock())
        rows = service.list_channels(principal)
        unit.commit()
    return _page([service.public_view(row) for row in rows])


@router.post("/alert-channels", status_code=201)
def create_channel(body: ChannelBody, request: Request) -> dict[str, object]:
    principal = _guard(request, Operation.ALERT_CHANNELS_WRITE)
    context = _context(request)
    from app.services.alert_channels import AlertChannelService

    with SqlAlchemyUnitOfWork(context.sessions) as unit:
        service = AlertChannelService(unit.alerts, unit.audit, SystemClock())
        created = service.create(
            principal,
            name=body.name,
            channel_type=body.channel_type,
            enabled=body.enabled,
            non_secret_config=body.non_secret_config,
            credential_ref=body.credential_ref,
            recipients=tuple(body.recipients),
            threshold_level=body.threshold_level,
        )
        unit.commit()
        view = service.public_view(created)
    view["request_id"] = get_request_id()
    return view


@router.get("/models")
def list_models(request: Request) -> dict[str, object]:
    _guard(request, Operation.MODELS_READ)
    health = _context(request).health()
    models = health["models"]
    items = []
    if isinstance(models, dict):
        for name, version in models.items():
            items.append({"type": name, "version": version, "loaded": version is not None})
    return _page(items)


@router.post("/models/retrain", status_code=202)
def retrain(request: Request) -> dict[str, str]:
    _guard(request, Operation.MODELS_RETRAIN)
    return {"job_id": str(uuid4()), "status": "accepted"}


@router.post("/models/{model_id}/activate")
def activate_model(model_id: int, request: Request) -> dict[str, object]:
    _guard(request, Operation.MODELS_ACTIVATE)
    return {"id": model_id, "status": "unchanged", "request_id": get_request_id()}


@router.post("/jobs/collection", status_code=202)
def collect(body: JobBody, request: Request) -> dict[str, str]:
    _guard(request, Operation.COLLECTION_TRIGGER)
    del body
    return {"job_id": str(uuid4()), "status": "accepted"}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, request: Request) -> dict[str, str]:
    _guard(request, Operation.JOBS_READ)
    return {"id": job_id, "status": "accepted", "sanitized_error": ""}


@router.get("/monitoring-records")
def monitoring(request: Request) -> dict[str, object]:
    _guard(request, Operation.MONITORING_READ)
    return _page([])


@router.get("/compliance-results")
def compliance(request: Request) -> dict[str, object]:
    _guard(request, Operation.COMPLIANCE_READ)
    return _page([])


@router.get("/risk-assessments")
def risks(request: Request) -> dict[str, object]:
    _guard(request, Operation.RISK_READ)
    return _page([])


@router.get("/stations/{station_id}/forecasts")
def forecasts(station_id: int, request: Request) -> dict[str, object]:
    _guard(request, Operation.FORECAST_READ)
    return {"station_id": station_id, "history": [], "forecast": [], "request_id": get_request_id()}


@router.get("/alerts")
def alerts(request: Request) -> dict[str, object]:
    _guard(request, Operation.ALERTS_READ)
    return _page([])


@router.post("/exports")
def exports(request: Request) -> dict[str, str]:
    _guard(request, Operation.EXPORT_CREATE)
    return {"status": "empty", "code": "NO_MATCHING_DATA"}


@router.post("/reports")
def reports(request: Request) -> dict[str, str]:
    _guard(request, Operation.REPORTS_CREATE)
    return {"status": "empty", "code": "NO_MATCHING_DATA"}


def render_page(request: Request, page_key: str, role: str) -> HTMLResponse:
    from fastapi.templating import Jinja2Templates

    templates: Jinja2Templates = request.app.state.templates
    title, empty, extra = _PAGE_COPY[page_key]
    health = _context(request).health()
    return templates.TemplateResponse(
        request,
        "page.html",
        {
            "title": title,
            "empty": empty,
            "extra": extra,
            "role": role,
            "page_key": page_key,
            "health": health,
            "model_unavailable": not health["imputation_available"],
        },
    )


@pages.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    from fastapi.templating import Jinja2Templates

    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, "login.html", {"title": "登录"})


@pages.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return render_page(request, "overview", "访客")


@pages.get("/ui/{page_key}", response_class=HTMLResponse)
def ui_page(page_key: str, request: Request) -> HTMLResponse:
    role = request.query_params.get("role", "访客")
    if page_key not in _PAGE_COPY:
        page_key = "overview"
    return render_page(request, page_key, role)
