"""Framework-light, uniform API errors with request correlation support."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .logging import sanitize_text, sanitize_value

logger = logging.getLogger(__name__)

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class ErrorCode(str, Enum):
    """Stable external error codes used by API clients."""

    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_TIME_RANGE = "INVALID_TIME_RANGE"
    TIME_RANGE_EXCEEDS_LIMIT = "TIME_RANGE_EXCEEDS_LIMIT"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    NO_MATCHING_DATA = "NO_MATCHING_DATA"
    CHINESE_FONT_UNAVAILABLE = "CHINESE_FONT_UNAVAILABLE"


HTTP_STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.INVALID_TIME_RANGE: 400,
    ErrorCode.TIME_RANGE_EXCEEDS_LIMIT: 400,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.INVALID_CREDENTIALS: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    ErrorCode.CONFIGURATION_ERROR: 503,
    ErrorCode.NO_MATCHING_DATA: 404,
    ErrorCode.CHINESE_FONT_UNAVAILABLE: 503,
}


@dataclass(frozen=True)
class ErrorDetail:
    """A machine-readable explanation of one invalid request field."""

    field: str
    reason: str


class AppError(Exception):
    """Known application failure rendered with the platform error envelope."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: Sequence[ErrorDetail | Mapping[str, Any]] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = tuple(details or ())
        self.status_code = status_code if status_code is not None else HTTP_STATUS_BY_CODE[code]
        super().__init__(message)


def new_request_id() -> str:
    """Create a UUID request correlation identifier."""
    return str(uuid4())


def set_request_id(request_id: str | None = None) -> Token[str | None]:
    """Set the current request identifier, generating a UUID when absent."""
    return _request_id.set(request_id or new_request_id())


def get_request_id() -> str:
    """Get the current request identifier, creating one for non-HTTP callers."""
    request_id = _request_id.get()
    if request_id is None:
        request_id = new_request_id()
        _request_id.set(request_id)
    return request_id


@contextmanager
def request_id_context(request_id: str | None = None) -> Iterator[str]:
    """Temporarily bind a request ID for services, CLIs, and tests."""
    token = set_request_id(request_id)
    try:
        yield get_request_id()
    finally:
        _request_id.reset(token)


def _serialize_detail(detail: ErrorDetail | Mapping[str, Any]) -> dict[str, Any]:
    raw = asdict(detail) if isinstance(detail, ErrorDetail) else dict(detail)
    return dict(sanitize_value(raw))


def error_payload(error: AppError, *, request_id: str | None = None) -> dict[str, Any]:
    """Build the documented API error envelope without leaking sensitive values."""
    return {
        "error": {
            "code": error.code.value,
            "message": sanitize_text(error.message),
            "details": [_serialize_detail(detail) for detail in error.details],
        },
        "request_id": request_id or get_request_id(),
    }


def _request_id_from_request(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) else get_request_id()


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Render a known application error as the uniform JSON response."""
    request_id = _request_id_from_request(request)
    response = JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc, request_id=request_id),
    )
    response.headers["X-Request-ID"] = request_id
    return response


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Safely map unexpected exceptions to an unavailable-service response."""
    request_id = _request_id_from_request(request)
    logger.error(
        "Unhandled platform exception",
        extra={"request_id": request_id, "exception": sanitize_value(exc)},
    )
    error = AppError(ErrorCode.SERVICE_UNAVAILABLE, "服务暂时不可用")
    response = JSONResponse(
        status_code=error.status_code,
        content=error_payload(error, request_id=request_id),
    )
    response.headers["X-Request-ID"] = request_id
    return response


def _trusted_request_id(value: str | None) -> str:
    """Accept only UUID-shaped incoming IDs so correlation IDs remain predictable."""
    if value is None:
        return new_request_id()
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        return new_request_id()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind a request UUID and expose it to clients through a response header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _trusted_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        with request_id_context(request_id):
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def register_error_handlers(app: Any) -> None:
    """Register the minimal FastAPI integration without requiring application config."""
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
