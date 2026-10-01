"""Supervision reports. An empty period does not create a file."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.adapters.exports.common import ExportMeta, ExportRow
from app.adapters.exports.report import write_report_pdf, write_report_xlsx
from app.core.errors import AppError, ErrorCode, get_request_id
from app.core.fonts import ChineseFontStatus
from app.domain.records import AuditDraft
from app.domain.repositories import AuditRepository


def build_report(
    rows: tuple[ExportRow, ...] | list[ExportRow],
    *,
    fmt: str,
    meta: ExportMeta,
    destination: Path,
    font: ChineseFontStatus | None,
    actor_id: int,
    audit: AuditRepository,
    now: datetime,
) -> Path:
    if not rows:
        raise AppError(ErrorCode.NO_MATCHING_DATA, "该周期无数据")
    if fmt == "xlsx":
        write_report_xlsx(destination, rows, meta)
    elif fmt == "pdf":
        if font is None:
            raise AppError(ErrorCode.CHINESE_FONT_UNAVAILABLE, "中文字体不可用")
        write_report_pdf(destination, rows, meta, font)
    else:
        raise AppError(ErrorCode.VALIDATION_ERROR, "报告格式无效")
    audit.append(
        AuditDraft(
            user_id=actor_id,
            action="REPORT_CREATED",
            object_type="report",
            object_id=fmt,
            request_id=get_request_id(),
            result="SUCCESS",
            details={"format": fmt, "query": meta.query, "user_id": str(actor_id)},
            ip_hash=None,
            created_at=now,
        )
    )
    return destination
