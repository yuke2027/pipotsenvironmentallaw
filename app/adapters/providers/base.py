"""Provider DTOs shared by online and CSV adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ProviderObservation:
    station_code: str
    observed_at: datetime
    pm25: float | None
    pm10: float | None
    aqi: float | None
    external_id: str | None = None


@dataclass(frozen=True)
class ProviderHealth:
    ok: bool
    schema_version: int | None
    detail: str


class AirQualityProvider(Protocol):
    def fetch(self, city: str, since: datetime | None) -> list[ProviderObservation]: ...

    def health(self) -> ProviderHealth: ...
