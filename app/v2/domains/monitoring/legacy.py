"""Compatibility query facade for legacy export tasks.

New HTTP routes use ``MonitoringService``.  This adapter remains temporarily
available for export jobs that need to compose the observation statement.
"""

from datetime import date

from typing import Any

from sqlalchemy import Select, select

from app.v2.shared.http_errors import ErrorCode
from app.v2.common import fail
from app.v2.domains.collection.models import SourceFile
from app.v2.domains.monitoring.models import Observation, Station


def filtered(start: date | None, end: date | None, station_id: str | None = None,
             pollutant: str | None = None, city_id: str | None = None,
             basis: str = "hourly") -> Select[Any]:
    if start and end and (end < start or (end - start).days > 731):
        fail("查询时间顺序错误或超过两年", ErrorCode.INVALID_TIME_RANGE)
    statement = select(Observation).join(SourceFile).join(
        Station, Observation.station_id == Station.id
    ).where(SourceFile.is_current.is_(True))
    if start:
        statement = statement.where(Observation.local_date >= start)
    if end:
        statement = statement.where(Observation.local_date <= end)
    if station_id:
        statement = statement.where(Observation.station_id == station_id)
    if city_id:
        statement = statement.where(Station.city_id == city_id)
    if pollutant:
        statement = statement.where(Observation.pollutant == pollutant)
    return statement.where(Observation.basis == ("source_aqi" if pollutant == "AQI" else basis))
