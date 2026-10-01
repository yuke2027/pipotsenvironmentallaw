"""Readable Excel export with a data sheet and a metadata sheet."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from app.adapters.exports.common import TRACE_COLUMNS, ExportMeta, ExportRow, row_values
from app.services.risk import DISCLAIMER


def write_xlsx(path: Path, rows: tuple[ExportRow, ...] | list[ExportRow], meta: ExportMeta) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    data = workbook.active
    data.title = "数据"
    data.append(list(TRACE_COLUMNS))
    for row in rows:
        data.append(row_values(row, meta))
    meta_sheet = workbook.create_sheet("元数据")
    meta_sheet.append(["exported_at", meta.exported_at.isoformat()])
    meta_sheet.append(["timezone", meta.timezone])
    meta_sheet.append(["query", meta.query])
    meta_sheet.append(["method", meta.method])
    meta_sheet.append(["period", meta.period])
    meta_sheet.append(["disclaimer", DISCLAIMER])
    temporary = path.with_suffix(path.suffix + ".partial")
    workbook.save(temporary)
    temporary.replace(path)
