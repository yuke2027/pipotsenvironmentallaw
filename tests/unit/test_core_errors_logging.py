"""Boundary tests for uniform errors and secret redaction."""

from __future__ import annotations

import logging
from io import StringIO
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import (
    AppError,
    ErrorCode,
    ErrorDetail,
    RequestIdMiddleware,
    error_payload,
    register_error_handlers,
    request_id_context,
)
from app.core.logging import REDACTED, SensitiveDataFilter, sanitize_audit_details, sanitize_value


@pytest.mark.unit
def test_error_payload_uses_mapped_status_details_and_request_id() -> None:
    """Known errors retain a stable code, mapped status, and field detail."""
    error = AppError(
        ErrorCode.INVALID_TIME_RANGE,
        "开始时间不能晚于结束时间",
        details=[ErrorDetail(field="start_time", reason="must_be_lte_end_time")],
    )

    with request_id_context("b55f281b-9696-4496-905b-950e8dbb4c6b"):
        payload = error_payload(error)

    assert error.status_code == 400
    assert payload == {
        "error": {
            "code": "INVALID_TIME_RANGE",
            "message": "开始时间不能晚于结束时间",
            "details": [{"field": "start_time", "reason": "must_be_lte_end_time"}],
        },
        "request_id": "b55f281b-9696-4496-905b-950e8dbb4c6b",
    }


@pytest.mark.unit
def test_error_handlers_add_uuid_request_id_and_normalize_validation_response() -> None:
    """HTTP integration returns the documented envelope and correlation header."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/time-range")
    async def invalid_time_range() -> None:
        raise AppError(
            ErrorCode.INVALID_TIME_RANGE,
            "开始时间不能晚于结束时间",
            details=[{"field": "start_time", "reason": "must_be_lte_end_time"}],
        )

    client = TestClient(app)
    response = client.get("/time-range")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_TIME_RANGE"
    assert response.json()["error"]["details"] == [
        {"field": "start_time", "reason": "must_be_lte_end_time"}
    ]
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    UUID(response.json()["request_id"])


@pytest.mark.unit
def test_recursive_sanitization_redacts_nested_lists_exception_text_and_audit_details() -> None:
    """Secrets cannot survive nested payload, exception, or audit sanitization."""
    secret_values = ("db-password", "api-token", "Bearer credential", "smtp-secret", "hook-secret")
    payload = {
        "password": "db-password",
        "children": [
            {"token": "api-token"},
            {"authorization": "Bearer credential"},
            {"smtp_secret": "smtp-secret", "webhook_secret": "hook-secret"},
        ],
        "failure": RuntimeError(
            "SMTP password=db-password; token=api-token; webhook_secret=hook-secret"
        ),
    }

    sanitized = sanitize_value(payload)
    audit = sanitize_audit_details({"action": "notify", "details": payload})

    assert sanitized["password"] == REDACTED
    assert sanitized["children"] == [
        {"token": REDACTED},
        {"authorization": REDACTED},
        {"smtp_secret": REDACTED, "webhook_secret": REDACTED},
    ]
    assert "db-password" not in sanitized["failure"]
    assert "api-token" not in sanitized["failure"]
    assert "hook-secret" not in sanitized["failure"]
    assert audit["details"]["children"][2]["smtp_secret"] == REDACTED
    assert all(secret not in repr((sanitized, audit)) for secret in secret_values)


@pytest.mark.unit
def test_logging_filter_redacts_message_exception_and_structured_audit_extra() -> None:
    """Filter protects rendered log output, including exception and audit metadata."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(SensitiveDataFilter())
    logger = logging.getLogger("tests.sensitive-data-filter")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    try:
        try:
            raise RuntimeError("authorization: Bearer bearer-token; smtp_secret=mail-secret")
        except RuntimeError:
            logger.exception(
                "delivery failed token=%s",
                "message-token",
                extra={"audit_details": {"webhook_secret": "hook-secret"}},
            )
    finally:
        logger.handlers = []
        logger.propagate = True

    output = stream.getvalue()
    for secret in ("bearer-token", "mail-secret", "message-token", "hook-secret"):
        assert secret not in output
    assert REDACTED in output


@pytest.mark.unit
def test_request_id_middleware_reuses_valid_uuid_and_rejects_untrusted_header() -> None:
    """Middleware preserves valid correlation IDs and replaces invalid client input."""
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    supplied_id = "b55f281b-9696-4496-905b-950e8dbb4c6b"
    assert client.get("/ok", headers={"X-Request-ID": supplied_id}).headers[
        "X-Request-ID"
    ] == supplied_id
    replacement_id = client.get("/ok", headers={"X-Request-ID": "not-a-uuid"}).headers[
        "X-Request-ID"
    ]
    UUID(replacement_id)
    assert replacement_id != "not-a-uuid"
