"""Property 2: configuration parsing is deterministic and does not leak secrets."""

from __future__ import annotations

import logging
import os
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic_core import PydanticUndefined

from app.core.config import Settings, SettingsStartupError, load_settings


def _classified_fields() -> tuple[tuple[str, ...], dict[str, Any]]:
    required: list[str] = []
    defaults: dict[str, Any] = {}
    for name, field in Settings.model_fields.items():
        if field.is_required() or field.default is PydanticUndefined:
            required.append(name)
        else:
            defaults[name] = field.default
    return tuple(required), defaults


REQUIRED_FIELDS, DEFAULTS = _classified_fields()
DEFAULT_NAMES = tuple(DEFAULTS)
ENV_NAMES = tuple(
    sorted({name.upper() for name in Settings.model_fields} | {"JWT_SECRET", "ESP_JWT_SECRET", "CHINESE_FONT_PATH"})
)


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _rendered_output(error: BaseException | None, records: list[logging.LogRecord]) -> str:
    parts = [str(error) if error is not None else ""]
    for record in records:
        parts.append(record.getMessage())
        config_field = getattr(record, "config_field", None)
        if isinstance(config_field, str):
            parts.append(config_field)
    return "\n".join(parts)


@given(
    omitted=st.frozensets(st.sampled_from(DEFAULT_NAMES), min_size=1),
    secret=st.from_regex(r"sek-[A-Za-z0-9]{16}", fullmatch=True),
    drop_required=st.booleans(),
)
@pytest.mark.property
def test_property_02_config_resolution_is_deterministic(
    omitted: frozenset[str],
    secret: str,
    drop_required: bool,
) -> None:
    """Omitting a default applies that default; omitting a required field fails closed.

    **Property 2：配置解析确定性**
    **Validates: Requirements 1.7, 1.8, 14.6**
    """
    saved_env = {name: os.environ.pop(name) for name in ENV_NAMES if name in os.environ}
    logger = logging.getLogger("app.core.config")
    previous_level = logger.level
    handler = _ListHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        kwargs: dict[str, Any] = {}
        if not drop_required:
            kwargs["jwt_secret"] = secret
        for name, default in DEFAULTS.items():
            if name in omitted:
                continue
            if name == "alert_webhook_credential_ref":
                kwargs[name] = secret
            else:
                kwargs[name] = default

        failure: SettingsStartupError | None = None
        settings: Settings | None = None
        try:
            settings = load_settings(_env_file=None, **kwargs)
        except SettingsStartupError as error:
            failure = error

        rendered = _rendered_output(failure, handler.records)
        assert secret not in rendered
        assert failure is None or failure.__cause__ is None

        if drop_required:
            assert failure is not None
            assert settings is None
            assert "JWT_SECRET" in failure.field_names
            assert secret not in failure.field_names
            return

        assert failure is None
        assert settings is not None
        applied = {
            record.config_field
            for record in handler.records
            if record.message == "CONFIG_DEFAULT_APPLIED"
        }
        for name in omitted:
            assert getattr(settings, name) == DEFAULTS[name]
            assert name in applied
        assert "jwt_secret" not in applied
        assert REQUIRED_FIELDS == ("jwt_secret",)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        os.environ.update(saved_env)
