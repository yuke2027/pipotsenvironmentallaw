"""JSON webhook alerts. Callers pass an httpx client, normally with MockTransport."""

from __future__ import annotations

from typing import Mapping

import httpx

from app.adapters.notifications.base import AlertPayload


class WebhookNotifier:
    def __init__(
        self,
        client: httpx.Client,
        *,
        url: str,
        credential_ref: str | None,
        secrets: Mapping[str, str],
        timeout_seconds: float = 5.0,
    ) -> None:
        self._client = client
        self._url = url
        self._credential_ref = credential_ref
        self._secrets = secrets
        self._timeout = timeout_seconds

    def deliver(self, payload: AlertPayload) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._credential_ref:
            secret = self._secrets.get(self._credential_ref, "")
            if secret:
                headers["Authorization"] = f"Bearer {secret}"
        response = self._client.post(
            self._url,
            json=payload.as_mapping(),
            headers=headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
