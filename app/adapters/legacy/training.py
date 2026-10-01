"""Explicit-artifact bridge for legacy training components and metrics."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np

from app.domain.dataframe_contracts import (
    AlgorithmContractError,
    ScalerArtifact,
    TrainingDataset,
    validate_metrics,
    validate_scaler_artifact,
    validate_tensor,
)
from legacy_algorithms import train_all_models as legacy_training


class _ArrayScaler:
    """Private numeric replacement for the legacy function-local scaler class."""

    def __init__(self, artifact: ScalerArtifact) -> None:
        self.mean_ = artifact.mean.copy()
        self.scale_ = artifact.scale.copy()

    def inverse_transform(self, values: np.ndarray[Any, np.dtype[Any]]) -> np.ndarray[Any, np.dtype[Any]]:
        return values * self.scale_ + self.mean_


def calculate_original_scale_metrics(
    original: np.ndarray[Any, np.dtype[Any]],
    imputed: np.ndarray[Any, np.dtype[Any]],
    observed_mask: np.ndarray[Any, np.dtype[Any]],
    scaler: ScalerArtifact,
    *,
    masked_positions: np.ndarray[Any, np.dtype[Any]] | None = None,
) -> dict[str, float]:
    """Delegate original-scale metrics while keeping paths and scaler explicit."""

    validate_scaler_artifact(scaler, "metrics scaler")
    original_checked = validate_tensor(
        original,
        feature_order=scaler.feature_order,
        context="metrics original tensor",
        allow_nan=True,
    )
    imputed_checked = validate_tensor(
        imputed,
        feature_order=scaler.feature_order,
        context="metrics imputed tensor",
        allow_nan=True,
        expected_shape=original_checked.shape,
    )
    if not isinstance(observed_mask, np.ndarray) or observed_mask.dtype != bool:
        raise AlgorithmContractError("metrics observed mask must be a boolean ndarray")
    if observed_mask.shape != original_checked.shape:
        raise AlgorithmContractError("metrics observed mask shape drifted")
    if masked_positions is not None and (
        not isinstance(masked_positions, np.ndarray)
        or masked_positions.dtype != bool
        or masked_positions.shape != original_checked.shape
    ):
        raise AlgorithmContractError("metrics masked positions shape or dtype drifted")

    # ResultsSaver creates directories for visualizer setup.  Keep those legacy
    # side effects private and discard them after metric calculation.
    with TemporaryDirectory(prefix="legacy-metrics-") as temporary:
        root = Path(temporary)
        saver = legacy_training.ResultsSaver(root / "results", root / "plots")
        metrics = saver.calculate_metrics(
            original_checked,
            imputed_checked,
            observed_mask,
            _ArrayScaler(scaler),
            len(scaler.feature_order),
            masked_positions=masked_positions,
        )
    return validate_metrics(metrics, "legacy metrics result")


def create_pypots_imputer(dataset: TrainingDataset, *, n_epochs: int = 10) -> object:
    """Expose a configured legacy trainer without consulting legacy path globals."""

    if n_epochs <= 0:
        raise AlgorithmContractError("PyPOTS epoch count must be positive")
    if dataset.n_steps <= 0 or dataset.n_features != len(dataset.feature_order):
        raise AlgorithmContractError("training dataset dimensions are invalid")
    return legacy_training.PyPOTSImputer(dataset.n_steps, dataset.n_features, n_epochs=n_epochs)


def create_lstm_imputer(
    dataset: TrainingDataset, *, n_epochs: int = 50, hidden_units: int = 128
) -> object:
    """Expose a configured legacy LSTM trainer with explicit dimensions only."""

    if n_epochs <= 0 or hidden_units <= 0:
        raise AlgorithmContractError("LSTM epoch count and hidden units must be positive")
    if dataset.n_steps <= 0 or dataset.n_features != len(dataset.feature_order):
        raise AlgorithmContractError("training dataset dimensions are invalid")
    return legacy_training.LSTMImputer(
        dataset.n_steps,
        dataset.n_features,
        n_epochs=n_epochs,
        hidden_units=hidden_units,
    )
