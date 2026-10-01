"""Property 25: inverted ranges and oversized spans are rejected with a named field."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.errors import AppError, ErrorCode
from app.domain.query_spec import validate_time_range

_ORIGIN = datetime(2026, 3, 1, tzinfo=timezone.utc)


@given(
    start_hours=st.integers(min_value=0, max_value=48),
    end_delta_hours=st.integers(min_value=-48, max_value=400),
    max_days=st.integers(min_value=1, max_value=10),
)
@pytest.mark.property
def test_property_25_time_range_boundaries(start_hours: int, end_delta_hours: int, max_days: int) -> None:
    """start > end names start_time; an oversized span names the maximum; equality is allowed.

    **Feature: environmental-supervision-platform, Property 25: 时间查询边界**
    **Property 25：时间查询边界**
    **Validates: Requirements 11.3, 11.4**
    """

    start = _ORIGIN + timedelta(hours=start_hours)
    end = start + timedelta(hours=end_delta_hours)
    limit = timedelta(days=max_days)
    try:
        validate_time_range(start, end, limit)
    except AppError as error:
        failure: AppError | None = error
    else:
        failure = None
    if start > end:
        assert failure is not None
        assert failure.code == ErrorCode.INVALID_TIME_RANGE
        assert any(getattr(detail, "field", None) == "start_time" for detail in failure.details)
        return
    if end - start > limit:
        assert failure is not None
        assert failure.code == ErrorCode.TIME_RANGE_EXCEEDS_LIMIT
        assert any(str(max_days) in getattr(detail, "reason", "") for detail in failure.details)
        return
    assert failure is None
