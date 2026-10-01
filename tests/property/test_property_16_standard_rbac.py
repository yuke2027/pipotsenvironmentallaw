"""Property 16: supervisors and researchers cannot change standards."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.clock import FrozenClock
from app.core.errors import AppError
from app.domain.audit_actions import ACTION_AUTHORIZATION_DENIED
from app.domain.principal import Principal
from app.services.standards import StandardsService
from tests.property.test_property_15_standard_versioning import _Audit, _Standards

_WHEN = datetime(2026, 1, 1, tzinfo=timezone.utc)


@given(
    role=st.sampled_from(("监管人员", "研究者")),
    operation=st.sampled_from(("create", "replace", "deactivate")),
    limit=st.floats(min_value=1, max_value=80, allow_nan=False, allow_infinity=False),
)
@pytest.mark.property
def test_property_16_non_admins_cannot_change_standards(role: str, operation: str, limit: float) -> None:
    """A non-admin write is 403, leaves standards unchanged, and is audited.

    **Feature: environmental-supervision-platform, Property 16: 非管理员不能改变标准**
    **Property 16：非管理员不能改变标准**
    **Validates: Requirements 6.8, 13.10**
    """

    standards = _Standards()
    audit = _Audit()
    service = StandardsService(standards, audit, FrozenClock(_WHEN))  # type: ignore[arg-type]
    actor = Principal(2, "user", role, False, "jti", _WHEN)
    before = dict(standards.rows)
    with pytest.raises(AppError) as denied:
        if operation == "create":
            service.create(
                actor,
                standard_key="PM25",
                version="1",
                pollutant="PM2.5",
                statistic_basis="24h_mean",
                limit_value=limit,
                unit="ug",
                legal_basis_name="GB",
                legal_article="article",
                penalty_basis="law",
            )
        elif operation == "replace":
            service.replace(
                actor,
                1,
                expected_version="1",
                limit_value=limit,
                statistic_basis="24h_mean",
                version="2",
                unit="ug",
                legal_basis_name="GB",
                legal_article="article",
                penalty_basis="law",
            )
        else:
            service.deactivate(actor, 1, expected_version="1")
    assert denied.value.status_code == 403
    assert standards.rows == before
    assert audit.actions == [ACTION_AUTHORIZATION_DENIED]
