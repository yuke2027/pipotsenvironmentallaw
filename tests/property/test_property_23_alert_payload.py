"""Property 23: email and webhook payloads carry the seven fields and no credentials."""

from __future__ import annotations

import json

import httpx
import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.adapters.notifications.base import REQUIRED_FIELDS, AlertPayload, payload_contains_secret, render_email
from app.adapters.notifications.email import EmailNotifier
from app.adapters.notifications.webhook import WebhookNotifier

_SECRET = "sek-alert-secret"
_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=8,
).filter(lambda value: payload_contains_secret(value, _SECRET) is False)


class _SMTP:
    def __init__(self) -> None:
        self.bodies: list[str] = []

    def login(self, secret: str) -> None:
        del secret

    def send(self, *, recipients: tuple[str, ...], subject: str, body: str) -> None:
        del recipients, subject
        self.bodies.append(body)


@given(city=_TEXT, station=_TEXT, pollutant=_TEXT, statistic=_TEXT, limit=_TEXT, ratio=_TEXT, level=_TEXT)
@pytest.mark.property
def test_property_23_alert_payload_is_complete(
    city: str,
    station: str,
    pollutant: str,
    statistic: str,
    limit: str,
    ratio: str,
    level: str,
) -> None:
    """Enabled email and webhook bodies contain the seven fields and no credential.

    **Feature: environmental-supervision-platform, Property 23: 告警载荷完整**
    **Property 23：告警载荷完整**
    **Validates: Requirements 10.2, 10.3, 10.10**
    """

    payload = AlertPayload(
        city=city + "市",
        station=station + "站",
        pollutant=pollutant,
        statistic=statistic,
        limit=limit,
        ratio=ratio,
        level=level,
    )
    _subject, body = render_email(payload)
    smtp = _SMTP()
    EmailNotifier(
        smtp,
        credential_ref="smtp-ref",
        secrets={"smtp-ref": _SECRET},
        recipients=("ops@example.com",),
    ).deliver(payload)
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    WebhookNotifier(
        client,
        url="https://alerts.example.test/hook",
        credential_ref="hook-ref",
        secrets={"hook-ref": _SECRET},
    ).deliver(payload)
    rendered_json = json.dumps(captured["json"], ensure_ascii=False)
    for field in REQUIRED_FIELDS:
        assert field in body
        assert field in rendered_json
    assert payload_contains_secret(body, _SECRET) is False
    assert payload_contains_secret(rendered_json, _SECRET) is False
    assert smtp.bodies and payload_contains_secret(smtp.bodies[-1], _SECRET) is False
