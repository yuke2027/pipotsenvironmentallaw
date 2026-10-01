"""Read models for standards, analysis, identity, alerts, and jobs."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.errors import (
    DuplicateNameError,
    DuplicateUsernameError,
    UserNotFoundError,
    VersionConflictError,
)

from app.db.models import (
    Alert,
    AlertChannelConfig,
    AlertDeliveryAttempt,
    AuditLog,
    ComplianceResult,
    ForecastResult,
    ForecastRun,
    JobRun,
    LegalStandard,
    ModelActivation,
    ModelRegistry,
    RevokedToken,
    RiskAssessment,
    RiskThreshold,
    User,
)
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
    Page,
    RevokedTokenDraft,
    RiskAssessmentDraft,
    RiskThresholdRecord,
    StandardsSnapshot,
    UserDraft,
    UserRecord,
)
from app.repositories.sqlalchemy.pagination import paginate


class SqlAlchemyStandardsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def snapshot(self, at: datetime) -> StandardsSnapshot:
        standards = self._session.scalars(
            select(LegalStandard)
            .where(
                LegalStandard.is_active.is_(True),
                LegalStandard.effective_from <= at,
                or_(LegalStandard.effective_to.is_(None), LegalStandard.effective_to > at),
            )
            .order_by(LegalStandard.id)
        ).all()
        thresholds = self._session.scalars(
            select(RiskThreshold)
            .where(
                RiskThreshold.is_active.is_(True),
                RiskThreshold.effective_from <= at,
            )
            .order_by(RiskThreshold.id)
        ).all()
        return StandardsSnapshot(
            captured_at=at,
            standards=tuple(_standard_record(row) for row in standards),
            risk_thresholds=tuple(_threshold_record(row) for row in thresholds),
        )

    def list_standards(
        self, page: int, page_size: int, *, pollutant: str | None = None
    ) -> Page[LegalStandardRecord]:
        statement = select(LegalStandard).order_by(LegalStandard.id)
        if pollutant is not None:
            statement = statement.where(LegalStandard.pollutant == pollutant)
        rows, total = paginate(self._session, statement, page, page_size)
        return Page(
            items=tuple(_standard_record(row) for row in rows),
            page=page,
            page_size=page_size,
            total=total,
        )

    def get(self, standard_id: int) -> LegalStandardRecord | None:
        row = self._session.get(LegalStandard, standard_id)
        return None if row is None else _standard_record(row)

    def insert_standard(self, draft: StandardDraft) -> int:
        row = LegalStandard(
            standard_key=draft.standard_key,
            version=draft.version,
            pollutant=draft.pollutant,
            statistic_basis=draft.statistic_basis,
            limit_value=draft.limit_value,
            unit=draft.unit,
            legal_basis_name=draft.legal_basis_name,
            legal_article=draft.legal_article,
            penalty_basis=draft.penalty_basis,
            effective_from=draft.effective_from,
            effective_to=draft.effective_to,
            is_active=draft.is_active,
            supersedes_id=draft.supersedes_id,
            created_by=draft.created_by,
            created_at=draft.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def close_standard(self, standard_id: int, *, effective_to: datetime, expected_version: str) -> None:
        row = self._session.get(LegalStandard, standard_id)
        if row is None:
            raise LookupError("standard does not exist")
        if row.version != expected_version:
            raise VersionConflictError()
        row.is_active = False
        row.effective_to = effective_to
        self._session.flush()


class SqlAlchemyAnalysisRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_compliance(self, draft: ComplianceDraft) -> int:
        row = ComplianceResult(
            station_id=draft.station_id,
            local_date=draft.local_date,
            pollutant=draft.pollutant,
            daily_mean=draft.daily_mean,
            max_value=draft.max_value,
            min_value=draft.min_value,
            valid_points=draft.valid_points,
            standard_id=draft.standard_id,
            standard_limit_snapshot=draft.standard_limit_snapshot,
            exceed_ratio=draft.exceed_ratio,
            status=draft.status,
            risk_level=draft.risk_level,
            calculated_at=draft.calculated_at,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def add_risk(self, draft: RiskAssessmentDraft) -> int:
        row = RiskAssessment(
            compliance_result_id=draft.compliance_result_id,
            risk_score=draft.risk_score,
            risk_level=draft.risk_level,
            legal_consequences=draft.legal_consequences,
            recommended_actions=list(draft.recommended_actions),
            penalty_estimate_text=draft.penalty_estimate_text,
            disclaimer=draft.disclaimer,
            assessed_at=draft.assessed_at,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def add_forecast_run(self, draft: ForecastRunDraft) -> int:
        row = ForecastRun(
            station_id=draft.station_id,
            generated_at=draft.generated_at,
            method=draft.method,
            method_version=draft.method_version,
            horizon_hours=draft.horizon_hours,
            history_start=draft.history_start,
            history_end=draft.history_end,
            status=draft.status,
            skip_reason=draft.skip_reason,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def add_forecast_result(self, draft: ForecastResultDraft) -> int:
        row = ForecastResult(
            run_id=draft.run_id,
            forecast_at=draft.forecast_at,
            pollutant=draft.pollutant,
            predicted_value=draft.predicted_value,
            exceedance_probability=draft.exceedance_probability,
            standard_id=draft.standard_id,
            is_warning=draft.is_warning,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def list_compliance(self, page: int, page_size: int) -> Page[ComplianceRecord]:
        rows, total = paginate(
            self._session,
            select(ComplianceResult).order_by(ComplianceResult.id),
            page,
            page_size,
        )
        return Page(
            items=tuple(
                ComplianceRecord(
                    id=row.id,
                    station_id=row.station_id,
                    local_date=row.local_date,
                    pollutant=row.pollutant,
                    status=row.status,
                    standard_id=row.standard_id,
                    standard_limit_snapshot=row.standard_limit_snapshot,
                    risk_level=row.risk_level,
                )
                for row in rows
            ),
            page=page,
            page_size=page_size,
            total=total,
        )


class SqlAlchemyModelRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def register(self, draft: ModelDraft) -> int:
        row = ModelRegistry(
            model_type=draft.model_type,
            version=draft.version,
            artifact_path=draft.artifact_path,
            artifact_sha256=draft.artifact_sha256,
            scaler_path=draft.scaler_path,
            feature_order=list(draft.feature_order),
            n_steps=draft.n_steps,
            n_features=draft.n_features,
            trained_at=draft.trained_at,
            metrics=dict(draft.metrics),
            status=draft.status,
            created_by=draft.created_by,
            created_at=draft.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def activate(
        self,
        model_type: str,
        model_id: int,
        *,
        activated_by: int,
        activated_at: datetime,
    ) -> None:
        model = self._session.get(ModelRegistry, model_id)
        if model is None or model.model_type != model_type:
            raise LookupError("model version does not belong to the requested type")
        current = self._session.get(ModelActivation, model_type)
        if current is None:
            self._session.add(
                ModelActivation(
                    model_type=model_type,
                    model_id=model_id,
                    activated_at=activated_at,
                    activated_by=activated_by,
                )
            )
        else:
            current.model_id = model_id
            current.activated_at = activated_at
            current.activated_by = activated_by
        self._session.flush()

    def current_activation(self, model_type: str) -> ModelActivationRecord | None:
        row = self._session.get(ModelActivation, model_type)
        if row is None:
            return None
        return ModelActivationRecord(
            model_type=row.model_type,
            model_id=row.model_id,
            activated_at=row.activated_at,
            activated_by=row.activated_by,
        )


class SqlAlchemyAlertRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_channel(self, draft: AlertChannelDraft) -> int:
        row = AlertChannelConfig(
            name=draft.name,
            channel_type=draft.channel_type,
            enabled=draft.enabled,
            non_secret_config=dict(draft.non_secret_config),
            credential_ref=draft.credential_ref,
            recipients=list(draft.recipients),
            threshold_level=draft.threshold_level,
            created_by=draft.created_by,
            updated_at=draft.updated_at,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as error:
            raise DuplicateNameError() from error
        return row.id

    def list_channels(self) -> tuple[AlertChannelRecord, ...]:
        rows = self._session.scalars(select(AlertChannelConfig).order_by(AlertChannelConfig.id)).all()
        return tuple(_channel_record(row) for row in rows)

    def get_channel(self, channel_id: int) -> AlertChannelRecord | None:
        row = self._session.get(AlertChannelConfig, channel_id)
        return None if row is None else _channel_record(row)

    def update_channel(self, channel_id: int, draft: AlertChannelDraft) -> None:
        row = self._session.get(AlertChannelConfig, channel_id)
        if row is None:
            raise LookupError("alert channel does not exist")
        row.name = draft.name
        row.channel_type = draft.channel_type
        row.enabled = draft.enabled
        row.non_secret_config = dict(draft.non_secret_config)
        row.credential_ref = draft.credential_ref
        row.recipients = list(draft.recipients)
        row.threshold_level = draft.threshold_level
        row.updated_at = draft.updated_at
        try:
            with self._session.begin_nested():
                self._session.flush()
        except IntegrityError as error:
            raise DuplicateNameError() from error

    def add_alert(self, draft: AlertDraft) -> int:
        row = Alert(
            compliance_result_id=draft.compliance_result_id,
            channel_id=draft.channel_id,
            station_id=draft.station_id,
            pollutant=draft.pollutant,
            alert_date=draft.alert_date,
            trigger_snapshot=dict(draft.trigger_snapshot),
            status=draft.status,
            attempt_count=0,
            failure_reason=None,
            dedupe_reason=None,
            generated_at=draft.generated_at,
            pushed_at=None,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def find_alert(
        self, station_id: int, pollutant: str, alert_date: date, channel_id: int
    ) -> AlertRecord | None:
        row = self._session.scalar(
            select(Alert).where(
                Alert.station_id == station_id,
                Alert.pollutant == pollutant,
                Alert.alert_date == alert_date,
                Alert.channel_id == channel_id,
            )
        )
        return None if row is None else _alert_record(row)

    def update_alert(
        self,
        alert_id: int,
        *,
        status: str,
        attempt_count: int,
        failure_reason: str | None,
        dedupe_reason: str | None,
        pushed_at: datetime | None,
    ) -> None:
        row = self._session.get(Alert, alert_id)
        if row is None:
            raise LookupError("alert does not exist")
        row.status = status
        row.attempt_count = attempt_count
        row.failure_reason = failure_reason
        row.dedupe_reason = dedupe_reason
        row.pushed_at = pushed_at
        self._session.flush()

    def add_delivery_attempt(self, draft: DeliveryAttemptDraft) -> int:
        row = AlertDeliveryAttempt(
            alert_id=draft.alert_id,
            attempt_no=draft.attempt_no,
            started_at=draft.started_at,
            finished_at=draft.finished_at,
            outcome=draft.outcome,
            sanitized_error=draft.sanitized_error,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def list_alerts(self, page: int, page_size: int) -> Page[AlertRecord]:
        rows, total = paginate(self._session, select(Alert).order_by(Alert.id), page, page_size)
        return Page(
            items=tuple(
                _alert_record(row)
                for row in rows
            ),
            page=page,
            page_size=page_size,
            total=total,
        )


class SqlAlchemyAuthRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_user(self, draft: UserDraft) -> int:
        now = draft.created_at
        row = User(
            username=draft.username,
            password_hash=draft.password_hash,
            role=draft.role,
            is_active=draft.is_active,
            must_change_password=draft.must_change_password,
            failed_login_count=0,
            last_failed_at=None,
            locked_until=None,
            password_changed_at=None,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as error:
            raise DuplicateUsernameError() from error
        return row.id

    def get_by_username(self, username: str) -> UserRecord | None:
        row = self._session.scalar(select(User).where(User.username == username))
        return None if row is None else _user_record(row)

    def get_by_id(self, user_id: int) -> UserRecord | None:
        row = self._session.get(User, user_id)
        return None if row is None else _user_record(row)

    def list_users(self, page: int, page_size: int) -> Page[UserRecord]:
        rows, total = paginate(self._session, select(User).order_by(User.id), page, page_size)
        return Page(
            items=tuple(_user_record(row) for row in rows),
            page=page,
            page_size=page_size,
            total=total,
        )

    def save_login_failure(
        self,
        user_id: int,
        *,
        failed_login_count: int,
        last_failed_at: datetime,
        locked_until: datetime | None,
        updated_at: datetime,
    ) -> None:
        row = self._require_user(user_id)
        row.failed_login_count = failed_login_count
        row.last_failed_at = last_failed_at
        row.locked_until = locked_until
        row.updated_at = updated_at
        self._session.flush()

    def clear_login_failures(self, user_id: int, *, updated_at: datetime) -> None:
        row = self._require_user(user_id)
        row.failed_login_count = 0
        row.last_failed_at = None
        row.locked_until = None
        row.updated_at = updated_at
        self._session.flush()

    def change_password(
        self,
        user_id: int,
        *,
        password_hash: str,
        must_change_password: bool,
        password_changed_at: datetime,
        updated_at: datetime,
    ) -> None:
        row = self._require_user(user_id)
        row.password_hash = password_hash
        row.must_change_password = must_change_password
        row.password_changed_at = password_changed_at
        row.updated_at = updated_at
        self._session.flush()

    def update_account(
        self,
        user_id: int,
        *,
        role: str | None,
        is_active: bool | None,
        updated_at: datetime,
    ) -> None:
        row = self._require_user(user_id)
        if role is not None:
            row.role = role
        if is_active is not None:
            row.is_active = is_active
        row.updated_at = updated_at
        self._session.flush()

    def _require_user(self, user_id: int) -> User:
        row = self._session.get(User, user_id)
        if row is None:
            raise UserNotFoundError()
        return row

    def revoke_token(self, draft: RevokedTokenDraft) -> int:
        row = RevokedToken(
            jti=draft.jti,
            user_id=draft.user_id,
            expires_at=draft.expires_at,
            revoked_at=draft.revoked_at,
            reason=draft.reason,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def is_token_revoked(self, jti: str) -> bool:
        found = self._session.scalar(select(RevokedToken.id).where(RevokedToken.jti == jti))
        return found is not None


class SqlAlchemyAuditRepository:
    """Append-only audit log. There is no update or delete method."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, draft: AuditDraft) -> int:
        row = AuditLog(
            user_id=draft.user_id,
            action=draft.action,
            object_type=draft.object_type,
            object_id=draft.object_id,
            request_id=draft.request_id,
            result=draft.result,
            details=None if draft.details is None else dict(draft.details),
            ip_hash=draft.ip_hash,
            created_at=draft.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def list_entries(self, page: int, page_size: int) -> Page[AuditRecord]:
        rows, total = paginate(
            self._session,
            select(AuditLog).order_by(AuditLog.id),
            page,
            page_size,
        )
        return Page(
            items=tuple(_audit_record(row) for row in rows),
            page=page,
            page_size=page_size,
            total=total,
        )

    def list_by_user_action(self, user_id: int, action: str) -> tuple[AuditRecord, ...]:
        rows = self._session.scalars(
            select(AuditLog)
            .where(AuditLog.user_id == user_id, AuditLog.action == action)
            .order_by(AuditLog.id)
        ).all()
        return tuple(_audit_record(row) for row in rows)


class SqlAlchemyJobRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def start(self, draft: JobRunDraft) -> int:
        row = JobRun(
            pipeline_run_id=draft.pipeline_run_id,
            job_name=draft.job_name,
            target_scope=draft.target_scope,
            started_at=draft.started_at,
            finished_at=None,
            status="RUNNING",
            request_count=0,
            inserted_count=0,
            skipped_count=0,
            failure_count=0,
            sanitized_error=None,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def finish(self, job_id: int, outcome: JobFinish) -> None:
        row = self._session.get(JobRun, job_id)
        if row is None:
            raise LookupError("job run does not exist")
        row.finished_at = outcome.finished_at
        row.status = outcome.status
        row.request_count = outcome.request_count
        row.inserted_count = outcome.inserted_count
        row.skipped_count = outcome.skipped_count
        row.failure_count = outcome.failure_count
        row.sanitized_error = outcome.sanitized_error
        self._session.flush()


def _standard_record(row: LegalStandard) -> LegalStandardRecord:
    return LegalStandardRecord(
        id=row.id,
        standard_key=row.standard_key,
        version=row.version,
        pollutant=row.pollutant,
        statistic_basis=row.statistic_basis,
        limit_value=row.limit_value,
        unit=row.unit,
        legal_basis_name=row.legal_basis_name,
        legal_article=row.legal_article,
        penalty_basis=row.penalty_basis,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        is_active=row.is_active,
    )


def _user_record(row: User) -> UserRecord:
    return UserRecord(
        id=row.id,
        username=row.username,
        password_hash=row.password_hash,
        role=row.role,
        is_active=row.is_active,
        must_change_password=row.must_change_password,
        failed_login_count=row.failed_login_count,
        locked_until=row.locked_until,
        last_failed_at=row.last_failed_at,
        password_changed_at=row.password_changed_at,
    )


def _audit_record(row: AuditLog) -> AuditRecord:
    raw_details = row.details
    details = None if raw_details is None else {str(key): str(value) for key, value in raw_details.items()}
    return AuditRecord(
        id=row.id,
        user_id=row.user_id,
        action=row.action,
        object_type=row.object_type,
        object_id=row.object_id,
        result=row.result,
        created_at=row.created_at,
        details=details,
    )


def _channel_record(row: AlertChannelConfig) -> AlertChannelRecord:
    raw = row.non_secret_config or {}
    config = {str(key): str(value) for key, value in raw.items()}
    recipients = tuple(str(item) for item in row.recipients)
    return AlertChannelRecord(
        id=row.id,
        name=row.name,
        channel_type=row.channel_type,
        enabled=row.enabled,
        non_secret_config=config,
        credential_ref=row.credential_ref,
        recipients=recipients,
        threshold_level=row.threshold_level,
    )


def _alert_record(row: Alert) -> AlertRecord:
    return AlertRecord(
        id=row.id,
        station_id=row.station_id,
        pollutant=row.pollutant,
        alert_date=row.alert_date,
        channel_id=row.channel_id,
        status=row.status,
        dedupe_reason=row.dedupe_reason,
        attempt_count=row.attempt_count,
        failure_reason=row.failure_reason,
        pushed_at=row.pushed_at,
    )


def _threshold_record(row: RiskThreshold) -> RiskThresholdRecord:
    return RiskThresholdRecord(
        id=row.id,
        version=row.version,
        level=row.level,
        upper_bound=row.upper_bound,
        description_zh=row.description_zh,
        is_active=row.is_active,
        effective_from=row.effective_from,
    )
