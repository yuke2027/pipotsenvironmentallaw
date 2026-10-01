"""Golden regression tests for the migrated legacy legal supervision algorithms.

Tests import the canonical ``legacy_algorithms`` package module directly and use
in-memory DataFrames only; they never access network or project data files.
"""

from __future__ import annotations

import pandas as pd
import pytest

from legacy_algorithms.legal_supervision import (
    ComplianceChecker,
    EnvironmentalLegalStandards,
    LegalRiskAssessor,
)


@pytest.fixture
def legacy_standards() -> EnvironmentalLegalStandards:
    """Return the legacy standards object used by both legacy algorithms."""
    return EnvironmentalLegalStandards()


@pytest.fixture
def legacy_measurements() -> pd.DataFrame:
    """Fixed, local wide input containing the three legacy pollutant columns."""
    return pd.DataFrame(
        [
            {
                "station_id": "station-alpha",
                "date": "2025-01-01",
                "PM2.5": 70.0,
                "PM10": 100.0,
                "AQI": 100.0,
            },
            {
                "station_id": "station-alpha",
                "date": "2025-01-01",
                "PM2.5": 80.0,
                "PM10": 200.0,
                "AQI": 200.0,
            },
            {
                "station_id": "station-beta",
                "date": "2025-01-02",
                "PM2.5": 60.0,
                "PM10": 90.0,
                "AQI": 50.0,
            },
        ]
    )


@pytest.mark.golden
def test_compliance_checker_golden_output_for_pm25_pm10_and_aqi_input(
    legacy_standards: EnvironmentalLegalStandards,
    legacy_measurements: pd.DataFrame,
) -> None:
    """**Validates: Requirements 7.1, 15.2, 16.3**

    The legacy wide input contains PM2.5, PM10, and AQI.  AQI deliberately has
    no ``24h_mean`` standard in ``EnvironmentalLegalStandards``, so the current
    unmodified checker emits no AQI result.  This is a golden compatibility
    contract, not a reason to change the legacy calculation; a later database
    standards adapter/service boundary supplies the platform's AQI behavior.
    """
    results = ComplianceChecker(legacy_standards).check_all_pollutants(
        legacy_measurements
    )

    expected = pd.DataFrame(
        [
            {
                "station_id": "station-alpha",
                "date": "2025-01-01",
                "pollutant": "PM2.5",
                "daily_mean": 75.0,
                "standard_limit": 75,
                "exceed_ratio": 1.0,
                "is_compliant": True,
                "risk_level": "high",
                "risk_description": "高风险：超过标准限值，需要采取治理措施",
                "max_value": 80.0,
                "min_value": 70.0,
                "data_points": 2,
            },
            {
                "station_id": "station-beta",
                "date": "2025-01-02",
                "pollutant": "PM2.5",
                "daily_mean": 60.0,
                "standard_limit": 75,
                "exceed_ratio": 0.8,
                "is_compliant": True,
                "risk_level": "medium",
                "risk_description": "中风险：接近标准限值，需要关注",
                "max_value": 60.0,
                "min_value": 60.0,
                "data_points": 1,
            },
            {
                "station_id": "station-alpha",
                "date": "2025-01-01",
                "pollutant": "PM10",
                "daily_mean": 150.0,
                "standard_limit": 150,
                "exceed_ratio": 1.0,
                "is_compliant": True,
                "risk_level": "high",
                "risk_description": "高风险：超过标准限值，需要采取治理措施",
                "max_value": 200.0,
                "min_value": 100.0,
                "data_points": 2,
            },
            {
                "station_id": "station-beta",
                "date": "2025-01-02",
                "pollutant": "PM10",
                "daily_mean": 90.0,
                "standard_limit": 150,
                "exceed_ratio": 0.6,
                "is_compliant": True,
                "risk_level": "low",
                "risk_description": "低风险：符合标准，无需采取行动",
                "max_value": 90.0,
                "min_value": 90.0,
                "data_points": 1,
            },
        ]
    )

    pd.testing.assert_frame_equal(results, expected)
    assert "AQI" not in results["pollutant"].tolist()


