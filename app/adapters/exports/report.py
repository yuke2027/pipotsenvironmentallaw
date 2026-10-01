"""Supervision report workbooks and PDFs."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from app.adapters.exports.common import ExportMeta, ExportRow
from app.adapters.exports.pdf_export import write_pdf
from app.services.risk import DISCLAIMER


def report_lines(rows: tuple[ExportRow, ...] | list[ExportRow], meta: ExportMeta) -> list[str]:
    measured = sum(row.measured_count for row in rows)
    imputed = sum(row.imputed_count for row in rows)
    lines = [
        f"统计周期 {meta.period or meta.query}",
        f"生成时间 {meta.exported_at.isoformat()}",
        f"时区 {meta.timezone}",
        f"方法 {meta.method}",
        f"实测点数 {measured}",
        f"插补点数 {imputed}",
    ]
    for row in rows:
        lines.append(
            " ".join(
                (
                    row.city,
                    row.station,
                    row.pollutant,
                    f"来源{row.source}",
                    "插补" if row.is_imputed else "实测",
                    row.legal_article,
                    row.standard_version,
                    row.recommendation,
                    row.penalty_estimate or "",
                    DISCLAIMER if row.penalty_estimate else "",
                )
            )
        )
    lines.append(DISCLAIMER)
    return lines


def write_report_xlsx(path: Path, rows: tuple[ExportRow, ...] | list[ExportRow], meta: ExportMeta) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "监督报告"
    for line in report_lines(rows, meta):
        sheet.append([line])
    temporary = path.with_suffix(path.suffix + ".partial")
    workbook.save(temporary)
    temporary.replace(path)


def write_report_pdf(
    path: Path,
    rows: tuple[ExportRow, ...] | list[ExportRow],
    meta: ExportMeta,
    font: object,
) -> None:
    from app.core.fonts import ChineseFontStatus

    if not isinstance(font, ChineseFontStatus):
        raise TypeError("font status is required")
    summary = ExportRow(
        city="汇总",
        station="全部",
        pollutant="综合",
        value=" ".join(report_lines(rows, meta)),
        source="MIXED",
        is_imputed=any(row.is_imputed for row in rows),
        legal_article=rows[0].legal_article if rows else "",
        standard_version=rows[0].standard_version if rows else "",
        penalty_estimate=DISCLAIMER,
        recommendation=meta.method,
    )
    write_pdf(path, [summary], meta, font)
