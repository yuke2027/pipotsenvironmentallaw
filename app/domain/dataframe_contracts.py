"""Pure DataFrame and ndarray contracts used at legacy algorithm boundaries.

These checks deliberately run before and after every legacy call.  They raise a
single, domain-specific exception so callers can abort their enclosing unit of
work before persisting any result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

AnyArray = np.ndarray[Any, np.dtype[Any]]
FloatArray = np.ndarray[Any, np.dtype[np.float64]]
BoolArray = np.ndarray[Any, np.dtype[np.bool_]]

FEATURE_COLUMNS: tuple[str, ...] = ("PM2.5", "PM10", "AQI")
MEASUREMENT_COLUMNS: tuple[str, ...] = (
    "station_id",
    "timestamp",
    "date",
    *FEATURE_COLUMNS,
)


class AlgorithmContractError(ValueError):
    """Raised when a legacy algorithm violates its declared data contract."""

    code = "ALGORITHM_CONTRACT_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(f"{self.code}: {message}")


@dataclass(frozen=True)
class ScalerArtifact:
    """Portable numeric scaling metadata; never serialize a legacy local class."""

    feature_order: tuple[str, ...]
    mean: FloatArray
    scale: FloatArray


@dataclass(frozen=True)
class TrainingDataset:
    """Explicit, validated training tensors produced by the legacy processor."""

    feature_order: tuple[str, ...]
    n_steps: int
    n_features: int
    train_x: FloatArray
    train_original: FloatArray
    validation_x: FloatArray
    validation_original: FloatArray
    test_x: FloatArray
    masks: Mapping[str, BoolArray]
    scaler: ScalerArtifact


@dataclass(frozen=True)
class ImputationResult:
    """The fixed three-split result returned by a legacy imputer."""

    train: FloatArray
    validation: FloatArray
    test: FloatArray


def require_frame(value: object, context: str) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame):
        raise AlgorithmContractError(f"{context} must be a pandas DataFrame")
    return value


def require_columns(
    frame: pd.DataFrame,
    required: Sequence[str],
    context: str,
    *,
    exact: bool = False,
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise AlgorithmContractError(f"{context} is missing columns: {missing}")
    if exact and list(frame.columns) != list(required):
        raise AlgorithmContractError(
            f"{context} columns drifted: expected {list(required)}, got {frame.columns.tolist()}"
        )


def require_identifier_values(frame: pd.DataFrame, columns: Sequence[str], context: str) -> None:
    for column in columns:
        values = frame[column]
        if values.isna().any() or values.astype(str).str.strip().eq("").any():
            raise AlgorithmContractError(f"{context}.{column} contains a missing or empty key")


def require_sorted_unique(
    frame: pd.DataFrame, keys: Sequence[str], context: str
) -> None:
    require_columns(frame, keys, context)
    if frame.duplicated(list(keys)).any():
        raise AlgorithmContractError(f"{context} contains duplicate keys: {list(keys)}")
    ordered = frame.sort_values(list(keys), kind="mergesort").index.to_list()
    if frame.index.to_list() != ordered:
        raise AlgorithmContractError(f"{context} must be sorted by keys: {list(keys)}")


def require_nonnegative_finite(
    frame: pd.DataFrame,
    columns: Sequence[str],
    context: str,
    *,
    allow_null: bool,
) -> None:
    require_columns(frame, columns, context)
    for column in columns:
        numeric = pd.to_numeric(frame[column], errors="coerce")
        invalid_type = frame[column].notna() & numeric.isna()
        finite = np.isfinite(numeric.fillna(0.0).to_numpy(dtype=float))
        negative = numeric.fillna(0.0).lt(0).to_numpy()
        null = numeric.isna().to_numpy()
        if invalid_type.any() or not finite.all() or negative.any() or (not allow_null and null.any()):
            raise AlgorithmContractError(
                f"{context}.{column} must contain only non-negative finite values"
                + (" or null" if allow_null else "")
            )


def validate_measurements(frame: pd.DataFrame, context: str) -> None:
    """Validate the repository-to-algorithm measurement DataFrame contract."""

    require_frame(frame, context)
    require_columns(frame, MEASUREMENT_COLUMNS, context)
    require_identifier_values(frame, ("station_id", "timestamp", "date"), context)
    require_sorted_unique(frame, ("station_id", "date", "timestamp"), context)
    require_nonnegative_finite(frame, FEATURE_COLUMNS, context, allow_null=True)


def validate_feature_order(feature_order: Sequence[str], context: str) -> tuple[str, ...]:
    order = tuple(feature_order)
    if order != FEATURE_COLUMNS:
        raise AlgorithmContractError(
            f"{context} feature order must be {list(FEATURE_COLUMNS)}, got {list(order)}"
        )
    return order


def validate_tensor(
    values: object,
    *,
    feature_order: Sequence[str],
    context: str,
    allow_nan: bool,
    expected_shape: tuple[int, ...] | None = None,
) -> FloatArray:
    validate_feature_order(feature_order, context)
    if not isinstance(values, np.ndarray) or values.ndim != 3:
        raise AlgorithmContractError(f"{context} must be a three-dimensional numpy array")
    if values.shape[-1] != len(FEATURE_COLUMNS):
        raise AlgorithmContractError(f"{context} has an unexpected feature dimension")
    if expected_shape is not None and values.shape != expected_shape:
        raise AlgorithmContractError(
            f"{context} shape drifted: expected {expected_shape}, got {values.shape}"
        )
    try:
        numeric = values.astype(float, copy=False)
    except (TypeError, ValueError) as error:
        raise AlgorithmContractError(f"{context} must contain numeric values") from error
    if np.isinf(numeric).any() or (not allow_nan and np.isnan(numeric).any()):
        raise AlgorithmContractError(
            f"{context} must contain finite values" + (" or NaN" if allow_nan else "")
        )
    if np.nanmin(numeric, initial=0.0) < 0:
        raise AlgorithmContractError(f"{context} must not contain negative values")
    return numeric


def validate_scaler_artifact(artifact: ScalerArtifact, context: str) -> None:
    validate_feature_order(artifact.feature_order, context)
    if artifact.mean.shape != (len(FEATURE_COLUMNS),) or artifact.scale.shape != (
        len(FEATURE_COLUMNS),
    ):
        raise AlgorithmContractError(f"{context} scaler arrays must match the feature order")
    if not np.isfinite(artifact.mean).all() or not np.isfinite(artifact.scale).all():
        raise AlgorithmContractError(f"{context} scaler arrays must be finite")
    if (artifact.scale <= 0).any():
        raise AlgorithmContractError(f"{context} scaler scale must be positive")


def require_exact_mapping_keys(
    value: Mapping[str, Any], expected: Sequence[str], context: str
) -> None:
    actual = set(value)
    expected_set = set(expected)
    if actual != expected_set:
        raise AlgorithmContractError(
            f"{context} keys drifted: expected {sorted(expected_set)}, got {sorted(actual)}"
        )


def validate_metrics(metrics: Mapping[str, object], context: str) -> dict[str, float]:
    expected = ("MSE", "MAE", "RMSE")
    require_exact_mapping_keys(metrics, expected, context)
    converted: dict[str, float] = {}
    for key in expected:
        raw = metrics[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise AlgorithmContractError(f"{context}.{key} must be numeric")
        try:
            value = float(raw)
        except (TypeError, ValueError) as error:
            raise AlgorithmContractError(f"{context}.{key} must be numeric") from error
        if not np.isfinite(value) or value < 0:
            raise AlgorithmContractError(f"{context}.{key} must be non-negative and finite")
        converted[key] = value
    return converted
