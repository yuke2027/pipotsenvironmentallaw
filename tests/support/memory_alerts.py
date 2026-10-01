"""In-memory alert repository for notification tests."""

from __future__ import annotations

from datetime import date, datetime

from app.domain.errors import DuplicateNameError
from app.domain.records import (
    AlertChannelDraft,
    AlertChannelRecord,
    AlertDraft,
    AlertRecord,
    DeliveryAttemptDraft,
    Page,
)


class MemoryAlertRepository:
    def __init__(self) -> None:
        self.channels: dict[int, AlertChannelRecord] = {}
        self.alerts: dict[int, AlertRecord] = {}
        self.attempts: list[DeliveryAttemptDraft] = []
        self._next_channel = 1
        self._next_alert = 1

    def add_channel(self, draft: AlertChannelDraft) -> int:
        if any(row.name == draft.name for row in self.channels.values()):
            raise DuplicateNameError()
        channel_id = self._next_channel
        self._next_channel += 1
        self.channels[channel_id] = _channel(channel_id, draft)
        return channel_id

    def list_channels(self) -> tuple[AlertChannelRecord, ...]:
        return tuple(self.channels[key] for key in sorted(self.channels))

    def get_channel(self, channel_id: int) -> AlertChannelRecord | None:
        return self.channels.get(channel_id)

    def update_channel(self, channel_id: int, draft: AlertChannelDraft) -> None:
        if channel_id not in self.channels:
            raise LookupError("alert channel does not exist")
        if any(row.name == draft.name and key != channel_id for key, row in self.channels.items()):
            raise DuplicateNameError()
        self.channels[channel_id] = _channel(channel_id, draft)

    def add_alert(self, draft: AlertDraft) -> int:
        alert_id = self._next_alert
        self._next_alert += 1
        self.alerts[alert_id] = AlertRecord(
            id=alert_id,
            station_id=draft.station_id,
            pollutant=draft.pollutant,
            alert_date=draft.alert_date,
            channel_id=draft.channel_id,
            status=draft.status,
        )
        return alert_id

    def find_alert(
        self, station_id: int, pollutant: str, alert_date: date, channel_id: int
    ) -> AlertRecord | None:
        for row in self.alerts.values():
            if (
                row.station_id == station_id
                and row.pollutant == pollutant
                and row.alert_date == alert_date
                and row.channel_id == channel_id
            ):
                return row
        return None

    def update_alert(
        self,
        alert_id: int,
        *,
        status: str,
        attempt_count: int,
        failure_reason: str | None,
        dedupe_reason: str | None,
        pushed_at: datetime | None,
    ) -> None:
        current = self.alerts[alert_id]
        self.alerts[alert_id] = AlertRecord(
            id=current.id,
            station_id=current.station_id,
            pollutant=current.pollutant,
            alert_date=current.alert_date,
            channel_id=current.channel_id,
            status=status,
            dedupe_reason=dedupe_reason,
            attempt_count=attempt_count,
            failure_reason=failure_reason,
            pushed_at=pushed_at,
        )

    def add_delivery_attempt(self, draft: DeliveryAttemptDraft) -> int:
        self.attempts.append(draft)
        return len(self.attempts)

    def list_alerts(self, page: int, page_size: int) -> Page[AlertRecord]:
        ordered = tuple(self.alerts[key] for key in sorted(self.alerts))
        start = (page - 1) * page_size
        return Page(items=ordered[start : start + page_size], page=page, page_size=page_size, total=len(ordered))


def _channel(channel_id: int, draft: AlertChannelDraft) -> AlertChannelRecord:
    return AlertChannelRecord(
        id=channel_id,
        name=draft.name,
        channel_type=draft.channel_type,
        enabled=draft.enabled,
        non_secret_config=dict(draft.non_secret_config),
        credential_ref=draft.credential_ref,
        recipients=draft.recipients,
        threshold_level=draft.threshold_level,
    )
