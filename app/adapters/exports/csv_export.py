"""UTF-8 BOM CSV export."""

from __future__ import annotations

import csv
from pathlib import Path

from app.adapters.exports.common import TRACE_COLUMNS, ExportMeta, ExportRow, row_values


def write_csv(path: Path, rows: tuple[ExportRow, ...] | list[ExportRow], meta: ExportMeta) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(TRACE_COLUMNS)
        for row in rows:
            writer.writerow(row_values(row, meta))
    temporary.replace(path)
