from datetime import date, datetime
from typing import Any, NoReturn, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode, get_request_id
from app.core.logging import sanitize_value
from app.v2.domains.auth.models import Audit

ROLES = ("管理员", "监管主管", "执法人员", "研究者")
MANAGERS = ("管理员", "监管主管")
REGULATORS = ("管理员", "监管主管", "执法人员")
POLLUTANTS = ("PM2.5", "PM10", "SO2", "NO2", "O3", "CO")
UNITS = {**{p: "μg/m³" for p in POLLUTANTS}, "CO": "mg/m³", "AQI": "指数"}

_ModelT = TypeVar("_ModelT")


def fail(message: str, code: ErrorCode = ErrorCode.VALIDATION_ERROR) -> NoReturn:
    raise AppError(code, message)


def serialize(obj: Any, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    hidden = {"password_hash", "token_hash", "csrf_hash", "storage_key", *exclude}
    def visible(value: Any) -> Any:
        if isinstance(value, dict): return {k: visible(v) for k, v in value.items() if k not in hidden}
        if isinstance(value, list): return [visible(v) for v in value]
        return value.isoformat() if isinstance(value, (datetime, date)) else value
    result: dict[str, Any] = {}
    for attribute in inspect(type(obj)).column_attrs:
        key = attribute.key
        if key in hidden:
            continue
        value = getattr(obj, key)
        result[key] = visible(value)
    return result


def page(session: Session, statement: Select[Any], page_number: int = 1, page_size: int = 20) -> dict[str, Any]:
    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    items = session.scalars(statement.offset((page_number - 1) * page_size).limit(page_size)).all()
    return {"items": [serialize(item) for item in items], "page": page_number,
            "page_size": page_size, "total": total, "request_id": get_request_id()}


def audit(session: Session, actor_id: str | None, action: str, kind: str,
          object_id: str | None = None, detail: dict[str, Any] | None = None) -> None:
    session.add(Audit(actor_id=actor_id, action=action, object_type=kind,
                      object_id=object_id, detail=sanitize_value(detail or {}), request_id=get_request_id()))


def require_entity(session: Session, model: type[_ModelT], entity_id: str) -> _ModelT:
    entity = session.get(model, entity_id)
    if entity is None:
        fail("记录不存在", ErrorCode.NOT_FOUND)
    return entity
