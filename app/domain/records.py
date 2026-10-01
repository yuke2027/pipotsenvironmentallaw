"""Plain records exchanged with repository protocols."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Generic, Mapping, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class WriteCounts:
    inserted: int
    skipped: int
    invalid: int


@dataclass(frozen=True)
class MonitoringDraft:
    station_id: int
    observed_at: datetime
    pm25: float | None
    pm10: float | None
    aqi: float | None
    source: str
    is_imputed: bool = False
    original_missing_mask: Mapping[str, bool] | None = None
    provider_record_id: str | None = None


@dataclass(frozen=True)
class StationRef:
    id: int
    code: str
    name_zh: str
    city_name: str


@dataclass(frozen=True)
class MonitoringRecordView:
    id: int
    station_id: int
    observed_at: datetime
    pm25: float | None
    pm10: float | None
    aqi: float | None
    source: str
    is_imputed: bool
    original_missing_mask: dict[str, bool] | None
    provider_record_id: str | None


@dataclass(frozen=True)
class LegalStandardRecord:
    id: int
    standard_key: str
    version: str
    pollutant: str
    statistic_basis: str
    limit_value: float
    unit: str
    legal_basis_name: str
    legal_article: str
    penalty_basis: str
    effective_from: datetime
    effective_to: datetime | None
    is_active: bool


@dataclass(frozen=True)
class RiskThresholdRecord:
    id: int
    version: str
    level: str
    upper_bound: float | None
    description_zh: str
    is_active: bool
    effective_from: datetime


@dataclass(frozen=True)
class StandardDraft:
    standard_key: str
    version: str
    pollutant: str
    statistic_basis: str
    limit_value: float
    unit: str
    legal_basis_name: str
    legal_article: str
    penalty_basis: str
    effective_from: datetime
    effective_to: datetime | None
    is_active: bool
    supersedes_id: int | None
    created_by: int
    created_at: datetime


@dataclass(frozen=True)
class StandardsSnapshot:
    captured_at: datetime
    standards: tuple[LegalStandardRecord, ...]
    risk_thresholds: tuple[RiskThresholdRecord, ...]


@dataclass(frozen=True)
class ComplianceDraft:
    station_id: int
    local_date: date
    pollutant: str
    daily_mean: float | None
    max_value: float | None
    min_value: float | None
    valid_points: int
    standard_id: int
    standard_limit_snapshot: float | None
    exceed_ratio: float | None
    status: str
    risk_level: str | None
    calculated_at: datetime


@dataclass(frozen=True)
class ComplianceRecord:
    id: int
    station_id: int
    local_date: date
    pollutant: str
    status: str
    standard_id: int
    standard_limit_snapshot: float | None
    risk_level: str | None


@dataclass(frozen=True)
class RiskAssessmentDraft:
    compliance_result_id: int
    risk_score: float
    risk_level: str
    legal_consequences: str
    recommended_actions: tuple[str, ...]
    penalty_estimate_text: str
    disclaimer: str
    assessed_at: datetime


@dataclass(frozen=True)
class ForecastRunDraft:
    station_id: int
    generated_at: datetime
    method: str
    method_version: str
    horizon_hours: int
    history_start: datetime
    history_end: datetime
    status: str
    skip_reason: str | None


@dataclass(frozen=True)
class ForecastResultDraft:
    run_id: int
    forecast_at: datetime
    pollutant: str
    predicted_value: float
    exceedance_probability: float
    standard_id: int
    is_warning: bool


@dataclass(frozen=True)
class ModelDraft:
    model_type: str
    version: str
    artifact_path: str
    artifact_sha256: str
    scaler_path: str | None
    feature_order: tuple[str, ...]
    n_steps: int
    n_features: int
    trained_at: datetime
    metrics: Mapping[str, float]
    status: str
    created_by: int
    created_at: datetime


@dataclass(frozen=True)
class ModelActivationRecord:
    model_type: str
    model_id: int
    activated_at: datetime
    activated_by: int


@dataclass(frozen=True)
class AlertChannelDraft:
    name: str
    channel_type: str
    enabled: bool
    non_secret_config: Mapping[str, str]
    credential_ref: str | None
    recipients: tuple[str, ...]
    threshold_level: str
    created_by: int
    updated_at: datetime


@dataclass(frozen=True)
class AlertDraft:
    compliance_result_id: int
    channel_id: int
    station_id: int
    pollutant: str
    alert_date: date
    trigger_snapshot: Mapping[str, str]
    status: str
    generated_at: datetime


@dataclass(frozen=True)
class AlertChannelRecord:
    id: int
    name: str
    channel_type: str
    enabled: bool
    non_secret_config: dict[str, str]
    credential_ref: str | None
    recipients: tuple[str, ...]
    threshold_level: str


@dataclass(frozen=True)
class AlertRecord:
    id: int
    station_id: int
    pollutant: str
    alert_date: date
    channel_id: int
    status: str
    dedupe_reason: str | None = None
    attempt_count: int = 0
    failure_reason: str | None = None
    pushed_at: datetime | None = None


@dataclass(frozen=True)
class DeliveryAttemptDraft:
    alert_id: int
    attempt_no: int
    started_at: datetime
    finished_at: datetime | None
    outcome: str
    sanitized_error: str | None


@dataclass(frozen=True)
class UserDraft:
    """Identity row. ``password_hash`` must already be a one-way hash."""

    username: str
    password_hash: str
    role: str
    is_active: bool
    must_change_password: bool
    created_at: datetime


@dataclass(frozen=True)
class UserRecord:
    id: int
    username: str
    password_hash: str
    role: str
    is_active: bool
    must_change_password: bool
    failed_login_count: int
    locked_until: datetime | None
    last_failed_at: datetime | None = None
    password_changed_at: datetime | None = None


@dataclass(frozen=True)
class RevokedTokenDraft:
    jti: str
    user_id: int
    expires_at: datetime
    revoked_at: datetime
    reason: str


@dataclass(frozen=True)
class AuditDraft:
    user_id: int | None
    action: str
    object_type: str
    object_id: str | None
    request_id: str | None
    result: str
    details: Mapping[str, str] | None
    ip_hash: str | None
    created_at: datetime


@dataclass(frozen=True)
class AuditRecord:
    id: int
    user_id: int | None
    action: str
    object_type: str
    object_id: str | None
    result: str
    created_at: datetime
    details: Mapping[str, str] | None = None


@dataclass(frozen=True)
class JobRunDraft:
    pipeline_run_id: str
    job_name: str
    target_scope: str | None
    started_at: datetime


@dataclass(frozen=True)
class JobFinish:
    finished_at: datetime
    status: str
    request_count: int
    inserted_count: int
    skipped_count: int
    failure_count: int
    sanitized_error: str | None
