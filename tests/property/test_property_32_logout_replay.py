"""Property 32: logout revokes a token, and auth events are audited."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.api.dependencies.auth import access_protected
from app.core.errors import AppError
from app.core.security import hash_password
from app.domain.audit_actions import ACTION_CHANGE_PASSWORD, ACTION_LOGIN, ACTION_LOGOUT
from app.domain.permissions import ALL_PROTECTED_OPERATIONS, Operation
from app.domain.records import UserDraft
from tests.support.auth_factory import memory_service


@given(
    operation=st.sampled_from(ALL_PROTECTED_OPERATIONS),
    new_password=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=8,
        max_size=16,
    ).filter(lambda value: value != "right-password"),
)
@pytest.mark.property
def test_property_32_logout_blocks_replay(operation: Operation, new_password: str) -> None:
    """A logged-out jti is 401 on every protected operation, and auth events are audited.

    **Feature: environmental-supervision-platform, Property 32: 登出阻止重放**
    **Property 32：登出阻止重放**
    **Validates: Requirements 13.14, 13.16**
    """

    service, auth, audit, clock = memory_service()
    auth.add_user(
        UserDraft(
            username="replay-user",
            password_hash=hash_password("right-password"),
            role="管理员",
            is_active=True,
            must_change_password=False,
            created_at=clock.now(),
        )
    )
    first = service.login("replay-user", "right-password")
    service.logout(first.access_token)
    _assert_rejected(service, audit, clock, first.access_token, operation)

    second = service.login("replay-user", "right-password")
    service.change_password(second.access_token, "right-password", new_password)
    _assert_rejected(service, audit, clock, second.access_token, operation)
    service.login("replay-user", new_password)
    actions = {entry.action for entry in audit.entries}
    assert ACTION_LOGIN in actions
    assert ACTION_LOGOUT in actions
    assert ACTION_CHANGE_PASSWORD in actions


def _assert_rejected(
    service: object,
    audit: object,
    clock: object,
    token: str,
    operation: Operation,
) -> None:
    from app.core.clock import FrozenClock
    from app.services.auth import AuthService
    from tests.support.memory_auth import MemoryAuditRepository

    if not isinstance(service, AuthService) or not isinstance(audit, MemoryAuditRepository):
        raise TypeError("expected memory auth collaborators")
    if not isinstance(clock, FrozenClock):
        raise TypeError("expected FrozenClock")
    calls: list[Mapping[str, str]] = []

    def business(payload: Mapping[str, str]) -> None:
        calls.append(payload)

    with pytest.raises(AppError) as caught:
        access_protected(
            token,
            operation,
            auth_service=service,
            audit=audit,
            clock=clock,
            business=business,
        )
    assert caught.value.status_code == 401
    assert calls == []
