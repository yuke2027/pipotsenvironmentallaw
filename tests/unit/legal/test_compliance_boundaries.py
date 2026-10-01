"""Boundary examples for compliance and the four risk bands."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.compliance import evaluate_group
from app.services.risk import assess_outcome
from tests.support.legal_snapshots import legal_snapshot

_DAY = date(2026, 4, 1)


def _one(value: float, limit: float = 75) -> object:
    outcomes = evaluate_group(
        station_id="S1",
        local_date=_DAY,
        values={"PM2.5": [value], "PM10": [value], "AQI": [value]},
        snapshot=legal_snapshot({"PM2.5": limit, "PM10": limit, "AQI": limit}),
        min_points=1,
    )
    return outcomes[0]


@pytest.mark.unit
def test_compliance_equal_below_above_and_insufficient() -> None:
    assert _one(75).is_compliant is True  # type: ignore[attr-defined]
    assert _one(10).is_compliant is True  # type: ignore[attr-defined]
    assert _one(90).is_compliant is False  # type: ignore[attr-defined]
    short = evaluate_group(
        station_id="S1",
        local_date=_DAY,
        values={"PM2.5": [1.0], "PM10": [], "AQI": []},
        snapshot=legal_snapshot({"PM2.5": 75, "PM10": 150, "AQI": 100}),
        min_points=2,
    )
    assert all(item.status == "INSUFFICIENT" and item.is_compliant is None for item in short)


@pytest.mark.unit
def test_four_risk_bands_and_score_cap() -> None:
    snapshot = legal_snapshot({"PM2.5": 100, "PM10": 100, "AQI": 100})
    expected = {0.5: "低", 0.9: "中", 1.2: "高", 3.0: "严重"}
    for ratio, level in expected.items():
        outcomes = evaluate_group(
            station_id="S1",
            local_date=_DAY,
            values={"PM2.5": [100 * ratio]},
            snapshot=snapshot,
            min_points=1,
        )
        view = assess_outcome(outcomes[0], snapshot)
        assert outcomes[0].risk_level == level
        assert 0 <= view.risk_score <= 100
        if outcomes[0].is_compliant:
            assert view.risk_score == 20
    high = evaluate_group(
        station_id="S1",
        local_date=_DAY,
        values={"PM2.5": [10000.0]},
        snapshot=snapshot,
        min_points=1,
    )
    capped = assess_outcome(high[0], snapshot)
    assert capped.risk_score == 100
