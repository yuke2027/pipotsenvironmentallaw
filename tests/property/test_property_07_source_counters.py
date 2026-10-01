"""Property 7: source flags and ingest counters stay aligned."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.enums import MONITORING_SOURCES
from app.domain.records import MonitoringDraft, WriteCounts
from app.services.collection import ingest

_BASE = datetime(2026, 3, 1, tzinfo=timezone.utc)


class _MemoryMonitoring:
    def __init__(self) -> None:
        self.rows: dict[tuple[int, datetime], MonitoringDraft] = {}

    def insert_batch(self, records: list[MonitoringDraft]) -> WriteCounts:
        inserted = skipped = invalid = 0
        for record in records:
            if record.source not in MONITORING_SOURCES or _bad(record):
                invalid += 1
                continue
            key = (record.station_id, record.observed_at)
            if key in self.rows:
                skipped += 1
                continue
            self.rows[key] = record
            inserted += 1
        return WriteCounts(inserted=inserted, skipped=skipped, invalid=invalid)

    def get(self, station_id: int, observed_at: datetime) -> MonitoringDraft | None:
        return self.rows.get((station_id, observed_at))

    def latest_observed_at(self, station_ids: tuple[int, ...]) -> datetime | None:
        del station_ids
        return None


def _bad(record: MonitoringDraft) -> bool:
    return any(value is not None and value < 0 for value in (record.pm25, record.pm10, record.aqi))


@given(
    source=st.sampled_from(MONITORING_SOURCES),
    values=st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=2),
            st.integers(min_value=0, max_value=4),
            st.integers(min_value=-1, max_value=5),
        ),
        min_size=1,
        max_size=8,
    ),
)
@pytest.mark.property
def test_property_07_source_and_counters_match(
    source: str,
    values: list[tuple[int, int, int]],
) -> None:
    """Stored source matches the entry point and received equals the repository split.

    **Feature: environmental-supervision-platform, Property 7: 来源与计数可追溯**
    **Property 7：来源与计数可追溯**
    **Validates: Requirements 2.8, 2.9**
    """

    drafts = [
        MonitoringDraft(
            station_id=station_id,
            observed_at=_BASE + timedelta(minutes=minute),
            pm25=float(reading),
            pm10=1,
            aqi=1,
            source="ONLINE",
            is_imputed=False,
        )
        for station_id, minute, reading in values
    ]
    monitoring = _MemoryMonitoring()
    handler = _Handler()
    logger = logging.getLogger("app.services.collection")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        report = ingest(drafts, monitoring, source=source)  # type: ignore[arg-type]
    finally:
        logger.removeHandler(handler)
    assert report.received == report.counts.inserted + report.counts.skipped + report.counts.invalid
    matching = [record for record in handler.records if getattr(record, "event", None) == "INGEST_COUNTS"]
    assert matching
    last = matching[-1]
    assert last.received == report.received
    assert last.inserted == report.counts.inserted
    assert last.skipped == report.counts.skipped
    assert last.invalid == report.counts.invalid
    assert last.source == source
    for stored in monitoring.rows.values():
        assert stored.source == source
        assert stored.is_imputed is (source == "IMPUTED")


class _Handler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
