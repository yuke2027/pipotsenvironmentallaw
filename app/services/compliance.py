"""Daily compliance. Insufficient groups never reach risk or alerts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.adapters.legacy.legal import DatabaseLegalStandardsAdapter, check_compliance, platform_risk_level
from app.domain.records import StandardsSnapshot

Followup = Callable[["ComplianceOutcome"], None]


@dataclass(frozen=True)
class ComplianceOutcome:
    station_id: str
    local_date: date
    pollutant: str
    status: str
    daily_mean: float | None
    max_value: float | None
    min_value: float | None
    valid_points: int
    standard_id: int | None
    standard_limit_snapshot: float | None
    exceed_ratio: float | None
    risk_level: str | None
    is_compliant: bool | None


def evaluate_group(
    *,
    station_id: str,
    local_date: date,
    values: dict[str, Sequence[float | None]],
    snapshot: StandardsSnapshot,
    min_points: int,
    risk: Followup | None = None,
    alert: Followup | None = None,
) -> tuple[ComplianceOutcome, ...]:
    """Judge each pollutant. Follow-ups run only for groups that have a conclusion."""

    adapter = DatabaseLegalStandardsAdapter(snapshot)
    outcomes: list[ComplianceOutcome] = []
    for pollutant, samples in values.items():
        finite = [float(sample) for sample in samples if sample is not None and sample == sample]
        if len(finite) < min_points:
            outcome = ComplianceOutcome(
                station_id=station_id,
                local_date=local_date,
                pollutant=pollutant,
                status="INSUFFICIENT",
                daily_mean=None,
                max_value=None,
                min_value=None,
                valid_points=len(finite),
                standard_id=None,
                standard_limit_snapshot=None,
                exceed_ratio=None,
                risk_level=None,
                is_compliant=None,
            )
        else:
            outcome = _from_algorithm(station_id, local_date, pollutant, finite, adapter)
        outcomes.append(outcome)
        if outcome.status == "INSUFFICIENT":
            continue
        if risk is not None:
            risk(outcome)
        if alert is not None:
            alert(outcome)
    return tuple(outcomes)


def _from_algorithm(
    station_id: str,
    local_date: date,
    pollutant: str,
    finite: list[float],
    adapter: DatabaseLegalStandardsAdapter,
) -> ComplianceOutcome:
    rows = []
    for index, value in enumerate(finite):
        row = {
            "station_id": station_id,
            "timestamp": index,
            "date": local_date.isoformat(),
            "PM2.5": 0.0,
            "PM10": 0.0,
            "AQI": 0.0,
        }
        row[pollutant] = value
        rows.append(row)
    frame = pd.DataFrame(rows)
    result = check_compliance(frame, adapter, pollutants=(pollutant,))
    matched = result[result["pollutant"] == pollutant].iloc[0]
    legacy_level = str(matched["risk_level"]) if matched["risk_level"] is not None else None
    limit = float(matched["standard_limit"])
    return ComplianceOutcome(
        station_id=station_id,
        local_date=local_date,
        pollutant=pollutant,
        status="COMPLIANT" if bool(matched["is_compliant"]) else "NON_COMPLIANT",
        daily_mean=float(matched["daily_mean"]),
        max_value=float(matched["max_value"]),
        min_value=float(matched["min_value"]),
        valid_points=int(matched["data_points"]),
        standard_id=adapter.standard_ids.get((pollutant, "24h_mean")),
        standard_limit_snapshot=limit,
        exceed_ratio=float(matched["exceed_ratio"]),
        risk_level=None if legacy_level is None else platform_risk_level(legacy_level),
        is_compliant=bool(matched["is_compliant"]),
    )
