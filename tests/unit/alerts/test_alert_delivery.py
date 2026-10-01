"""Example tests for alert delivery, dedupe, and channel administration."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app.adapters.http.retry import ExternalCaller, StepClock
from app.adapters.notifications.base import AlertPayload
from app.adapters.notifications.email import EmailNotifier
from app.adapters.notifications.webhook import WebhookNotifier
from app.core.clock import FrozenClock
from app.core.errors import AppError
from app.domain.principal import Principal
from app.services.alert_channels import AlertChannelService
from app.services.alerts import AlertService, AlertTrigger
from tests.support.memory_alerts import MemoryAlertRepository
from tests.support.memory_auth import MemoryAuditRepository

_NOW = datetime(2026, 6, 2, tzinfo=timezone.utc)
_SECRET = "channel-secret-value"


class _SMTP:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.bodies: list[str] = []

    def login(self, secret: str) -> None:
        assert secret == _SECRET

    def send(self, *, recipients: tuple[str, ...], subject: str, body: str) -> None:
        del recipients, subject
        if self.failures:
            self.failures -= 1
            raise TimeoutError("smtp timeout")
        self.bodies.append(body)


def _trigger(day: date, status: str = "NON_COMPLIANT", level: str = "严重") -> AlertTrigger:
    return AlertTrigger(1, 4, "PM2.5", day, status, level, "北京", "东城", "90", "75", "1.2")


def _service(repo: MemoryAlertRepository) -> AlertService:
    return AlertService(repo, ExternalCaller(StepClock(), min_interval_seconds=0, base_delay_seconds=0, max_retries=3))


@pytest.mark.unit
def test_email_and_webhook_round_trip_without_echoing_the_secret() -> None:
    smtp = _SMTP()
    payload = AlertPayload("北京", "东城", "PM2.5", "90", "75", "1.2", "严重")
    EmailNotifier(smtp, credential_ref="smtp-ref", secrets={"smtp-ref": _SECRET}, recipients=("a@example.com",)).deliver(
        payload
    )
    assert "城市：北京" in smtp.bodies[0]
    assert _SECRET not in smtp.bodies[0]
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode("utf-8")
        assert request.headers["Authorization"] == f"Bearer {_SECRET}"
        return httpx.Response(204)

    WebhookNotifier(
        httpx.Client(transport=httpx.MockTransport(handler)),
        url="https://alerts.example.test/hook",
        credential_ref="hook-ref",
        secrets={"hook-ref": _SECRET},
    ).deliver(payload)
    parsed = json.loads(seen["body"])
    assert parsed["站点"] == "东城"
    assert _SECRET not in seen["body"]


@pytest.mark.unit
def test_retry_exhaustion_unique_conflict_and_next_day() -> None:
    repo = MemoryAlertRepository()
    failing = _SMTP(failures=10)

    class _Fail:
        def deliver(self, payload: AlertPayload) -> None:
            failing.send(recipients=("a@example.com",), subject="x", body="y")

    result = _service(repo).dispatch(_trigger(date(2026, 6, 2)), channel_id=1, threshold_level="高", notifier=_Fail(), now=_NOW)
    assert result.sent is False
    assert result.attempts == 4
    stored = repo.find_alert(4, "PM2.5", date(2026, 6, 2), 1)
    assert stored is not None and stored.status == "FAILED"
    ok = _SMTP()

    class _Ok:
        def deliver(self, payload: AlertPayload) -> None:
            ok.send(recipients=("a@example.com",), subject="x", body=payload.city)

    sent = _service(repo).dispatch(_trigger(date(2026, 6, 2)), channel_id=1, threshold_level="高", notifier=_Ok(), now=_NOW)
    assert sent.sent is True
    again = _service(repo).dispatch(
        _trigger(date(2026, 6, 2)), channel_id=1, threshold_level="高", notifier=_Ok(), now=_NOW
    )
    assert again.deduped is True
    assert len(ok.bodies) == 1
    next_day = _service(repo).dispatch(
        _trigger(date(2026, 6, 3)), channel_id=1, threshold_level="高", notifier=_Ok(), now=_NOW + timedelta(days=1)
    )
    assert next_day.sent is True
    assert len(ok.bodies) == 2


@pytest.mark.unit
def test_non_admin_channel_write_is_rejected_and_secret_is_not_stored() -> None:
    repo = MemoryAlertRepository()
    audit = MemoryAuditRepository()
    service = AlertChannelService(repo, audit, FrozenClock(_NOW))
    researcher = Principal(2, "researcher", "研究者", False, "j", _NOW)
    with pytest.raises(AppError) as denied:
        service.create(
            researcher,
            name="mail",
            channel_type="email",
            enabled=True,
            non_secret_config={"host": "smtp.example.test"},
            credential_ref="smtp-ref",
            recipients=("a@example.com",),
            threshold_level="高",
        )
    assert denied.value.status_code == 403
    assert repo.channels == {}
    admin = Principal(1, "admin", "管理员", False, "j", _NOW)
    with pytest.raises(AppError) as invalid:
        service.create(
            admin,
            name="mail",
            channel_type="email",
            enabled=True,
            non_secret_config={"password": _SECRET},
            credential_ref="smtp-ref",
            recipients=("a@example.com",),
            threshold_level="高",
        )
    assert invalid.value.status_code == 422
    created = service.create(
        admin,
        name="mail",
        channel_type="email",
        enabled=True,
        non_secret_config={"host": "smtp.example.test"},
        credential_ref="smtp-ref",
        recipients=("a@example.com",),
        threshold_level="高",
    )
    view = json.dumps(service.public_view(created), ensure_ascii=False)
    assert _SECRET not in view
    assert created.credential_ref == "smtp-ref"
    rendered_audit = json.dumps([entry.details for entry in audit.entries], ensure_ascii=False)
    assert _SECRET not in rendered_audit
