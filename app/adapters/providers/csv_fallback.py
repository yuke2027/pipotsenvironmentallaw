"""Wide-CSV fallback that reuses the legacy preprocessing adapter.

Rows produced here are historical or file-based observations. Callers must
label them ``CSV`` and must not present them as new online measurements.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from app.adapters.legacy.preprocessing import preprocess_wide_dataframe
from app.adapters.providers.base import ProviderHealth, ProviderObservation
from app.domain.dataframe_contracts import AlgorithmContractError

_SHANGHAI = timezone(timedelta(hours=8))


class LegacyWideCsvProvider:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def health(self) -> ProviderHealth:
        exists = self._directory.is_dir()
        return ProviderHealth(ok=exists, schema_version=None, detail="csv" if exists else "missing")

    def fetch(self, city: str, since: datetime | None) -> list[ProviderObservation]:
        del city, since
        observations: list[ProviderObservation] = []
        if not self._directory.is_dir():
            return observations
        for path in sorted(self._directory.glob("*.csv")):
            frame = pd.read_csv(path)
            try:
                converted = preprocess_wide_dataframe(frame)
            except (AlgorithmContractError, ValueError, OSError):
                continue
            for dated in converted.particulate.values():
                observations.extend(_rows(dated))
        return observations


def rows_from_particulate(frame: pd.DataFrame) -> list[ProviderObservation]:
    return _rows(frame)


def _rows(frame: pd.DataFrame) -> list[ProviderObservation]:
    observations: list[ProviderObservation] = []
    for record in frame.to_dict(orient="records"):
        hour = int(record["timestamp"])
        local = _local_timestamp(record["date"], hour)
        observations.append(
            ProviderObservation(
                station_code=str(record["station_id"]),
                observed_at=local.astimezone(timezone.utc),
                pm25=_float_or_none(record.get("PM2.5")),
                pm10=_float_or_none(record.get("PM10")),
                aqi=_float_or_none(record.get("AQI")),
                external_id=None,
            )
        )
    return observations


def _local_timestamp(date_value: object, hour: int) -> datetime:
    text = str(date_value).split(".", 1)[0]
    if "-" in text:
        local = datetime.fromisoformat(f"{text}T{hour:02d}:00:00")
    else:
        local = datetime.strptime(text, "%Y%m%d").replace(hour=hour, minute=0, second=0, microsecond=0)
    if local.tzinfo is None:
        local = local.replace(tzinfo=_SHANGHAI)
    return local


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None
