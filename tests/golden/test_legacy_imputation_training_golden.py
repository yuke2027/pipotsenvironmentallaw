"""Golden contracts for the migrated legacy imputation and training modules.

These tests exercise the canonical ``legacy_algorithms`` package path. Expensive
third-party training is replaced with fakes; assertions capture only observed
DataFrame and array contracts.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import numpy as np
import pandas as pd
import pytest

import legacy_algorithms.data_imputation as legacy_imputation
import legacy_algorithms.train_all_models as legacy_training


FEATURE_COLUMNS = ["PM2.5", "PM10", "AQI"]


def _daily_frame(station_id: str, offset: float) -> pd.DataFrame:
    """Create the fixed one-day, three-feature input used by the golden tests."""

    hours = np.arange(24, dtype=float)
    frame = pd.DataFrame(
        {
            "station_id": [station_id] * 24,
            "PM2.5": 10.0 + offset + hours,
            "PM10": 20.0 + offset + 2.0 * hours,
            "AQI": 30.0 + offset + 3.0 * hours,
            "date": ["2025-01-01"] * 24,
            "timestamp": [f"2025-01-01 {hour:02d}:00:00" for hour in range(24)],
        }
    )
    frame.loc[3, "PM10"] = np.nan
    return frame


@pytest.fixture
def deterministic_dataset(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Build a fixed 2-station x 24-step legacy dataset without random drift."""

    selected_positions = {(0, 0, 0), (0, 5, 0)}

    def fixed_random(shape: tuple[int, int, int]) -> np.ndarray:
        assert shape == (1, 24, 3)
        values = np.full(shape, 0.9, dtype=float)
        for position in selected_positions:
            values[position] = 0.1
        return values

    monkeypatch.setattr(legacy_imputation.np.random, "random", fixed_random)
    processor = legacy_imputation.AirQualityDataProcessor()
    one_day_for_two_stations = pd.concat(
        [_daily_frame("station-a", 0.0), _daily_frame("station-b", 100.0)],
        ignore_index=True,
    )
    dataset = processor.process_dataset([one_day_for_two_stations])
    assert dataset is not None
    return dataset


@pytest.mark.golden
def test_air_quality_data_processor_has_fixed_feature_array_and_mask_contract(
    deterministic_dataset: dict[str, Any],
) -> None:
    """Lock the processor's feature order, split shapes, padding-free sample and masks."""

    dataset = deterministic_dataset

    assert dataset["feature_columns"] == FEATURE_COLUMNS
    assert dataset["n_steps"] == 24
    assert dataset["n_features"] == 3
    assert dataset["train_X"].shape == (1, 24, 3)
    assert dataset["val_X"].shape == (0, 24, 3)
    assert dataset["test_X"].shape == (1, 24, 3)
    assert dataset["train_X"].dtype == np.float32
    assert dataset["mask"]["train"].shape == (1, 24, 3)
    assert dataset["mask"]["val"].shape == (0, 24, 3)
    assert dataset["mask"]["test"].shape == (1, 24, 3)

    expected_masked = np.zeros((1, 24, 3), dtype=bool)
    expected_masked[0, 0, 0] = True
    expected_masked[0, 5, 0] = True
    np.testing.assert_array_equal(dataset["train_masked_positions"], expected_masked)
    assert not dataset["mask"]["train"][0, 0, 0]
    assert not dataset["mask"]["train"][0, 5, 0]
    assert not dataset["mask"]["test"][0, 3, 1]

    # The scaler is function-local by design.  Golden tests consume only its
    # numeric interface and intentionally do not pickle/serialize the object.
    scaler = dataset["scaler"]
    assert "process_dataset.<locals>.MultiFeatureScaler" in type(scaler).__qualname__
    np.testing.assert_allclose(
        scaler.inverse_transform(dataset["train_X_ori"][0, :1]),
        np.array([[10.0, 20.0, 30.0]]),
        rtol=1e-6,
        atol=1e-6,
    )
    assert scaler.mean_.shape == (3,)
    assert scaler.scale_.shape == (3,)
    assert np.all(np.isfinite(scaler.mean_))
    assert np.all(scaler.scale_ > 0)


@pytest.mark.golden
def test_process_daily_data_keeps_dataframe_column_order(tmp_path: Any) -> None:
    """Lock the root DataFrame input/output columns used by the training loader."""

    source = _daily_frame("station-a", 0.0)
    source_path = tmp_path / "particulate.csv"
    source.to_csv(source_path, index=False)

    processed = legacy_imputation.AirQualityDataProcessor().process_daily_data(source_path)

    assert processed is not None
    assert list(processed.columns) == ["station_id", *FEATURE_COLUMNS, "date"]
    assert processed.shape == (24, 5)
    assert processed.loc[0, "station_id"] == "station-a"
    assert processed.loc[0, "date"] == "2025-01-01"
    assert np.isnan(processed.loc[3, "PM10"])


