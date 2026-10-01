"""Property 31: authorization matches the role matrix and denial is audited."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.api.dependencies.auth import authorize_operation
from app.core.errors import AppError
from app.domain.audit_actions import ACTION_AUTHORIZATION_DENIED
from app.domain.enums import USER_ROLES
from app.domain.permissions import ALL_PROTECTED_OPERATIONS, Operation, is_allowed
from tests.support.auth_factory import frozen_clock
from tests.support.memory_auth import MemoryAuditRepository


@given(
    role=st.sampled_from(USER_ROLES),
    operation=st.sampled_from(ALL_PROTECTED_OPERATIONS),
    marker=st.text(min_size=0, max_size=12),
)
@pytest.mark.property
def test_property_31_role_matrix_and_denial_audit(role: str, operation: Operation, marker: str) -> None:
    """Allowed calls run; denied calls do not write business state and are audited.

    **Feature: environmental-supervision-platform, Property 31: 角色权限矩阵与拒绝审计**
    **Property 31：角色权限矩阵与拒绝审计**
    **Validates: Requirements 13.1, 13.9, 13.10, 13.12, 13.13, 15.5**
    """

    audit = MemoryAuditRepository()
    writes: list[Mapping[str, str]] = []

    def business(payload: Mapping[str, str]) -> None:
        writes.append(payload)

    payload = {"marker": marker}
    allowed = is_allowed(role, operation)
    if allowed:
        authorize_operation(
            role=role,
            operation=operation,
            user_id=4,
            password_change_required=False,
            payload=payload,
            audit=audit,
            clock=frozen_clock(),
            business=business,
        )
        assert writes == [payload]
        assert all(entry.action != ACTION_AUTHORIZATION_DENIED for entry in audit.entries)
        return

    with pytest.raises(AppError) as denied:
        authorize_operation(
            role=role,
            operation=operation,
            user_id=4,
            password_change_required=False,
            payload=payload,
            audit=audit,
            clock=frozen_clock(),
            business=business,
        )
    assert denied.value.status_code == 403
    assert writes == []
    assert [entry.action for entry in audit.entries] == [ACTION_AUTHORIZATION_DENIED]
    assert audit.entries[0].result == "DENIED"