@pytest.mark.golden
def test_legal_risk_assessor_golden_output_for_all_four_risk_levels(
    legacy_standards: EnvironmentalLegalStandards,
) -> None:
    """**Validates: Requirements 8.1, 15.3, 16.3**

    Freeze each legacy risk tier's score, consequence, recommendation, and
    penalty text.  The input mimics the compliance-result columns consumed by
    ``LegalRiskAssessor`` and uses only deterministic, local data.
    """
    compliance_results = pd.DataFrame(
        [
            {
                "station_id": "station-low",
                "date": "2025-01-02",
                "pollutant": "PM10",
                "daily_mean": 90.0,
                "exceed_ratio": 0.6,
                "is_compliant": True,
                "risk_level": "low",
            },
            {
                "station_id": "station-medium",
                "date": "2025-01-02",
                "pollutant": "PM2.5",
                "daily_mean": 60.0,
                "exceed_ratio": 0.8,
                "is_compliant": True,
                "risk_level": "medium",
            },
            {
                "station_id": "station-high",
                "date": "2025-01-03",
                "pollutant": "PM2.5",
                "daily_mean": 100.0,
                "exceed_ratio": 4.0 / 3.0,
                "is_compliant": False,
                "risk_level": "high",
            },
            {
                "station_id": "station-critical",
                "date": "2025-01-04",
                "pollutant": "AQI",
                "daily_mean": 300.0,
                "exceed_ratio": 2.0,
                "is_compliant": False,
                "risk_level": "critical",
            },
        ]
    )

    results = LegalRiskAssessor(legacy_standards).assess_risk(compliance_results)

    expected = pd.DataFrame(
        [
            {
                "station_id": "station-low",
                "date": "2025-01-02",
                "pollutant": "PM10",
                "risk_score": 10.0,
                "risk_level": "low",
                "legal_consequences": "无法律风险，符合环境空气质量标准",
                "recommended_actions": "保持现状，继续监测",
                "penalty_estimate": "无处罚",
                "compliance_status": "合规",
            },
            {
                "station_id": "station-medium",
                "date": "2025-01-02",
                "pollutant": "PM2.5",
                "risk_score": 20.0,
                "risk_level": "medium",
                "legal_consequences": "无法律风险，符合环境空气质量标准",
                "recommended_actions": "加强日常监管; 预防性减排措施",
                "penalty_estimate": "无处罚",
                "compliance_status": "合规",
            },
            {
                "station_id": "station-high",
                "date": "2025-01-03",
                "pollutant": "PM2.5",
                "risk_score": 100.0,
                "risk_level": "high",
                "legal_consequences": "轻微超标，建议加强监测",
                "recommended_actions": "立即采取减排措施; 加强监测频率; 启动应急预案; 向环保部门报告; 考虑临时停产或限产",
                "penalty_estimate": "50-100万元",
                "compliance_status": "超标",
            },
            {
                "station_id": "station-critical",
                "date": "2025-01-04",
                "pollutant": "AQI",
                "risk_score": 100.0,
                "risk_level": "critical",
                "legal_consequences": "可能面临行政处罚（10-100万元）; 可能被责令限期治理; 可能面临更严厉的行政处罚（50-500万元）; 可能被责令停产整治; 严重污染天气，可能启动应急响应; 可能面临最高1000万元罚款",
                "recommended_actions": "立即采取减排措施; 加强监测频率; 启动应急预案; 向环保部门报告; 考虑临时停产或限产",
                "penalty_estimate": "300-1000万元",
                "compliance_status": "超标",
            },
        ]
    )

    pd.testing.assert_frame_equal(results, expected)


@pytest.mark.golden
def test_legacy_compliant_low_risk_score_stays_10_until_service_boundary(
    legacy_standards: EnvironmentalLegalStandards,
) -> None:
    """**Validates: Requirements 8.4, 15.3, 16.3**

    The legacy formula applies the ``low`` multiplier to its compliant baseline
    and therefore returns 10, although the platform business boundary must
    later expose 20 for any compliant result.  Keep this test and the explicit
    assertion as a guard against modifying ``_calculate_risk_score`` or any
    other legacy calculation body; the compatibility normalization belongs only
    in the future risk service.
    """
    compliant_low = pd.DataFrame(
        [
            {
                "station_id": "station-low",
                "date": "2025-01-02",
                "pollutant": "PM10",
                "daily_mean": 90.0,
                "exceed_ratio": 0.6,
                "is_compliant": True,
                "risk_level": "low",
            }
        ]
    )

    result = LegalRiskAssessor(legacy_standards).assess_risk(compliant_low)

    assert result.loc[0, "risk_score"] == 10.0
    # Requirement 8.4 is met later by app.services.risk, not by this algorithm.
    assert 20.0 != result.loc[0, "risk_score"]
