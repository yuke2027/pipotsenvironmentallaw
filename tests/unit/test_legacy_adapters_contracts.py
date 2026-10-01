"""Unit and contract tests for the task 2.4 legacy algorithm boundaries."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.adapters.legacy import imputation, legal, preprocessing, training
from app.domain.dataframe_contracts import (
    AlgorithmContractError,
    ScalerArtifact,
    TrainingDataset,
)


def _measurements() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "station_id": ["station-a", "station-a"],
            "timestamp": ["2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z"],
            "date": ["2025-01-01", "2025-01-01"],
            "PM2.5": [20.0, 30.0],
            "PM10": [40.0, 50.0],
            "AQI": [60.0, 70.0],
        }
    )


def _dataset() -> TrainingDataset:
    values = np.array([[[1.0, 2.0, 3.0], [4.0, np.nan, 6.0]]], dtype=float)
    mask = ~np.isnan(values)
    return TrainingDataset(
        feature_order=("PM2.5", "PM10", "AQI"),
        n_steps=2,
        n_features=3,
        train_x=values,
        train_original=values.copy(),
        validation_x=np.empty((0, 2, 3), dtype=float),
        validation_original=np.empty((0, 2, 3), dtype=float),
        test_x=values.copy(),
        masks={"train": mask, "val": np.empty((0, 2, 3), dtype=bool), "test": mask.copy()},
        scaler=ScalerArtifact(
            feature_order=("PM2.5", "PM10", "AQI"),
            mean=np.array([0.0, 0.0, 0.0]),
            scale=np.array([1.0, 1.0, 1.0]),
        ),
    )


def test_preprocessing_adapter_returns_sorted_validated_frames() -> None:
    source = pd.DataFrame(
        {
            "date": ["20250101", "20250101", "20250101"],
            "hour": [0, 0, 0],
            "type": ["PM2.5", "PM10", "AQI"],
            "station-a": [10.0, 20.0, 30.0],
        }
    )

    result = preprocessing.preprocess_wide_dataframe(source)

    particulate = result.particulate["20250101"]
    assert particulate.columns.tolist() == ["station_id", "timestamp", "PM2.5", "PM10", "AQI", "date"]
    assert particulate.to_dict("records") == [
        {"station_id": "station-a", "timestamp": 0, "PM2.5": 10.0, "PM10": 20.0, "AQI": 30.0, "date": 20250101}
    ]


def test_preprocessing_adapter_rejects_negative_values_before_legacy_call(monkeypatch: pytest.MonkeyPatch) -> None:
    source = pd.DataFrame(
        {"date": ["20250101"] * 3, "hour": [0] * 3, "type": ["PM2.5", "PM10", "AQI"], "station-a": [-1.0, 2.0, 3.0]}
    )
    monkeypatch.setattr(preprocessing.legacy, "process_air_quality_data", lambda *_args, **_kwargs: pytest.fail("legacy called"))

    with pytest.raises(AlgorithmContractError, match="ALGORITHM_CONTRACT_ERROR"):
        preprocessing.preprocess_wide_dataframe(source)


def test_imputation_adapter_rejects_return_key_drift_atomically(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeImputer:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def perform_imputation(self, _dataset: dict[str, object]) -> dict[str, np.ndarray]:
            return {"train_imputed": np.ones((1, 2, 3)), "val_imputed": np.ones((0, 2, 3))}

    monkeypatch.setattr(imputation.legacy, "PyPOTSImputer", FakeImputer)
    with pytest.raises(AlgorithmContractError, match="keys drifted"):
        imputation.run_pypots_imputation(_dataset())


def test_training_metrics_use_explicit_scaler_and_validate_return_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSaver:
        def __init__(self, *_args: object) -> None:
            pass

        def calculate_metrics(self, *_args: object, **_kwargs: object) -> dict[str, float]:
            return {"MSE": 4.0, "MAE": 2.0, "RMSE": 2.0}

    monkeypatch.setattr(training.legacy_training, "ResultsSaver", FakeSaver)
    dataset = _dataset()
    metrics = training.calculate_original_scale_metrics(
        dataset.train_original,
        np.nan_to_num(dataset.train_x, nan=5.0),
        dataset.masks["train"],
        dataset.scaler,
    )
    assert metrics == {"MSE": 4.0, "MAE": 2.0, "RMSE": 2.0}


def test_legal_adapters_sort_results_and_reject_result_key_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    standards = legal.legacy.EnvironmentalLegalStandards()
    compliance = legal.check_compliance(_measurements(), standards, pollutants=("PM2.5", "PM10"))
    assert compliance[["station_id", "date", "pollutant"]].values.tolist() == [
        ["station-a", "2025-01-01", "PM10"],
        ["station-a", "2025-01-01", "PM2.5"],
    ]

    original = legal.legacy.LegalRiskAssessor.assess_risk

    def drop_one_result(self: object, compliance_results: pd.DataFrame) -> pd.DataFrame:
        result = original(self, compliance_results)
        return result.iloc[:1].copy()

    monkeypatch.setattr(legal.legacy.LegalRiskAssessor, "assess_risk", drop_one_result)
    with pytest.raises(AlgorithmContractError, match="keys drifted"):
        legal.assess_risk(compliance, standards)


def test_measurement_contract_rejects_unsorted_or_nonfinite_input() -> None:
    invalid = _measurements().iloc[::-1].reset_index(drop=True)
    invalid.loc[0, "PM2.5"] = np.inf

    with pytest.raises(AlgorithmContractError, match="must be sorted|non-negative finite"):
        legal.check_compliance(invalid, legal.legacy.EnvironmentalLegalStandards())
