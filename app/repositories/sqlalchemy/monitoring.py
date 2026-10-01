"""Idempotent monitoring writes.

The repository looks up ``(station_id, observed_at)`` before inserting. A
concurrent unique conflict is rolled back to a savepoint and counted as a
skip. The first stored values are never updated.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import MonitoringRecord
from app.db.types import utc_now
from app.domain.enums import MONITORING_SOURCES
from app.domain.records import MonitoringDraft, MonitoringRecordView, WriteCounts


class SqlAlchemyMonitoringRepository:
    def __init__(
        self,
        session: Session,
        *,
        before_insert: Callable[[], None] | None = None,
    ) -> None:
        self._session = session
        self._before_insert = before_insert

    def insert_batch(self, records: Sequence[MonitoringDraft]) -> WriteCounts:
        inserted = 0
        skipped = 0
        invalid = 0
        for record in records:
            if _invalid(record):
                invalid += 1
                continue
            existing = self._session.scalar(
                select(MonitoringRecord.id).where(
                    MonitoringRecord.station_id == record.station_id,
                    MonitoringRecord.observed_at == record.observed_at,
                )
            )
            if existing is not None:
                skipped += 1
                continue
            if self._before_insert is not None:
                self._before_insert()
            try:
                with self._session.begin_nested():
                    now = utc_now()
                    self._session.add(
                        MonitoringRecord(
                            station_id=record.station_id,
                            observed_at=record.observed_at,
                            pm25=record.pm25,
                            pm10=record.pm10,
                            aqi=record.aqi,
                            source=record.source,
                            is_imputed=record.is_imputed,
                            original_missing_mask=_copy_mask(record.original_missing_mask),
                            provider_record_id=record.provider_record_id,
                            ingested_at=now,
                            updated_at=now,
                        )
                    )
                    self._session.flush()
            except IntegrityError:
                skipped += 1
            else:
                inserted += 1
        return WriteCounts(inserted=inserted, skipped=skipped, invalid=invalid)

    def get(self, station_id: int, observed_at: datetime) -> MonitoringRecordView | None:
        row = self._session.scalar(
            select(MonitoringRecord).where(
                MonitoringRecord.station_id == station_id,
                MonitoringRecord.observed_at == observed_at,
            )
        )
        if row is None:
            return None
        return _view(row)

    def latest_observed_at(self, station_ids: Sequence[int]) -> datetime | None:
        if not station_ids:
            return None
        value = self._session.scalar(
            select(func.max(MonitoringRecord.observed_at)).where(
                MonitoringRecord.station_id.in_(tuple(station_ids))
            )
        )
        return value if isinstance(value, datetime) else None


def _invalid(record: MonitoringDraft) -> bool:
    if record.source not in MONITORING_SOURCES:
        return True
    if record.observed_at.tzinfo is None or record.observed_at.tzinfo.utcoffset(record.observed_at) is None:
        return True
    return any(_invalid_measurement(value) for value in (record.pm25, record.pm10, record.aqi))


def _invalid_measurement(value: float | None) -> bool:
    return value is not None and (not math.isfinite(value) or value < 0)


def _copy_mask(mask: Mapping[str, bool] | None) -> dict[str, bool] | None:
    if mask is None:
        return None
    return {str(key): bool(value) for key, value in mask.items()}


def _view(row: MonitoringRecord) -> MonitoringRecordView:
    return MonitoringRecordView(
        id=row.id,
        station_id=row.station_id,
        observed_at=row.observed_at,
        pm25=row.pm25,
        pm10=row.pm10,
        aqi=row.aqi,
        source=row.source,
        is_imputed=row.is_imputed,
        original_missing_mask=_copy_mask(_mask_dict(row.original_missing_mask)),
        provider_record_id=row.provider_record_id,
    )


def _mask_dict(value: object) -> dict[str, bool] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError("original_missing_mask must be a JSON object")
    return {str(key): bool(item) for key, item in value.items()}
