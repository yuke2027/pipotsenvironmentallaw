"""Authenticate before business work, then authorize against the role matrix.

Unauthenticated callers fail with 401 before a business callable runs. A role
that is outside the matrix fails with 403, writes ``AUTHORIZATION_DENIED``,
and also skips the business callable.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from app.core.clock import Clock
from app.core.errors import AppError, ErrorCode, get_request_id
from app.domain.audit_actions import ACTION_AUTHORIZATION_DENIED
from app.domain.permissions import FIRST_LOGIN_OPERATIONS, Operation, is_allowed
from app.domain.principal import Principal
from app.domain.records import AuditDraft
from app.domain.repositories import AuditRepository
from app.services.auth import AuthService


def token_from_authorization(header: str | None) -> str | None:
    """Return the bearer token, or None when the header is missing or malformed."""

    if header is None:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or value.strip() == "":
        return None
    return value.strip()


def authorize_operation(
    *,
    role: str,
    operation: Operation,
    user_id: int | None,
    password_change_required: bool,
    payload: Mapping[str, str],
    audit: AuditRepository,
    clock: Clock,
    business: Callable[[Mapping[str, str]], None],
) -> None:
    """Apply the matrix. Denial audits and does not call ``business``."""

    if password_change_required and operation not in FIRST_LOGIN_OPERATIONS:
        _deny(audit, clock, user_id, role, operation)
        raise AppError(ErrorCode.FORBIDDEN, "权限不足")
    if not is_allowed(role, operation):
        _deny(audit, clock, user_id, role, operation)
        raise AppError(ErrorCode.FORBIDDEN, "权限不足")
    business(payload)


def access_protected(
    token: str | None,
    operation: Operation,
    *,
    auth_service: AuthService,
    audit: AuditRepository,
    clock: Clock,
    business: Callable[[Mapping[str, str]], None],
    payload: Mapping[str, str] | None = None,
) -> Principal:
    """Authenticate, authorize, then run business work.

    Invalid, expired, revoked, and disabled tokens raise 401 before ``business``.
    """

    principal = auth_service.authenticate(token)
    authorize_operation(
        role=principal.role,
        operation=operation,
        user_id=principal.user_id,
        password_change_required=principal.password_change_required,
        payload={} if payload is None else payload,
        audit=audit,
        clock=clock,
        business=business,
    )
    return principal


def _deny(
    audit: AuditRepository,
    clock: Clock,
    user_id: int | None,
    role: str,
    operation: Operation,
) -> None:
    audit.append(
        AuditDraft(
            user_id=user_id,
            action=ACTION_AUTHORIZATION_DENIED,
            object_type="operation",
            object_id=operation.value,
            request_id=get_request_id(),
            result="DENIED",
            details={"role": role, "operation": operation.value},
            ip_hash=None,
            created_at=clock.now(),
        )
    )
