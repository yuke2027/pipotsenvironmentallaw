"""Single, validated runtime configuration source.

Configuration uses the following precedence for deployed settings: environment
variables, then a local ``.env`` file, then documented defaults.  The settings
object is deliberately not instantiated at import time so startup can validate
``JWT_SECRET`` before opening a listening socket.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_LOGGER = logging.getLogger(__name__)


class Settings(BaseSettings):
    """The sole source of configurable platform behaviour.

    Environment variable names use the upper-case field name (for example,
    ``COLLECTION_INTERVAL_SECONDS``).  ``JWT_SECRET`` also accepts the
    deployment-friendly ``ESP_JWT_SECRET`` alias.  A local ``.env`` file is
    read from the project root unless callers explicitly provide ``_env_file``
    (which is useful for isolated tests and deployment tooling).
    """

    model_config = SettingsConfigDict(
        env_file=DEFAULT_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    project_root: Path = DEFAULT_PROJECT_ROOT
    database_url: str | None = None
    database_path: Path = Path("var/environmental_supervision.db")

    target_cities: Annotated[tuple[str, ...], NoDecode] = ("北京",)
    collection_interval_seconds: int = Field(default=3600, ge=1)
    imputation_interval_seconds: int = Field(default=3600, ge=1)
    compliance_interval_seconds: int = Field(default=3600, ge=1)
    risk_interval_seconds: int = Field(default=3600, ge=1)
    forecast_interval_seconds: int = Field(default=3600, ge=1)
    alert_interval_seconds: int = Field(default=3600, ge=1)
    minimum_request_interval_seconds: float = Field(default=1.0, ge=0.0)
    cnemc_enabled: bool = False
    cnemc_endpoint: str | None = None
    cnemc_schema_version: int = Field(default=1, ge=1)
    cnemc_credential_ref: str | None = None
    provider_timeout_seconds: float = Field(default=10.0, gt=0)
    retry_base_delay_seconds: float = Field(default=1.0, ge=0)

    alert_threshold_level: str = "高"
    alert_email_credential_ref: str | None = None
    alert_webhook_credential_ref: str | None = None

    data_dir: Path = Path("data")
    model_dir: Path = Path("var/models")
    export_dir: Path = Path("var/exports")
    local_config_dir: Path = Path("var/config")

    forecast_horizon_hours: int = Field(default=24, ge=1)
    forecast_warning_probability: float = Field(default=0.7, ge=0.0, le=1.0)
    forecast_min_samples: int = Field(default=168, ge=1)

    jwt_secret: SecretStr = Field(
        validation_alias=AliasChoices("JWT_SECRET", "ESP_JWT_SECRET"),
        repr=False,
    )
    jwt_expire_seconds: int = Field(default=8 * 60 * 60, ge=1)
    login_max_failures: int = Field(default=5, ge=1)
    login_lock_seconds: int = Field(default=15 * 60, ge=1)

    max_query_span_days: int = Field(default=31, ge=1)
    min_compliance_points: int = Field(default=1, ge=1)
    timezone: str = "Asia/Shanghai"
    chinese_font_path: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("CHINESE_FONT_PATH"),
    )
    font_candidates: Annotated[tuple[str, ...], NoDecode] = (
        "Noto Sans CJK SC",
        "Microsoft YaHei",
        "SimHei",
        "WenQuanYi Zen Hei",
    )

    @field_validator("target_cities", "font_candidates", mode="before")
    @classmethod
    def parse_string_sequence(cls, value: Any) -> tuple[str, ...] | Any:
        """Accept JSON arrays or comma-separated values in environment files."""
        if not isinstance(value, str):
            return value

        candidate = value.strip()
        if candidate.startswith("["):
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError as error:
                raise ValueError("must be a JSON array or comma-separated list") from error
        else:
            value = candidate.split(",")

        if not isinstance(value, list):
            raise ValueError("must be a JSON array or comma-separated list")
        parsed = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
        if not parsed:
            raise ValueError("must contain at least one value")
        return parsed

    @field_validator("target_cities", "font_candidates")
    @classmethod
    def require_nonempty_sequence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("must contain at least one value")
        return value

    def model_post_init(self, __context: Any) -> None:
        """Emit one structured, non-secret event for every applied default."""
        for field_name in type(self).model_fields:
            if field_name not in self.model_fields_set:
                _CONFIG_LOGGER.info(
                    "CONFIG_DEFAULT_APPLIED",
                    extra={"event": "CONFIG_DEFAULT_APPLIED", "config_field": field_name},
                )


class SettingsStartupError(RuntimeError):
    """Configuration failure raised before the process opens a listening socket.

    The message names the offending fields and never includes submitted values,
    so a missing or invalid secret cannot be echoed into logs or the console.
    """

    def __init__(self, field_names: tuple[str, ...]) -> None:
        self.field_names = field_names
        rendered = ", ".join(field_names) if field_names else "unknown"
        super().__init__(
            "CONFIGURATION_ERROR: invalid or missing settings before listen: " + rendered
        )


def public_setting_name(field_name: str) -> str:
    """Return the operator-facing name for a settings field or its alias."""
    field = Settings.model_fields.get(field_name)
    if field is None:
        return field_name
    alias = field.validation_alias
    if isinstance(alias, AliasChoices):
        return str(next(iter(alias.choices)))
    if isinstance(alias, str):
        return alias
    return field_name.upper()


def load_settings(**overrides: Any) -> Settings:
    """Validate settings before anything is allowed to listen.

    ``ValidationError`` payloads include the raw input mapping.  This boundary
    drops that payload and reports only field names.
    """
    try:
        return Settings(**overrides)
    except ValidationError as error:
        names = tuple(
            dict.fromkeys(
                public_setting_name(str(item["loc"][0]))
                for item in error.errors()
                if item.get("loc")
            )
        )
        raise SettingsStartupError(names) from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance after startup validation."""
    return load_settings()


def reset_settings_cache() -> None:
    """Clear cached settings for controlled test or process reconfiguration."""
    get_settings.cache_clear()
