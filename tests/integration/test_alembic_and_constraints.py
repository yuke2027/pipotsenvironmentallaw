"""Alembic baseline, repeat upgrade, backup, and constraint checks on tmp SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.db.migration_policy import SQLITE_RENDER_AS_BATCH
from app.db.models import Base, City, MonitoringRecord, Station
from app.db.session import SQLITE_BUSY_TIMEOUT_MS, create_engine_from_url, session_factory, sqlite_file_url
from app.db.types import utc_now
from app.db.upgrade import current_revision, upgrade_database

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _schema(path: Path) -> list[tuple[str, str, str | None]]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
    finally:
        connection.close()
    return [(str(row[0]), str(row[1]), None if row[2] is None else str(row[2])) for row in rows]


def _table_names(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    finally:
        connection.close()
    return {str(row[0]) for row in rows}


@pytest.mark.integration
def test_empty_database_upgrades_to_head(tmp_path: Path) -> None:
    database = tmp_path / "empty.db"
    url = sqlite_file_url(database)
    backup = upgrade_database(url, backup_directory=tmp_path / "backups")

    assert backup is None
    assert current_revision(url) == "0002_baseline"
    assert set(Base.metadata.tables) <= _table_names(database)


@pytest.mark.integration
def test_repeat_upgrade_leaves_schema_unchanged(tmp_path: Path) -> None:
    url = sqlite_file_url(tmp_path / "repeat.db")
    upgrade_database(url, backup_directory=tmp_path / "backups")
    before = _schema(tmp_path / "repeat.db")

    backup = upgrade_database(url, backup_directory=tmp_path / "backups")

    assert backup is None
    assert _schema(tmp_path / "repeat.db") == before
    assert current_revision(url) == "0002_baseline"


@pytest.mark.integration
def test_existing_database_is_backed_up_before_upgrade(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    url = sqlite_file_url(database)
    upgrade_database(url, backup_directory=tmp_path / "ignored", revision="0001_empty")
    assert current_revision(url) == "0001_empty"
    assert "monitoring_records" not in _table_names(database)

    backup = upgrade_database(url, backup_directory=tmp_path / "backups")

    assert backup is not None
    assert backup.parent == tmp_path / "backups"
    assert current_revision(sqlite_file_url(backup)) == "0001_empty"
    assert "monitoring_records" not in _table_names(backup)
    assert current_revision(url) == "0002_baseline"
    assert "monitoring_records" in _table_names(database)


@pytest.mark.integration
def test_sqlite_pragmas_checks_and_restricted_deletes(tmp_path: Path) -> None:
    url = sqlite_file_url(tmp_path / "constraints.db")
    upgrade_database(url, backup_directory=tmp_path / "backups")
    engine = create_engine_from_url(url)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert str(connection.exec_driver_sql("PRAGMA journal_mode").scalar()).lower() == "wal"
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == SQLITE_BUSY_TIMEOUT_MS
            assert SQLITE_BUSY_TIMEOUT_MS > 0

        inspector = inspect(engine)
        unique_sets = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("monitoring_records")
        }
        unique_sets.update(
            tuple(item["column_names"])
            for item in inspector.get_indexes("monitoring_records")
            if item["unique"]
        )
        assert ("station_id", "observed_at") in unique_sets
        check_names = {item["name"] for item in inspector.get_check_constraints("monitoring_records")}
        assert "ck_monitoring_pm25_nonnegative" in check_names
        assert "ck_legal_standards_limit_positive" in {
            item["name"] for item in inspector.get_check_constraints("legal_standards")
        }
        assert "ck_forecast_results_probability" in {
            item["name"] for item in inspector.get_check_constraints("forecast_results")
        }
        referred = {item["referred_table"] for item in inspector.get_foreign_keys("stations")}
        assert referred == {"cities"}

        factory = session_factory(engine)
        with factory() as session:
            city = City(code="beijing", name_zh="北京", timezone="UTC", enabled=True, created_at=utc_now())
            session.add(city)
            session.flush()
            station = Station(
                city_id=city.id,
                code="station-a",
                name_zh="站A",
                enabled=True,
                latitude=None,
                longitude=None,
                provider_metadata=None,
            )
            session.add(station)
            session.commit()
            city_id = city.id
            station_id = station.id

        with factory() as session:
            session.add(_monitoring(station_id, pm25=-1.0))
            with pytest.raises(IntegrityError):
                session.commit()

        with factory() as session:
            session.add(_monitoring(station_id + 999, pm25=1.0))
            with pytest.raises(IntegrityError):
                session.commit()

        with factory() as session:
            persisted = session.get(City, city_id)
            assert persisted is not None
            session.delete(persisted)
            with pytest.raises(IntegrityError):
                session.commit()
        with factory() as session:
            assert session.scalar(select(Station).where(Station.id == station_id)) is not None
    finally:
        engine.dispose()


@pytest.mark.integration
def test_upgrade_refuses_the_production_database_name(tmp_path: Path) -> None:
    url = sqlite_file_url(tmp_path / "environmental_supervision.db")
    with pytest.raises(RuntimeError, match="production"):
        upgrade_database(url, backup_directory=tmp_path / "backups")
    assert not (tmp_path / "environmental_supervision.db").exists()


@pytest.mark.integration
def test_business_models_keep_sqlite_policy_out_of_schema_sql() -> None:
    env_source = (_PROJECT_ROOT / "app" / "db" / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "render_as_batch=SQLITE_RENDER_AS_BATCH" in env_source
    assert SQLITE_RENDER_AS_BATCH is True
    for path in (_PROJECT_ROOT / "app" / "db" / "models").rglob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        assert "pragma " not in source
        assert "dialects.sqlite" not in source


def _monitoring(station_id: int, *, pm25: float) -> MonitoringRecord:
    now = utc_now()
    return MonitoringRecord(
        station_id=station_id,
        observed_at=now,
        pm25=pm25,
        pm10=1.0,
        aqi=1.0,
        source="ONLINE",
        is_imputed=False,
        original_missing_mask=None,
        provider_record_id=None,
        ingested_at=now,
        updated_at=now,
    )
