"""Property 6: monitoring writes are idempotent, including a unique-conflict race."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, City, MonitoringRecord, Station
from app.db.session import create_engine_from_url, session_factory, sqlite_file_url
from app.db.types import utc_now
from app.domain.records import MonitoringDraft, WriteCounts
from app.repositories.sqlalchemy.monitoring import SqlAlchemyMonitoringRepository

_BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)


@st.composite
def monitoring_cases(
    draw: st.DrawFn,
) -> tuple[list[tuple[int, int, int, int, int]], list[int], int]:
    count = draw(st.integers(min_value=1, max_value=8))
    records = [
        (
            draw(st.integers(min_value=0, max_value=2)),
            draw(st.integers(min_value=0, max_value=12)),
            draw(st.integers(min_value=0, max_value=500)),
            draw(st.integers(min_value=0, max_value=500)),
            draw(st.integers(min_value=0, max_value=500)),
        )
        for _ in range(count)
    ]
    order = list(draw(st.permutations(list(range(count)))))
    repeats = draw(st.integers(min_value=1, max_value=3))
    return records, order, repeats


@pytest.mark.property
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(monitoring_cases())
def test_monitoring_writes_keep_the_first_value(
    tmp_path: Path,
    case: tuple[list[tuple[int, int, int, int, int]], list[int], int],
) -> None:
    raw_records, order, repeats = case
    database = tmp_path / f"property6-{uuid.uuid4().hex}.db"
    engine = create_engine_from_url(sqlite_file_url(database))
    try:
        Base.metadata.create_all(engine)
        factory = session_factory(engine)
        station_ids = _create_stations(factory())
        drafts = [
            MonitoringDraft(
                station_id=station_ids[station_index],
                observed_at=_BASE + timedelta(hours=hour),
                pm25=float(pm25),
                pm10=float(pm10),
                aqi=float(aqi),
                source="ONLINE",
            )
            for station_index, hour, pm25, pm10, aqi in raw_records
        ]
        ordered = [drafts[index] for index in order]
        first: dict[tuple[int, datetime], MonitoringDraft] = {}
        for draft in ordered:
            first.setdefault((draft.station_id, draft.observed_at), draft)

        with factory() as session:
            first_result = SqlAlchemyMonitoringRepository(session).insert_batch(ordered)
            session.commit()
        assert first_result.inserted == len(first)
        assert first_result.skipped == len(ordered) - len(first)
        assert first_result.invalid == 0

        for _ in range(repeats):
            conflicts = [
                MonitoringDraft(
                    station_id=draft.station_id,
                    observed_at=draft.observed_at,
                    pm25=draft.pm25 + 1 if draft.pm25 is not None else None,
                    pm10=draft.pm10,
                    aqi=draft.aqi,
                    source="CSV",
                )
                for draft in ordered
            ]
            with factory() as session:
                replay = SqlAlchemyMonitoringRepository(session).insert_batch(conflicts)
                session.commit()
            assert replay == WriteCounts(inserted=0, skipped=len(conflicts), invalid=0)

        with factory() as session:
            for key, draft in first.items():
                stored = SqlAlchemyMonitoringRepository(session).get(*key)
                assert stored is not None
                assert (stored.pm25, stored.pm10, stored.aqi, stored.source) == (
                    draft.pm25,
                    draft.pm10,
                    draft.aqi,
                    draft.source,
                )

        _assert_concurrent_unique_conflict(factory, station_ids[0])
        with factory() as session:
            for key, draft in first.items():
                stored = SqlAlchemyMonitoringRepository(session).get(*key)
                assert stored is not None
                assert stored.pm25 == draft.pm25
    finally:
        engine.dispose()


def _create_stations(session: Session) -> list[int]:
    try:
        city = City(code="property-city", name_zh="属性城市", timezone="UTC", enabled=True, created_at=utc_now())
        session.add(city)
        session.flush()
        identifiers: list[int] = []
        for index in range(3):
            station = Station(
                city_id=city.id,
                code=f"s{index}",
                name_zh=f"站{index}",
                enabled=True,
                latitude=None,
                longitude=None,
                provider_metadata=None,
            )
            session.add(station)
            session.flush()
            identifiers.append(station.id)
        session.commit()
        return identifiers
    finally:
        session.close()


def _assert_concurrent_unique_conflict(
    factory: sessionmaker[Session],
    station_id: int,
) -> None:
    observed_at = _BASE + timedelta(hours=1000)
    variants = (
        MonitoringDraft(station_id, observed_at, 1, 3, 4, "ONLINE"),
        MonitoringDraft(station_id, observed_at, 2, 3, 4, "ONLINE"),
    )
    barrier = threading.Barrier(2)
    results: list[WriteCounts] = []
    errors: list[BaseException] = []

    def worker(draft: MonitoringDraft) -> None:
        try:
            with factory() as session:
                repository = SqlAlchemyMonitoringRepository(
                    session,
                    before_insert=lambda: barrier.wait(timeout=10),
                )
                results.append(repository.insert_batch((draft,)))
                session.commit()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(draft,)) for draft in variants]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()
    assert errors == []
    assert sum(result.inserted for result in results) == 1
    assert sum(result.skipped for result in results) == 1

    with factory() as session:
        rows = session.scalars(
            select(MonitoringRecord).where(
                MonitoringRecord.station_id == station_id,
                MonitoringRecord.observed_at == observed_at,
            )
        ).all()
        assert len(rows) == 1
        stored = (rows[0].pm25, rows[0].pm10, rows[0].aqi, rows[0].source)
        assert stored in {(1, 3, 4, "ONLINE"), (2, 3, 4, "ONLINE")}
