"""Property 28: issued JWTs match configuration and bad tokens never reach business code."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.api.dependencies.auth import access_protected
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.domain.enums import USER_ROLES
from app.domain.permissions import Operation
from app.domain.records import UserDraft
from app.services.auth import AuthService
from tests.support.auth_factory import TEST_JWT_SECRET, auth_settings, memory_service
from app.core.security import hash_password


@given(
    role=st.sampled_from(USER_ROLES),
    ttl=st.integers(min_value=60, max_value=24 * 60 * 60),
    defect=st.sampled_from(("valid", "missing", "tampered", "expired", "revoked", "disabled")),
)
@pytest.mark.property
def test_property_28_jwt_issue_and_reject(role: str, ttl: int, defect: str) -> None:
    """Valid tokens expose configured claims; every other token is 401 before business work.

    **Feature: environmental-supervision-platform, Property 28: JWT 签发与拒绝**
    **Property 28：JWT 签发与拒绝**
    **Validates: Requirements 13.3, 13.4, 13.7, 13.8, 15.5**
    """

    service, auth, audit, clock = memory_service(settings=auth_settings(jwt_expire_seconds=ttl))
    user_id = auth.add_user(
        UserDraft(
            username=f"user-{role}",
            password_hash=hash_password("right-password"),
            role=role,
            is_active=True,
            must_change_password=False,
            created_at=clock.now(),
        )
    )
    logged_in = service.login(f"user-{role}", "right-password")
    claims = decode_access_token(logged_in.access_token, TEST_JWT_SECRET, clock.now())
    assert claims.sub == str(user_id)
    assert claims.role == role
    assert claims.exp - claims.iat == ttl
    assert claims.jti
    assert claims.password_change_required is False

    token: str | None = logged_in.access_token
    if defect == "missing":
        token = None
    elif defect == "tampered":
        header, payload, signature = logged_in.access_token.split(".")
        token = f"{header}.{payload}.{'a' if signature[0] != 'a' else 'b'}{signature[1:]}"
    elif defect == "expired":
        clock.advance(ttl)
    elif defect == "revoked":
        service.logout(logged_in.access_token)
    elif defect == "disabled":
        auth.update_account(user_id, role=None, is_active=False, updated_at=clock.now())

    calls: list[Mapping[str, str]] = []

    def business(payload: Mapping[str, str]) -> None:
        calls.append(payload)

    if defect == "valid":
        access_protected(
            token,
            Operation.MONITORING_READ,
            auth_service=service,
            audit=audit,
            clock=clock,
            business=business,
        )
        assert calls == [{}]
        return

    with pytest.raises(AppError) as caught:
        access_protected(
            token,
            Operation.MONITORING_READ,
            auth_service=service,
            audit=audit,
            clock=clock,
            business=business,
        )
    assert caught.value.status_code == 401
    assert calls == []
