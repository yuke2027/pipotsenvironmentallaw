"""Property 21: forecast points are complete, bounded, and warnings follow the threshold."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.forecasting import build_forecast

_END = datetime(2026, 5, 1, tzinfo=timezone.utc)


@given(
    horizon=st.integers(min_value=1, max_value=6),
    threshold=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
    level=st.floats(min_value=0, max_value=40, allow_nan=False, allow_infinity=False),
    limit=st.floats(min_value=1, max_value=80, allow_nan=False, allow_infinity=False),
)
@pytest.mark.property
def test_property_21_forecast_points_are_bounded(
    horizon: int,
    threshold: float,
    level: float,
    limit: float,
) -> None:
    """Every future hour has a finite non-negative value and a warning exactly at the threshold.

    **Feature: environmental-supervision-platform, Property 21: 预测输出完整有界**
    **Property 21：预测输出完整有界**
    **Validates: Requirements 9.1, 9.2, 9.3, 9.6**
    """

    history = {"PM2.5": [level] * 30, "PM10": [level] * 30}
    bundle = build_forecast(
        history,
        _END,
        generated_at=_END,
        horizon_hours=horizon,
        limits={"PM2.5": limit, "PM10": limit},
        warning_probability=threshold,
        min_samples=24,
    )
    assert bundle.status == "SUCCESS"
    assert bundle.method
    assert bundle.generated_at == _END
    assert len(bundle.points) == horizon * 2
    for point in bundle.points:
        assert point.predicted_value >= 0
        assert point.predicted_value == point.predicted_value
        assert 0 <= point.exceedance_probability <= 1
        assert point.is_warning is (point.exceedance_probability >= threshold)
