"""Empty exports and reports must not create files."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.adapters.exports.common import ExportMeta
from app.core.errors import AppError, ErrorCode
from app.domain.query_spec import validate_time_range
from app.services.exports import export_dataset
from app.services.reports import build_report
from tests.support.memory_auth import MemoryAuditRepository

_NOW = datetime(2026, 7, 2, tzinfo=timezone.utc)


@pytest.mark.unit
def test_empty_export_and_empty_report_create_no_file(tmp_path: Path) -> None:
    audit = MemoryAuditRepository()
    meta = ExportMeta(exported_at=_NOW, timezone="Asia/Shanghai", query="city=北京")
    export_path = tmp_path / "empty.csv"
    with pytest.raises(AppError) as export_error:
        export_dataset([], fmt="csv", meta=meta, destination=export_path, font=None, actor_id=1, audit=audit, now=_NOW)
    assert export_error.value.code == ErrorCode.NO_MATCHING_DATA
    assert not export_path.exists()
    report_path = tmp_path / "empty.xlsx"
    with pytest.raises(AppError) as report_error:
        build_report([], fmt="xlsx", meta=meta, destination=report_path, font=None, actor_id=1, audit=audit, now=_NOW)
    assert report_error.value.code == ErrorCode.NO_MATCHING_DATA
    assert not report_path.exists()
    start = _NOW
    validate_time_range(start, start, timedelta(days=31))
    validate_time_range(start, start + timedelta(days=31), timedelta(days=31))
