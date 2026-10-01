"""Property 9: wide-table conversion keeps station, hour, and pollutant cells."""

from __future__ import annotations

import contextlib
import io

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.adapters.legacy.preprocessing import preprocess_wide_dataframe


@given(
    stations=st.lists(st.sampled_from(("S1", "S2")), min_size=1, max_size=2, unique=True),
    hours=st.lists(st.sampled_from((0, 1, 2)), min_size=1, max_size=3, unique=True),
    data=st.data(),
)
@pytest.mark.property
def test_property_09_wide_values_survive_the_legacy_adapter(
    stations: list[str],
    hours: list[int],
    data: st.DataObject,
) -> None:
    """Each station/hour key is unique and matches the originating wide-table cell.

    **Feature: environmental-supervision-platform, Property 9: 宽表转换保持键和值**
    **Property 9：宽表转换保持键和值**
    **Validates: Requirements 3.2, 3.3, 15.4, 16.3**
    """

    cells: dict[tuple[str, int, str], float] = {}
    rows: list[dict[str, object]] = []
    for hour in hours:
        for pollutant in ("PM2.5", "PM10", "AQI"):
            row: dict[str, object] = {"date": 20250101, "hour": hour, "type": pollutant}
            for station in stations:
                value = float(data.draw(st.integers(min_value=0, max_value=40)))
                cells[(station, hour, pollutant)] = value
                row[station] = value
            rows.append(row)
    frame = pd.DataFrame(rows)
    with contextlib.redirect_stdout(io.StringIO()):
        converted = preprocess_wide_dataframe(frame)
    long_frame = pd.concat(list(converted.particulate.values()), ignore_index=True)
    keys = list(zip(long_frame["station_id"], long_frame["timestamp"]))
    assert len(keys) == len(set(keys))
    assert len(long_frame) == len(stations) * len(hours)
    for station, hour, pollutant in cells:
        match = long_frame[
            (long_frame["station_id"] == station) & (long_frame["timestamp"] == hour)
        ]
        assert len(match) == 1
        assert float(match.iloc[0][pollutant]) == cells[(station, hour, pollutant)]
