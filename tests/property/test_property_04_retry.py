"""Property 4: collection and alert calls share the retry ceiling and backoff."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.adapters.http.retry import ExternalCaller, RetryExhausted, StepClock

_BACKOFF = (1.0, 2.0, 4.0)


@given(
    kind=st.sampled_from(("collection", "alert")),
    failures=st.integers(min_value=0, max_value=6),
)
@pytest.mark.property
def test_property_04_retry_stops_after_success_or_the_budget(kind: str, failures: int) -> None:
    """Calls stay within the initial attempt plus three retries, then stop on success.

    **Feature: environmental-supervision-platform, Property 4: 外部调用重试边界**
    **Property 4：外部调用重试边界**
    **Validates: Requirements 2.4, 10.4, 15.6**
    """

    del kind
    caller = ExternalCaller(
        StepClock(),
        min_interval_seconds=0,
        base_delay_seconds=1,
        max_retries=3,
        max_jitter_seconds=0,
    )
    remaining = {"count": failures}

    def operation() -> str:
        if remaining["count"] > 0:
            remaining["count"] -= 1
            raise RuntimeError("temporary")
        return "ok"

    if failures <= 3:
        assert caller.execute(operation) == "ok"
        assert len(caller.starts) == failures + 1
        assert caller.backoff_sleeps == list(_BACKOFF[:failures])
        return
    with pytest.raises(RetryExhausted):
        caller.execute(operation)
    assert len(caller.starts) == 4
    assert caller.backoff_sleeps == list(_BACKOFF)
