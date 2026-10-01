"""Property 3: collection follows the configured cities and their watermarks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.adapters.http.retry import ExternalCaller, StepClock
from app.adapters.providers.base import ProviderHealth, ProviderObservation
from app.domain.records import StationRef, WriteCounts
from app.services.collection import CollectionService
from tests.support.auth_factory import auth_settings

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Catalog:
    def __init__(self, stations: dict[str, StationRef]) -> None:
        self._stations = stations

    def stations_for_city(self, city_name: str) -> tuple[StationRef, ...]:
        station = self._stations.get(city_name)
        return () if station is None else (station,)


class _Monitoring:
    def __init__(self, watermarks: dict[int, datetime | None]) -> None:
        self.watermarks = watermarks
        self.drafts: list[object] = []

    def latest_observed_at(self, station_ids: tuple[int, ...] | list[int]) -> datetime | None:
        if not station_ids:
            return None
        return self.watermarks.get(station_ids[0])

    def insert_batch(self, records: list[object]) -> WriteCounts:
        self.drafts.extend(records)
        return WriteCounts(inserted=len(records), skipped=0, invalid=0)

    def get(self, station_id: int, observed_at: datetime) -> None:
        return None


class _Provider:
    def __init__(self, rows: dict[str, list[ProviderObservation]]) -> None:
        self.rows = rows
        self.cities: list[str] = []
        self.enabled = True

    def fetch(self, city: str, since: datetime | None) -> list[ProviderObservation]:
        del since
        self.cities.append(city)
        return list(self.rows.get(city, []))

    def health(self) -> ProviderHealth:
        return ProviderHealth(True, 1, "ok")


@given(
    cities=st.lists(st.sampled_from(("北京", "上海", "广州")), min_size=1, max_size=3, unique=True),
    offsets=st.lists(st.integers(min_value=-5, max_value=5), min_size=1, max_size=4),
)
@pytest.mark.property
def test_property_03_incremental_collection_follows_cities(
    cities: list[str],
    offsets: list[int],
) -> None:
    """Provider cities match configuration and written online rows are newer than the watermark.

    **Feature: environmental-supervision-platform, Property 3: 城市驱动的增量采集**
    **Property 3：城市驱动的增量采集**
    **Validates: Requirements 2.1, 2.3**
    """

    stations = {
        city: StationRef(id=index + 1, code=f"S{index}", name_zh=city, city_name=city)
        for index, city in enumerate(cities)
    }
    watermarks = {station.id: _BASE for station in stations.values()}
    rows = {
        city: [
            ProviderObservation(
                station_code=stations[city].code,
                observed_at=_BASE + timedelta(hours=offset),
                pm25=1,
                pm10=1,
                aqi=1,
            )
            for offset in offsets
        ]
        for city in cities
    }
    provider = _Provider(rows)
    monitoring = _Monitoring(watermarks)
    service = CollectionService(
        monitoring,  # type: ignore[arg-type]
        _Catalog(stations),
        provider,
        ExternalCaller(StepClock(), min_interval_seconds=0, base_delay_seconds=0),
        auth_settings(target_cities=tuple(cities)),
    )
    service.collect()
    assert provider.cities == list(cities)
    for draft in monitoring.drafts:
        assert getattr(draft, "source") == "ONLINE"
        watermark = watermarks[getattr(draft, "station_id")]
        assert watermark is not None
        assert getattr(draft, "observed_at") > watermark
