"""Hour-of-day seasonal term plus a median slope. Outputs stay non-negative."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from numpy.typing import NDArray

METHOD = "seasonal-median-robust-trend"
METHOD_VERSION = "1"

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class ForecastPoint:
    forecast_at: datetime
    pollutant: str
    predicted_value: float
    exceedance_probability: float
    is_warning: bool


def forecast_series(
    history: FloatArray,
    history_end: datetime,
    *,
    horizon_hours: int,
    limit: float,
    warning_probability: float,
    pollutant: str,
) -> tuple[ForecastPoint, ...]:
    """Project one pollutant. ``history`` is an hourly series ending at ``history_end``."""

    if horizon_hours < 1:
        raise ValueError("horizon must be positive")
    if limit <= 0 or not math.isfinite(limit):
        raise ValueError("limit must be positive and finite")
    seasonal = _seasonal_median(history)
    slope = _median_slope(history)
    residuals = history - _seasonal_lookup(history, seasonal)
    scale = float(np.median(np.abs(residuals - np.median(residuals)))) or 1.0
    points: list[ForecastPoint] = []
    for step in range(1, horizon_hours + 1):
        instant = history_end + timedelta(hours=step)
        baseline = seasonal[instant.hour]
        predicted = max(0.0, float(baseline + slope * step))
        probability = _exceedance_probability(predicted, limit, scale)
        points.append(
            ForecastPoint(
                forecast_at=instant,
                pollutant=pollutant,
                predicted_value=predicted,
                exceedance_probability=probability,
                is_warning=probability >= warning_probability,
            )
        )
    return tuple(points)


def _seasonal_median(history: FloatArray) -> FloatArray:
    buckets: list[list[float]] = [[] for _ in range(24)]
    for index, value in enumerate(history):
        buckets[index % 24].append(float(value))
    seasonal = np.zeros(24, dtype=float)
    for hour, values in enumerate(buckets):
        seasonal[hour] = float(np.median(values)) if values else float(np.median(history))
    return seasonal


def _seasonal_lookup(history: FloatArray, seasonal: FloatArray) -> FloatArray:
    return np.asarray([seasonal[index % 24] for index in range(len(history))], dtype=float)


def _median_slope(history: FloatArray) -> float:
    if len(history) < 2:
        return 0.0
    diffs = np.diff(history.astype(float))
    return float(np.median(diffs))


def _exceedance_probability(predicted: float, limit: float, scale: float) -> float:
    # A logistic of the robust residual scale. The result is finite and inside [0, 1].
    distance = (predicted - limit) / max(scale, 1e-6)
    distance = max(-60.0, min(60.0, distance))
    probability = 1.0 / (1.0 + math.exp(-distance))
    return min(1.0, max(0.0, probability))
