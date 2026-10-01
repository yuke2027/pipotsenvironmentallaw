"""Risk persistence. Compliant business scores are forced to 20 after the legacy call."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from app.adapters.legacy.legal import DatabaseLegalStandardsAdapter, assess_risk
from app.domain.records import StandardsSnapshot
from app.services.compliance import ComplianceOutcome

DISCLAIMER = "预估结果，非执法依据"
_LEVEL_ORDER = {"低": 0, "中": 1, "高": 2, "严重": 3}
_LEGACY = {"低": "low", "中": "medium", "高": "high", "严重": "critical"}


@dataclass(frozen=True)
class RiskView:
    compliance_key: str
    risk_score: float
    risk_level: str
    legal_consequences: str
    recommended_actions: tuple[str, ...]
    penalty_estimate_text: str
    disclaimer: str


def business_score(raw_score: float, *, compliant: bool) -> float:
    """Clamp to [0, 100] and apply the compliant post-condition of 20."""

    if compliant:
        return 20.0
    if raw_score < 0:
        return 0.0
    if raw_score > 100:
        return 100.0
    return float(raw_score)


def assess_outcome(outcome: ComplianceOutcome, snapshot: StandardsSnapshot) -> RiskView:
    """Call the unchanged assessor, then apply the service post-condition."""

    if outcome.is_compliant is None or outcome.daily_mean is None or outcome.exceed_ratio is None:
        raise ValueError("insufficient compliance results cannot be assessed")
    legacy_level = _LEGACY.get(outcome.risk_level or "", "medium")
    frame = pd.DataFrame(
        [
            {
                "station_id": outcome.station_id,
                "date": outcome.local_date.isoformat(),
                "pollutant": outcome.pollutant,
                "daily_mean": outcome.daily_mean,
                "exceed_ratio": outcome.exceed_ratio,
                "is_compliant": outcome.is_compliant,
                "risk_level": legacy_level,
            }
        ]
    )
    assessed = assess_risk(frame, DatabaseLegalStandardsAdapter(snapshot))
    row = assessed.iloc[0]
    actions = str(row["recommended_actions"])
    return RiskView(
        compliance_key=f"{outcome.station_id}|{outcome.local_date.isoformat()}|{outcome.pollutant}",
        risk_score=business_score(float(row["risk_score"]), compliant=outcome.is_compliant),
        risk_level=str(outcome.risk_level or ""),
        legal_consequences=str(row["legal_consequences"]),
        recommended_actions=tuple(part for part in actions.split("; ") if part),
        penalty_estimate_text=str(row["penalty_estimate"]),
        disclaimer=DISCLAIMER,
    )


def sort_risks(
    items: Sequence[RiskView],
    *,
    level: str | None,
    descending: bool,
) -> tuple[RiskView, ...]:
    """Filter, then sort by level and score before any pagination slice."""

    chosen = [item for item in items if level is None or item.risk_level == level]
    chosen.sort(
        key=lambda item: (_LEVEL_ORDER.get(item.risk_level, 0), item.risk_score, item.compliance_key),
        reverse=descending,
    )
    return tuple(chosen)
