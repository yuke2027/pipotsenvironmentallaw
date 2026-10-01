"""Property 10: a bad CSV does not block a good one, and totals add up."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.records import WriteCounts
from app.services.csv_import import CsvImporter

_GOOD = """date,hour,type,S1
20250101,0,PM2.5,10
20250101,0,PM10,20
20250101,0,AQI,30
"""
_MISSING = """date,hour,S1
20250101,0,10
"""
_EXTRA = """date,hour,type,S1,EXTRA
20250101,0,PM2.5,10,1
20250101,0,PM10,20,1
20250101,0,AQI,30,1
"""


class _MemoryMonitoring:
    def __init__(self) -> None:
        self.rows: dict[tuple[int, datetime], object] = {}

    def insert_batch(self, records: list[object]) -> WriteCounts:
        inserted = skipped = 0
        for record in records:
            key = (getattr(record, "station_id"), getattr(record, "observed_at"))
            if key in self.rows:
                skipped += 1
                continue
            self.rows[key] = record
            inserted += 1
        return WriteCounts(inserted=inserted, skipped=skipped, invalid=0)

    def get(self, station_id: int, observed_at: datetime) -> object | None:
        return self.rows.get((station_id, observed_at))

    def latest_observed_at(self, station_ids: tuple[int, ...]) -> None:
        del station_ids
        return None


@given(
    good_files=st.integers(min_value=1, max_value=2),
    include_missing=st.booleans(),
    include_extra=st.booleans(),
)
@pytest.mark.property
def test_property_10_bad_files_are_isolated(good_files: int, include_missing: bool, include_extra: bool) -> None:
    """Bad files are reported and do not stop later files; totals match the file results.

    **Feature: environmental-supervision-platform, Property 10: 坏文件隔离与导入守恒**
    **Property 10：坏文件隔离与导入守恒**
    **Validates: Requirements 3.5, 3.6, 15.4**
    """

    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        for index in range(good_files):
            (root / f"good-{index}.csv").write_text(_GOOD, encoding="utf-8")
        if include_missing:
            (root / "missing-type.csv").write_text(_MISSING, encoding="utf-8")
        if include_extra:
            (root / "extra-column.csv").write_text(_EXTRA, encoding="utf-8")
        report = CsvImporter(_MemoryMonitoring(), {"S1": 1}).import_directory(  # type: ignore[arg-type]
            root,
            allowed_stations={"S1"},
        )
    assert report.files_seen == good_files + int(include_missing) + int(include_extra)
    assert report.inserted == sum(item.inserted for item in report.files)
    assert report.skipped == sum(item.skipped for item in report.files)
    assert report.invalid == sum(item.invalid for item in report.files)
    good = [item for item in report.files if item.error is None]
    assert good
    assert all(item.inserted + item.skipped == 1 for item in good)
    if include_missing:
        missing = next(item for item in report.files if item.name == "missing-type.csv")
        assert missing.error == "column mismatch"
        assert "type" in missing.missing_columns
    if include_extra:
        extra = next(item for item in report.files if item.name == "extra-column.csv")
        assert extra.error == "column mismatch"
        assert "EXTRA" in extra.extra_columns
    assert any(item.inserted > 0 for item in good)
