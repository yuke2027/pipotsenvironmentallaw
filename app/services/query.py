"""Filter, stable sort, and paginate monitoring and alert rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TypeVar

from app.domain.query_spec import QuerySpec, validate_time_range
from app.domain.records import Page


@dataclass(frozen=True)
class MonitoringQueryRow:
    id: int
    city: str
    station_id: int
    observed_at: datetime
    pollutant: str
    value: float
    source: str
    is_imputed: bool


@dataclass(frozen=True)
class AlertQueryRow:
    id: int
    city: str
    station_id: int
    generated_at: datetime
    pollutant: str
    status: str
    risk_level: str


def query_monitoring(
    rows: tuple[MonitoringQueryRow, ...] | list[MonitoringQueryRow],
    spec: QuerySpec,
    *,
    page: int,
    page_size: int,
    max_span: timedelta,
) -> Page[MonitoringQueryRow]:
    validate_time_range(spec.start, spec.end, max_span)
    matched = [row for row in rows if _monitoring_matches(row, spec)]
    matched.sort(key=lambda row: (row.observed_at, row.id))
    return _page(matched, page, page_size)


def query_alerts(
    rows: tuple[AlertQueryRow, ...] | list[AlertQueryRow],
    spec: QuerySpec,
    *,
    page: int,
    page_size: int,
    max_span: timedelta,
) -> Page[AlertQueryRow]:
    validate_time_range(spec.start, spec.end, max_span)
    matched = [row for row in rows if _alert_matches(row, spec)]
    matched.sort(key=lambda row: (row.generated_at, row.id))
    return _page(matched, page, page_size)


def _monitoring_matches(row: MonitoringQueryRow, spec: QuerySpec) -> bool:
    if not spec.start <= row.observed_at <= spec.end:
        return False
    if spec.city is not None and row.city != spec.city:
        return False
    if spec.station_id is not None and row.station_id != spec.station_id:
        return False
    if spec.pollutant is not None and row.pollutant != spec.pollutant:
        return False
    if spec.source is not None and row.source != spec.source:
        return False
    if spec.is_imputed is not None and row.is_imputed != spec.is_imputed:
        return False
    return True


def _alert_matches(row: AlertQueryRow, spec: QuerySpec) -> bool:
    if not spec.start <= row.generated_at <= spec.end:
        return False
    if spec.city is not None and row.city != spec.city:
        return False
    if spec.station_id is not None and row.station_id != spec.station_id:
        return False
    if spec.pollutant is not None and row.pollutant != spec.pollutant:
        return False
    if spec.alert_status is not None and row.status != spec.alert_status:
        return False
    if spec.risk_level is not None and row.risk_level != spec.risk_level:
        return False
    return True


RowT = TypeVar("RowT")


def _page(items: list[RowT], page: int, page_size: int) -> Page[RowT]:
    if page < 1 or page_size < 1:
        raise ValueError("page and page_size must be positive")
    start = (page - 1) * page_size
    window = tuple(items[start : start + page_size])
    return Page(items=window, page=page, page_size=page_size, total=len(items))
