"""Boundary checks for model artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.adapters.model_artifacts import (
    ArrayStandardizer,
    ArtifactError,
    apply_imputation,
    load_artifact,
    write_artifact,
)
from app.domain.dataframe_contracts import FEATURE_COLUMNS


def _payload() -> dict[str, object]:
    return {
        "scaler": {
            "schema_version": 1,
            "feature_order": list(FEATURE_COLUMNS),
            "mean": [0, 0, 0],
            "scale": [1, 1, 1],
            "n_features": 3,
            "n_steps": 4,
            "dtype": "float32",
        },
        "manifest": {"model_type": "saits", "n_steps": 4, "n_features": 3},
    }


def test_rejects_bad_checksum_pickle_and_path_escape(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()
    destination = write_artifact(root, "saits/v1", _payload(), b"model-bytes")
    assert (destination / "manifest.json").is_file()
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ArtifactError):
        load_artifact(root, "saits/v1")
    with pytest.raises(ArtifactError):
        load_artifact(root, "missing.pkl")
    with pytest.raises(ArtifactError):
        write_artifact(root, "../escape", _payload(), b"nope")
    broken = root / "broken"
    broken.mkdir()
    (broken / "model.bin").write_bytes(b"x")
    (broken / "scaler.json").write_text("{", encoding="utf-8")
    with pytest.raises(ArtifactError):
        load_artifact(root, "broken")


def test_short_series_is_a_no_op_and_observed_values_stay() -> None:
    observed = np.asarray([1.0, 2.0, 3.0])
    missing = np.asarray([False, True, False])
    filled, mask = apply_imputation(observed, missing, np.asarray([9.0, 8.0, 7.0]))
    assert filled.tolist() == [1.0, 8.0, 3.0]
    assert mask.tolist() == [False, True, False]
    with pytest.raises(ArtifactError):
        ArrayStandardizer(np.asarray([0.0, 0.0]), np.asarray([1.0, 1.0]), FEATURE_COLUMNS)
