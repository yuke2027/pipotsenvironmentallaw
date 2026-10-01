"""Configurable CNEMC client.

The component stays disabled until an endpoint is configured. Automatic tests
must pass an ``httpx.Client`` built with ``MockTransport``; this module does
not construct a client that dials the public internet.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

import httpx

from app.adapters.providers.base import ProviderHealth, ProviderObservation

SCHEMA_VERSION = 1


class ProviderDisabled(RuntimeError):
    def __init__(self) -> None:
        super().__init__("CNEMC provider is disabled")


class ProviderSchemaError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("CNEMC response schema is not supported")


class CNEMCPublicProvider:
    def __init__(
        self,
        *,
        enabled: bool,
        endpoint: str | None,
        schema_version: int,
        client: httpx.Client | None,
        credential_ref: str | None = None,
        secrets: Mapping[str, str] | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._enabled = enabled and bool(endpoint)
        self._endpoint = endpoint
        self._schema_version = schema_version
        self._client = client
        self._credential_ref = credential_ref
        self._secrets = dict(secrets or {})
        self._timeout = timeout_seconds

    @property
    def enabled(self) -> bool:
        return self._enabled

    def health(self) -> ProviderHealth:
        if not self._enabled:
            return ProviderHealth(ok=False, schema_version=None, detail="disabled")
        return ProviderHealth(ok=True, schema_version=self._schema_version, detail="configured")

    def fetch(self, city: str, since: datetime | None) -> list[ProviderObservation]:
        if not self._enabled or self._endpoint is None or self._client is None:
            raise ProviderDisabled()
        headers = {"Accept": "application/json"}
        if self._credential_ref:
            secret = self._secrets.get(self._credential_ref)
            if secret:
                headers["Authorization"] = f"Bearer {secret}"
        params = {"city": city, "schema_version": str(self._schema_version)}
        if since is not None:
            params["since"] = since.isoformat()
        response = self._client.get(self._endpoint, params=params, headers=headers, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("schema_version") != self._schema_version:
            raise ProviderSchemaError()
        raw_rows = payload.get("observations")
        if not isinstance(raw_rows, list):
            raise ProviderSchemaError()
        observations: list[ProviderObservation] = []
        for row in raw_rows:
            if not isinstance(row, dict):
                raise ProviderSchemaError()
            observations.append(_observation(row))
        return observations


def _observation(row: Mapping[str, object]) -> ProviderObservation:
    station = row.get("station_code")
    observed = row.get("observed_at")
    external = row.get("external_id")
    if not isinstance(station, str) or not isinstance(observed, str):
        raise ProviderSchemaError()
    return ProviderObservation(
        station_code=station,
        observed_at=datetime.fromisoformat(observed),
        pm25=_optional_float(row.get("pm25")),
        pm10=_optional_float(row.get("pm10")),
        aqi=_optional_float(row.get("aqi")),
        external_id=external if isinstance(external, str) else None,
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProviderSchemaError()
    return float(value)
