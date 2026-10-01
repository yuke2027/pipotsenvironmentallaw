"""Rows and metadata shared by CSV, Excel, PDF, and supervision reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.services.risk import DISCLAIMER

TRACE_COLUMNS: tuple[str, ...] = (
    "exported_at",
    "timezone",
    "query",
    "city",
    "station",
    "pollutant",
    "value",
    "source",
    "is_imputed",
    "legal_article",
    "standard_version",
    "penalty_estimate",
    "disclaimer",
)


@dataclass(frozen=True)
class ExportRow:
    city: str
    station: str
    pollutant: str
    value: str
    source: str
    is_imputed: bool
    legal_article: str
    standard_version: str
    penalty_estimate: str | None
    measured_count: int = 0
    imputed_count: int = 0
    recommendation: str = ""


@dataclass(frozen=True)
class ExportMeta:
    exported_at: datetime
    timezone: str
    query: str
    method: str = "supervision-export"
    period: str = ""


def row_values(row: ExportRow, meta: ExportMeta) -> list[str]:
    disclaimer = DISCLAIMER if row.penalty_estimate else ""
    return [
        meta.exported_at.isoformat(),
        meta.timezone,
        meta.query,
        row.city,
        row.station,
        row.pollutant,
        row.value,
        row.source,
        "插补" if row.is_imputed else "实测",
        row.legal_article,
        row.standard_version,
        row.penalty_estimate or "",
        disclaimer,
    ]
