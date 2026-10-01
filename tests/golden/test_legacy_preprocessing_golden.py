"""Golden regression tests for the migrated legacy CSV preprocessing behavior.

The fixtures deliberately capture observable behavior of ``process_air_quality_data``
through its canonical ``legacy_algorithms`` import. Each invocation operates on a
copied local fixture and an isolated temporary output directory.
"""

from __future__ import annotations

from pathlib import Path
from shutil import copyfile

import pandas as pd
import pytest

from legacy_algorithms.data_preprocessing import process_air_quality_data


FIXTURES = Path(__file__).parents[1] / "fixtures" / "golden"


def _copy_input(tmp_path: Path, fixture_name: str) -> Path:
    input_path = tmp_path / fixture_name
    copyfile(FIXTURES / fixture_name, input_path)
    return input_path


def _assert_csv_matches_golden(actual_path: Path, expected_name: str) -> None:
    actual = pd.read_csv(actual_path)
    expected = pd.read_csv(FIXTURES / expected_name)

    assert actual.columns.tolist() == expected.columns.tolist()
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False)


@pytest.mark.golden
def test_process_air_quality_data_matches_wide_table_golden_across_dates(
    tmp_path: Path,
) -> None:
    """Lock station/time keys, column order, values, nulls, and four artifacts."""
    output_dir = tmp_path / "processed"
    input_path = _copy_input(tmp_path, "valid_wide.csv")

    assert process_air_quality_data(input_path, output_dir=output_dir)

    expected_artifacts = {
        "20250101_particulate.csv": "valid_wide_expected_20250101_particulate.csv",
        "20250101_gas.csv": "valid_wide_expected_20250101_gas.csv",
        "20250102_particulate.csv": "valid_wide_expected_20250102_particulate.csv",
        "20250102_gas.csv": "valid_wide_expected_20250102_gas.csv",
    }
    assert {path.name for path in output_dir.iterdir()} == set(expected_artifacts)
    for artifact_name, expected_name in expected_artifacts.items():
        _assert_csv_matches_golden(output_dir / artifact_name, expected_name)


@pytest.mark.golden
def test_process_air_quality_data_matches_minimal_legal_file_golden(
    tmp_path: Path,
) -> None:
    """Lock the smallest accepted station/hour/pollutant input and both outputs."""
    output_dir = tmp_path / "processed"
    input_path = _copy_input(tmp_path, "minimal_wide.csv")

    assert process_air_quality_data(input_path, output_dir=output_dir)

    assert {path.name for path in output_dir.iterdir()} == {
        "20250103_particulate.csv",
        "20250103_gas.csv",
    }
    _assert_csv_matches_golden(
        output_dir / "20250103_particulate.csv",
        "minimal_wide_expected_particulate.csv",
    )
    _assert_csv_matches_golden(
        output_dir / "20250103_gas.csv", "minimal_wide_expected_gas.csv"
    )


@pytest.mark.golden
def test_process_air_quality_data_treats_mangled_duplicate_headers_as_stations(
    tmp_path: Path,
) -> None:
    """Lock pandas' duplicate-header suffixes as observable station identifiers."""
    output_dir = tmp_path / "processed"
    input_path = _copy_input(tmp_path, "duplicate_station_columns.csv")

    assert process_air_quality_data(input_path, output_dir=output_dir)

    _assert_csv_matches_golden(
        output_dir / "20250104_particulate.csv",
        "duplicate_station_columns_expected_particulate.csv",
    )
    _assert_csv_matches_golden(
        output_dir / "20250104_gas.csv",
        "duplicate_station_columns_expected_gas.csv",
    )


@pytest.mark.golden
@pytest.mark.parametrize(
    "fixture_name",
    [
        "missing_date_column.csv",
        "missing_hour_column.csv",
        "missing_type_column.csv",
    ],
)
def test_process_air_quality_data_rejects_missing_required_column_without_artifacts(
    tmp_path: Path, fixture_name: str
) -> None:
    """Lock every required-column failure boundary without producing CSV artifacts."""
    output_dir = tmp_path / "processed"
    input_path = _copy_input(tmp_path, fixture_name)

    assert not process_air_quality_data(input_path, output_dir=output_dir)
    assert output_dir.is_dir()
    assert list(output_dir.iterdir()) == []
