"""Chinese email alerts. The SMTP transport is injected so tests never open a socket."""

from __future__ import annotations

from typing import Mapping, Protocol

from app.adapters.notifications.base import AlertPayload, render_email


class SmtpTransport(Protocol):
    def login(self, secret: str) -> None: ...

    def send(self, *, recipients: tuple[str, ...], subject: str, body: str) -> None: ...


class EmailNotifier:
    def __init__(
        self,
        transport: SmtpTransport,
        *,
        credential_ref: str | None,
        secrets: Mapping[str, str],
        recipients: tuple[str, ...],
    ) -> None:
        self._transport = transport
        self._credential_ref = credential_ref
        self._secrets = secrets
        self._recipients = recipients

    def deliver(self, payload: AlertPayload) -> None:
        if self._credential_ref:
            secret = self._secrets.get(self._credential_ref, "")
            if secret:
                self._transport.login(secret)
        subject, body = render_email(payload)
        self._transport.send(recipients=self._recipients, subject=subject, body=body)
