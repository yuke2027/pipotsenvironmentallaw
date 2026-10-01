"""City and station lookups used by collection. No business rules live here."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import City, Station
from app.domain.records import StationRef


class SqlAlchemyCatalogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def stations_for_city(self, city_name: str) -> tuple[StationRef, ...]:
        rows = self._session.execute(
            select(Station, City.name_zh)
            .join(City, Station.city_id == City.id)
            .where(City.name_zh == city_name, Station.enabled.is_(True))
            .order_by(Station.id)
        ).all()
        return tuple(
            StationRef(id=station.id, code=station.code, name_zh=station.name_zh, city_name=city_name)
            for station, city_name in rows
        )
