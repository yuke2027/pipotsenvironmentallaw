"""Station forecasts. Short histories are skipped instead of inventing a curve."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from app.adapters.forecasting.baseline import METHOD, METHOD_VERSION, ForecastPoint, forecast_series


@dataclass(frozen=True)
class ForecastBundle:
    status: str
    method: str
    method_version: str
    generated_at: datetime
    horizon_hours: int
    points: tuple[ForecastPoint, ...]
    skip_reason: str | None


def build_forecast(
    history: dict[str, list[float]],
    history_end: datetime,
    *,
    generated_at: datetime,
    horizon_hours: int,
    limits: dict[str, float],
    warning_probability: float,
    min_samples: int,
) -> ForecastBundle:
    if horizon_hours < 1:
        raise ValueError("horizon must be positive")
    shortest = min((len(values) for values in history.values()), default=0)
    if shortest < min_samples:
        return ForecastBundle(
            status="SKIPPED",
            method=METHOD,
            method_version=METHOD_VERSION,
            generated_at=generated_at,
            horizon_hours=horizon_hours,
            points=(),
            skip_reason="history shorter than the minimum sample count",
        )
    points: list[ForecastPoint] = []
    for pollutant, values in history.items():
        points.extend(
            forecast_series(
                np.asarray(values, dtype=float),
                history_end,
                horizon_hours=horizon_hours,
                limit=limits[pollutant],
                warning_probability=warning_probability,
                pollutant=pollutant,
            )
        )
    return ForecastBundle(
        status="SUCCESS",
        method=METHOD,
        method_version=METHOD_VERSION,
        generated_at=generated_at,
        horizon_hours=horizon_hours,
        points=tuple(points),
        skip_reason=None,
    )
