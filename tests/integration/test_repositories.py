"""Repository round trips for standards, audit, models, jobs, and monitoring."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db.models import LegalStandard, ModelRegistry, Station, User
from app.db.seed import seed_reference_data
from app.db.session import create_engine_from_url, session_factory, sqlite_file_url
from app.db.upgrade import upgrade_database
from app.domain.records import (
    AlertChannelDraft,
    AlertDraft,
    AuditDraft,
    ComplianceDraft,
    DeliveryAttemptDraft,
    ForecastResultDraft,
    ForecastRunDraft,
    JobFinish,
    JobRunDraft,
    ModelDraft,
    MonitoringDraft,
    RevokedTokenDraft,
    RiskAssessmentDraft,
    UserDraft,
)
from app.repositories.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork

_WHEN = datetime(2025, 1, 1, tzinfo=timezone.utc)


@pytest.mark.integration
def test_repositories_snapshot_audit_models_and_monitoring(tmp_path: Path) -> None:
    url = sqlite_file_url(tmp_path / "repositories.db")
    upgrade_database(url, backup_directory=tmp_path / "backups")
    engine = create_engine_from_url(url)
    try:
        factory = session_factory(engine)
        with factory() as session:
            seed_reference_data(session, admin_password="TempAdmin#2026-initial")
            session.commit()
            station_id = session.scalar(select(func.min(Station.id)))
            assert station_id is not None

        with SqlAlchemyUnitOfWork(factory) as unit:
            snapshot = unit.standards.snapshot(_WHEN)
            limits = {
                (row.pollutant, row.statistic_basis): row.limit_value for row in snapshot.standards
            }
            assert limits[("PM2.5", "24h_mean")] == 75
            assert limits[("PM2.5", "annual_mean")] == 35
            assert limits[("PM10", "24h_mean")] == 150
            assert limits[("PM10", "annual_mean")] == 70
            aqi_limits = sorted(
                row.limit_value for row in snapshot.standards if row.pollutant == "AQI"
            )
            assert aqi_limits == [50, 100, 150, 200, 300, 500]
            assert [row.upper_bound for row in snapshot.risk_thresholds] == [0.8, 1.0, 1.5, None]
            page = unit.standards.list_standards(1, 4, pollutant="PM2.5")
            assert page.total == 2
            assert len(page.items) == 2
            assert {item.statistic_basis for item in page.items} == {"24h_mean", "annual_mean"}

            for index in range(3):
                unit.audit.append(
                    AuditDraft(
                        user_id=None,
                        action="SEED_CHECKED",
                        object_type="city",
                        object_id=str(index),
                        request_id=None,
                        result="SUCCESS",
                        details=None,
                        ip_hash=None,
                        created_at=_WHEN,
                    )
                )
            first_page = unit.audit.list_entries(1, 2)
            second_page = unit.audit.list_entries(2, 2)
            assert first_page.total == 3
            assert len(first_page.items) == 2
            assert len(second_page.items) == 1
            assert first_page.items[0].id != second_page.items[0].id

            creator = unit.auth.get_by_username("admin")
            assert creator is not None
            assert creator.must_change_password is True
            assert "TempAdmin#2026-initial" not in creator.password_hash
            first_model = unit.models.register(
                _model(creator.id, version="v1", digest="a" * 64)
            )
            second_model = unit.models.register(
                _model(creator.id, version="v2", digest="b" * 64)
            )
            unit.models.activate("imputer", first_model, activated_by=creator.id, activated_at=_WHEN)
            unit.models.activate("imputer", second_model, activated_by=creator.id, activated_at=_WHEN)
            active = unit.models.current_activation("imputer")
            assert active is not None
            assert active.model_id == second_model

            job_id = unit.jobs.start(
                JobRunDraft(
                    pipeline_run_id="run-1",
                    job_name="collect",
                    target_scope="beijing",
                    started_at=_WHEN,
                )
            )
            unit.jobs.finish(
                job_id,
                JobFinish(
                    finished_at=_WHEN,
                    status="SUCCESS",
                    request_count=2,
                    inserted_count=1,
                    skipped_count=1,
                    failure_count=0,
                    sanitized_error=None,
                ),
            )
            original = MonitoringDraft(
                station_id=station_id,
                observed_at=_WHEN,
                pm25=10,
                pm10=20,
                aqi=30,
                source="ONLINE",
            )
            conflict = MonitoringDraft(
                station_id=station_id,
                observed_at=_WHEN,
                pm25=99,
                pm10=98,
                aqi=97,
                source="CSV",
            )
            first_write = unit.monitoring.insert_batch((original, original))
            second_write = unit.monitoring.insert_batch((conflict,))
            stored = unit.monitoring.get(station_id, _WHEN)
            assert first_write.inserted == 1
            assert first_write.skipped == 1
            assert second_write.inserted == 0
            assert second_write.skipped == 1
            assert stored is not None
            assert (stored.pm25, stored.pm10, stored.aqi, stored.source) == (10, 20, 30, "ONLINE")
            invalid = unit.monitoring.insert_batch(
                (MonitoringDraft(station_id, _WHEN, -1, 1, 1, "ONLINE"),)
            )
            assert invalid.invalid == 1
            assert invalid.inserted == 0
            unit.commit()

        with factory() as session:
            assert session.scalar(select(func.count()).select_from(ModelRegistry)) == 2
            assert session.scalar(select(func.count()).select_from(Station)) == 35
    finally:
        engine.dispose()


@pytest.mark.integration
def test_analysis_alert_and_auth_repositories_round_trip(tmp_path: Path) -> None:
    url = sqlite_file_url(tmp_path / "analysis.db")
    upgrade_database(url, backup_directory=tmp_path / "backups")
    engine = create_engine_from_url(url)
    try:
        factory = session_factory(engine)
        with factory() as session:
            seed_reference_data(session, admin_password="TempAdmin#2026-initial")
            session.commit()
            station_id = session.scalar(select(func.min(Station.id)))
            standard_id = session.scalar(select(func.min(LegalStandard.id)))
            admin = session.scalar(select(User).where(User.username == "admin"))
            assert station_id is not None
            assert standard_id is not None
            assert admin is not None
            admin_id = admin.id

        with SqlAlchemyUnitOfWork(factory) as unit:
            compliance_id = unit.analysis.add_compliance(
                ComplianceDraft(
                    station_id=station_id,
                    local_date=date(2025, 1, 1),
                    pollutant="PM2.5",
                    daily_mean=10,
                    max_value=12,
                    min_value=8,
                    valid_points=20,
                    standard_id=standard_id,
                    standard_limit_snapshot=75,
                    exceed_ratio=0.1,
                    status="COMPLIANT",
                    risk_level="低",
                    calculated_at=_WHEN,
                )
            )
            unit.analysis.add_risk(
                RiskAssessmentDraft(
                    compliance_result_id=compliance_id,
                    risk_score=20,
                    risk_level="低",
                    legal_consequences="无",
                    recommended_actions=("继续观察",),
                    penalty_estimate_text="无",
                    disclaimer="预估结果，非执法依据",
                    assessed_at=_WHEN,
                )
            )
            run_id = unit.analysis.add_forecast_run(
                ForecastRunDraft(
                    station_id=station_id,
                    generated_at=_WHEN,
                    method="seasonal-trend",
                    method_version="1",
                    horizon_hours=24,
                    history_start=_WHEN,
                    history_end=_WHEN,
                    status="SUCCESS",
                    skip_reason=None,
                )
            )
            unit.analysis.add_forecast_result(
                ForecastResultDraft(
                    run_id=run_id,
                    forecast_at=_WHEN,
                    pollutant="PM2.5",
                    predicted_value=12,
                    exceedance_probability=0.25,
                    standard_id=standard_id,
                    is_warning=False,
                )
            )
            channel_id = unit.alerts.add_channel(
                AlertChannelDraft(
                    name="duty-mail",
                    channel_type="email",
                    enabled=True,
                    non_secret_config={"host": "mail.example"},
                    credential_ref="smtp-ref",
                    recipients=("duty@example.com",),
                    threshold_level="高",
                    created_by=admin_id,
                    updated_at=_WHEN,
                )
            )
            alert_id = unit.alerts.add_alert(
                AlertDraft(
                    compliance_result_id=compliance_id,
                    channel_id=channel_id,
                    station_id=station_id,
                    pollutant="PM2.5",
                    alert_date=date(2025, 1, 1),
                    trigger_snapshot={"status": "COMPLIANT"},
                    status="PENDING",
                    generated_at=_WHEN,
                )
            )
            unit.alerts.add_delivery_attempt(
                DeliveryAttemptDraft(
                    alert_id=alert_id,
                    attempt_no=1,
                    started_at=_WHEN,
                    finished_at=_WHEN,
                    outcome="SUCCESS",
                    sanitized_error=None,
                )
            )
            researcher_id = unit.auth.add_user(
                UserDraft(
                    username="researcher",
                    password_hash="$argon2id$not-the-plaintext",
                    role="研究者",
                    is_active=True,
                    must_change_password=True,
                    created_at=_WHEN,
                )
            )
            unit.auth.revoke_token(
                RevokedTokenDraft(
                    jti="token-1",
                    user_id=researcher_id,
                    expires_at=_WHEN,
                    revoked_at=_WHEN,
                    reason="logout",
                )
            )
            assert unit.auth.is_token_revoked("token-1") is True
            assert unit.auth.is_token_revoked("missing") is False
            assert unit.analysis.list_compliance(1, 10).total == 1
            assert unit.alerts.list_alerts(1, 10).total == 1
            unit.commit()
    finally:
        engine.dispose()


def _model(created_by: int, *, version: str, digest: str) -> ModelDraft:
    return ModelDraft(
        model_type="imputer",
        version=version,
        artifact_path=f"models/{version}",
        artifact_sha256=digest,
        scaler_path=None,
        feature_order=("PM2.5", "PM10", "AQI"),
        n_steps=4,
        n_features=3,
        trained_at=_WHEN,
        metrics={"MAE": 1.0},
        status="available",
        created_by=created_by,
        created_at=_WHEN,
    )
