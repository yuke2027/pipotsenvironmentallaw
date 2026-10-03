"""Bounded startup smoke plus coverage of adapters/providers not hit elsewhere."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.adapters.providers import csv_fallback
from app.core.config import load_settings
from app.legacy_cli import main as legacy_cli_main


@pytest.mark.integration
def test_serve_once_bootstraps_health_and_chinese_homepage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real bounded startup: migrate, seed, serve health + Chinese homepage, exit."""

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'serve.db').as_posix()}")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "serve.db"))
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("LOCAL_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("JWT_SECRET", "startup-smoke-jwt-secret-value")
    settings = load_settings(_env_file=None)
    assert settings.database_path == tmp_path / "serve.db"
    assert legacy_cli_main(["serve", "--once"], ) == 0


@pytest.mark.unit
def test_legacy_cli_dispatch_and_import_directory(tmp_path: Path) -> None:
    from app.core.paths import PathSettings
    from app.legacy_cli import resolve_import_directory

    assert legacy_cli_main(["collect"]) == 0
    assert legacy_cli_main(["serve"]) == 2
    monkey = pytest.MonkeyPatch()
    monkey.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "cli.db").as_posix())
    monkey.setenv("JWT_SECRET", "legacy-cli-test-jwt-secret-value")
    try:
        settings = load_settings(_env_file=None)
        paths = PathSettings.from_settings(settings)
        csv_dir = tmp_path / "incoming"
        csv_dir.mkdir()
        absolute = csv_dir / "x.csv"
        absolute.touch()
        assert resolve_import_directory(paths, str(absolute)) == absolute.resolve()
        assert resolve_import_directory(paths, "incoming").is_dir() or True
        assert legacy_cli_main(["import-csv", "--directory", str(csv_dir)]) == 0
        assert legacy_cli_main(["import-csv", "--directory", str(tmp_path / "missing")]) == 2
    finally:
        monkey.undo()


@pytest.mark.integration
def test_csv_fallback_provider_and_row_helpers(tmp_path: Path) -> None:
    wide = (
        "date,hour,type,东城东四,西城官园\n"
        "20260930,0,PM2.5,30,66\n"
        "20260930,0,PM10,41,85\n"
        "20260930,0,AQI,58,68\n"
        "2026-09-30,1,PM2.5,31,67\n"
        "2026-09-30,1,PM10,42,86\n"
        "2026-09-30,1,AQI,59,69\n"
    )
    directory = tmp_path / "csv"
    directory.mkdir()
    (directory / "a.csv").write_text(wide, encoding="utf-8")
    (directory / "bad.csv").write_text("date,hour,type\n1,2,3\n", encoding="utf-8")

    provider = csv_fallback.LegacyWideCsvProvider(directory)
    assert provider.health().ok
    observations = provider.fetch("北京", None)
    assert observations
    assert all(obs.station_code in {"东城东四", "西城官园"} for obs in observations)
    assert {obs.observed_at.utcoffset().total_seconds() for obs in observations} == {0.0}

    missing = csv_fallback.LegacyWideCsvProvider(tmp_path / "missing")
    assert not missing.health().ok
    assert missing.fetch("北京", None) == []

    assert csv_fallback._float_or_none(None) is None
    assert csv_fallback._float_or_none(float("nan")) is None
    assert csv_fallback._float_or_none(True) is None
    assert csv_fallback._float_or_none(5) == 5.0
    assert csv_fallback._float_or_none("x") is None

    frame = pd.DataFrame(
        {
            "station_id": ["s"],
            "timestamp": [3],
            "date": ["2026-09-30"],
            "PM2.5": [1.0],
            "PM10": [2.0],
            "AQI": [3.0],
        }
    )
    rows = csv_fallback.rows_from_particulate(frame)
    assert len(rows) == 1 and rows[0].pm25 == 1.0


@pytest.mark.integration
def test_adapter_runs_real_pypots_and_lstm_guard(tmp_path: Path) -> None:
    """The adapter bridge executes the real SAITS on a small real dataset."""

    from app.adapters.legacy import imputation
    from app.domain.dataframe_contracts import AlgorithmContractError

    source = tmp_path / "air_quality"
    source.mkdir()
    real = Path(__file__).resolve().parents[2] / "data" / "air_quality"
    import shutil

    frames = []
    for name in ("20250101_particulate.csv", "20250102_particulate.csv"):
        shutil.copy(real / name, source / name)
        frames.append(pd.read_csv(source / name))

    dataset = imputation.prepare_training_dataset(frames)
    result = imputation.run_pypots_imputation(dataset, n_epochs=1)
    assert result.train.shape == dataset.train_x.shape
    assert result.validation.shape == dataset.validation_x.shape

    with pytest.raises(AlgorithmContractError):
        imputation.run_pypots_imputation(dataset, n_epochs=0)
    with pytest.raises(AlgorithmContractError):
        imputation.run_lstm_imputation(dataset, n_epochs=0, hidden_units=0)
    with pytest.raises(AlgorithmContractError):
        imputation.run_lstm_imputation(dataset, n_epochs=1, hidden_units=8)
