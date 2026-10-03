"""ORM definitions owned by the monitoring domain; table names remain v2-compatible."""

from __future__ import annotations

from typing import Any
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.types import UtcDateTime
from app.v2.shared.persistence import Base, Entity


class City(Entity, Base):
    __tablename__ = "v2_cities"
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Shanghai")


class Station(Entity, Base):
    __tablename__ = "v2_stations"
    __table_args__ = (UniqueConstraint("city_id", "code"),)
    city_id: Mapped[str] = mapped_column(ForeignKey("v2_cities.id"), index=True)
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class StationAlias(Entity, Base):
    __tablename__ = "v2_station_aliases"
    __table_args__ = (UniqueConstraint("provider", "external_name", "valid_from"),)
    station_id: Mapped[str] = mapped_column(ForeignKey("v2_stations.id"))
    provider: Mapped[str] = mapped_column(String(50), default="quotsoft")
    external_name: Mapped[str] = mapped_column(String(100))
    valid_from: Mapped[date] = mapped_column(Date, default=date(2013, 1, 1))
    valid_to: Mapped[date | None] = mapped_column(Date)


class Observation(Entity, Base):
    __tablename__ = "v2_observations"
    __table_args__ = (
        UniqueConstraint("source_file_id", "station_id", "observed_at", "pollutant", "basis"),
        Index("ix_v2_obs_station_pollutant_time", "station_id", "pollutant", "observed_at"),
        Index("ix_v2_obs_time_pollutant", "observed_at", "pollutant"),
        Index("ix_v2_obs_date_basis_pollutant", "local_date", "basis", "pollutant", "station_id"),
    )
    source_file_id: Mapped[str] = mapped_column(ForeignKey("v2_source_files.id"), index=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("v2_stations.id"))
    observed_at: Mapped[datetime] = mapped_column(UtcDateTime)
    local_date: Mapped[date] = mapped_column(Date, index=True)
    pollutant: Mapped[str] = mapped_column(String(16))
    basis: Mapped[str] = mapped_column(String(24), default="hourly")
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    quality: Mapped[str] = mapped_column(String(20), default="valid")


class Standard(Entity, Base):
    __tablename__ = "v2_standards"
    __table_args__ = (UniqueConstraint("code", "pollutant", "basis", "grade", "effective_from"),)
    code: Mapped[str] = mapped_column(String(80))
    pollutant: Mapped[str] = mapped_column(String(16))
    basis: Mapped[str] = mapped_column(String(24))
    grade: Mapped[str] = mapped_column(String(16), default="二级")
    region: Mapped[str] = mapped_column(String(80), default="全国")
    limit_value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    min_points: Mapped[int] = mapped_column(Integer, default=20)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text)
    article: Mapped[str] = mapped_column(Text, default="表1")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Evaluation(Entity, Base):
    __tablename__ = "v2_evaluations"
    __table_args__ = (UniqueConstraint("station_id", "local_date", "pollutant", "basis", "snapshot_hash", "standard_id"),)
    station_id: Mapped[str] = mapped_column(ForeignKey("v2_stations.id"), index=True)
    local_date: Mapped[date] = mapped_column(Date, index=True)
    pollutant: Mapped[str] = mapped_column(String(16))
    basis: Mapped[str] = mapped_column(String(24))
    standard_id: Mapped[str] = mapped_column(ForeignKey("v2_standards.id"))
    standard_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    valid_points: Mapped[int] = mapped_column(Integer)
    value: Mapped[float | None] = mapped_column(Float)
    exceed_ratio: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    job_id: Mapped[str | None] = mapped_column(String(36))


class AQIResult(Entity, Base):
    __tablename__ = "v2_aqi_results"
    __table_args__ = (UniqueConstraint("station_id", "local_date", "snapshot_hash", "version"),)
    station_id: Mapped[str] = mapped_column(ForeignKey("v2_stations.id"))
    local_date: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[int | None] = mapped_column(Integer)
    components: Mapped[dict[str, Any]] = mapped_column(JSON)
    complete: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[str] = mapped_column(String(32))
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ['City', 'Station', 'StationAlias', 'Observation', 'Standard', 'Evaluation', 'AQIResult']
