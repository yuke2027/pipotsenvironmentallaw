"""Task 16.2: collect -> impute -> compliance -> risk -> forecast -> alert on a temp database.

External HTTP uses ``httpx.MockTransport``; the model, clock and notifier are fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.http.retry import ExternalCaller, StepClock
from app.adapters.model_artifacts import apply_imputation
from app.adapters.notifications.base import AlertPayload
from app.adapters.providers.cnemc import CNEMCPublicProvider
from app.db.models import (
    Alert,
    AlertDeliveryAttempt,
    ComplianceResult,
    ForecastResult,
    ForecastRun,
    JobRun,
    MonitoringRecord,
    RiskAssessment,
    Station,
    User,
)
from app.db.seed import seed_reference_data
from app.db.session import create_engine_from_url, session_factory, sqlite_file_url
from app.db.upgrade import upgrade_database
from app.domain.enums import RISK_LEVELS
from app.domain.records import (
    AlertChannelDraft,
    ComplianceDraft,
    ForecastResultDraft,
    ForecastRunDraft,
    JobFinish,
    JobRunDraft,
    RiskAssessmentDraft,
)
from app.repositories.sqlalchemy.catalog import SqlAlchemyCatalogRepository
from app.repositories.sqlalchemy.monitoring import SqlAlchemyMonitoringRepository
from app.repositories.sqlalchemy.store import (
    SqlAlchemyAlertRepository,
    SqlAlchemyAnalysisRepository,
    SqlAlchemyJobRunRepository,
    SqlAlchemyStandardsRepository,
)
from app.scheduler.jobs import STEP_NAMES, JobResult, failure, success
from app.scheduler.pipeline import Pipeline
from app.services.alerts import AlertService, AlertTrigger
from app.services.collection import CollectionService
from app.services.compliance import ComplianceOutcome, evaluate_group
from app.services.forecasting import build_forecast
from app.services.risk import assess_outcome
from tests.support.auth_factory import auth_settings

_SHANGHAI = ZoneInfo("Asia/Shanghai")
_NOW = datetime(2026, 1, 3, 12, 0, tzinfo=timezone.utc)
_FIRST_HOUR = datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc)
_LOCAL_DAY = date(2026, 1, 2)
_HOURS = 24
_MISSING_HOUR = 5


class _Notifier:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.payloads: list[AlertPayload] = []

    def deliver(self, payload: AlertPayload) -> None:
        if self.fail:
            raise OSError("notifier unavailable")
        self.payloads.append(payload)


@dataclass
class _Source:
    """Mutable MockTransport behaviour shared by cycles."""

    station_codes: tuple[str, str]
    healthy: bool = True
    calls: int = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if not self.healthy:
            return httpx.Response(500)
        noisy, quiet = self.station_codes
        rows: list[dict[str, object]] = []
        for hour in range(_HOURS):
            stamp = (_FIRST_HOUR + timedelta(hours=hour)).isoformat()
            rows.append(
                {
                    "station_code": noisy,
                    "observed_at": stamp,
                    "pm25": None if hour == _MISSING_HOUR else 100.0,
                    "pm10": 50.0,
                    "aqi": 120.0,
                }
            )
            rows.append({"station_code": quiet, "observed_at": stamp, "pm25": 20.0, "pm10": 40.0, "aqi": 50.0})
        rows.append({"station_code": "NOT-A-STATION", "observed_at": _FIRST_HOUR.isoformat(), "pm25": 1, "pm10": 1, "aqi": 1})
        rows.append({"station_code": quiet, "observed_at": (_FIRST_HOUR + timedelta(hours=40)).isoformat(), "pm25": -3, "pm10": 1, "aqi": 1})
        return httpx.Response(200, json={"schema_version": 1, "observations": rows})


@dataclass
class _Platform:
    session: Session
    source: _Source
    notifier: _Notifier
    pipeline: Pipeline
    cycle: int = 0
    compliance_ids: dict[tuple[int, str], int] = field(default_factory=dict)
    outcomes: list[tuple[int, ComplianceOutcome]] = field(default_factory=list)
    alert_results: list[object] = field(default_factory=list)
    channel_id: int = 0


def _build(tmp_path: Path, *, notifier_fails: bool = False) -> tuple[_Platform, object]:
    url = sqlite_file_url(tmp_path / "pipeline.db")
    upgrade_database(url, backup_directory=tmp_path / "backups")
    engine = create_engine_from_url(url)
    session = session_factory(engine)()
    seed_reference_data(session, admin_password="PipelineAdmin#2026")
    session.commit()
    names = session.scalars(select(Station.name_zh).order_by(Station.id).limit(2)).all()
    source = _Source((names[0], names[1]))
    notifier = _Notifier(fail=notifier_fails)
    settings = auth_settings(target_cities=("北京",), forecast_min_samples=_HOURS)

    client = httpx.Client(transport=httpx.MockTransport(source.handler))
    provider = CNEMCPublicProvider(enabled=True, endpoint="https://example.test/air", schema_version=1, client=client)
    caller = ExternalCaller(StepClock(), min_interval_seconds=0, base_delay_seconds=0)
    monitoring = SqlAlchemyMonitoringRepository(session)
    catalog = SqlAlchemyCatalogRepository(session)
    standards = SqlAlchemyStandardsRepository(session)
    analysis = SqlAlchemyAnalysisRepository(session)
    alerts = SqlAlchemyAlertRepository(session)
    jobs = SqlAlchemyJobRunRepository(session)
    collection = CollectionService(monitoring, catalog, provider, caller, settings)
    alert_service = AlertService(alerts, ExternalCaller(StepClock(), min_interval_seconds=0, base_delay_seconds=0))
    admin_id = session.scalar(select(User.id).where(User.username == "admin"))
    assert admin_id is not None
    channel_id = alerts.add_channel(
        AlertChannelDraft(
            name="e2e",
            channel_type="webhook",
            enabled=True,
            non_secret_config={"url": "https://hooks.example.test/a"},
            credential_ref=None,
            recipients=(),
            threshold_level=RISK_LEVELS[0],
            created_by=admin_id,
            updated_at=_NOW,
        )
    )
    session.commit()

    platform = _Platform(session, source, notifier, None, channel_id=channel_id)  # type: ignore[arg-type]

    def tracked(name: str, body: object) -> object:
        def run() -> JobResult:
            job_id = jobs.start(JobRunDraft(f"cycle-{platform.cycle}", name, "北京", _NOW))
            counts = (0, 0, 0, 0)
            try:
                result, counts = body()  # type: ignore[operator]
            except Exception:
                session.rollback()
                jobs.finish(job_id, JobFinish(_NOW, "FAILED", 0, 0, 0, 1, "error"))
                session.commit()
                raise
            jobs.finish(
                job_id,
                JobFinish(_NOW, result.status, counts[0], counts[1], counts[2], counts[3], result.reason),
            )
            session.commit()
            return result

        return run

    def collect() -> tuple[JobResult, tuple[int, int, int, int]]:
        report = collection.collect()
        counts = report.ingest.counts
        stats = (1, counts.inserted, counts.skipped, counts.invalid)
        if report.failed_cities:
            return failure("collection failed"), (1, 0, 0, 1)
        return success(no_op=report.no_op), stats

    def impute() -> tuple[JobResult, tuple[int, int, int, int]]:
        filled_total = 0
        for station_id in session.scalars(select(Station.id)).all():
            rows = session.scalars(
                select(MonitoringRecord).where(MonitoringRecord.station_id == station_id).order_by(MonitoringRecord.observed_at)
            ).all()
            if not any(row.pm25 is None for row in rows):
                continue
            observed = np.array([[0.0 if row.pm25 is None else row.pm25] for row in rows])
            mask = np.array([[row.pm25 is None] for row in rows])
            fake_model = np.full_like(observed, observed[~mask].mean())
            filled, original = apply_imputation(observed, mask, fake_model)
            for row, value, was_missing in zip(rows, filled[:, 0], original[:, 0]):
                if was_missing:
                    row.pm25 = float(value)
                    row.is_imputed = True
                    row.source = "IMPUTED"
                    row.original_missing_mask = {"pm25": True}
                    filled_total += 1
        return success(no_op=filled_total == 0), (0, 0, 0, 0)

    def _daily_values() -> dict[int, dict[date, dict[str, list[float]]]]:
        grouped: dict[int, dict[date, dict[str, list[float]]]] = {}
        for row in session.scalars(select(MonitoringRecord).order_by(MonitoringRecord.station_id, MonitoringRecord.observed_at)):
            stamp = row.observed_at if row.observed_at.tzinfo else row.observed_at.replace(tzinfo=timezone.utc)
            day = stamp.astimezone(_SHANGHAI).date()
            bucket = grouped.setdefault(row.station_id, {}).setdefault(day, {"PM2.5": [], "PM10": []})
            if row.pm25 is not None:
                bucket["PM2.5"].append(row.pm25)
            if row.pm10 is not None:
                bucket["PM10"].append(row.pm10)
        return grouped

    def compliance() -> tuple[JobResult, tuple[int, int, int, int]]:
        snapshot = standards.snapshot(_NOW)
        platform.outcomes.clear()
        for station_id, days in _daily_values().items():
            for day, values in days.items():
                for outcome in evaluate_group(
                    station_id=str(station_id),
                    local_date=day,
                    values=values,
                    snapshot=snapshot,
                    min_points=settings.min_compliance_points,
                ):
                    if outcome.status == "INSUFFICIENT":
                        continue
                    existing = session.scalar(
                        select(ComplianceResult.id).where(
                            ComplianceResult.station_id == station_id,
                            ComplianceResult.local_date == day,
                            ComplianceResult.pollutant == outcome.pollutant,
                        )
                    )
                    if existing is None:
                        existing = analysis.add_compliance(
                            ComplianceDraft(
                                station_id=station_id,
                                local_date=day,
                                pollutant=outcome.pollutant,
                                daily_mean=outcome.daily_mean,
                                max_value=outcome.max_value,
                                min_value=outcome.min_value,
                                valid_points=outcome.valid_points,
                                standard_id=outcome.standard_id or 0,
                                standard_limit_snapshot=outcome.standard_limit_snapshot,
                                exceed_ratio=outcome.exceed_ratio,
                                status=outcome.status,
                                risk_level=outcome.risk_level,
                                calculated_at=_NOW,
                            )
                        )
                    platform.outcomes.append((existing, outcome))
        return success(no_op=not platform.outcomes), (0, 0, 0, 0)

    def risk() -> tuple[JobResult, tuple[int, int, int, int]]:
        snapshot = standards.snapshot(_NOW)
        for compliance_id, outcome in platform.outcomes:
            if session.scalar(select(RiskAssessment.id).where(RiskAssessment.compliance_result_id == compliance_id)):
                continue
            view = assess_outcome(outcome, snapshot)
            analysis.add_risk(
                RiskAssessmentDraft(
                    compliance_result_id=compliance_id,
                    risk_score=view.risk_score,
                    risk_level=view.risk_level,
                    legal_consequences=view.legal_consequences,
                    recommended_actions=view.recommended_actions,
                    penalty_estimate_text=view.penalty_estimate_text,
                    disclaimer=view.disclaimer,
                    assessed_at=_NOW,
                )
            )
        return success(), (0, 0, 0, 0)

    def forecast() -> tuple[JobResult, tuple[int, int, int, int]]:
        snapshot = standards.snapshot(_NOW)
        limits = {item.pollutant: item.limit_value for item in snapshot.standards if item.statistic_basis == "24h_mean"}
        ids = {item.pollutant: item.id for item in snapshot.standards if item.statistic_basis == "24h_mean"}
        for station_id, days in _daily_values().items():
            values = days[_LOCAL_DAY]
            bundle = build_forecast(
                {"PM2.5": values["PM2.5"], "PM10": values["PM10"]},
                _FIRST_HOUR + timedelta(hours=_HOURS - 1),
                generated_at=_NOW,
                horizon_hours=24,
                limits={"PM2.5": limits["PM2.5"], "PM10": limits["PM10"]},
                warning_probability=settings.forecast_warning_probability,
                min_samples=settings.forecast_min_samples,
            )
            run_id = analysis.add_forecast_run(
                ForecastRunDraft(
                    station_id=station_id,
                    generated_at=_NOW,
                    method=bundle.method,
                    method_version=bundle.method_version,
                    horizon_hours=bundle.horizon_hours,
                    history_start=_FIRST_HOUR,
                    history_end=_FIRST_HOUR + timedelta(hours=_HOURS - 1),
                    status=bundle.status,
                    skip_reason=bundle.skip_reason,
                )
            )
            for point in bundle.points:
                analysis.add_forecast_result(
                    ForecastResultDraft(
                        run_id=run_id,
                        forecast_at=point.forecast_at,
                        pollutant=point.pollutant,
                        predicted_value=point.predicted_value,
                        exceedance_probability=point.exceedance_probability,
                        standard_id=ids[point.pollutant],
                        is_warning=point.is_warning,
                    )
                )
        return success(), (0, 0, 0, 0)

    def alert() -> tuple[JobResult, tuple[int, int, int, int]]:
        platform.alert_results.clear()
        for compliance_id, outcome in platform.outcomes:
            result = alert_service.dispatch(
                AlertTrigger(
                    compliance_result_id=compliance_id,
                    station_id=int(outcome.station_id),
                    pollutant=outcome.pollutant,
                    alert_date=outcome.local_date,
                    status=outcome.status,
                    risk_level=outcome.risk_level or RISK_LEVELS[0],
                    city="北京",
                    station=outcome.station_id,
                    statistic=f"{outcome.daily_mean:.1f}",
                    limit=f"{outcome.standard_limit_snapshot:.1f}",
                    ratio=f"{outcome.exceed_ratio:.2f}",
                ),
                channel_id=channel_id,
                threshold_level=RISK_LEVELS[0],
                notifier=notifier,
                now=_NOW,
            )
            platform.alert_results.append(result)
        failed = [item for item in platform.alert_results if item.created and not item.sent]  # type: ignore[attr-defined]
        return (failure("alert delivery failed") if failed else success()), (0, 0, 0, 0)

    bodies = {"collect": collect, "impute": impute, "compliance": compliance, "risk": risk, "forecast": forecast, "alert": alert}
    platform.pipeline = Pipeline({name: tracked(name, bodies[name]) for name in STEP_NAMES})  # type: ignore[arg-type]
    return platform, engine


def _run(platform: _Platform):
    platform.cycle += 1
    return platform.pipeline.run_once()


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


@pytest.mark.integration
def test_full_cycle_persists_every_stage_with_sources_and_references(tmp_path: Path) -> None:
    platform, engine = _build(tmp_path)
    try:
        session = platform.session
        run = _run(platform)

        assert run.status == "SUCCESS", run.reason
        assert run.executed == STEP_NAMES
        assert run.failed_step is None

        sources = dict(session.execute(select(MonitoringRecord.source, func.count()).group_by(MonitoringRecord.source)).all())
        assert sources == {"ONLINE": 2 * _HOURS - 1, "IMPUTED": 1}
        imputed = session.scalars(select(MonitoringRecord).where(MonitoringRecord.is_imputed.is_(True))).all()
        assert len(imputed) == 1
        assert imputed[0].pm25 == 100.0
        assert imputed[0].original_missing_mask == {"pm25": True}
        assert session.scalar(select(func.count()).select_from(MonitoringRecord).where(MonitoringRecord.pm25 < 0)) == 0

        compliance = session.scalars(select(ComplianceResult)).all()
        assert len(compliance) == 4
        statuses = {(row.pollutant, row.status) for row in compliance}
        assert ("PM2.5", "NON_COMPLIANT") in statuses
        assert ("PM2.5", "COMPLIANT") in statuses
        assert all(row.standard_id and row.standard_limit_snapshot for row in compliance)
        assert _count(session, RiskAssessment) == 4

        runs = session.scalars(select(ForecastRun)).all()
        assert len(runs) == 2 and all(item.status == "SUCCESS" for item in runs)
        results = session.scalars(select(ForecastResult)).all()
        assert len(results) == 2 * 2 * 24
        assert all(item.predicted_value >= 0 and 0 <= item.exceedance_probability <= 1 for item in results)

        alerts = session.scalars(select(Alert)).all()
        assert len(alerts) == 1
        assert alerts[0].status == "SENT"
        assert alerts[0].pollutant == "PM2.5"
        assert len(platform.notifier.payloads) == 1
        assert platform.notifier.payloads[0].level in RISK_LEVELS

        jobs = session.scalars(select(JobRun).order_by(JobRun.id)).all()
        assert [item.job_name for item in jobs] == list(STEP_NAMES)
        assert {item.status for item in jobs} == {"SUCCESS"}
        collect = jobs[0]
        assert collect.inserted_count == 2 * _HOURS
        assert collect.skipped_count == 0
        assert collect.failure_count == 2
        assert collect.inserted_count + collect.skipped_count + collect.failure_count == 2 * _HOURS + 2
    finally:
        platform.session.close()
        engine.dispose()  # type: ignore[attr-defined]


@pytest.mark.integration
def test_failed_collect_truncates_the_pass_and_next_cycle_recovers(tmp_path: Path) -> None:
    platform, engine = _build(tmp_path)
    try:
        session = platform.session
        platform.source.healthy = False
        broken = _run(platform)

        assert broken.status == "FAILED"
        assert broken.executed == ("collect",)
        assert broken.failed_step == "collect"
        assert _count(session, MonitoringRecord) == 0
        assert _count(session, ComplianceResult) == 0
        assert _count(session, Alert) == 0
        assert session.scalar(select(JobRun.status).where(JobRun.job_name == "collect")) == "FAILED"

        platform.source.healthy = True
        recovered = _run(platform)

        assert recovered.status == "SUCCESS"
        assert recovered.run_id != broken.run_id
        assert recovered.executed == STEP_NAMES
        assert _count(session, MonitoringRecord) == 2 * _HOURS
        assert _count(session, Alert) == 1
    finally:
        platform.session.close()
        engine.dispose()  # type: ignore[attr-defined]


@pytest.mark.integration
def test_second_cycle_is_incremental_and_same_day_alert_is_deduplicated(tmp_path: Path) -> None:
    platform, engine = _build(tmp_path)
    try:
        session = platform.session
        assert _run(platform).status == "SUCCESS"
        rows_after_first = _count(session, MonitoringRecord)

        second = _run(platform)

        assert second.status == "SUCCESS"
        assert _count(session, MonitoringRecord) == rows_after_first
        assert _count(session, ComplianceResult) == 4
        assert _count(session, RiskAssessment) == 4
        assert _count(session, Alert) == 1
        assert len(platform.notifier.payloads) == 1
        assert any(item.deduped for item in platform.alert_results)  # type: ignore[attr-defined]
        assert session.scalar(select(Alert.dedupe_reason)) == "same-day delivery already sent"
    finally:
        platform.session.close()
        engine.dispose()  # type: ignore[attr-defined]


@pytest.mark.integration
def test_alert_failure_keeps_earlier_stages_and_records_every_attempt(tmp_path: Path) -> None:
    platform, engine = _build(tmp_path, notifier_fails=True)
    try:
        session = platform.session
        run = _run(platform)

        assert run.status == "FAILED"
        assert run.failed_step == "alert"
        assert run.executed == STEP_NAMES
        assert _count(session, ComplianceResult) == 4
        assert _count(session, RiskAssessment) == 4
        alert = session.scalars(select(Alert)).one()
        assert alert.status == "FAILED"
        assert alert.attempt_count == 4
        assert alert.failure_reason
        attempts = session.scalars(select(AlertDeliveryAttempt).order_by(AlertDeliveryAttempt.attempt_no)).all()
        assert [item.attempt_no for item in attempts] == [1, 2, 3, 4]
        assert {item.outcome for item in attempts} == {"FAILED"}
        assert platform.notifier.payloads == []
    finally:
        platform.session.close()
        engine.dispose()  # type: ignore[attr-defined]
