"""Shared query specification for lists, exports, and reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.errors import AppError, ErrorCode, ErrorDetail


@dataclass(frozen=True)
class QuerySpec:
    start: datetime
    end: datetime
    city: str | None = None
    station_id: int | None = None
    pollutant: str | None = None
    source: str | None = None
    is_imputed: bool | None = None
    alert_status: str | None = None
    risk_level: str | None = None

    def describe(self) -> str:
        return (
            f"start={self.start.isoformat()};end={self.end.isoformat()};"
            f"city={self.city or ''};station_id={self.station_id or ''};"
            f"pollutant={self.pollutant or ''};source={self.source or ''};"
            f"is_imputed={self.is_imputed};alert_status={self.alert_status or ''};"
            f"risk_level={self.risk_level or ''}"
        )


def validate_time_range(start: datetime, end: datetime, max_span: timedelta) -> None:
    """Reject an inverted range or a span past the configured maximum.

    A span equal to the maximum is allowed. The error names ``start_time`` or
    the maximum allowed span.
    """

    if start.tzinfo is None or end.tzinfo is None:
        raise AppError(
            ErrorCode.INVALID_TIME_RANGE,
            "时间必须包含时区",
            details=(ErrorDetail(field="start_time", reason="timezone-aware instants are required"),),
        )
    if start > end:
        raise AppError(
            ErrorCode.INVALID_TIME_RANGE,
            "开始时间不能晚于结束时间",
            details=(ErrorDetail(field="start_time", reason="start must be earlier than or equal to end"),),
        )
    if end - start > max_span:
        raise AppError(
            ErrorCode.TIME_RANGE_EXCEEDS_LIMIT,
            "查询跨度超过上限",
            details=(ErrorDetail(field="max_span", reason=f"{max_span.days} days"),),
        )
