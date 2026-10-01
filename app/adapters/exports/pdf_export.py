"""Chinese PDF export. The caller supplies one already resolved font file."""

from __future__ import annotations

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.adapters.exports.common import ExportMeta, ExportRow, row_values
from app.core.errors import AppError, ErrorCode
from app.core.fonts import ChineseFontStatus
from app.services.risk import DISCLAIMER


def write_pdf(
    path: Path,
    rows: tuple[ExportRow, ...] | list[ExportRow],
    meta: ExportMeta,
    font: ChineseFontStatus,
) -> None:
    if not font.available or font.path is None or font.reportlab_font_name is None:
        raise AppError(ErrorCode.CHINESE_FONT_UNAVAILABLE, "中文字体不可用")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    pdfmetrics.registerFont(TTFont(font.reportlab_font_name, str(font.path)))
    drawing = canvas.Canvas(str(temporary), pageCompression=0)
    joined = "\n".join(" | ".join(row_values(row, meta)) for row in rows)
    drawing.setTitle(meta.query)
    drawing.setSubject(f"{DISCLAIMER} {meta.method} {meta.period}")
    drawing.setKeywords(joined)
    drawing.setFont(font.reportlab_font_name, 10)
    drawing.drawString(40, 820, f"导出时间 {meta.exported_at.isoformat()} 时区 {meta.timezone}")
    drawing.drawString(40, 804, f"查询条件 {meta.query}")
    drawing.drawString(40, 788, f"方法 {meta.method}")
    top = 760
    for row in rows:
        values = row_values(row, meta)
        line = " | ".join(values)
        drawing.drawString(40, top, line)
        top -= 14
        if top < 80:
            drawing.showPage()
            drawing.setFont(font.reportlab_font_name, 10)
            top = 800
    drawing.drawString(40, 48, DISCLAIMER)
    drawing.save()
    temporary.replace(path)
