"""DataFrame-only bridge for the legacy wide-table preprocessing function."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from typing import Mapping

import numpy as np
import pandas as pd

from app.domain.dataframe_contracts import (
    AlgorithmContractError,
    require_columns,
    require_frame,
    require_identifier_values,
    require_nonnegative_finite,
    require_sorted_unique,
)
from legacy_algorithms import data_preprocessing as legacy

_BASE_COLUMNS = ("date", "hour", "type")
_PARTICULATE_COLUMNS = ("station_id", "timestamp", "PM2.5", "PM10", "AQI", "date")
_GAS_KEYS = ("station_id", "timestamp", "date")


@dataclass(frozen=True)
class PreprocessingResult:
    """Validated per-date frames emitted by the historical converter."""

    particulate: Mapping[str, pd.DataFrame]
    gas: Mapping[str, pd.DataFrame]


def _validate_wide_input(frame: pd.DataFrame) -> None:
    require_frame(frame, "preprocessing input")
    require_columns(frame, _BASE_COLUMNS, "preprocessing input")
    station_columns = [column for column in frame.columns if column not in _BASE_COLUMNS]
    if not station_columns:
        raise AlgorithmContractError("preprocessing input must include at least one station column")
    require_identifier_values(frame, _BASE_COLUMNS, "preprocessing input")
    if not set(("PM2.5", "PM10", "AQI")).issubset(set(frame["type"].astype(str))):
        raise AlgorithmContractError("preprocessing input must include PM2.5, PM10, and AQI rows")
    require_nonnegative_finite(frame, station_columns, "preprocessing input", allow_null=True)


def _validate_particulate_output(frame: pd.DataFrame, context: str) -> None:
    require_columns(frame, _PARTICULATE_COLUMNS, context, exact=True)
    require_identifier_values(frame, ("station_id", "timestamp", "date"), context)
    require_sorted_unique(frame, ("station_id", "date", "timestamp"), context)
    require_nonnegative_finite(frame, ("PM2.5", "PM10", "AQI"), context, allow_null=True)


def _validate_gas_output(frame: pd.DataFrame, context: str) -> None:
    require_columns(frame, _GAS_KEYS, context)
    require_identifier_values(frame, _GAS_KEYS, context)
    require_sorted_unique(frame, ("station_id", "date", "timestamp"), context)
    gas_columns = [column for column in frame.columns if column not in _GAS_KEYS]
    require_nonnegative_finite(frame, gas_columns, context, allow_null=True)


def preprocess_wide_dataframe(source: pd.DataFrame) -> PreprocessingResult:
    """Run the unchanged file-based legacy converter behind a DataFrame boundary.

    The adapter owns a temporary directory and only returns results after every
    generated artifact satisfies the contract.  Failed validation therefore
    exposes no partial result to the caller.
    """

    _validate_wide_input(source)
    with TemporaryDirectory(prefix="legacy-preprocessing-") as temporary:
        root = Path(temporary)
        input_path = root / "input.csv"
        output_dir = root / "output"
        source.to_csv(input_path, index=False)
        if not legacy.process_air_quality_data(input_path, output_dir=output_dir):
            raise AlgorithmContractError("legacy preprocessing reported failure")

        particulate: dict[str, pd.DataFrame] = {}
        gas: dict[str, pd.DataFrame] = {}
        for path in sorted(output_dir.glob("*_particulate.csv")):
            date = path.name.removesuffix("_particulate.csv")
            frame = pd.read_csv(path)
            _validate_particulate_output(frame, f"preprocessing particulate output {date}")
            particulate[date] = frame
        for path in sorted(output_dir.glob("*_gas.csv")):
            date = path.name.removesuffix("_gas.csv")
            frame = pd.read_csv(path)
            _validate_gas_output(frame, f"preprocessing gas output {date}")
            gas[date] = frame

        if not particulate or set(particulate) != set(gas):
            raise AlgorithmContractError("legacy preprocessing emitted incomplete date artifacts")
        return PreprocessingResult(
            particulate=MappingProxyType(particulate), gas=MappingProxyType(gas)
        )