@pytest.mark.golden
def test_pypots_imputer_uses_missing_mask_and_preserves_split_shapes(
    monkeypatch: pytest.MonkeyPatch, deterministic_dataset: dict[str, Any]
) -> None:
    """Lock the SAITS construction, mask polarity and three-array result contract."""

    class FakeSAITS:
        instances: list["FakeSAITS"] = []

        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.fit_input: dict[str, np.ndarray] | None = None
            self.impute_inputs: list[dict[str, np.ndarray]] = []
            self.__class__.instances.append(self)

        def fit(self, train_set: dict[str, np.ndarray]) -> None:
            self.fit_input = train_set

        def impute(self, data: dict[str, np.ndarray]) -> np.ndarray:
            self.impute_inputs.append(data)
            return np.nan_to_num(data["X"], nan=-7.0)

    fake_pypots = types.ModuleType("pypots")
    fake_imputation_module = types.ModuleType("pypots.imputation")
    fake_imputation_module.SAITS = FakeSAITS
    fake_pypots.imputation = fake_imputation_module
    monkeypatch.setitem(sys.modules, "pypots", fake_pypots)
    monkeypatch.setitem(sys.modules, "pypots.imputation", fake_imputation_module)

    imputer = legacy_imputation.PyPOTSImputer(n_steps=24, n_features=3, n_epochs=2)
    results = imputer.perform_imputation(deterministic_dataset)

    assert results is not None
    assert set(results) == {"train_imputed", "val_imputed", "test_imputed"}
    for split in ("train", "val", "test"):
        assert results[f"{split}_imputed"].shape == deterministic_dataset[f"{split}_X"].shape

    model = FakeSAITS.instances[0]
    assert model.kwargs == {
        "n_steps": 24,
        "n_features": 3,
        "n_layers": 2,
        "d_model": 256,
        "d_ffn": 128,
        "n_heads": 4,
        "d_k": 64,
        "d_v": 64,
        "dropout": 0.1,
        "epochs": 2,
        "batch_size": 32,
        "device": "cpu",
    }
    assert model.fit_input is not None
    np.testing.assert_array_equal(model.fit_input["X"], deterministic_dataset["train_X"])
    np.testing.assert_array_equal(
        model.fit_input["missing_mask"], ~deterministic_dataset["mask"]["train"]
    )
    assert len(model.impute_inputs) == 3
    for observed, split in zip(model.impute_inputs, ("train", "val", "test")):
        np.testing.assert_array_equal(
            observed["missing_mask"], ~deterministic_dataset["mask"][split]
        )
    assert results["train_imputed"][0, 0, 0] == -7.0


@pytest.mark.golden
def test_lstm_imputer_fills_only_missing_positions_with_fake_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lock LSTM's zero-fill input and observed-value-preserving merge behavior."""

    class FakeKerasModel:
        def __init__(self) -> None:
            self.compile_kwargs: dict[str, Any] | None = None
            self.fit_args: tuple[Any, ...] | None = None
            self.fit_kwargs: dict[str, Any] | None = None
            self.saved_path: str | None = None
            self.predict_inputs: list[np.ndarray] = []

        def compile(self, **kwargs: Any) -> None:
            self.compile_kwargs = kwargs

        def fit(self, *args: Any, **kwargs: Any) -> object:
            self.fit_args = args
            self.fit_kwargs = kwargs
            return object()

        def save(self, path: str) -> None:
            self.saved_path = path

        def predict(self, values: np.ndarray, verbose: int) -> np.ndarray:
            assert verbose == 0
            self.predict_inputs.append(values.copy())
            return np.full_like(values, 77.0)

    fake_keras = types.SimpleNamespace(
        optimizers=types.SimpleNamespace(Adam=lambda **kwargs: ("adam", kwargs)),
        callbacks=types.SimpleNamespace(
            EarlyStopping=lambda **kwargs: ("early_stopping", kwargs),
            ReduceLROnPlateau=lambda **kwargs: ("reduce_lr", kwargs),
        ),
    )
    fake_tensorflow = types.ModuleType("tensorflow")
    fake_tensorflow.keras = fake_keras
    monkeypatch.setitem(sys.modules, "tensorflow", fake_tensorflow)

    model = FakeKerasModel()
    imputer = legacy_imputation.LSTMImputer(n_steps=2, n_features=3, n_epochs=1, hidden_units=4)
    monkeypatch.setattr(imputer, "_build_model", lambda: model)
    dataset = {
        "train_X": np.array([[[1.0, np.nan, 3.0], [4.0, 5.0, 6.0]]], dtype=np.float32),
        "val_X": np.array([[[7.0, 8.0, np.nan], [10.0, 11.0, 12.0]]], dtype=np.float32),
        "test_X": np.array([[[np.nan, 14.0, 15.0], [16.0, 17.0, 18.0]]], dtype=np.float32),
        "mask": {
            "train": np.array([[[True, False, True], [True, True, True]]]),
            "val": np.array([[[True, True, False], [True, True, True]]]),
            "test": np.array([[[False, True, True], [True, True, True]]]),
        },
    }

    results = imputer.perform_imputation(dataset)

    assert results is not None
    assert model.fit_args is not None
    np.testing.assert_array_equal(
        model.fit_args[0],
        np.array([[[1.0, 0.0, 3.0], [4.0, 5.0, 6.0]]], dtype=np.float32),
    )
    assert model.fit_kwargs is not None
    assert model.fit_kwargs["epochs"] == 1
    assert model.fit_kwargs["batch_size"] == 32
    assert len(model.predict_inputs) == 3
    for filled_input in model.predict_inputs:
        assert not np.isnan(filled_input).any()
    assert model.saved_path is not None

    for split in ("train", "val", "test"):
        expected = np.where(
            dataset["mask"][split], np.nan_to_num(dataset[f"{split}_X"], nan=0.0), 77.0
        )
        np.testing.assert_array_equal(results[f"{split}_imputed"], expected)


