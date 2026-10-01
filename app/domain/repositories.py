"""Repository protocols. Services depend on these, not on ORM classes."""

from __future__ import annotations

from datetime import date, datetime
from types import TracebackType
from typing import Protocol, Sequence

from app.domain.records import (
    AlertChannelDraft,
    AlertChannelRecord,
    AlertDraft,
    AlertRecord,
    AuditDraft,
    AuditRecord,
    ComplianceDraft,
    ComplianceRecord,
    DeliveryAttemptDraft,
    ForecastResultDraft,
    ForecastRunDraft,
    JobFinish,
    JobRunDraft,
    LegalStandardRecord,
    StandardDraft,
    ModelActivationRecord,
    ModelDraft,
    MonitoringDraft,
    MonitoringRecordView,
    Page,
    StationRef,
    RevokedTokenDraft,
    RiskAssessmentDraft,
    StandardsSnapshot,
    UserDraft,
    UserRecord,
    WriteCounts,
)


class MonitoringRepository(Protocol):
    def insert_batch(self, records: Sequence[MonitoringDraft]) -> WriteCounts: ...

    def get(self, station_id: int, observed_at: datetime) -> MonitoringRecordView | None: ...

    def latest_observed_at(self, station_ids: Sequence[int]) -> datetime | None: ...


class CatalogRepository(Protocol):
    def stations_for_city(self, city_name: str) -> tuple[StationRef, ...]: ...


class StandardsRepository(Protocol):
    def snapshot(self, at: datetime) -> StandardsSnapshot: ...

    def list_standards(
        self, page: int, page_size: int, *, pollutant: str | None = None
    ) -> Page[LegalStandardRecord]: ...

    def get(self, standard_id: int) -> LegalStandardRecord | None: ...

    def insert_standard(self, draft: StandardDraft) -> int: ...

    def close_standard(self, standard_id: int, *, effective_to: datetime, expected_version: str) -> None: ...


class AnalysisRepository(Protocol):
    def add_compliance(self, draft: ComplianceDraft) -> int: ...

    def add_risk(self, draft: RiskAssessmentDraft) -> int: ...

    def add_forecast_run(self, draft: ForecastRunDraft) -> int: ...

    def add_forecast_result(self, draft: ForecastResultDraft) -> int: ...

    def list_compliance(self, page: int, page_size: int) -> Page[ComplianceRecord]: ...


class ModelRepository(Protocol):
    def register(self, draft: ModelDraft) -> int: ...

    def activate(
        self,
        model_type: str,
        model_id: int,
        *,
        activated_by: int,
        activated_at: datetime,
    ) -> None: ...

    def current_activation(self, model_type: str) -> ModelActivationRecord | None: ...


class AlertRepository(Protocol):
    def add_channel(self, draft: AlertChannelDraft) -> int: ...

    def list_channels(self) -> tuple[AlertChannelRecord, ...]: ...

    def get_channel(self, channel_id: int) -> AlertChannelRecord | None: ...

    def update_channel(self, channel_id: int, draft: AlertChannelDraft) -> None: ...

    def add_alert(self, draft: AlertDraft) -> int: ...

    def find_alert(
        self, station_id: int, pollutant: str, alert_date: date, channel_id: int
    ) -> AlertRecord | None: ...

    def update_alert(
        self,
        alert_id: int,
        *,
        status: str,
        attempt_count: int,
        failure_reason: str | None,
        dedupe_reason: str | None,
        pushed_at: datetime | None,
    ) -> None: ...

    def add_delivery_attempt(self, draft: DeliveryAttemptDraft) -> int: ...

    def list_alerts(self, page: int, page_size: int) -> Page[AlertRecord]: ...


class AuthRepository(Protocol):
    def add_user(self, draft: UserDraft) -> int: ...

    def get_by_username(self, username: str) -> UserRecord | None: ...

    def get_by_id(self, user_id: int) -> UserRecord | None: ...

    def list_users(self, page: int, page_size: int) -> Page[UserRecord]: ...

    def save_login_failure(
        self,
        user_id: int,
        *,
        failed_login_count: int,
        last_failed_at: datetime,
        locked_until: datetime | None,
        updated_at: datetime,
    ) -> None: ...

    def clear_login_failures(self, user_id: int, *, updated_at: datetime) -> None: ...

    def change_password(
        self,
        user_id: int,
        *,
        password_hash: str,
        must_change_password: bool,
        password_changed_at: datetime,
        updated_at: datetime,
    ) -> None: ...

    def update_account(
        self,
        user_id: int,
        *,
        role: str | None,
        is_active: bool | None,
        updated_at: datetime,
    ) -> None: ...

    def revoke_token(self, draft: RevokedTokenDraft) -> int: ...

    def is_token_revoked(self, jti: str) -> bool: ...


class AuditRepository(Protocol):
    def append(self, draft: AuditDraft) -> int: ...

    def list_entries(self, page: int, page_size: int) -> Page[AuditRecord]: ...

    def list_by_user_action(self, user_id: int, action: str) -> tuple[AuditRecord, ...]: ...


class JobRunRepository(Protocol):
    def start(self, draft: JobRunDraft) -> int: ...

    def finish(self, job_id: int, outcome: JobFinish) -> None: ...


class UnitOfWork(Protocol):
    monitoring: MonitoringRepository
    catalog: CatalogRepository
    standards: StandardsRepository
    analysis: AnalysisRepository
    models: ModelRepository
    alerts: AlertRepository
    auth: AuthRepository
    audit: AuditRepository
    jobs: JobRunRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...
