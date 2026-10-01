"""Alert triggering, delivery attempts, and same-day deduplication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.adapters.http.retry import ExternalCaller, RetryExhausted
from app.adapters.notifications.base import AlertPayload, Notifier
from app.core.logging import sanitize_text
from app.domain.enums import RISK_LEVELS
from app.domain.records import AlertDraft, DeliveryAttemptDraft
from app.domain.repositories import AlertRepository

_RANK = {level: index for index, level in enumerate(RISK_LEVELS)}


@dataclass(frozen=True)
class AlertTrigger:
    compliance_result_id: int
    station_id: int
    pollutant: str
    alert_date: date
    status: str
    risk_level: str
    city: str
    station: str
    statistic: str
    limit: str
    ratio: str


@dataclass(frozen=True)
class DispatchResult:
    created: bool
    sent: bool
    deduped: bool
    attempts: int


def reaches_threshold(status: str, risk_level: str, threshold_level: str) -> bool:
    """Only a non-compliant result at or above the channel threshold can alert."""

    if status != "NON_COMPLIANT":
        return False
    if risk_level not in _RANK or threshold_level not in _RANK:
        return False
    return _RANK[risk_level] >= _RANK[threshold_level]


class AlertService:
    def __init__(self, alerts: AlertRepository, caller: ExternalCaller) -> None:
        self._alerts = alerts
        self._caller = caller

    def dispatch(
        self,
        trigger: AlertTrigger,
        *,
        channel_id: int,
        threshold_level: str,
        notifier: Notifier,
        now: datetime,
    ) -> DispatchResult:
        if not reaches_threshold(trigger.status, trigger.risk_level, threshold_level):
            return DispatchResult(created=False, sent=False, deduped=False, attempts=0)
        existing = self._alerts.find_alert(
            trigger.station_id, trigger.pollutant, trigger.alert_date, channel_id
        )
        if existing is not None and existing.status == "SENT":
            self._alerts.update_alert(
                existing.id,
                status="SENT",
                attempt_count=existing.attempt_count,
                failure_reason=existing.failure_reason,
                dedupe_reason="same-day delivery already sent",
                pushed_at=existing.pushed_at,
            )
            return DispatchResult(created=False, sent=False, deduped=True, attempts=0)
        alert_id = existing.id if existing is not None else self._alerts.add_alert(
            AlertDraft(
                compliance_result_id=trigger.compliance_result_id,
                channel_id=channel_id,
                station_id=trigger.station_id,
                pollutant=trigger.pollutant,
                alert_date=trigger.alert_date,
                trigger_snapshot=trigger_snapshot(trigger),
                status="PENDING",
                generated_at=now,
            )
        )
        payload = AlertPayload(
            city=trigger.city,
            station=trigger.station,
            pollutant=trigger.pollutant,
            statistic=trigger.statistic,
            limit=trigger.limit,
            ratio=trigger.ratio,
            level=trigger.risk_level,
        )
        attempts = 0

        def operation() -> None:
            nonlocal attempts
            attempts += 1
            started = datetime.now(timezone.utc)
            try:
                notifier.deliver(payload)
            except Exception as exc:
                self._alerts.add_delivery_attempt(
                    DeliveryAttemptDraft(
                        alert_id=alert_id,
                        attempt_no=attempts,
                        started_at=started,
                        finished_at=datetime.now(timezone.utc),
                        outcome="FAILED",
                        sanitized_error=sanitize_text(type(exc).__name__),
                    )
                )
                raise
            self._alerts.add_delivery_attempt(
                DeliveryAttemptDraft(
                    alert_id=alert_id,
                    attempt_no=attempts,
                    started_at=started,
                    finished_at=datetime.now(timezone.utc),
                    outcome="SUCCESS",
                    sanitized_error=None,
                )
            )

        try:
            self._caller.execute(operation)
        except RetryExhausted as exc:
            self._alerts.update_alert(
                alert_id,
                status="FAILED",
                attempt_count=attempts,
                failure_reason=sanitize_text(str(exc)),
                dedupe_reason=None,
                pushed_at=None,
            )
            return DispatchResult(created=existing is None, sent=False, deduped=False, attempts=attempts)
        self._alerts.update_alert(
            alert_id,
            status="SENT",
            attempt_count=attempts,
            failure_reason=None,
            dedupe_reason=None,
            pushed_at=now,
        )
        return DispatchResult(created=existing is None, sent=True, deduped=False, attempts=attempts)


def trigger_snapshot(trigger: AlertTrigger) -> dict[str, str]:
    return {
        "城市": trigger.city,
        "站点": trigger.station,
        "污染物": trigger.pollutant,
        "统计值": trigger.statistic,
        "限值": trigger.limit,
        "倍数": trigger.ratio,
        "等级": trigger.risk_level,
    }
