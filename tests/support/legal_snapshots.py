"""Small standard snapshots for compliance and risk tests."""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.records import LegalStandardRecord, RiskThresholdRecord, StandardsSnapshot

_WHEN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def legal_snapshot(limits: dict[str, float], *, version_suffix: str = "1") -> StandardsSnapshot:
    standards = []
    for index, (pollutant, limit) in enumerate(limits.items(), start=1):
        standards.append(
            LegalStandardRecord(
                id=index if version_suffix == "1" else index + 100,
                standard_key=f"{pollutant}-{version_suffix}",
                version=version_suffix,
                pollutant=pollutant,
                statistic_basis="24h_mean",
                limit_value=limit,
                unit="ug",
                legal_basis_name="GB 3095-2012",
                legal_article="表1",
                penalty_basis="大气污染防治法",
                effective_from=_WHEN,
                effective_to=None,
                is_active=True,
            )
        )
    thresholds = (
        RiskThresholdRecord(1, "2012", "低", 0.8, "低风险", True, _WHEN),
        RiskThresholdRecord(2, "2012", "中", 1.0, "中风险", True, _WHEN),
        RiskThresholdRecord(3, "2012", "高", 1.5, "高风险", True, _WHEN),
        RiskThresholdRecord(4, "2012", "严重", None, "严重风险", True, _WHEN),
    )
    return StandardsSnapshot(_WHEN, tuple(standards), thresholds)
