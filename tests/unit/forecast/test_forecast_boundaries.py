"""Forecast boundary examples."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.forecasting import build_forecast

_END = datetime(2026, 5, 1, 3, tzinfo=timezone.utc)


def test_non_positive_horizon_is_rejected_and_short_history_is_skipped() -> None:
    history = {"PM2.5": [1.0] * 23, "PM10": [1.0] * 23}
    with pytest.raises(ValueError):
        build_forecast(
            history,
            _END,
            generated_at=_END,
            horizon_hours=0,
            limits={"PM2.5": 75, "PM10": 150},
            warning_probability=0.5,
            min_samples=24,
        )
    skipped = build_forecast(
        history,
        _END,
        generated_at=_END,
        horizon_hours=2,
        limits={"PM2.5": 75, "PM10": 150},
        warning_probability=0.5,
        min_samples=24,
    )
    assert skipped.status == "SKIPPED"
    assert skipped.skip_reason
    assert skipped.points == ()


def test_threshold_equality_warns_and_hours_stay_on_the_clock() -> None:
    bundle = build_forecast(
        {"PM2.5": [200.0] * 24, "PM10": [1.0] * 24},
        _END,
        generated_at=_END,
        horizon_hours=2,
        limits={"PM2.5": 1, "PM10": 1000},
        warning_probability=0.5,
        min_samples=24,
    )
    pm25 = [point for point in bundle.points if point.pollutant == "PM2.5"]
    assert pm25[0].forecast_at == _END + timedelta(hours=1)
    assert pm25[0].forecast_at.minute == 0
    assert all(point.is_warning is (point.exceedance_probability >= 0.5) for point in bundle.points)
