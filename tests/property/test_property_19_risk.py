"""Property 19: risk output is complete, bounded, and compliant scores are 20."""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.compliance import evaluate_group
from app.services.risk import DISCLAIMER, assess_outcome
from tests.support.legal_snapshots import legal_snapshot


@given(
    value=st.floats(min_value=0, max_value=400, allow_nan=False, allow_infinity=False),
    limit=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False),
)
@pytest.mark.property
def test_property_19_risk_is_bounded_and_compliant_scores_are_20(value: float, limit: float) -> None:
    """Persisted scores stay in range, fields are present, and compliant output is 20.

    **Feature: environmental-supervision-platform, Property 19: 风险评估完整且有界**
    **Property 19：风险评估完整且有界**
    **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 15.3, 16.3**
    """

    snapshot = legal_snapshot({"PM2.5": limit, "PM10": limit, "AQI": limit})
    outcomes = evaluate_group(
        station_id="S1",
        local_date=date(2026, 2, 1),
        values={"PM2.5": [value], "PM10": [value], "AQI": [value]},
        snapshot=snapshot,
        min_points=1,
    )
    views = [assess_outcome(outcome, snapshot) for outcome in outcomes]
    keys = [view.compliance_key for view in views]
    assert len(keys) == len(set(keys))
    for outcome, view in zip(outcomes, views):
        assert 0 <= view.risk_score <= 100
        assert view.risk_level
        assert view.legal_consequences
        assert view.recommended_actions
        assert view.penalty_estimate_text
        assert view.disclaimer == DISCLAIMER
        if outcome.is_compliant:
            assert view.risk_score == 20
