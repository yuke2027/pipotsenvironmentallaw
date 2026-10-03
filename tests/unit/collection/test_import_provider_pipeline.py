"""Example tests for CNEMC parsing, CSV isolation, and one scheduler pass."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from app.adapters.http.retry import ExternalCaller, StepClock
from app.adapters.providers.cnemc import CNEMCPublicProvider
from app.legacy_cli import build_parser, resolve_import_directory
from app.core.paths import PathSettings
from app.db.models import City, Station
from app.db.types import utc_now
from app.domain.records import WriteCounts
from app.repositories.sqlalchemy.catalog import SqlAlchemyCatalogRepository
from app.repositories.sqlalchemy.monitoring import SqlAlchemyMonitoringRepository
from app.scheduler.jobs import STEP_NAMES, failure, success
from app.scheduler.pipeline import Pipeline, build_scheduler
from app.services.collection import CollectionService
from app.services.csv_import import CsvImporter
from tests.support.auth_factory import auth_settings, migrated_factory

_WHEN = datetime(2026, 1, 1, tzinfo=timezone.utc)
_GOOD = """date,hour,type,东城
20250101,0,PM2.5,10
20250101,0,PM10,20
20250101,0,AQI,30
"""


class _Mem:
    def __init__(self) -> None:
        self.rows: list[object] = []

    def latest_observed_at(self, station_ids: tuple[int, ...]) -> datetime | None:
        del station_ids
        return _WHEN

    def insert_batch(self, records: list[object]) -> WriteCounts:
        self.rows.extend(records)
        return WriteCounts(inserted=len(records), skipped=0, invalid=0)

    def get(self, station_id: int, observed_at: datetime) -> None:
        del station_id, observed_at
        return None


class _Cities:
    def stations_for_city(self, city_name: str) -> tuple[object, ...]:
        from app.domain.records import StationRef

        if city_name != "北京":
            return ()
        return (StationRef(1, "S1", "东城", "北京"),)


@pytest.mark.unit
def test_cnemc_mock_transport_maps_known_stations_and_counts_invalid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["city"] == "北京"
        assert "example.test" in str(request.url)
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "observations": [
                    {
                        "station_code": "S1",
                        "observed_at": "2026-01-02T00:00:00+00:00",
                        "pm25": 1,
                        "pm10": 2,
                        "aqi": 3,
                    },
                    {
                        "station_code": "UNKNOWN",
                        "observed_at": "2026-01-02T00:00:00+00:00",
                        "pm25": 1,
                        "pm10": 2,
                        "aqi": 3,
                    },
                    {
                        "station_code": "S1",
                        "observed_at": "2026-01-02T01:00:00+00:00",
                        "pm25": -1,
                        "pm10": 2,
                        "aqi": 3,
                    },
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = CNEMCPublicProvider(
        enabled=True,
        endpoint="https://example.test/air",
        schema_version=1,
        client=client,
        credential_ref="cnemc",
        secrets={"cnemc": "secret-value"},
    )
    monitoring = _Mem()
    report = CollectionService(
        monitoring,  # type: ignore[arg-type]
        _Cities(),  # type: ignore[arg-type]
        provider,
        ExternalCaller(StepClock(), min_interval_seconds=0, base_delay_seconds=0),
        auth_settings(target_cities=("北京",)),
    ).collect()
    assert len(monitoring.rows) == 1
    assert report.ingest.counts.invalid == 2
    assert provider.health().ok is True
    disabled = CNEMCPublicProvider(enabled=False, endpoint=None, schema_version=1, client=client)
    assert disabled.health().detail == "disabled"
    called = {"count": 0}

    def forbidden(request: httpx.Request) -> httpx.Response:
        del request
        called["count"] += 1
        return httpx.Response(500)

    blocked = httpx.Client(transport=httpx.MockTransport(forbidden))
    quiet = CNEMCPublicProvider(enabled=False, endpoint="https://example.test/air", schema_version=1, client=blocked)
    with pytest.raises(Exception):
        quiet.fetch("北京", None)
    assert called["count"] == 0


@pytest.mark.unit
def test_csv_examples_cover_empty_bad_duplicate_and_data1_names(tmp_path: Path) -> None:
    factory, engine = migrated_factory(tmp_path)
    try:
        with factory() as session:
            city = City(code="110000", name_zh="北京", timezone="Asia/Shanghai", enabled=True, created_at=utc_now())
            session.add(city)
            session.flush()
            station = Station(
                city_id=city.id,
                code="S1",
                name_zh="东城",
                enabled=True,
            )
            session.add(station)
            session.commit()
            station_id = station.id
            monitoring = SqlAlchemyMonitoringRepository(session)
            importer = CsvImporter(monitoring, {"东城": station_id, "S1": station_id})
            empty = tmp_path / "empty"
            empty.mkdir()
            assert importer.import_directory(empty, allowed_stations={"东城"}).files_seen == 0
            mixed = tmp_path / "mixed"
            mixed.mkdir()
            (mixed / "data1.csv").write_text(_GOOD, encoding="utf-8")
            (mixed / "data1-again.csv").write_text(_GOOD, encoding="utf-8")
            (mixed / "missing.csv").write_text("date,hour,东城\n20250101,0,1\n", encoding="utf-8")
            (mixed / "extra.csv").write_text(
                "date,hour,type,东城,EXTRA\n20250101,1,PM2.5,1,1\n20250101,1,PM10,1,1\n20250101,1,AQI,1,1\n",
                encoding="utf-8",
            )
            report = importer.import_directory(mixed, allowed_stations={"东城"})
            session.commit()
            assert report.files_seen == 4
            assert report.inserted == 1
            assert report.skipped == 1
            assert any(item.name == "missing.csv" and "type" in item.missing_columns for item in report.files)
            assert any(item.name == "extra.csv" and "EXTRA" in item.extra_columns for item in report.files)
            stored = monitoring.get(station_id, monitoring.latest_observed_at((station_id,)) or _WHEN)
            assert stored is not None
            assert stored.source == "CSV"
            assert stored.is_imputed is False
            assert SqlAlchemyCatalogRepository(session).stations_for_city("北京")[0].name_zh == "东城"
    finally:
        engine.dispose()


@pytest.mark.unit
def test_pipeline_runs_once_and_scheduler_uses_the_configured_interval() -> None:
    calls: list[str] = []

    def step(name: str, outcome: str) -> object:
        def run() -> object:
            calls.append(name)
            if outcome == "fail":
                return failure("stopped")
            return success(no_op=True)

        return run

    steps = {name: step(name, "fail" if name == "risk" else "ok") for name in STEP_NAMES}
    pipeline = Pipeline(steps)  # type: ignore[arg-type]
    result = pipeline.run_once()
    assert result.executed == ("collect", "impute", "compliance", "risk")
    assert result.failed_step == "risk"
    scheduler = build_scheduler(pipeline, 3600)
    job = scheduler.get_job("supervision-pipeline")
    assert job is not None
    assert isinstance(scheduler, BackgroundScheduler)
    parser = build_parser()
    parsed = parser.parse_args(["import-csv", "--directory", "data1"])
    assert parsed.directory == "data1"
    paths = PathSettings.from_settings(auth_settings(project_root=Path("E:/pipotsenvironmentallaw/pipotsenvironmentallaw")))
    resolved = resolve_import_directory(paths, "incoming")
    assert resolved.parent == paths.data_dir
