"""Incremental city collection. Network calls stay outside the database transaction."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from app.adapters.http.retry import ExternalCaller, RetryExhausted
from app.adapters.providers.base import AirQualityProvider, ProviderObservation
from app.adapters.providers.cnemc import ProviderDisabled
from app.core.config import Settings
from app.domain.records import MonitoringDraft, StationRef, WriteCounts
from app.domain.repositories import CatalogRepository, MonitoringRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestReport:
    source: str
    received: int
    counts: WriteCounts


@dataclass(frozen=True)
class CollectionReport:
    cities: tuple[str, ...]
    ingest: IngestReport
    failed_cities: tuple[str, ...]
    no_op: bool


def ingest(
    drafts: list[MonitoringDraft],
    monitoring: MonitoringRepository,
    *,
    source: str,
) -> IngestReport:
    """Persist one batch and emit counts that match the repository result."""

    stamped = [
        MonitoringDraft(
            station_id=draft.station_id,
            observed_at=draft.observed_at,
            pm25=draft.pm25,
            pm10=draft.pm10,
            aqi=draft.aqi,
            source=source,
            is_imputed=source == "IMPUTED",
            original_missing_mask=draft.original_missing_mask,
            provider_record_id=draft.provider_record_id,
        )
        for draft in drafts
    ]
    counts = monitoring.insert_batch(stamped)
    received = counts.inserted + counts.skipped + counts.invalid
    logger.info(
        "INGEST_COUNTS",
        extra={
            "event": "INGEST_COUNTS",
            "source": source,
            "received": received,
            "inserted": counts.inserted,
            "skipped": counts.skipped,
            "invalid": counts.invalid,
        },
    )
    return IngestReport(source=source, received=received, counts=counts)


class CollectionService:
    def __init__(
        self,
        monitoring: MonitoringRepository,
        catalog: CatalogRepository,
        provider: AirQualityProvider,
        caller: ExternalCaller,
        settings: Settings,
        *,
        fallback: AirQualityProvider | None = None,
    ) -> None:
        self._monitoring = monitoring
        self._catalog = catalog
        self._provider = provider
        self._caller = caller
        self._settings = settings
        self._fallback = fallback

    def collect(self, cities: tuple[str, ...] | None = None) -> CollectionReport:
        selected = self._settings.target_cities if cities is None else cities
        online: list[MonitoringDraft] = []
        fallback_rows: list[MonitoringDraft] = []
        invalid = 0
        failed: list[str] = []
        for city in selected:
            stations = self._catalog.stations_for_city(city)
            watermark = self._monitoring.latest_observed_at(tuple(station.id for station in stations))
            try:
                observations, source = self._fetch(city, watermark)
            except (RetryExhausted, ProviderDisabled, OSError, RuntimeError):
                failed.append(city)
                continue
            city_drafts, city_invalid = _select_online(observations, stations, watermark)
            invalid += city_invalid
            if source == "CSV":
                fallback_rows.extend(city_drafts)
            else:
                online.extend(city_drafts)
        report = _combine(
            ingest(online, self._monitoring, source="ONLINE"),
            ingest(fallback_rows, self._monitoring, source="CSV") if fallback_rows else None,
            invalid,
        )
        return CollectionReport(
            cities=tuple(selected),
            ingest=report,
            failed_cities=tuple(failed),
            no_op=report.received == 0 and not failed,
        )

    def _fetch(self, city: str, watermark: datetime | None) -> tuple[list[ProviderObservation], str]:
        if not getattr(self._provider, "enabled", True):
            raise ProviderDisabled()

        def operation() -> list[ProviderObservation]:
            return self._provider.fetch(city, watermark)

        try:
            return self._caller.execute(operation), "ONLINE"
        except (RetryExhausted, ProviderDisabled):
            if self._fallback is None:
                raise
            return self._fallback.fetch(city, watermark), "CSV"


def _combine(primary: IngestReport, secondary: IngestReport | None, extra_invalid: int) -> IngestReport:
    inserted = primary.counts.inserted
    skipped = primary.counts.skipped
    invalid = primary.counts.invalid + extra_invalid
    if secondary is not None:
        inserted += secondary.counts.inserted
        skipped += secondary.counts.skipped
        invalid += secondary.counts.invalid
    counts = WriteCounts(inserted=inserted, skipped=skipped, invalid=invalid)
    received = counts.inserted + counts.skipped + counts.invalid
    logger.info(
        "INGEST_COUNTS",
        extra={
            "event": "INGEST_COUNTS",
            "source": primary.source,
            "received": received,
            "inserted": counts.inserted,
            "skipped": counts.skipped,
            "invalid": counts.invalid,
        },
    )
    return IngestReport(source=primary.source, received=received, counts=counts)


def _select_online(
    observations: list[ProviderObservation],
    stations: tuple[StationRef, ...],
    watermark: datetime | None,
) -> tuple[list[MonitoringDraft], int]:
    by_code = {station.code: station for station in stations}
    by_name = {station.name_zh: station for station in stations}
    drafts: list[MonitoringDraft] = []
    invalid = 0
    for observation in observations:
        if watermark is not None and observation.observed_at <= watermark:
            continue
        station = by_code.get(observation.station_code) or by_name.get(observation.station_code)
        if station is None or _bad_observation(observation):
            invalid += 1
            continue
        drafts.append(
            MonitoringDraft(
                station_id=station.id,
                observed_at=observation.observed_at.astimezone(timezone.utc),
                pm25=observation.pm25,
                pm10=observation.pm10,
                aqi=observation.aqi,
                source="ONLINE",
                is_imputed=False,
                provider_record_id=observation.external_id,
            )
        )
    return drafts, invalid


def _bad_observation(observation: ProviderObservation) -> bool:
    if observation.observed_at.tzinfo is None:
        return True
    return any(_bad_value(value) for value in (observation.pm25, observation.pm10, observation.aqi))


def _bad_value(value: float | None) -> bool:
    return value is not None and (not math.isfinite(value) or value < 0)
