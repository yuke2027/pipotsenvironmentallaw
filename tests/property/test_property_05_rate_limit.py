"""Property 5: external calls, including retries, honor the minimum interval."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.adapters.http.retry import ExternalCaller, StepClock


@given(
    interval=st.integers(min_value=0, max_value=15),
    failures=st.lists(st.integers(min_value=0, max_value=3), min_size=1, max_size=5),
)
@pytest.mark.property
def test_property_05_request_spacing_includes_retries(interval: int, failures: list[int]) -> None:
    """Adjacent attempt start times are at least the configured interval apart.

    **Feature: environmental-supervision-platform, Property 5: 请求限速下界**
    **Property 5：请求限速下界**
    **Validates: Requirements 2.6, 15.6**
    """

    clock = StepClock()
    caller = ExternalCaller(
        clock,
        min_interval_seconds=interval,
        base_delay_seconds=0,
        max_retries=3,
        max_jitter_seconds=0,
    )
    for fail_count in failures:
        remaining = fail_count

        def operation(left: list[int] = [remaining]) -> str:
            if left[0] > 0:
                left[0] -= 1
                raise RuntimeError("temporary")
            return "ok"

        assert caller.execute(operation) == "ok"
    starts = caller.starts
    assert len(starts) == sum(failures) + len(failures)
    for previous, current in zip(starts, starts[1:]):
        assert current - previous >= interval
