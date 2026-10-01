"""Validated DataFrame bridge for unchanged legal compliance and risk logic."""

from __future__ import annotations

from typing import Protocol, Sequence

import numpy as np
import pandas as pd

from app.domain.records import LegalStandardRecord, StandardsSnapshot
from app.domain.dataframe_contracts import (
    AlgorithmContractError,
    FEATURE_COLUMNS,
    require_columns,
    require_identifier_values,
    require_nonnegative_finite,
    require_sorted_unique,
    validate_measurements,
)
from legacy_algorithms import legal_supervision as legacy


class LegalStandards(Protocol):
    """The narrow standards interface consumed by the legacy legal algorithms."""

    def get_standard(self, pollutant: str, standard_type: str = "24h_mean") -> float | None: ...

    def get_risk_level(
        self, value: float, pollutant: str, standard_type: str = "24h_mean"
    ) -> str | None: ...

    def get_risk_description(self, risk_level: str | None) -> str: ...


_COMPLIANCE_COLUMNS = (
    "station_id",
    "date",
    "pollutant",
    "daily_mean",
    "standard_limit",
    "exceed_ratio",
    "is_compliant",
    "risk_level",
    "risk_description",
    "max_value",
    "min_value",
    "data_points",
)
_RISK_COLUMNS = (
    "station_id",
    "date",
    "pollutant",
    "risk_score",
    "risk_level",
    "legal_consequences",
    "recommended_actions",
    "penalty_estimate",
    "compliance_status",
)


def _validate_compliance_input(frame: pd.DataFrame) -> None:
    require_columns(
        frame,
        ("station_id", "date", "pollutant", "daily_mean", "exceed_ratio", "is_compliant", "risk_level"),
        "risk input",
    )
    require_identifier_values(frame, ("station_id", "date", "pollutant", "risk_level"), "risk input")
    require_sorted_unique(frame, ("station_id", "date", "pollutant"), "risk input")
    require_nonnegative_finite(frame, ("daily_mean", "exceed_ratio"), "risk input", allow_null=False)


def _validate_compliance_output(frame: pd.DataFrame, source: pd.DataFrame) -> None:
    require_columns(frame, _COMPLIANCE_COLUMNS, "compliance result", exact=True)
    require_identifier_values(frame, ("station_id", "date", "pollutant", "risk_level"), "compliance result")
    require_sorted_unique(frame, ("station_id", "date", "pollutant"), "compliance result")
    require_nonnegative_finite(
        frame,
        ("daily_mean", "standard_limit", "exceed_ratio", "max_value", "min_value", "data_points"),
        "compliance result",
        allow_null=False,
    )
    source_pairs = set(zip(source["station_id"], source["date"]))
    result_pairs = set(zip(frame["station_id"], frame["date"]))
    if not result_pairs.issubset(source_pairs):
        raise AlgorithmContractError("compliance result introduced an unknown station/date key")


def check_compliance(
    measurements: pd.DataFrame,
    standards: LegalStandards,
    *,
    pollutants: Sequence[str] = FEATURE_COLUMNS,
) -> pd.DataFrame:
    """Run legacy aggregation after input validation and return a sorted full result."""

    validate_measurements(measurements, "compliance input")
    if not pollutants or any(pollutant not in FEATURE_COLUMNS for pollutant in pollutants):
        raise AlgorithmContractError("compliance pollutants must be platform feature columns")
    result = legacy.ComplianceChecker(standards).check_all_pollutants(
        measurements.copy(), pollutant_cols=list(pollutants)
    )
    if not isinstance(result, pd.DataFrame) or result.empty:
        raise AlgorithmContractError("legacy compliance checker returned no results")
    result = result.sort_values(["station_id", "date", "pollutant"], kind="mergesort").reset_index(drop=True)
    _validate_compliance_output(result, measurements)
    return result


def _validate_risk_output(frame: pd.DataFrame, expected_keys: set[tuple[object, object, object]]) -> None:
    require_columns(frame, _RISK_COLUMNS, "risk result", exact=True)
    require_identifier_values(frame, ("station_id", "date", "pollutant", "risk_level"), "risk result")
    require_sorted_unique(frame, ("station_id", "date", "pollutant"), "risk result")
    require_nonnegative_finite(frame, ("risk_score",), "risk result", allow_null=False)
    if frame["risk_score"].gt(100).any():
        raise AlgorithmContractError("risk result score must not exceed 100")
    result_keys = set(zip(frame["station_id"], frame["date"], frame["pollutant"]))
    if result_keys != expected_keys:
        raise AlgorithmContractError("risk result keys drifted from compliance input")


def assess_risk(compliance_results: pd.DataFrame, standards: LegalStandards) -> pd.DataFrame:
    """Run legacy risk assessment and reject any dropped or invented result key."""

    _validate_compliance_input(compliance_results)
    result = legacy.LegalRiskAssessor(standards).assess_risk(compliance_results.copy())
    if not isinstance(result, pd.DataFrame) or result.empty:
        raise AlgorithmContractError("legacy risk assessor returned no results")
    result = result.sort_values(["station_id", "date", "pollutant"], kind="mergesort").reset_index(drop=True)
    expected_keys = set(
        zip(
            compliance_results["station_id"],
            compliance_results["date"],
            compliance_results["pollutant"],
        )
    )
    _validate_risk_output(result, expected_keys)
    return result


_LEGACY_LEVELS = {"低": "low", "中": "medium", "高": "high", "严重": "critical"}
_PLATFORM_LEVELS = {english: chinese for chinese, english in _LEGACY_LEVELS.items()}


class DatabaseLegalStandardsAdapter:
    """Read limits and risk bounds from a database snapshot. Nothing is hardcoded."""

    def __init__(self, snapshot: StandardsSnapshot) -> None:
        self._snapshot = snapshot
        self.standard_ids: dict[tuple[str, str], int] = {}

    def get_standard(self, pollutant: str, standard_type: str = "24h_mean") -> float | None:
        row = self._match(pollutant, standard_type)
        if row is None:
            return None
        self.standard_ids[(pollutant, standard_type)] = row.id
        return row.limit_value

    def get_risk_level(self, value: float, pollutant: str, standard_type: str = "24h_mean") -> str | None:
        limit = self.get_standard(pollutant, standard_type)
        if limit is None or limit <= 0:
            return None
        ratio = value / limit
        for threshold in self._snapshot.risk_thresholds:
            legacy = _LEGACY_LEVELS.get(threshold.level)
            if legacy is None:
                continue
            if threshold.upper_bound is None or ratio < threshold.upper_bound:
                return legacy
        return "critical"

    def get_risk_description(self, risk_level: str | None) -> str:
        chinese = _PLATFORM_LEVELS.get(risk_level or "", risk_level)
        for threshold in self._snapshot.risk_thresholds:
            if threshold.level == chinese:
                return threshold.description_zh
        return "未知风险等级"

    def _match(self, pollutant: str, standard_type: str) -> LegalStandardRecord | None:
        rows = [
            row
            for row in self._snapshot.standards
            if row.pollutant == pollutant and row.is_active and row.statistic_basis == standard_type
        ]
        if not rows and pollutant == "AQI" and standard_type == "24h_mean":
            rows = [
                row
                for row in self._snapshot.standards
                if row.pollutant == "AQI" and row.is_active and row.statistic_basis == "aqi_level_2"
            ]
        if not rows:
            return None
        return rows[-1]


def platform_risk_level(legacy_level: str) -> str:
    """Map the algorithm's English level onto the stored Chinese level."""

    return _PLATFORM_LEVELS.get(legacy_level, legacy_level)
