"""Property 1: health fields match the real database and model state."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.lifecycle import ModelHealth, health_payload


@given(
    database_ok=st.booleans(),
    saits_version=st.one_of(st.none(), st.from_regex(r"saits-[0-9]{1,3}", fullmatch=True)),
    saits_loaded=st.booleans(),
    lstm_version=st.one_of(st.none(), st.from_regex(r"lstm-[0-9]{1,3}", fullmatch=True)),
    lstm_loaded=st.booleans(),
)
@pytest.mark.property
def test_property_01_health_matches_runtime_state(
    database_ok: bool,
    saits_version: str | None,
    saits_loaded: bool,
    lstm_version: str | None,
    lstm_loaded: bool,
) -> None:
    """Health reports a model version only when that version is loaded.

    **Feature: environmental-supervision-platform, Property 1: 健康状态映射**
    **Property 1：健康状态映射**
    **Validates: Requirements 1.5**
    """

    saits = None if saits_version is None else ModelHealth(saits_version, saits_loaded)
    lstm = None if lstm_version is None else ModelHealth(lstm_version, lstm_loaded)
    payload = health_payload(database_ok=database_ok, saits=saits, lstm=lstm)
    assert payload["database"] == ("ok" if database_ok else "unavailable")
    models = payload["models"]
    assert isinstance(models, dict)
    expected_saits = saits_version if saits_loaded and saits_version else None
    expected_lstm = lstm_version if lstm_loaded and lstm_version else None
    assert models["saits"] == expected_saits
    assert models["lstm"] == expected_lstm
    assert payload["imputation_available"] is (expected_saits is not None or expected_lstm is not None)
    reported = {value for value in (models["saits"], models["lstm"]) if isinstance(value, str)}
    if not saits_loaded or saits_version is None:
        assert saits_version not in reported or saits_version == expected_lstm
    if not lstm_loaded or lstm_version is None:
        assert lstm_version not in reported or lstm_version == expected_saits
