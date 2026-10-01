"""Property 17: compliance follows the database limit and keeps old references."""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.compliance import evaluate_group
from tests.support.legal_snapshots import legal_snapshot

_DAY = date(2026, 1, 2)
_SAMPLE = st.one_of(st.none(), st.floats(min_value=0, max_value=80, allow_nan=False, allow_infinity=False))


@given(
    samples=st.lists(_SAMPLE, min_size=1, max_size=6),
    limit=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False),
)
@pytest.mark.property
def test_property_17_compliance_uses_the_database_limit(samples: list[float | None], limit: float) -> None:
    """Means and compliance follow the snapshot, and a later snapshot does not rewrite history.

    **Feature: environmental-supervision-platform, Property 17: 数据库标准驱动的合规判定**
    **Property 17：数据库标准驱动的合规判定**
    **Validates: Requirements 6.12, 7.1, 7.2, 7.3, 7.4, 7.6, 15.2, 15.7, 16.3**
    """

    finite = [value for value in samples if value is not None]
    if not finite:
        finite = [0.0]
        samples = [0.0]
    limits = {"PM2.5": limit, "PM10": limit, "AQI": limit}
    first = evaluate_group(
        station_id="S1",
        local_date=_DAY,
        values={name: samples for name in limits},
        snapshot=legal_snapshot(limits),
        min_points=1,
    )
    reference_mean = sum(finite) / len(finite)
    for outcome in first:
        assert outcome.valid_points == len(finite)
        assert outcome.daily_mean == pytest.approx(reference_mean)
        assert outcome.max_value == pytest.approx(max(finite))
        assert outcome.min_value == pytest.approx(min(finite))
        assert outcome.exceed_ratio == pytest.approx(reference_mean / limit)
        assert outcome.is_compliant is (reference_mean <= limit)
        assert outcome.standard_id is not None
    saved_ids = tuple(outcome.standard_id for outcome in first)
    second = evaluate_group(
        station_id="S1",
        local_date=_DAY,
        values={name: samples for name in limits},
        snapshot=legal_snapshot({name: limit / 2 for name in limits}, version_suffix="2"),
        min_points=1,
    )
    assert tuple(outcome.standard_id for outcome in first) == saved_ids
    assert all(old != new.standard_id for old, new in zip(saved_ids, second))
