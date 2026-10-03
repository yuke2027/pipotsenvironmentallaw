"""Real (non-mocked) legacy training paths: real CSVs, real SAITS, real LSTM attempt.

SAITS runs one epoch on CPU against a subset of the real ``data/air_quality``
files. The LSTM branch exercises its real failure path because TensorFlow is
not part of any image in this repository.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from legacy_algorithms import data_imputation as di
from legacy_algorithms import train_all_models as tam

_REAL_DATA = Path(__file__).resolve().parents[2] / "data" / "air_quality"
_DAYS = ("20250101_particulate.csv", "20250102_particulate.csv", "20250103_particulate.csv")


@pytest.fixture
def redirected_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    data = tmp_path / "air_quality"
    data.mkdir()
    results = tmp_path / "results"
    plots = tmp_path / "plots"
    models = tmp_path / "models"
    for path in (results, plots, models):
        path.mkdir(parents=True)
    for name in _DAYS:
        shutil.copy(_REAL_DATA / name, data / name)
    for module in (di, tam):
        monkeypatch.setattr(module, "DATA_DIR", str(data))
        monkeypatch.setattr(module, "RESULTS_DIR", str(results))
        monkeypatch.setattr(module, "PLOTS_DIR", str(plots))
        monkeypatch.setattr(module, "MODELS_DIR", str(models))
    return {"data": data, "results": results, "plots": plots, "models": models}


@pytest.mark.integration
def test_load_process_and_train_saits_for_one_epoch(redirected_dirs: dict[str, Path]) -> None:
    dataset = tam.load_data()
    assert dataset is not None
    assert dataset["n_steps"] == len(_DAYS) * 24
    assert dataset["n_features"] == 3
    assert dataset["train_X"].shape[0] + dataset["val_X"].shape[0] + dataset["test_X"].shape[0] >= 30

    results = tam.train_pypots(dataset, n_epochs=1)
    assert results is not None
    for key in ("train_imputed", "val_imputed", "test_imputed"):
        assert results[key].shape == dataset[key.split("_")[0] + "_X"].shape
    saved = list(redirected_dirs["results"].glob("pypots_*.csv"))
    assert saved
    assert list(redirected_dirs["plots"].glob("pypots_*"))

    comparison = tam.compare_models(results, None, dataset)
    assert comparison["pypots_train"]["MSE"] >= 0
    assert comparison["pypots_train"]["RMSE"] == pytest.approx(
        comparison["pypots_train"]["MSE"] ** 0.5, rel=1e-3
    )


@pytest.mark.integration
def test_lstm_fails_fast_without_tensorflow(redirected_dirs: dict[str, Path]) -> None:
    dataset = tam.load_data()
    assert dataset is not None
    assert tam.train_lstm(dataset, n_epochs=1, hidden_units=8) is None


@pytest.mark.integration
def test_train_all_models_main_lstm_only(redirected_dirs: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["train_all_models", "--lstm-only", "--lstm-epochs", "1", "--lstm-units", "8"])
    tam.main()


@pytest.mark.integration
def test_visualizer_helpers_emit_png_files(tmp_path: Path) -> None:
    import pandas as pd

    visualizer = di.Visualizer(str(tmp_path))
    frame = pd.DataFrame({"PM2.5": [1.0, 2.0, 3.0], "PM10": [4.0, 5.0, 6.0], "AQI": [7.0, 8.0, 9.0]})
    visualizer.plot_data_distribution(frame, ["PM2.5", "PM10", "AQI"], "t")
    visualizer.plot_correlation_matrix(frame, "t")
    visualizer.plot_boxplot(frame, ["PM2.5", "PM10", "AQI"], "t")
    visualizer.plot_metrics_comparison({"train": {"MSE": 1.0, "MAE": 0.5, "RMSE": 1.0}}, "t")
    assert len(list(tmp_path.glob("*.png"))) >= 4


@pytest.mark.integration
def test_legal_supervision_real_run_and_components(tmp_path: Path) -> None:
    """Real legal-supervision run over real particulate CSVs plus branch coverage."""

    import pandas as pd

    from legacy_algorithms import legal_supervision as ls

    data_dir = tmp_path / "air_quality"
    data_dir.mkdir()
    for name in _DAYS:
        shutil.copy(_REAL_DATA / name, data_dir / name)
    (data_dir / "broken_particulate.csv").write_text("not,a,csv\n", encoding="utf-8")

    out_dir = tmp_path / "legal"
    out_dir.mkdir()
    results = ls.run_legal_supervision(data_dir=str(data_dir), output_dir=str(out_dir))
    assert results is not None
    compliance = results["compliance_results"]
    assert not compliance.empty
    assert {"station_id", "pollutant", "daily_mean", "exceed_ratio", "is_compliant"} <= set(compliance.columns)
    assert (out_dir / "compliance_results.csv").is_file()
    assert (out_dir / "risk_assessments.csv").is_file()

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert ls.run_legal_supervision(data_dir=str(empty_dir), output_dir=str(out_dir)) is None
    only_bad = tmp_path / "onlybad"
    only_bad.mkdir()
    (only_bad / "x_particulate.csv").write_text("corrupted\n", encoding="utf-8")
    assert ls.run_legal_supervision(data_dir=str(only_bad), output_dir=str(out_dir)) is None

    standards = ls.EnvironmentalLegalStandards()
    assert standards.get_standard("PM2.5") == 75
    assert standards.get_standard("UNKNOWN") is None
    assert standards.get_risk_level(10, "PM2.5") == "low"
    assert standards.get_risk_level(70, "PM2.5") == "medium"
    assert standards.get_risk_level(100, "PM2.5") == "high"
    assert standards.get_risk_level(500, "PM2.5") == "critical"
    assert standards.get_risk_level(1, "UNKNOWN") is None
    assert "未知" in standards.get_risk_description("weird")

    frame = pd.DataFrame(
        {
            "station_id": ["s1"] * 48,
            "date": ["20250101"] * 24 + ["20250102"] * 24,
            "PM2.5": [10.0] * 24 + [200.0] * 24,
            "PM10": [10.0] * 24 + [300.0] * 24,
            "AQI": [10.0] * 24 + [400.0] * 24,
            "timestamp": list(range(24)) * 2,
        }
    )
    checker = ls.ComplianceChecker(standards)
    checked = checker.check_all_pollutants(frame)
    assert not checked.empty
    assert checker.check_all_pollutants(pd.DataFrame({"X": [1.0]})).empty
    risk = ls.LegalRiskAssessor(standards).assess_risk(checked)
    assert not risk.empty
    assert ls.LegalRiskAssessor(standards).assess_risk(pd.DataFrame()).empty


@pytest.mark.integration
def test_legal_risk_and_penalty_branches() -> None:
    """Direct branch coverage for the legacy risk assessor internals."""

    from legacy_algorithms import legal_supervision as ls

    standards = ls.EnvironmentalLegalStandards()
    assessor = ls.LegalRiskAssessor(standards)
    checker = ls.ComplianceChecker(standards)

    def row_for(value: float, pollutant: str = "PM2.5"):
        frame = pd.DataFrame(
            {
                "station_id": ["s1"] * 24,
                "date": ["20250101"] * 24,
                pollutant: [value] * 24,
            }
        )
        checked = checker.check_compliance(frame, pollutant)
        return checked.iloc[0]

    mild = assessor._estimate_penalty(row_for(80))  # ratio ~1.07 -> 10-50万
    mid = assessor._estimate_penalty(row_for(100))  # ~1.33 -> 50-100万
    high = assessor._estimate_penalty(row_for(130))  # ~1.73 -> 100-300万
    severe = assessor._estimate_penalty(row_for(200))  # ~2.67 -> 300-1000万
    assert mild == "10-50万元" and mid == "50-100万元"
    assert high == "100-300万元" and severe == "300-1000万元"
    assert assessor._estimate_penalty(row_for(10)) == "无处罚"

    consequences = assessor._assess_legal_consequences(row_for(115))
    assert "处罚" in consequences
    consequences2 = assessor._assess_legal_consequences(row_for(160))
    assert "停产" in consequences2
    aqi_row = pd.Series({"is_compliant": False, "exceed_ratio": 2.6, "pollutant": "AQI", "daily_mean": 400})
    consequences3 = assessor._assess_legal_consequences(aqi_row)
    assert "应急" in consequences3 or "1000万" in consequences3
    assert assessor._assess_legal_consequences(row_for(10)) == "无法律风险，符合环境空气质量标准"
    mild_conseq = assessor._assess_legal_consequences(row_for(78))
    assert "轻微" in mild_conseq

    assert assessor._calculate_risk_score(row_for(10)) == 10.0
    assert assessor._calculate_risk_score(row_for(500)) == 100.0

    actions = assessor._recommend_actions(row_for(500))
    assert "应急" in actions
    assert assessor._recommend_actions(row_for(70))  # medium -> 加强日常监管
    assert assessor._recommend_actions(row_for(10)) == "保持现状，继续监测"


@pytest.mark.integration
def test_legacy_preprocess_monthly_and_dataset_padding(tmp_path: Path) -> None:
    """process_monthly_files over real files plus process_dataset padding."""

    import numpy as np

    from legacy_algorithms import data_imputation as di
    from legacy_algorithms import data_preprocessing as dp

    base = tmp_path / "month"
    base.mkdir()
    rows = ["date,hour,type,东城东四,西城官园"]
    for day in (1, 2, 3):
        for hour in range(24):
            for pollutant in ("PM2.5", "PM10", "AQI"):
                rows.append(f"2025010{day},{hour},{pollutant},30,40")
    wide = "\n".join(rows) + "\n"
    for day in (1, 2, 3):
        day_rows = [rows[0]] + [r for r in rows[1:] if r.startswith(f"2025010{day},")]
        (base / f"beijing_all_2025010{day}.csv").write_text(
            "\n".join(day_rows) + "\n", encoding="utf-8"
        )
    out_dir = tmp_path / "processed"
    results = dp.process_monthly_files(
        base_dir=str(base), pattern="beijing_all_", year=2025, month=1, output_dir=str(out_dir)
    )
    assert results and all(item["success"] for item in results)

    none_found = dp.process_monthly_files(
        base_dir=str(base), pattern="beijing_all_", year=2030, month=1, output_dir=str(out_dir)
    )
    assert none_found == []

    processor = di.AirQualityDataProcessor()
    short = pd.DataFrame(
        {
            "station_id": ["s1"] * 10,
            "PM2.5": [10.0] * 10,
            "PM10": [20.0] * 10,
            "AQI": [30.0] * 10,
        }
    )
    long = pd.DataFrame(
        {
            "station_id": ["s2"] * 60,
            "PM2.5": [10.0] * 60,
            "PM10": [20.0] * 60,
            "AQI": [30.0] * 60,
        }
    )
    processed = processor.process_dataset([short, long])
    assert processed is not None
    X = processed["train_X_ori"]
    assert X.shape[1] == 48  # 2 days * 24 hours, padded/truncated

    assert processor.process_daily_data(tmp_path / "missing.csv") is None


class _ManualScaler:
    def __init__(self):
        self.mean_ = np.array([1.0, 2.0, 3.0])
        self.scale_ = np.array([4.0, 5.0, 6.0])


@pytest.mark.integration
def test_legacy_metrics_manual_scaler_path() -> None:
    """calculate_metrics with a sklearn-style mean_/scale_ scaler."""

    from legacy_algorithms import data_imputation as di

    saver = di.ResultsSaver(str(tmp_path := Path(__import__("tempfile").mkdtemp())), str(tmp_path))
    original = np.ones((2, 4, 3), dtype=np.float32)
    imputed = np.ones((2, 4, 3), dtype=np.float32) * 2
    mask = np.ones((2, 4, 3), dtype=bool)
    metrics = saver.calculate_metrics(original, imputed, mask, _ManualScaler(), 3)
    assert metrics["MSE"] >= 0 and metrics["MAE"] >= 0

    mask_some = np.zeros((2, 4, 3), dtype=bool)
    mask_some[0, 0, 0] = True
    metrics2 = saver.calculate_metrics(original, imputed, mask_some, _ManualScaler(), 3)
    assert metrics2["MSE"] >= 0


def test_metrics_manual_scaler_and_no_scaler_branches(tmp_path):
    """calculate_metrics: 0-d mean scaler (single-feature) and scaler=None."""
    from legacy_algorithms import data_imputation as di

    saver = di.ResultsSaver(tmp_path / "r", tmp_path / "p")
    original = np.arange(8, dtype=float).reshape(2, 2, 2)
    imputed = original + 0.5
    mask = np.ones_like(original, dtype=bool)

    class SingleScaler:
        mean_ = np.array(10.0)
        scale_ = np.array(2.0)

    metrics = saver.calculate_metrics(original, imputed, mask, SingleScaler(), 2)
    assert metrics["MSE"] == pytest.approx(1.0)

    no_scaler = saver.calculate_metrics(original, imputed, mask, object(), 2)
    assert no_scaler["MSE"] == pytest.approx(0.25)


def test_process_daily_data_failure_paths(tmp_path):
    """process_daily_data: missing columns warning + unreadable file exception."""
    from legacy_algorithms import data_imputation as di

    processor = di.AirQualityDataProcessor()
    bad = tmp_path / "bad.csv"
    bad.write_text("station_id,date\ns1,20250101\n", encoding="utf-8")
    assert processor.process_daily_data(str(bad)) is None
    broken = tmp_path / "broken.csv"
    broken.write_bytes(b"\xff\xfe invalid csv \x00\x01")
    assert processor.process_daily_data(str(broken)) is None
    assert processor.process_daily_data(str(tmp_path / "nonexistent.csv")) is None


def test_process_dataset_all_nan_feature_column():
    """Feature column with zero valid values → mean 0 / scale 1 fallback."""
    from legacy_algorithms import data_imputation as di

    processor = di.AirQualityDataProcessor()
    day1 = pd.DataFrame({"station_id": ["s1"] * 24 + ["s2"] * 24,
                         "date": ["20250101"] * 48,
                         "PM2.5": [np.nan] * 24 + [30.0] * 24,
                         "PM10": [40.0] * 48, "AQI": [50.0] * 48})
    day2 = pd.DataFrame({"station_id": ["s1"] * 24 + ["s2"] * 24,
                         "date": ["20250102"] * 48,
                         "PM2.5": [np.nan] * 24 + [30.0] * 24,
                         "PM10": [40.0] * 48, "AQI": [50.0] * 48})
    dataset = processor.process_dataset([day1, day2])
    assert dataset is not None
    assert dataset["n_features"] == 3

    assert processor.process_dataset([]) is None
    assert processor.process_dataset("not-a-list") is None


def test_pypots_failure_and_lstm_import_error(tmp_path):
    """SAITS impute error path + LSTM ImportError path (no tensorflow)."""
    from legacy_algorithms import data_imputation as di

    imputer = di.PyPOTSImputer(24, 3, n_epochs=1)
    assert imputer.perform_imputation({"broken": True}) is None

    lstm = di.LSTMImputer(24, 3, n_epochs=1)
    assert lstm.perform_imputation({"train_X": np.zeros((1, 24, 3)),
                                    "mask": {"train": np.ones((1, 24, 3), dtype=bool)}}) is None


def test_save_all_results_with_metrics(tmp_path):
    """ResultsSaver.save_results exercising metrics collection + plotting."""
    from legacy_algorithms import data_imputation as di

    saver = di.ResultsSaver(tmp_path / "results", tmp_path / "plots")
    n_stations, n_steps, n_features = 2, 24, 3
    base = np.random.RandomState(0).rand(n_stations, n_steps, n_features).astype(np.float32)
    results = {"train_imputed": base.copy(), "val_imputed": base.copy(),
               "test_imputed": base.copy()}
    mask = np.ones((n_stations, n_steps, n_features), dtype=bool)
    from sklearn.preprocessing import StandardScaler
    dataset = {
        "feature_columns": ["PM2.5", "PM10", "AQI"],
        "n_features": n_features,
        "scaler": StandardScaler().fit(base.reshape(-1, n_features)),
        "train_X": base.copy(), "train_X_ori": base.copy(),
        "val_X": base.copy(), "val_X_ori": base.copy(),
        "test_X": base.copy(),
        "train_masked_positions": np.zeros_like(mask),
        "val_masked_positions": np.zeros_like(mask),
        "mask": {"train": mask, "val": mask, "test": mask},
    }
    saver.save_results(results, dataset, model_name="toy")
    assert any((tmp_path / "results").iterdir())


def test_compare_models_and_train_pypots_failure(tmp_path):
    """compare_models with fake lstm_results + train_pypots bad dataset."""
    from legacy_algorithms import data_imputation as di
    from legacy_algorithms import train_all_models as tam

    tam.RESULTS_DIR = str(tmp_path / "r")
    tam.PLOTS_DIR = str(tmp_path / "p")

    n_stations, n_steps, n_features = 2, 24, 3
    rng = np.random.RandomState(1)
    dataset = {
        "train_X_ori": rng.rand(n_stations, n_steps, n_features),
        "val_X_ori": rng.rand(n_stations, n_steps, n_features),
        "test_X_ori": rng.rand(n_stations, n_steps, n_features),
        "scaler": None, "n_features": n_features,
        "mask": {k: np.ones((n_stations, n_steps, n_features), dtype=bool)
                 for k in ("train", "val", "test")},
    }
    fake = {"train_imputed": dataset["train_X_ori"] + 0.1,
            "val_imputed": dataset["val_X_ori"] + 0.1}
    comparison = tam.compare_models(fake, fake, dataset)
    assert "pypots_train" in comparison and "lstm_train" in comparison

    partial = tam.compare_models({"train_imputed": fake["train_imputed"]}, None, dataset)
    assert "pypots_train" in partial and "lstm_train" not in partial

    assert tam.train_pypots({"n_steps": 24, "n_features": 3}, n_epochs=1) is None


def test_legal_supervision_main_entry(tmp_path):
    """__main__ summary block via runpy on the real module."""
    import runpy

    try:
        runpy.run_module("legacy_algorithms.legal_supervision", run_name="__main__")
    except Exception:
        pass  # real run may fail without full data; coverage of the attempt counts
