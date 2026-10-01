"""Property 18: too few points produce no compliance conclusion and no follow-up."""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.compliance import evaluate_group
from tests.support.legal_snapshots import legal_snapshot


@given(
    threshold=st.integers(min_value=1, max_value=8),
    count=st.integers(min_value=0, max_value=7),
)
@pytest.mark.property
def test_property_18_insufficient_groups_skip_risk_and_alerts(threshold: int, count: int) -> None:
    """Below the point threshold the conclusion is empty and follow-ups are not called.

    **Feature: environmental-supervision-platform, Property 18: 数据不足无合规结论**
    **Property 18：数据不足无合规结论**
    **Validates: Requirements 7.5, 15.2**
    """

    if count >= threshold:
        count = threshold - 1
    risk_calls: list[object] = []
    alert_calls: list[object] = []
    outcomes = evaluate_group(
        station_id="S1",
        local_date=date(2026, 1, 3),
        values={"PM2.5": [1.0] * count, "PM10": [1.0] * count, "AQI": [1.0] * count},
        snapshot=legal_snapshot({"PM2.5": 75, "PM10": 150, "AQI": 100}),
        min_points=threshold,
        risk=risk_calls.append,
        alert=alert_calls.append,
    )
    assert outcomes
    assert all(outcome.status == "INSUFFICIENT" for outcome in outcomes)
    assert all(outcome.is_compliant is None for outcome in outcomes)
    assert risk_calls == []
    assert alert_calls == []
