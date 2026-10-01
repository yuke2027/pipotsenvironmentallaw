"""Reference data extracted from repository wide tables and initial legal values.

Pollutant limits and risk upper bounds exist only in this module.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.domain.enums import CRITICAL_RISK_LEVEL, RISK_LEVELS

WIDE_TABLE_GLOB = "beijing_all_*.csv"
WIDE_TABLE_BASE_COLUMNS = frozenset({"date", "hour", "type"})
EXPECTED_STATION_COUNT = 35
BEIJING_CITY_NAME = "北京"
BEIJING_TIMEZONE = "Asia/Shanghai"
INITIAL_ADMIN_USERNAME = "admin"
INITIAL_ADMIN_ROLE = "管理员"
LEGAL_EFFECTIVE_FROM = datetime(2016, 1, 1, tzinfo=timezone.utc)
RISK_THRESHOLD_VERSION = "1"


@dataclass(frozen=True)
class LegalStandardSeed:
    standard_key: str
    version: str
    pollutant: str
    statistic_basis: str
    limit_value: float
    unit: str
    legal_basis_name: str
    legal_article: str
    penalty_basis: str


@dataclass(frozen=True)
class RiskThresholdSeed:
    version: str
    level: str
    upper_bound: float | None
    description_zh: str


def default_wide_table_directory() -> Path:
    return Path(__file__).resolve().parents[2] / "data1"


def beijing_city_code(data_directory: Path) -> str:
    """Use the shared filename prefix of the Beijing wide tables as the city code."""

    paths = sorted(data_directory.glob(WIDE_TABLE_GLOB))
    if not paths:
        raise FileNotFoundError(f"no {WIDE_TABLE_GLOB} files in {data_directory}")
    prefix, separator, _rest = paths[0].name.partition("_all_")
    if not separator or not prefix:
        raise ValueError(f"unexpected wide-table name: {paths[0].name}")
    return prefix


def extract_beijing_station_names(data_directory: Path) -> tuple[str, ...]:
    """Read station columns from existing wide-table headers.

    Every ``beijing_all_*.csv`` file must share one header. Names are the
    columns other than date, hour, and type, in file order.
    """

    paths = sorted(data_directory.glob(WIDE_TABLE_GLOB))
    if not paths:
        raise FileNotFoundError(f"no {WIDE_TABLE_GLOB} files in {data_directory}")
    headers: list[tuple[str, ...]] = []
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            columns = tuple(next(csv.reader(handle)))
        headers.append(columns)
    first = headers[0]
    if any(header != first for header in headers[1:]):
        raise ValueError("beijing_all wide tables do not share one station header")
    names = tuple(column for column in first if column not in WIDE_TABLE_BASE_COLUMNS)
    if len(names) != EXPECTED_STATION_COUNT:
        raise ValueError(f"expected {EXPECTED_STATION_COUNT} station columns, found {len(names)}")
    if len(set(names)) != len(names):
        raise ValueError("wide-table station columns are not unique")
    return names


_GB = "GB 3095-2012"
_GB_ARTICLE = "GB 3095-2012 表1 环境空气污染物基本项目浓度限值"
_GB_PENALTY = "中华人民共和国大气污染防治法"
_HJ = "HJ 633-2012"
_HJ_ARTICLE = "HJ 633-2012 表1 空气质量分指数及对应的污染物项目浓度限值"
_PM_UNIT = "μg/m³"
_AQI_UNIT = "指数"

LEGAL_STANDARD_SEEDS: tuple[LegalStandardSeed, ...] = (
    LegalStandardSeed("GB3095-2012-PM25-24H", "2012", "PM2.5", "24h_mean", 75, _PM_UNIT, _GB, _GB_ARTICLE, _GB_PENALTY),
    LegalStandardSeed("GB3095-2012-PM25-ANNUAL", "2012", "PM2.5", "annual_mean", 35, _PM_UNIT, _GB, _GB_ARTICLE, _GB_PENALTY),
    LegalStandardSeed("GB3095-2012-PM10-24H", "2012", "PM10", "24h_mean", 150, _PM_UNIT, _GB, _GB_ARTICLE, _GB_PENALTY),
    LegalStandardSeed("GB3095-2012-PM10-ANNUAL", "2012", "PM10", "annual_mean", 70, _PM_UNIT, _GB, _GB_ARTICLE, _GB_PENALTY),
    LegalStandardSeed("HJ633-2012-AQI-L1", "2012", "AQI", "aqi_level_1", 50, _AQI_UNIT, _HJ, _HJ_ARTICLE, _HJ),
    LegalStandardSeed("HJ633-2012-AQI-L2", "2012", "AQI", "aqi_level_2", 100, _AQI_UNIT, _HJ, _HJ_ARTICLE, _HJ),
    LegalStandardSeed("HJ633-2012-AQI-L3", "2012", "AQI", "aqi_level_3", 150, _AQI_UNIT, _HJ, _HJ_ARTICLE, _HJ),
    LegalStandardSeed("HJ633-2012-AQI-L4", "2012", "AQI", "aqi_level_4", 200, _AQI_UNIT, _HJ, _HJ_ARTICLE, _HJ),
    LegalStandardSeed("HJ633-2012-AQI-L5", "2012", "AQI", "aqi_level_5", 300, _AQI_UNIT, _HJ, _HJ_ARTICLE, _HJ),
    LegalStandardSeed("HJ633-2012-AQI-L6", "2012", "AQI", "aqi_level_6", 500, _AQI_UNIT, _HJ, _HJ_ARTICLE, _HJ),
)

RISK_THRESHOLD_SEEDS: tuple[RiskThresholdSeed, ...] = (
    RiskThresholdSeed(RISK_THRESHOLD_VERSION, "低", 0.8, "超标倍数处于低风险区间"),
    RiskThresholdSeed(RISK_THRESHOLD_VERSION, "中", 1.0, "超标倍数处于中风险区间"),
    RiskThresholdSeed(RISK_THRESHOLD_VERSION, "高", 1.5, "超标倍数处于高风险区间"),
    RiskThresholdSeed(RISK_THRESHOLD_VERSION, CRITICAL_RISK_LEVEL, None, "超标倍数处于严重风险区间且无上界"),
)


def validate_risk_threshold_seeds(rows: tuple[RiskThresholdSeed, ...] = RISK_THRESHOLD_SEEDS) -> None:
    """Require finite upper bounds to increase and the critical level to be open."""

    levels = tuple(row.level for row in rows)
    if levels != RISK_LEVELS:
        raise ValueError("risk threshold levels must follow the closed level order")
    finite: list[float] = []
    unbounded: list[RiskThresholdSeed] = []
    for row in rows:
        if row.upper_bound is None:
            unbounded.append(row)
        else:
            finite.append(row.upper_bound)
    if len(unbounded) != 1 or unbounded[0].level != CRITICAL_RISK_LEVEL:
        raise ValueError("only the critical risk level may omit an upper bound")
    if finite != sorted(finite) or len(finite) != len(set(finite)):
        raise ValueError("risk upper bounds must be strictly increasing")