@pytest.mark.golden
def test_results_saver_reports_metrics_after_inverse_scaling(tmp_path: Any) -> None:
    """Lock MSE/MAE/RMSE to values computed on selected original-scale points."""

    class FixedScaler:
        mean_ = np.array([10.0, 20.0, 30.0])
        scale_ = np.array([2.0, 3.0, 4.0])

        def inverse_transform(self, values: np.ndarray) -> np.ndarray:
            return values * self.scale_ + self.mean_

    original = np.array([[[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]])
    imputed = np.array([[[0.5, -1.0, 0.0], [1.0, 1.5, 0.5]]])
    mask = np.ones_like(original, dtype=bool)
    masked_positions = np.zeros_like(original, dtype=bool)
    masked_positions[0, 0, 0] = True
    masked_positions[0, 1, 2] = True

    metrics = legacy_imputation.ResultsSaver(tmp_path / "results", tmp_path / "plots").calculate_metrics(
        original,
        imputed,
        mask,
        FixedScaler(),
        n_features=3,
        masked_positions=masked_positions,
    )

    assert metrics == pytest.approx(
        {"MSE": 2.5, "MAE": 1.5, "RMSE": np.sqrt(2.5)}, rel=1e-12, abs=1e-12
    )
    assert metrics["RMSE"] ** 2 == pytest.approx(metrics["MSE"], rel=1e-12, abs=1e-12)


@pytest.mark.golden
def test_training_helpers_delegate_to_fake_imputers_and_result_saver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lock train_all_models delegation without constructing real PyPOTS/TensorFlow models."""

    calls: list[tuple[str, Any]] = []

    class FakePyPOTSImputer:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(("pypots_init", kwargs))

        def perform_imputation(self, dataset: dict[str, Any]) -> dict[str, np.ndarray]:
            calls.append(("pypots_run", dataset))
            return {"train_imputed": np.zeros((1, 2, 3))}

    class FakeLSTMImputer:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(("lstm_init", kwargs))

        def perform_imputation(self, dataset: dict[str, Any]) -> dict[str, np.ndarray]:
            calls.append(("lstm_run", dataset))
            return {"train_imputed": np.ones((1, 2, 3))}

    class FakeResultsSaver:
        def __init__(self, results_dir: str, plots_dir: str) -> None:
            calls.append(("saver_init", (results_dir, plots_dir)))

        def save_results(
            self, results: dict[str, np.ndarray], dataset: dict[str, Any], model_name: str
        ) -> None:
            calls.append(("save_results", (results, dataset, model_name)))

    monkeypatch.setattr(legacy_training, "PyPOTSImputer", FakePyPOTSImputer)
    monkeypatch.setattr(legacy_training, "LSTMImputer", FakeLSTMImputer)
    monkeypatch.setattr(legacy_training, "ResultsSaver", FakeResultsSaver)
    dataset = {"n_steps": 2, "n_features": 3}

    pypots_results = legacy_training.train_pypots(dataset, n_epochs=4)
    lstm_results = legacy_training.train_lstm(dataset, n_epochs=5, hidden_units=6)

    assert pypots_results is not None
    assert lstm_results is not None
    np.testing.assert_array_equal(pypots_results["train_imputed"], np.zeros((1, 2, 3)))
    np.testing.assert_array_equal(lstm_results["train_imputed"], np.ones((1, 2, 3)))
    assert ("pypots_init", {"n_steps": 2, "n_features": 3, "n_epochs": 4}) in calls
    assert (
        "lstm_init",
        {"n_steps": 2, "n_features": 3, "n_epochs": 5, "hidden_units": 6},
    ) in calls
    assert [entry[1][2] for entry in calls if entry[0] == "save_results"] == ["pypots", "lstm"]
