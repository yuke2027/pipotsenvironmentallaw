"""Property 22: alerts fire only for qualifying results and skip a sent same-day key."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.adapters.http.retry import ExternalCaller, StepClock
from app.adapters.notifications.base import AlertPayload
from app.domain.enums import COMPLIANCE_STATUSES, RISK_LEVELS
from app.services.alerts import AlertService, AlertTrigger, reaches_threshold
from tests.support.memory_alerts import MemoryAlertRepository

_NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


class _Notifier:
    def __init__(self) -> None:
        self.calls = 0

    def deliver(self, payload: AlertPayload) -> None:
        self.calls += 1


@given(
    status=st.sampled_from(COMPLIANCE_STATUSES),
    risk_level=st.sampled_from(RISK_LEVELS),
    threshold=st.sampled_from(RISK_LEVELS),
    existing=st.sampled_from((None, "SENT", "FAILED")),
    day=st.dates(min_value=date(2026, 1, 1), max_value=date(2026, 1, 28)),
)
@pytest.mark.property
def test_property_22_alert_trigger_and_same_day_dedupe(
    status: str,
    risk_level: str,
    threshold: str,
    existing: str | None,
    day: date,
) -> None:
    """A sent same-day key is not delivered again. Other results follow the threshold.

    **Feature: environmental-supervision-platform, Property 22: 告警触发与日内去重**
    **Property 22：告警触发与日内去重**
    **Validates: Requirements 10.1, 10.6**
    """

    repo = MemoryAlertRepository()
    if existing is not None:
        alert_id = repo.add_alert(
            __import__("app.domain.records", fromlist=["AlertDraft"]).AlertDraft(
                compliance_result_id=1,
                channel_id=7,
                station_id=3,
                pollutant="PM2.5",
                alert_date=day,
                trigger_snapshot={},
                status="PENDING",
                generated_at=_NOW,
            )
        )
        repo.update_alert(
            alert_id,
            status=existing,
            attempt_count=1,
            failure_reason=None,
            dedupe_reason=None,
            pushed_at=_NOW if existing == "SENT" else None,
        )
    notifier = _Notifier()
    result = AlertService(
        repo,
        ExternalCaller(StepClock(), min_interval_seconds=0, base_delay_seconds=0),
    ).dispatch(
        AlertTrigger(
            compliance_result_id=1,
            station_id=3,
            pollutant="PM2.5",
            alert_date=day,
            status=status,
            risk_level=risk_level,
            city="北京",
            station="东城",
            statistic="80",
            limit="75",
            ratio="1.1",
        ),
        channel_id=7,
        threshold_level=threshold,
        notifier=notifier,
        now=_NOW,
    )
    qualified = reaches_threshold(status, risk_level, threshold)
    if not qualified:
        assert notifier.calls == 0
        assert result.sent is False
        return
    if existing == "SENT":
        assert notifier.calls == 0
        assert result.deduped is True
        stored = repo.find_alert(3, "PM2.5", day, 7)
        assert stored is not None
        assert stored.dedupe_reason
        return
    assert notifier.calls == 1
    assert result.sent is True
    stored = repo.find_alert(3, "PM2.5", day, 7)
    assert stored is not None
    assert stored.status == "SENT"
