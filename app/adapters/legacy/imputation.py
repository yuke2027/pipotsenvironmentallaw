"""Validated bridge for legacy tensor preparation and imputation."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from app.domain.dataframe_contracts import (
    AlgorithmContractError,
    BoolArray,
    FEATURE_COLUMNS,
    FloatArray,
    ImputationResult,
    ScalerArtifact,
    TrainingDataset,
    require_exact_mapping_keys,
    validate_feature_order,
    validate_measurements,
    validate_scaler_artifact,
    validate_tensor,
)
from legacy_algorithms import data_imputation as legacy

_SPLITS = ("train", "val", "test")
_RESULT_KEYS = tuple(f"{split}_imputed" for split in _SPLITS)


def prepare_training_dataset(daily_frames: Sequence[pd.DataFrame]) -> TrainingDataset:
    """Convert sorted daily DataFrames to explicit numeric tensors and scaler data."""

    if not daily_frames:
        raise AlgorithmContractError("imputation input must contain at least one daily DataFrame")
    for index, frame in enumerate(daily_frames):
        validate_measurements(frame, f"imputation input[{index}]")

    raw_dataset = legacy.AirQualityDataProcessor().process_dataset(list(daily_frames))
    if not isinstance(raw_dataset, dict):
        raise AlgorithmContractError("legacy dataset processor returned no dataset")
    expected = {
        "n_steps",
        "n_features",
        "feature_columns",
        "scaler",
        "train_X",
        "train_X_ori",
        "train_masked_positions",
        "val_X",
        "val_X_ori",
        "val_masked_positions",
        "test_X",
        "mask",
    }
    if set(raw_dataset) != expected:
        raise AlgorithmContractError("legacy dataset keys drifted")
    feature_order = validate_feature_order(raw_dataset["feature_columns"], "legacy dataset")
    n_steps = raw_dataset["n_steps"]
    n_features = raw_dataset["n_features"]
    if not isinstance(n_steps, int) or n_steps <= 0 or n_features != len(FEATURE_COLUMNS):
        raise AlgorithmContractError("legacy dataset dimensions are invalid")
    masks = raw_dataset["mask"]
    if not isinstance(masks, dict):
        raise AlgorithmContractError("legacy dataset masks must be a mapping")
    require_exact_mapping_keys(masks, _SPLITS, "legacy dataset masks")

    tensors: dict[str, FloatArray] = {}
    originals: dict[str, FloatArray] = {}
    for split in _SPLITS:
        tensor = validate_tensor(
            raw_dataset[f"{split}_X"],
            feature_order=feature_order,
            context=f"legacy {split} tensor",
            allow_nan=True,
        )
        original = validate_tensor(
            raw_dataset[f"{split}_X_ori"],
            feature_order=feature_order,
            context=f"legacy {split} original tensor",
            allow_nan=True,
            expected_shape=tensor.shape,
        )
        mask = masks[split]
        if not isinstance(mask, np.ndarray) or mask.dtype != bool or mask.shape != tensor.shape:
            raise AlgorithmContractError(f"legacy {split} mask shape or dtype drifted")
        tensors[split] = tensor
        originals[split] = original

    scaler = raw_dataset["scaler"]
    artifact = ScalerArtifact(
        feature_order=feature_order,
        mean=np.asarray(getattr(scaler, "mean_", None), dtype=float),
        scale=np.asarray(getattr(scaler, "scale_", None), dtype=float),
    )
    validate_scaler_artifact(artifact, "legacy dataset")
    return TrainingDataset(
        feature_order=feature_order,
        n_steps=n_steps,
        n_features=n_features,
        train_x=tensors["train"],
        train_original=originals["train"],
        validation_x=tensors["val"],
        validation_original=originals["val"],
        test_x=tensors["test"],
        masks={split: masks[split].copy() for split in _SPLITS},
        scaler=artifact,
    )


def to_legacy_dataset(dataset: TrainingDataset) -> dict[str, object]:
    """Build the exact in-memory mapping required by unchanged legacy imputers."""

    validate_feature_order(dataset.feature_order, "training dataset")
    validate_scaler_artifact(dataset.scaler, "training dataset")
    if dataset.n_features != len(FEATURE_COLUMNS) or dataset.n_steps <= 0:
        raise AlgorithmContractError("training dataset dimensions are invalid")
    tensors = {
        "train": (dataset.train_x, dataset.train_original),
        "val": (dataset.validation_x, dataset.validation_original),
        "test": (dataset.test_x, dataset.test_x),
    }
    for split, (tensor, original) in tensors.items():
        checked = validate_tensor(
            tensor,
            feature_order=dataset.feature_order,
            context=f"training dataset {split}",
            allow_nan=True,
        )
        validate_tensor(
            original,
            feature_order=dataset.feature_order,
            context=f"training dataset {split} original",
            allow_nan=True,
            expected_shape=checked.shape,
        )
        mask = dataset.masks.get(split)
        if not isinstance(mask, np.ndarray) or mask.dtype != bool or mask.shape != checked.shape:
            raise AlgorithmContractError(f"training dataset {split} mask shape or dtype drifted")

    return {
        "n_steps": dataset.n_steps,
        "n_features": dataset.n_features,
        "feature_columns": list(dataset.feature_order),
        "train_X": dataset.train_x.copy(),
        "train_X_ori": dataset.train_original.copy(),
        "val_X": dataset.validation_x.copy(),
        "val_X_ori": dataset.validation_original.copy(),
        "test_X": dataset.test_x.copy(),
        "mask": {split: dataset.masks[split].copy() for split in _SPLITS},
    }


def _validate_imputation_result(result: object, dataset: TrainingDataset) -> ImputationResult:
    if not isinstance(result, dict):
        raise AlgorithmContractError("legacy imputer returned no result mapping")
    require_exact_mapping_keys(result, _RESULT_KEYS, "legacy imputer result")
    expected_shapes = {
        "train": dataset.train_x.shape,
        "val": dataset.validation_x.shape,
        "test": dataset.test_x.shape,
    }
    tensors = {
        split: validate_tensor(
            result[f"{split}_imputed"],
            feature_order=dataset.feature_order,
            context=f"legacy imputer {split} result",
            allow_nan=False,
            expected_shape=expected_shapes[split],
        )
        for split in _SPLITS
    }
    return ImputationResult(
        train=tensors["train"], validation=tensors["val"], test=tensors["test"]
    )


def run_pypots_imputation(dataset: TrainingDataset, *, n_epochs: int = 10) -> ImputationResult:
    """Run legacy SAITS with no file, configuration, or persistence dependency."""

    if n_epochs <= 0:
        raise AlgorithmContractError("PyPOTS epoch count must be positive")
    imputer = legacy.PyPOTSImputer(dataset.n_steps, dataset.n_features, n_epochs=n_epochs)
    result = imputer.perform_imputation(to_legacy_dataset(dataset))
    return _validate_imputation_result(result, dataset)


def run_lstm_imputation(
    dataset: TrainingDataset, *, n_epochs: int = 50, hidden_units: int = 128
) -> ImputationResult:
    """Run legacy LSTM with explicit dimensions and validated returned tensors."""

    if n_epochs <= 0 or hidden_units <= 0:
        raise AlgorithmContractError("LSTM epoch count and hidden units must be positive")
    imputer = legacy.LSTMImputer(
        dataset.n_steps, dataset.n_features, n_epochs=n_epochs, hidden_units=hidden_units
    )
    result = imputer.perform_imputation(to_legacy_dataset(dataset))
    return _validate_imputation_result(result, dataset)
