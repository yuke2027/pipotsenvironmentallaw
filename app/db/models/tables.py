"""SQLAlchemy models for design section 5.

Constraints use generic column types, ForeignKey, UniqueConstraint, Index, and
CheckConstraint. Connection settings stay in the session callback.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql.elements import conv
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UtcDateTime
from app.domain.enums import (
    ALERT_CHANNEL_TYPES,
    ALERT_STATUSES,
    COMPLIANCE_STATUSES,
    CRITICAL_RISK_LEVEL,
    DELIVERY_OUTCOMES,
    FORECAST_STATUSES,
    JOB_STATUSES,
    MODEL_STATUSES,
    MONITORING_SOURCES,
    RISK_LEVELS,
    USER_ROLES,
)


def _sql_in(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join("'" + value.replace("'", "''") + "'" for value in values)
    return f"{column} IN ({rendered})"


def _check(sqltext: str, *, name: str) -> CheckConstraint:
    """Keep an explicit constraint name instead of running it through naming tokens."""

    return CheckConstraint(sqltext, name=conv(name))


class City(Base):
    __tablename__ = "cities"
    __table_args__ = (
        UniqueConstraint("code", name="uq_cities_code"),
        UniqueConstraint("name_zh", name="uq_cities_name_zh"),
        Index("ix_cities_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name_zh: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    stations: Mapped[list[Station]] = relationship(back_populates="city")


class Station(Base):
    __tablename__ = "stations"
    __table_args__ = (
        UniqueConstraint("city_id", "code", name="uq_stations_city_code"),
        Index("ix_stations_city_enabled", "city_id", "enabled"),
        _check(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_stations_latitude",
        ),
        _check(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_stations_longitude",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id", ondelete="RESTRICT"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name_zh: Mapped[str] = mapped_column(String(64), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    provider_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    city: Mapped[City] = relationship(back_populates="stations")
    monitoring_records: Mapped[list[MonitoringRecord]] = relationship(back_populates="station")
    compliance_results: Mapped[list[ComplianceResult]] = relationship(back_populates="station")
    forecast_runs: Mapped[list[ForecastRun]] = relationship(back_populates="station")
    alerts: Mapped[list[Alert]] = relationship(back_populates="station")


class MonitoringRecord(Base):
    __tablename__ = "monitoring_records"
    __table_args__ = (
        UniqueConstraint("station_id", "observed_at", name="uq_monitoring_station_observed"),
        Index("ix_monitoring_station_observed", "station_id", "observed_at"),
        Index("ix_monitoring_observed_at", "observed_at"),
        Index("ix_monitoring_source", "source"),
        _check("pm25 IS NULL OR pm25 >= 0", name="ck_monitoring_pm25_nonnegative"),
        _check("pm10 IS NULL OR pm10 >= 0", name="ck_monitoring_pm10_nonnegative"),
        _check("aqi IS NULL OR aqi >= 0", name="ck_monitoring_aqi_nonnegative"),
        _check(_sql_in("source", MONITORING_SOURCES), name="ck_monitoring_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    pm25: Mapped[float | None] = mapped_column(Float, nullable=True)
    pm10: Mapped[float | None] = mapped_column(Float, nullable=True)
    aqi: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    is_imputed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    original_missing_mask: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    provider_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    station: Mapped[Station] = relationship(back_populates="monitoring_records")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        Index("ix_users_role_active", "role", "is_active"),
        Index("ix_users_locked_until", "locked_until"),
        _check(_sql_in("role", USER_ROLES), name="ck_users_role"),
        _check("failed_login_count >= 0", name="ck_users_failed_login_count"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    legal_standards: Mapped[list[LegalStandard]] = relationship(back_populates="creator")
    risk_thresholds: Mapped[list[RiskThreshold]] = relationship(back_populates="creator")
    registered_models: Mapped[list[ModelRegistry]] = relationship(back_populates="creator")
    model_activations: Mapped[list[ModelActivation]] = relationship(back_populates="activator")
    alert_channels: Mapped[list[AlertChannelConfig]] = relationship(back_populates="creator")
    revoked_tokens: Mapped[list[RevokedToken]] = relationship(back_populates="user")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="user")


class LegalStandard(Base):
    __tablename__ = "legal_standards"
    __table_args__ = (
        UniqueConstraint("standard_key", "version", name="uq_legal_standards_key_version"),
        Index(
            "ix_legal_standards_lookup",
            "pollutant",
            "statistic_basis",
            "is_active",
            "effective_from",
        ),
        _check("limit_value > 0", name="ck_legal_standards_limit_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    standard_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    pollutant: Mapped[str] = mapped_column(String(32), nullable=False)
    statistic_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    limit_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    legal_basis_name: Mapped[str] = mapped_column(String(128), nullable=False)
    legal_article: Mapped[str] = mapped_column(Text, nullable=False)
    penalty_basis: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("legal_standards.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    supersedes: Mapped[LegalStandard | None] = relationship(
        remote_side="LegalStandard.id",
        foreign_keys=[supersedes_id],
    )
    creator: Mapped[User] = relationship(back_populates="legal_standards")
    compliance_results: Mapped[list[ComplianceResult]] = relationship(back_populates="standard")
    forecast_results: Mapped[list[ForecastResult]] = relationship(back_populates="standard")


class RiskThreshold(Base):
    __tablename__ = "risk_thresholds"
    __table_args__ = (
        UniqueConstraint("version", "level", name="uq_risk_thresholds_version_level"),
        Index("ix_risk_thresholds_active_from", "is_active", "effective_from"),
        _check(_sql_in("level", RISK_LEVELS), name="ck_risk_thresholds_level"),
        _check(
            f"(level = '{CRITICAL_RISK_LEVEL}' AND upper_bound IS NULL) OR "
            f"(level <> '{CRITICAL_RISK_LEVEL}' AND upper_bound IS NOT NULL AND upper_bound > 0)",
            name="ck_risk_thresholds_upper_bound",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    upper_bound: Mapped[float | None] = mapped_column(Float, nullable=True)
    description_zh: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    creator: Mapped[User] = relationship(back_populates="risk_thresholds")


class ComplianceResult(Base):
    __tablename__ = "compliance_results"
    __table_args__ = (
        UniqueConstraint(
            "station_id",
            "local_date",
            "pollutant",
            "standard_id",
            name="uq_compliance_station_date_pollutant_standard",
        ),
        Index("ix_compliance_date_pollutant_status", "local_date", "pollutant", "status"),
        Index("ix_compliance_station_date", "station_id", "local_date"),
        _check(_sql_in("status", COMPLIANCE_STATUSES), name="ck_compliance_status"),
        _check(
            "risk_level IS NULL OR " + _sql_in("risk_level", RISK_LEVELS),
            name="ck_compliance_risk_level",
        ),
        _check("valid_points >= 0", name="ck_compliance_valid_points"),
        _check(
            "standard_limit_snapshot IS NULL OR standard_limit_snapshot > 0",
            name="ck_compliance_limit_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    pollutant: Mapped[str] = mapped_column(String(32), nullable=False)
    daily_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_points: Mapped[int] = mapped_column(Integer, nullable=False)
    standard_id: Mapped[int] = mapped_column(
        ForeignKey("legal_standards.id", ondelete="RESTRICT"),
        nullable=False,
    )
    standard_limit_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    exceed_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    station: Mapped[Station] = relationship(back_populates="compliance_results")
    standard: Mapped[LegalStandard] = relationship(back_populates="compliance_results")
    risk_assessment: Mapped[RiskAssessment | None] = relationship(back_populates="compliance_result")
    alerts: Mapped[list[Alert]] = relationship(back_populates="compliance_result")


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        UniqueConstraint("compliance_result_id", name="uq_risk_assessments_compliance"),
        Index("ix_risk_assessments_level_score", "risk_level", "risk_score"),
        _check(_sql_in("risk_level", RISK_LEVELS), name="ck_risk_assessments_level"),
        _check("risk_score >= 0", name="ck_risk_assessments_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    compliance_result_id: Mapped[int] = mapped_column(
        ForeignKey("compliance_results.id", ondelete="RESTRICT"),
        nullable=False,
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    legal_consequences: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_actions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    penalty_estimate_text: Mapped[str] = mapped_column(Text, nullable=False)
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    compliance_result: Mapped[ComplianceResult] = relationship(back_populates="risk_assessment")


class ForecastRun(Base):
    __tablename__ = "forecast_runs"
    __table_args__ = (
        Index("ix_forecast_runs_station_generated", "station_id", "generated_at"),
        _check(_sql_in("status", FORECAST_STATUSES), name="ck_forecast_runs_status"),
        _check("horizon_hours >= 1", name="ck_forecast_runs_horizon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    method_version: Mapped[str] = mapped_column(String(32), nullable=False)
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    history_start: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    history_end: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    station: Mapped[Station] = relationship(back_populates="forecast_runs")
    results: Mapped[list[ForecastResult]] = relationship(back_populates="run")


class ForecastResult(Base):
    __tablename__ = "forecast_results"
    __table_args__ = (
        UniqueConstraint("run_id", "forecast_at", "pollutant", name="uq_forecast_results_run_time_pollutant"),
        Index("ix_forecast_results_warning", "forecast_at", "is_warning"),
        _check("predicted_value >= 0", name="ck_forecast_results_predicted_nonnegative"),
        _check(
            "exceedance_probability >= 0 AND exceedance_probability <= 1",
            name="ck_forecast_results_probability",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id", ondelete="RESTRICT"), nullable=False)
    forecast_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    pollutant: Mapped[str] = mapped_column(String(32), nullable=False)
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    exceedance_probability: Mapped[float] = mapped_column(Float, nullable=False)
    standard_id: Mapped[int] = mapped_column(
        ForeignKey("legal_standards.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_warning: Mapped[bool] = mapped_column(Boolean, nullable=False)

    run: Mapped[ForecastRun] = relationship(back_populates="results")
    standard: Mapped[LegalStandard] = relationship(back_populates="forecast_results")


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    __table_args__ = (
        UniqueConstraint("model_type", "version", name="uq_model_registry_type_version"),
        UniqueConstraint("artifact_sha256", name="uq_model_registry_sha256"),
        Index("ix_model_registry_type_status_trained", "model_type", "status", "trained_at"),
        _check(_sql_in("status", MODEL_STATUSES), name="ck_model_registry_status"),
        _check("n_steps >= 1 AND n_features >= 1", name="ck_model_registry_shape"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scaler_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    feature_order: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    n_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    n_features: Mapped[int] = mapped_column(Integer, nullable=False)
    trained_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    creator: Mapped[User] = relationship(back_populates="registered_models")
    activation: Mapped[ModelActivation | None] = relationship(
        back_populates="model",
        foreign_keys="ModelActivation.model_id",
    )


class ModelActivation(Base):
    __tablename__ = "model_activations"

    model_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("model_registry.id", ondelete="RESTRICT"),
        nullable=False,
    )
    activated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    activated_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    model: Mapped[ModelRegistry] = relationship(
        back_populates="activation",
        foreign_keys=[model_id],
    )
    activator: Mapped[User] = relationship(back_populates="model_activations")


class AlertChannelConfig(Base):
    __tablename__ = "alert_channel_configs"
    __table_args__ = (
        UniqueConstraint("name", name="uq_alert_channels_name"),
        Index("ix_alert_channels_enabled_type", "enabled", "channel_type"),
        _check(_sql_in("channel_type", ALERT_CHANNEL_TYPES), name="ck_alert_channels_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    non_secret_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    credential_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipients: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    threshold_level: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    creator: Mapped[User] = relationship(back_populates="alert_channels")
    alerts: Mapped[list[Alert]] = relationship(back_populates="channel")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint(
            "station_id",
            "pollutant",
            "alert_date",
            "channel_id",
            name="uq_alerts_station_pollutant_date_channel",
        ),
        Index("ix_alerts_generated_status", "generated_at", "status"),
        Index("ix_alerts_station_date", "station_id", "alert_date"),
        _check(_sql_in("status", ALERT_STATUSES), name="ck_alerts_status"),
        _check("attempt_count >= 0", name="ck_alerts_attempt_count"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    compliance_result_id: Mapped[int] = mapped_column(
        ForeignKey("compliance_results.id", ondelete="RESTRICT"),
        nullable=False,
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("alert_channel_configs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False)
    pollutant: Mapped[str] = mapped_column(String(32), nullable=False)
    alert_date: Mapped[date] = mapped_column(Date, nullable=False)
    trigger_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    pushed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    compliance_result: Mapped[ComplianceResult] = relationship(back_populates="alerts")
    channel: Mapped[AlertChannelConfig] = relationship(back_populates="alerts")
    station: Mapped[Station] = relationship(back_populates="alerts")
    delivery_attempts: Mapped[list[AlertDeliveryAttempt]] = relationship(back_populates="alert")


class AlertDeliveryAttempt(Base):
    __tablename__ = "alert_delivery_attempts"
    __table_args__ = (
        UniqueConstraint("alert_id", "attempt_no", name="uq_alert_attempts_alert_no"),
        _check("attempt_no >= 1", name="ck_alert_attempts_attempt_no"),
        _check(_sql_in("outcome", DELIVERY_OUTCOMES), name="ck_alert_attempts_outcome"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="RESTRICT"), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    sanitized_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    alert: Mapped[Alert] = relationship(back_populates="delivery_attempts")


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    __table_args__ = (
        UniqueConstraint("jti", name="uq_revoked_tokens_jti"),
        Index("ix_revoked_tokens_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    jti: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped[User] = relationship(back_populates="revoked_tokens")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
        Index("ix_audit_logs_object", "object_type", "object_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)

    user: Mapped[User | None] = relationship(back_populates="audit_logs")


class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (
        Index("ix_job_runs_name_started", "job_name", "started_at"),
        Index("ix_job_runs_pipeline", "pipeline_run_id"),
        _check(_sql_in("status", JOB_STATUSES), name="ck_job_runs_status"),
        _check("request_count >= 0", name="ck_job_runs_request_count"),
        _check("inserted_count >= 0", name="ck_job_runs_inserted_count"),
        _check("skipped_count >= 0", name="ck_job_runs_skipped_count"),
        _check("failure_count >= 0", name="ck_job_runs_failure_count"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    target_scope: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sanitized_error: Mapped[str | None] = mapped_column(Text, nullable=True)
