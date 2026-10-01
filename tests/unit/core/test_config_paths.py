"""Isolated tests for the task 2.1 configuration and paths infrastructure."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.paths import PathSettings


@pytest.mark.unit
def test_environment_variables_override_local_dotenv_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Environment configuration must take precedence over local settings."""
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "JWT_SECRET=local-secret\n"
        "COLLECTION_INTERVAL_SECONDS=120\n"
        "TARGET_CITIES=北京,天津\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JWT_SECRET", "environment-secret")
    monkeypatch.setenv("COLLECTION_INTERVAL_SECONDS", "300")

    settings = Settings(_env_file=dotenv)

    assert settings.jwt_secret.get_secret_value() == "environment-secret"
    assert settings.collection_interval_seconds == 300
    assert settings.target_cities == ("北京", "天津")


@pytest.mark.unit
def test_defaults_emit_named_structured_events(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every omitted optional field logs the required default-applied event."""
    with caplog.at_level(logging.INFO, logger="app.core.config"):
        settings = Settings(jwt_secret="test-only-secret", _env_file=None)

    applied = [
        record
        for record in caplog.records
        if record.message == "CONFIG_DEFAULT_APPLIED"
    ]
    applied_fields = {record.config_field for record in applied}

    assert settings.collection_interval_seconds == 3600
    assert "collection_interval_seconds" in applied_fields
    assert "jwt_secret" not in applied_fields
    assert all("test-only-secret" not in record.getMessage() for record in applied)


@pytest.mark.unit
def test_missing_jwt_secret_is_rejected_without_default() -> None:
    """JWT_SECRET is required before an application can proceed to listening."""
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None)


@pytest.mark.unit
def test_path_settings_resolve_and_create_only_configured_directories(
    tmp_path: Path,
) -> None:
    """Runtime locations are absolute and derive from one PathSettings object."""
    settings = Settings(
        jwt_secret="test-only-secret",
        project_root=tmp_path,
        data_dir="input-data",
        model_dir="runtime/models",
        export_dir="runtime/exports",
        local_config_dir="runtime/config",
        database_path="runtime/platform.db",
        _env_file=None,
    )

    paths = PathSettings.from_settings(settings)
    paths.ensure_directories()

    assert paths.data_dir == (tmp_path / "input-data").resolve()
    assert paths.database_path == (tmp_path / "runtime/platform.db").resolve()
    assert paths.database_url.endswith("/runtime/platform.db")
    assert paths.model_dir.is_dir()
    assert paths.export_path("daily", "report.csv") == (
        tmp_path / "runtime/exports/daily/report.csv"
    ).resolve()


@pytest.mark.unit
def test_path_settings_reject_relative_path_escapes(tmp_path: Path) -> None:
    """Relative configuration and child paths cannot bypass the configured root."""
    escaped_settings = Settings(
        jwt_secret="test-only-secret",
        project_root=tmp_path,
        export_dir="../outside",
        _env_file=None,
    )

    with pytest.raises(ValueError, match="escapes project_root"):
        PathSettings.from_settings(escaped_settings)

    paths = PathSettings.from_settings(
        Settings(jwt_secret="test-only-secret", project_root=tmp_path, _env_file=None)
    )
    with pytest.raises(ValueError, match="escapes configured directory"):
        paths.export_path("..", "outside.csv")
