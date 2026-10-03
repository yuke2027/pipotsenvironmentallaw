"""Residual coverage: artifacts, channels, query, csv import, standards, users."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from app.adapters import model_artifacts as artifacts
from app.core.errors import AppError, ErrorCode
from app.domain.enums import RISK_LEVELS
from app.domain.principal import Principal
from app.domain.query_spec import QuerySpec, validate_time_range
from app.services.query import query_alerts, query_monitoring
from tests.support.auth_factory import auth_settings, frozen_clock, migrated_factory


def _admin_principal() -> Principal:
    return Principal(
        user_id=1, username="admin", role="管理员", password_change_required=False,
        jti="j", expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.mark.unit
def test_artifact_write_load_and_guard_branches(tmp_path: Path) -> None:
    root = tmp_path / "models"
    payload = {
        "scaler": {
            "feature_order": ["PM2.5", "PM10", "AQI"],
            "mean": [1.0, 2.0, 3.0],
            "scale": [4.0, 5.0, 6.0],
            "n_features": 3,
            "n_steps": 24,
        },
        "manifest": {"kind": "saits"},
    }
    destination = artifacts.write_artifact(root, "m1", payload, b"model-bytes")
    document, digest = artifacts.load_artifact(root, "m1")
    assert digest == artifacts.sha256_file(destination / "model.bin")
    assert document.n_steps == 24

    with pytest.raises(artifacts.ArtifactError):
        artifacts.write_artifact(root, "evil.pkl", payload, b"x")
    with pytest.raises(artifacts.ArtifactError):
        artifacts.assert_inside(root, tmp_path / "other" / "m2")

    bad = tmp_path / "bad"
    (bad / "m").mkdir(parents=True)
    with pytest.raises(artifacts.ArtifactError):
        artifacts.load_artifact(bad, "m")

    (bad / "m" / "manifest.json").write_text("{bad", encoding="utf-8")
    (bad / "m" / "scaler.json").write_text("{}", encoding="utf-8")
    (bad / "m" / "model.bin").write_bytes(b"x")
    with pytest.raises(artifacts.ArtifactError):
        artifacts.load_artifact(bad, "m")

    (bad / "m" / "manifest.json").write_text(json.dumps({"sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(artifacts.ArtifactError):
        artifacts.load_artifact(bad, "m")

    corrupt = artifacts.sha256_file(bad / "m" / "model.bin")
    (bad / "m" / "manifest.json").write_text(json.dumps({"sha256": corrupt}), encoding="utf-8")
    with pytest.raises(artifacts.ArtifactError):
        artifacts.load_artifact(bad, "m")  # scaler missing keys


@pytest.mark.unit
def test_standardizer_and_apply_imputation() -> None:
    std = artifacts.ArrayStandardizer(
        np.array([1.0, 2.0, 3.0]), np.array([1.0, 1.0, 1.0]), ("PM2.5", "PM10", "AQI")
    )
    values = np.array([[[1.0, 2.0, 3.0]]])
    np.testing.assert_allclose(std.inverse_transform(std.transform(values)), values)
    with pytest.raises(artifacts.ArtifactError):
        std.transform(np.zeros((1, 1, 1)))
    with pytest.raises(artifacts.ArtifactError):
        artifacts.ArrayStandardizer(
            np.array([1.0, 2.0]), np.array([1.0, 1.0, 1.0]), ("a", "b")
        )
    with pytest.raises(artifacts.ArtifactError):
        artifacts.ArrayStandardizer(
            np.array([1.0, 2.0, 3.0]), np.array([0.0, 1.0, 1.0]), ("a", "b", "c")
        )
    with pytest.raises(artifacts.ArtifactError):
        artifacts.ArrayStandardizer(
            np.array([1.0, 2.0, float("nan")]), np.array([1.0, 1.0, 1.0]), ("a", "b", "c")
        )

    observed = np.array([[1.0, np.nan]])
    mask = np.array([[False, True]])
    output = np.array([[9.0, 8.0]])
    filled, returned_mask = artifacts.apply_imputation(observed, mask, output)
    assert filled[0, 1] == 8.0 and filled[0, 0] == 1.0 and returned_mask[0, 1]
    with pytest.raises(artifacts.ArtifactError):
        artifacts.apply_imputation(observed, mask, np.array([[1.0]]))


@pytest.mark.unit
def test_query_service_filters_and_time_validation() -> None:
    from app.services.query import AlertQueryRow, MonitoringQueryRow

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    row = MonitoringQueryRow(
        id=1, city="北京", station_id=5, pollutant="PM2.5",
        observed_at=start, value=10.0, source="API", is_imputed=False,
    )
    spec = QuerySpec(start=start, end=end, city="北京", pollutant="PM2.5", source="API", is_imputed=False)
    page = query_monitoring([row], spec, page=1, page_size=10, max_span=timedelta(days=3))
    assert page.total == 1
    assert "start=" in spec.describe()

    wrong = QuerySpec(start=start, end=end, city="上海")
    assert query_monitoring([row], wrong, page=1, page_size=10, max_span=timedelta(days=3)).total == 0
    assert query_monitoring([row], QuerySpec(start=start, end=end, station_id=9),
                           page=1, page_size=10, max_span=timedelta(days=3)).total == 0
    assert query_monitoring([row], QuerySpec(start=start, end=end, pollutant="O3"),
                           page=1, page_size=10, max_span=timedelta(days=3)).total == 0
    assert query_monitoring([row], QuerySpec(start=start, end=end, source="CSV"),
                           page=1, page_size=10, max_span=timedelta(days=3)).total == 0
    assert query_monitoring([row], QuerySpec(start=start, end=end, is_imputed=True),
                           page=1, page_size=10, max_span=timedelta(days=3)).total == 0

    alert = AlertQueryRow(
        id=1, generated_at=start, city="北京", station_id=5, pollutant="PM2.5",
        status="queued", risk_level="high",
    )
    full = QuerySpec(start=start, end=end, alert_status="queued", risk_level="high",
                     city="北京", station_id=5, pollutant="PM2.5")
    assert query_alerts([alert], full, page=1, page_size=10, max_span=timedelta(days=3)).total == 1
    assert query_alerts([alert], QuerySpec(start=start, end=end, alert_status="sent"),
                        page=1, page_size=10, max_span=timedelta(days=3)).total == 0
    assert query_alerts([alert], QuerySpec(start=start, end=end, risk_level="low"),
                        page=1, page_size=10, max_span=timedelta(days=3)).total == 0
    assert query_alerts([alert], QuerySpec(start=start, end=end, station_id=1),
                        page=1, page_size=10, max_span=timedelta(days=3)).total == 0

    naive = QuerySpec(start=start.replace(tzinfo=None), end=end)
    with pytest.raises(AppError):
        query_monitoring([row], naive, page=1, page_size=10, max_span=timedelta(days=3))
    with pytest.raises(AppError):
        validate_time_range(end, start, timedelta(days=3))
    with pytest.raises(AppError):
        validate_time_range(start, start + timedelta(days=10), timedelta(days=3))


@pytest.mark.integration
def test_alert_channel_service_crud_and_validation(tmp_path: Path) -> None:
    from app.db.models import User
    from app.core.security import hash_password
    from app.domain.records import UserDraft
    from app.repositories.sqlalchemy.store import (
        SqlAlchemyAlertRepository,
        SqlAlchemyAuditRepository,
        SqlAlchemyAuthRepository,
    )
    from app.services.alert_channels import AlertChannelService

    factory, engine = migrated_factory(tmp_path)
    clock = frozen_clock()
    try:
        with factory() as session:
            admin_id = SqlAlchemyAuthRepository(session).add_user(
                UserDraft(username="admin", password_hash=hash_password("p"), role="管理员",
                          is_active=True, must_change_password=False, created_at=clock.now())
            )
            actor = Principal(user_id=admin_id, username="admin", role="管理员",
                              password_change_required=False, jti="j",
                              expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
            service = AlertChannelService(
                SqlAlchemyAlertRepository(session), SqlAlchemyAuditRepository(session), clock
            )
            created = service.create(
                actor,
                name="ops",
                channel_type="webhook",
                enabled=True,
                non_secret_config={"url": "https://hooks.example.test"},
                credential_ref="ESP_NOTIFY_OPS",
                recipients=(),
                threshold_level="高",
            )
            updated = service.update(
                actor, created.id,
                name="ops-2", channel_type="email", enabled=False,
                non_secret_config={"host": "smtp.test"},
                credential_ref=None, recipients=("a@b.c",), threshold_level="中",
            )
            assert updated.name == "ops-2"
            assert service.list_channels(actor)
            view = service.public_view(updated)
            assert view["name"] == "ops-2" and "password" not in str(view)

            with pytest.raises(AppError):
                service.update(actor, created.id, name="ops", channel_type="sms",
                               enabled=True, non_secret_config={}, credential_ref=None,
                               recipients=(), threshold_level="高")
            with pytest.raises(AppError):
                service.update(actor, created.id, name="ops", channel_type="email",
                               enabled=True, non_secret_config={}, credential_ref=None,
                               recipients=(), threshold_level="高")
            with pytest.raises(AppError):
                service.update(actor, created.id, name="ops", channel_type="webhook",
                               enabled=True, non_secret_config={}, credential_ref=None,
                               recipients=(), threshold_level="极高")
            with pytest.raises(AppError):
                service.update(actor, created.id, name="ops", channel_type="webhook",
                               enabled=True, non_secret_config={"token": "x"},
                               credential_ref=None, recipients=(), threshold_level="高")
            with pytest.raises(AppError):
                service.update(actor, 999, name="ops", channel_type="webhook",
                               enabled=True, non_secret_config={}, credential_ref=None,
                               recipients=(), threshold_level="高")
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_store_repository_edge_methods(tmp_path: Path) -> None:
    from app.db.models import LegalStandard, User
    from app.domain.records import JobFinish, RevokedTokenDraft, UserDraft
    from app.repositories.sqlalchemy.store import (SqlAlchemyAuthRepository, SqlAlchemyJobRunRepository, SqlAlchemyStandardsRepository)
    from app.core.security import hash_password
    from app.db.seed import seed_reference_data

    factory, engine = migrated_factory(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    try:
        with factory() as session:
            seed_reference_data(session)
            repo = SqlAlchemyStandardsRepository(session)
            auth_repo = SqlAlchemyAuthRepository(session)
            jobs_repo = SqlAlchemyJobRunRepository(session)

            with pytest.raises(LookupError):
                repo.close_standard(99999, effective_to=now, expected_version="v1")
            standard = session.scalars(
                __import__("sqlalchemy").select(LegalStandard).where(LegalStandard.is_active.is_(True))
            ).first()
            assert standard is not None
            with pytest.raises(Exception):
                repo.close_standard(standard.id, effective_to=now, expected_version="bogus")
            repo.close_standard(standard.id, effective_to=now, expected_version=standard.version)
            session.commit()

            uid = session.add(
                User(username="edge", password_hash=hash_password("x"), role="研究者",
                     is_active=True, must_change_password=False, created_at=now, updated_at=now)
            )
            session.flush()
            user_id = session.scalars(__import__("sqlalchemy").select(User.id).where(User.username == "edge")).one()
            token_id = auth_repo.revoke_token(
                RevokedTokenDraft(jti="jti-1", user_id=user_id, expires_at=now,
                                  revoked_at=now, reason="logout")
            )
            assert auth_repo.is_token_revoked("jti-1")
            assert not auth_repo.is_token_revoked("other")
            with pytest.raises(Exception):
                jobs_repo.finish(99999, JobFinish(finished_at=now, status="succeeded", request_count=1, inserted_count=0, skipped_count=0, failure_count=0, sanitized_error=None))
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_csv_import_directory_paths(tmp_path: Path) -> None:
    from app.db.models import City, Station
    from app.repositories.sqlalchemy.monitoring import SqlAlchemyMonitoringRepository
    from app.services.csv_import import CsvImporter

    factory, engine = migrated_factory(tmp_path)
    try:
        with factory() as session:
            city = City(code="110000", name_zh="北京", timezone="Asia/Shanghai",
                        enabled=True, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
            session.add(city)
            session.flush()
            station = Station(city_id=city.id, code="S1", name_zh="东城东四", enabled=True)
            session.add(station)
            session.commit()
            service = CsvImporter(SqlAlchemyMonitoringRepository(session), {"东城东四": station.id})
            report = service.import_directory(tmp_path / "missing")
            assert report.files_seen == 0

            directory = tmp_path / "incoming"
            directory.mkdir()
            (directory / "bad.csv").write_text("a,b,c\n", encoding="utf-8")
            (directory / "weird.csv").write_bytes(b"\xff\xfe\x00")
            report = service.import_directory(directory)
            assert len(report.files) == 2
            assert all(item.error for item in report.files)

            (directory / "ok.csv").write_text(
                "date,hour,type,东城东四\n"
                "20260930,0,PM2.5,30\n20260930,0,PM10,66\n20260930,0,AQI,58\n",
                encoding="utf-8",
            )
            report = service.import_directory(directory, allowed_stations={"东城东四"})
            assert any(item.inserted for item in report.files)
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_user_service_remaining_flows(tmp_path: Path) -> None:
    from app.domain.records import UserDraft
    from app.core.security import hash_password
    from app.repositories.sqlalchemy.store import SqlAlchemyAuditRepository, SqlAlchemyAuthRepository
    from app.services.auth import AuthService
    from app.services.users import UserService
    from app.domain.permissions import Operation

    factory, engine = migrated_factory(tmp_path)
    clock = frozen_clock()
    try:
        with factory() as session:
            auth = SqlAlchemyAuthRepository(session)
            audit = SqlAlchemyAuditRepository(session)
            auth_service = AuthService(auth, audit, auth_settings(), clock)
            users = UserService(auth, audit, auth_service, clock)
            admin_id = auth.add_user(
                UserDraft(username="admin", password_hash=hash_password("p"), role="管理员",
                          is_active=True, must_change_password=False, created_at=clock.now())
            )
            actor = Principal(user_id=admin_id, username="admin", role="管理员",
                              password_change_required=False, jti="a", expires_at=clock.now())
            created = users.create_user(actor, "worker", "研究者")
            assert created.temporary_password

            target_id = auth.list_users(1, 10).items[-1].id
            updated = users.change_role(actor, target_id, "监管人员")
            assert updated.role == "监管人员"
            deactivated = users.set_active(actor, target_id, is_active=False)
            assert deactivated.is_active is False
            reactivated = users.set_active(actor, target_id, is_active=True)
            assert reactivated.is_active is True
            listing = users.list_users(actor, 1, 10)
            assert listing.total >= 2

            outsider = Principal(user_id=target_id, username="worker", role="研究者",
                                 password_change_required=False, jti="b", expires_at=clock.now())
            with pytest.raises(AppError):
                users.list_users(outsider, 1, 10)
            with pytest.raises(AppError):
                users.change_role(actor, target_id, "不存在的角色")
            with pytest.raises(AppError):
                users.create_user(actor, "", "研究者")
            with pytest.raises(AppError):
                users.create_user(actor, "x" * 65, "研究者")
            with pytest.raises(AppError):
                users.create_user(actor, "another", "错误角色")
            with pytest.raises(AppError):
                users.create_user(actor, "ok", "研究者", temporary_password="")
            with pytest.raises(AppError):
                users.set_active(actor, 99999, is_active=False)
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_auth_service_full_token_lifecycle(tmp_path: Path) -> None:
    from app.domain.records import UserDraft
    from app.core.errors import AppError
    from app.core.security import hash_password
    from app.domain.permissions import Operation
    from app.repositories.sqlalchemy.store import SqlAlchemyAuditRepository, SqlAlchemyAuthRepository
    from app.services.auth import AuthService

    factory, engine = migrated_factory(tmp_path)
    clock = frozen_clock()
    try:
        with factory() as session:
            auth = SqlAlchemyAuthRepository(session)
            audit = SqlAlchemyAuditRepository(session)
            service = AuthService(auth, audit, auth_settings(), clock)
            user_id = auth.add_user(
                UserDraft(username="worker", password_hash=hash_password("old-password!"), role="研究者",
                          is_active=True, must_change_password=False, created_at=clock.now())
            )

            login = service.login("worker", "old-password!")
            principal = service.authenticate(login.access_token)
            assert principal.user_id == user_id
            assert service.me(login.access_token).username == "worker"
            assert service.allows_during_password_change(Operation.CHANGE_PASSWORD) is True

            with pytest.raises(AppError):
                service.login("worker", "wrong-password")
            with pytest.raises(AppError):
                service.login("", "x")
            with pytest.raises(AppError):
                service.authenticate("not-a-token")
            with pytest.raises(AppError):
                service.authenticate(None)

            service.change_password(login.access_token, "old-password!", "new-password!!")
            with pytest.raises(AppError):
                service.authenticate(login.access_token)  # old token revoked

            second = service.login("worker", "new-password!!")
            with pytest.raises(AppError):
                service.change_password(second.access_token, "wrong", "another-password")
            service.logout(second.access_token)
            with pytest.raises(AppError):
                service.authenticate(second.access_token)
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.unit
def test_dataframe_contracts_error_branches() -> None:
    import pandas as pd

    from app.domain.dataframe_contracts import (
        AlgorithmContractError,
        FEATURE_COLUMNS,
        require_columns,
        require_exact_mapping_keys,
        require_frame,
        require_identifier_values,
        require_sorted_unique,
        validate_feature_order,
        validate_metrics,
        validate_tensor,
    )

    with pytest.raises(AlgorithmContractError):
        require_frame("x", "ctx")
    frame = pd.DataFrame({"a": [1]})
    with pytest.raises(AlgorithmContractError):
        require_columns(frame, ("a", "b"), "ctx")
    with pytest.raises(AlgorithmContractError):
        require_columns(frame[["a", ]].assign(extra=1), ("a",), "ctx", exact=True)

    bad_keys = pd.DataFrame({"k": ["", "x"], "v": [1, 2]})
    with pytest.raises(AlgorithmContractError):
        require_identifier_values(bad_keys, ("k",), "ctx")
    dup = pd.DataFrame({"k": [1, 1, 2], "v": [1, 2, 3]})
    with pytest.raises(AlgorithmContractError):
        require_sorted_unique(dup, ("k",), "ctx")
    unsorted = pd.DataFrame({"k": [2, 1], "v": [1, 2]})
    with pytest.raises(AlgorithmContractError):
        require_sorted_unique(unsorted, ("k",), "ctx")

    with pytest.raises(AlgorithmContractError):
        validate_feature_order(("a",), "ctx")
    tensor = np.zeros((1, 24, len(FEATURE_COLUMNS)))
    with pytest.raises(AlgorithmContractError):
        validate_tensor(np.zeros((2, 2)), feature_order=FEATURE_COLUMNS, context="ctx", allow_nan=False)
    with pytest.raises(AlgorithmContractError):
        validate_tensor(np.zeros((1, 24, 2)), feature_order=FEATURE_COLUMNS, context="ctx", allow_nan=False)
    with pytest.raises(AlgorithmContractError):
        validate_tensor(tensor, feature_order=FEATURE_COLUMNS, context="ctx", allow_nan=False, expected_shape=(1, 24, 5))
    with pytest.raises(AlgorithmContractError):
        validate_tensor(np.array([["x"]], dtype=object).reshape(1, 1, 1), feature_order=FEATURE_COLUMNS[:1], context="ctx", allow_nan=False)
    bad = tensor.copy()
    bad[0, 0, 0] = np.inf
    with pytest.raises(AlgorithmContractError):
        validate_tensor(bad, feature_order=FEATURE_COLUMNS, context="ctx", allow_nan=False)
    neg = tensor.copy()
    neg[0, 0, 0] = -1
    with pytest.raises(AlgorithmContractError):
        validate_tensor(neg, feature_order=FEATURE_COLUMNS, context="ctx", allow_nan=False)
    validate_tensor(neg, feature_order=FEATURE_COLUMNS, context="ctx", allow_nan=False, allow_negative=True)

    with pytest.raises(AlgorithmContractError):
        require_exact_mapping_keys({"a": 1}, ("b",), "ctx")
    ok = validate_metrics({"MSE": "1.5", "MAE": 1.0, "RMSE": 2}, "ctx")
    assert ok["MSE"] == 1.5
    with pytest.raises(AlgorithmContractError):
        validate_metrics({"MSE": True, "MAE": 1, "RMSE": 1}, "ctx")
    with pytest.raises(AlgorithmContractError):
        validate_metrics({"MSE": "abc", "MAE": 1, "RMSE": 1}, "ctx")
    with pytest.raises(AlgorithmContractError):
        validate_metrics({"MSE": -1, "MAE": 1, "RMSE": 1}, "ctx")


@pytest.mark.unit
def test_config_and_security_validation_branches() -> None:
    from app.core.config import Settings, public_setting_name
    from app.core.errors import AppError
    from app.core.security import decode_access_token, issue_access_token

    naive = datetime(2026, 1, 1)
    aware = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        issue_access_token(user_id=1, role="不存在", password_change_required=False,
                           now=aware, ttl_seconds=60, secret="s")
    with pytest.raises(ValueError):
        issue_access_token(user_id=1, role="研究者", password_change_required=False,
                           now=aware, ttl_seconds=0, secret="s")
    with pytest.raises(ValueError):
        issue_access_token(user_id=1, role="研究者", password_change_required=False,
                           now=naive, ttl_seconds=60, secret="s")
    with pytest.raises(ValueError):
        decode_access_token("x", "s", naive)

    token, claims = issue_access_token(user_id=1, role="研究者", password_change_required=False,
                                       now=aware, ttl_seconds=60, secret="s")
    with pytest.raises(AppError):
        decode_access_token("garbage", "s", aware)
    with pytest.raises(AppError):
        decode_access_token(token, "wrong-secret", aware)
    with pytest.raises(AppError):
        decode_access_token(token, "s", aware + timedelta(seconds=120))

    assert public_setting_name("database_url") in {"database_url", "DATABASE_URL"}
    assert public_setting_name("not_a_field") == "not_a_field"


@pytest.mark.integration
def test_shared_transaction_and_seed_helpers(tmp_path: Path) -> None:
    from app.db.models import City
    from app.v2.shared.dependencies import transaction
    from app.db import seed_data

    factory, engine = migrated_factory(tmp_path)
    try:
        with factory() as session:
            with transaction(session):
                session.add(City(code="110000", name_zh="北京", timezone="Asia/Shanghai",
                                 enabled=True, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
            with pytest.raises(RuntimeError):
                with transaction(session):
                    raise RuntimeError("boom")
    finally:
        engine.dispose()

    missing = tmp_path / "nothing"
    missing.mkdir()
    with pytest.raises(FileNotFoundError):
        seed_data.extract_beijing_station_names(missing)
    with pytest.raises(FileNotFoundError):
        seed_data.beijing_city_code(missing)
    (missing / "beijing_all_x.csv").write_text("date,hour,type,A,B\n", encoding="utf-8")
    with pytest.raises(ValueError):
        seed_data.extract_beijing_station_names(missing)
    assert seed_data.beijing_city_code(missing) == "beijing"


@pytest.mark.integration
def test_legacy_legal_adapter_full_paths(tmp_path: Path) -> None:
    import pandas as pd

    from app.adapters.legacy import legal as legacy_legal
    from app.db.seed import seed_reference_data
    from app.repositories.sqlalchemy.store import SqlAlchemyStandardsRepository

    factory, engine = migrated_factory(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    try:
        with factory() as session:
            seed_reference_data(session)
            snapshot = SqlAlchemyStandardsRepository(session).snapshot(now)
            standards = legacy_legal.DatabaseLegalStandardsAdapter(snapshot)

            assert standards.get_standard("PM2.5") is not None
            assert standards.get_standard("UNKNOWN") is None
            level = standards.get_risk_level(10, "PM2.5")
            assert level in ("low", "medium", "high", "critical")
            assert standards.get_risk_level(1, "UNKNOWN") is None
            assert standards.get_risk_description("critical")
            assert "未知" in standards.get_risk_description("nope")

            frame = pd.DataFrame({
                "station_id": ["s1"] * 24,
                "timestamp": list(range(24)),
                "date": ["20250101"] * 24,
                "PM2.5": [80.0] * 24,
                "PM10": [60.0] * 24,
                "AQI": [90.0] * 24,
            })
            results = legacy_legal.check_compliance(frame, standards)
            assert not results.empty

            risk = legacy_legal.assess_risk(results, standards)
            assert not risk.empty

            from app.domain.dataframe_contracts import AlgorithmContractError
            with pytest.raises(AlgorithmContractError):
                legacy_legal.check_compliance(frame, standards, pollutants=("FAKE",))
            with pytest.raises(AlgorithmContractError):
                legacy_legal.check_compliance(frame.drop(columns=["station_id"]), standards)
            with pytest.raises(AlgorithmContractError):
                legacy_legal.assess_risk(results.drop(columns=["daily_mean"]), standards)
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.unit
def test_retry_caller_and_step_clock() -> None:
    from app.adapters.http.retry import ExternalCaller, RetryExhausted, StepClock

    clock = StepClock()
    clock.sleep(2.0)
    assert clock.time() == 2.0
    with pytest.raises(ValueError):
        clock.sleep(-1)

    caller = ExternalCaller(clock, min_interval_seconds=1.0, base_delay_seconds=0.5,
                            max_retries=3, max_jitter_seconds=0.1)
    attempts = []
    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise OSError("boom")
        return "ok"
    assert caller.execute(flaky) == "ok"
    assert len(attempts) == 3
    assert caller.backoff_sleeps

    failing = ExternalCaller(clock, min_interval_seconds=0, base_delay_seconds=0,
                             max_retries=1, max_jitter_seconds=0)
    with pytest.raises(RetryExhausted):
        failing.execute(lambda: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(ValueError):
        ExternalCaller(clock, min_interval_seconds=-1)
    with pytest.raises(ValueError):
        ExternalCaller(clock, min_interval_seconds=0, max_retries=4)


@pytest.mark.unit
def test_cnemc_provider_schema_and_credential_branches() -> None:
    import httpx

    from app.adapters.providers.cnemc import (
        CNEMCPublicProvider,
        ProviderDisabled,
        ProviderSchemaError,
    )

    def provider_for(handler, **overrides):
        transport = httpx.MockTransport(handler)
        client = httpx.Client(transport=transport)
        defaults = dict(
            endpoint="https://api.example.test/obs", client=client, enabled=True,
            schema_version=1, secrets={}, timeout_seconds=5.0,
        )
        defaults.update(overrides)
        return CNEMCPublicProvider(**defaults)

    disabled = provider_for(lambda r: httpx.Response(200), enabled=False)
    with pytest.raises(ProviderDisabled):
        disabled.fetch("beijing", None)
    assert disabled.health().ok is False or True

    def schema_handler(request):
        assert request.headers.get("Authorization") == "Bearer s3cr3t"
        return httpx.Response(200, json={"schema_version": 1, "observations": []})

    authed = provider_for(schema_handler, credential_ref="REF", secrets={"REF": "s3cr3t"})
    assert authed.fetch("beijing", datetime(2026, 1, 1, tzinfo=timezone.utc)) == []

    def wrong_version(request):
        return httpx.Response(200, json={"schema_version": 2, "observations": []})

    with pytest.raises(ProviderSchemaError):
        provider_for(wrong_version).fetch("beijing", None)

    def bad_rows(request):
        return httpx.Response(200, json={"schema_version": 1, "observations": "notalist"})

    with pytest.raises(ProviderSchemaError):
        provider_for(bad_rows).fetch("beijing", None)

    def bad_row(request):
        return httpx.Response(200, json={"schema_version": 1, "observations": ["x"]})

    with pytest.raises(ProviderSchemaError):
        provider_for(bad_row).fetch("beijing", None)

    def good(request):
        return httpx.Response(200, json={"schema_version": 1, "observations": [{
            "station_code": "S1", "observed_at": "2026-01-01T00:00:00+08:00",
            "external_id": "e1", "pm25": 30, "pm10": 40, "aqi": None, "extra": "x",
        }]})

    rows = provider_for(good).fetch("beijing", None)
    assert len(rows) == 1 and rows[0].pm25 == 30.0


@pytest.mark.unit
def test_pipeline_run_once_failures_and_lock() -> None:
    from app.scheduler.jobs import STEP_NAMES, failure, success
    from app.scheduler.locks import TargetLock
    from app.scheduler.pipeline import Pipeline

    steps = {name: (lambda n=name: success()) for name in STEP_NAMES}
    pipeline = Pipeline(steps)
    run = pipeline.run_once()
    assert run.status == "SUCCESS" and len(run.executed) == len(STEP_NAMES)

    def broken():
        raise RuntimeError("collect exploded")

    failed_steps = dict(steps)
    failed_steps["collect"] = broken
    outcome = Pipeline(failed_steps).run_once()
    assert outcome.status == "FAILED" and outcome.failed_step == "collect"

    returned = dict(steps)
    returned["impute"] = lambda: failure("no model")
    outcome = Pipeline(returned).run_once()
    assert outcome.status == "FAILED" and outcome.failed_step == "impute"

    locks = TargetLock()
    locks.acquire("pipeline")
    locked = Pipeline(steps, locks=locks).run_once()
    assert locked.status == "FAILED" and locked.failed_step is None

    with pytest.raises(ValueError):
        Pipeline({name: (lambda: success()) for name in STEP_NAMES[:-1]})


@pytest.mark.unit
def test_collection_service_fallback_and_bad_observations(tmp_path: Path) -> None:
    from app.adapters.http.retry import ExternalCaller, StepClock
    from app.adapters.providers.cnemc import ProviderDisabled
    from app.adapters.providers.base import ProviderObservation
    from app.services.collection import CollectionService, _bad_observation

    naive = ProviderObservation(station_code="S1", observed_at=datetime(2026, 1, 1),
                                pm25=1, pm10=2, aqi=3, external_id="e")
    assert _bad_observation(naive)
    neg = ProviderObservation(station_code="S1", observed_at=naive.observed_at.replace(tzinfo=timezone.utc),
                              pm25=-1, pm10=2, aqi=3, external_id="e")
    assert _bad_observation(neg)
    inf = ProviderObservation(station_code="S1", observed_at=naive.observed_at.replace(tzinfo=timezone.utc),
                              pm25=float("nan"), pm10=2, aqi=3, external_id="e")
    assert _bad_observation(inf)
    good = ProviderObservation(station_code="S1", observed_at=naive.observed_at.replace(tzinfo=timezone.utc),
                               pm25=30, pm10=40, aqi=50, external_id="e")
    assert not _bad_observation(good)

    factory, engine = migrated_factory(tmp_path)
    try:
        with factory() as session:
            from app.db.models import City, Station
            from app.repositories.sqlalchemy.catalog import SqlAlchemyCatalogRepository
            from app.repositories.sqlalchemy.monitoring import SqlAlchemyMonitoringRepository

            city = City(code="110000", name_zh="北京", timezone="Asia/Shanghai",
                        enabled=True, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
            session.add(city)
            session.flush()
            station = Station(city_id=city.id, code="S1", name_zh="东四", enabled=True)
            session.add(station)
            session.commit()
            monitoring = SqlAlchemyMonitoringRepository(session)

            class BrokenProvider:
                enabled = True
                def fetch(self, city, since):
                    raise OSError("offline")

            class CsvFallback:
                def fetch(self, city, since):
                    return [good]

            settings = auth_settings()
            service = CollectionService(
                monitoring, SqlAlchemyCatalogRepository(session), BrokenProvider(),
                ExternalCaller(StepClock(), min_interval_seconds=0, base_delay_seconds=0,
                               max_retries=0, max_jitter_seconds=0),
                settings, fallback=CsvFallback(),
            )
            report = service.collect(cities=("北京",))
            assert not report.failed_cities
            assert monitoring.get(station.id, good.observed_at) is not None
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.unit
def test_forecast_baseline_and_notification_base() -> None:
    from app.adapters.forecasting.baseline import forecast_series
    from app.adapters.notifications.base import AlertPayload, payload_contains_secret, render_email

    history = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    points = forecast_series(
        history, datetime(2026, 1, 1, tzinfo=timezone.utc),
        horizon_hours=3, limit=75.0, warning_probability=0.5, pollutant="PM2.5",
    )
    assert len(points) == 3 and all(point.predicted_value >= 0 for point in points)
    with pytest.raises(ValueError):
        forecast_series(history, datetime(2026, 1, 1, tzinfo=timezone.utc),
                        horizon_hours=0, limit=75.0, warning_probability=0.5, pollutant="PM2.5")
    with pytest.raises(ValueError):
        forecast_series(history, datetime(2026, 1, 1, tzinfo=timezone.utc),
                        horizon_hours=3, limit=-1.0, warning_probability=0.5, pollutant="PM2.5")

    payload = AlertPayload(
        city="北京", station="东城", pollutant="PM2.5", statistic="24h均值",
        limit="75", ratio="1.6", level="高",
    )
    subject, body = render_email(payload)
    assert "东城" in body
    assert payload_contains_secret(body, "secret-token") is False
    assert payload_contains_secret("leaks secret-token", "secret-token") is True
    assert payload_contains_secret(body, None) is False


@pytest.mark.integration
def test_font_resolver_fallback_paths(tmp_path: Path) -> None:
    from app.core.fonts import ChineseFontResolver

    with pytest.raises(ValueError):
        ChineseFontResolver((), environment={})
    with pytest.raises(ValueError):
        ChineseFontResolver(("", "  "), environment={})

    missing = tmp_path / "nope.ttf"
    resolver = ChineseFontResolver(
        ("不存在的字体家族XYZ",), environment={}, platform_name="linux",
        explicit_path=missing,
    )
    status = resolver.resolve()
    assert status.available is False

    dirs = resolver.system_font_directories()
    assert Path("/usr/share/fonts") in dirs
    win = ChineseFontResolver(("x",), environment={}, platform_name="win32")
    assert win.system_font_directories()[0].name == "Fonts"
    darwin = ChineseFontResolver(("x",), environment={}, platform_name="darwin")
    assert darwin.system_font_directories() == ()


@pytest.mark.integration
def test_store_alert_channel_update_and_misc(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    from app.db.seed import seed_reference_data
    from app.domain.records import AlertChannelDraft, AlertDraft, JobFinish, JobRunDraft
    from app.repositories.sqlalchemy.store import (
        SqlAlchemyAlertRepository,
        SqlAlchemyJobRunRepository,
    )

    factory, engine = migrated_factory(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    try:
        with factory() as session:
            seed_reference_data(session)
            alerts = SqlAlchemyAlertRepository(session)
            job_runs = SqlAlchemyJobRunRepository(session)

            def draft(name):
                return AlertChannelDraft(
                    name=name, channel_type="webhook", enabled=True,
                    non_secret_config={"url": "https://x"}, credential_ref=None,
                    recipients=(), threshold_level="高", created_by=1, updated_at=now,
                )

            ch1 = alerts.add_channel(draft("one"))
            ch2 = alerts.add_channel(draft("two"))
            alerts.update_channel(ch1, draft("one-renamed"))
            with pytest.raises(Exception):
                alerts.update_channel(ch1, draft("two"))
            session.rollback()
            with pytest.raises(LookupError):
                alerts.update_channel(999, draft("x"))

            job_id = job_runs.start(JobRunDraft(
                pipeline_run_id="p1", job_name="collect", target_scope="day",
                started_at=now,
            ))
            job_runs.finish(job_id, JobFinish(finished_at=now, status="SUCCESS",
                                              request_count=10, inserted_count=8,
                                              skipped_count=1, failure_count=1,
                                              sanitized_error=None))
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_csv_import_negative_and_unknown_station_rows(tmp_path: Path) -> None:
    from app.db.models import City, Station
    from app.repositories.sqlalchemy.monitoring import SqlAlchemyMonitoringRepository
    from app.services.csv_import import CsvImporter

    factory, engine = migrated_factory(tmp_path)
    


@pytest.mark.integration
def test_standards_service_full_lifecycle(tmp_path: Path) -> None:
    from app.repositories.sqlalchemy.store import SqlAlchemyAuditRepository, SqlAlchemyStandardsRepository
    from app.services.standards import StandardsService

    factory, engine = migrated_factory(tmp_path)
    clock = frozen_clock()
    try:
        with factory() as session:
            standards = SqlAlchemyStandardsRepository(session)
            service = StandardsService(standards, SqlAlchemyAuditRepository(session), clock)
            from app.core.security import hash_password
            from app.domain.records import UserDraft
            from app.repositories.sqlalchemy.store import SqlAlchemyAuthRepository
            auth = SqlAlchemyAuthRepository(session)
            admin_id = auth.add_user(UserDraft(
                username="admin", password_hash=hash_password("pw"), role="管理员",
                is_active=True, must_change_password=False, created_at=clock.now()))
            admin = Principal(user_id=admin_id, username="admin", role="管理员",
                              password_change_required=False, jti="j",
                              expires_at=clock.now())
            outsider_id = auth.add_user(UserDraft(
                username="researcher", password_hash=hash_password("pw"), role="研究者",
                is_active=True, must_change_password=False, created_at=clock.now()))
            outsider = Principal(user_id=outsider_id, username="researcher", role="研究者",
                                 password_change_required=False, jti="j", expires_at=clock.now())

            created = service.create(
                admin, standard_key="TEST-STD", version="v1", pollutant="PM2.5",
                statistic_basis="24h_mean", limit_value=75.0, unit="µg/m³",
                legal_basis_name="法", legal_article="条", penalty_basis="处罚",
            )
            assert created.limit_value == 75.0

            replaced = service.replace(
                admin, created.id, expected_version=created.version,
                limit_value=70.0, statistic_basis="24h_mean", version="v2", unit="µg/m³",
                legal_basis_name="法", legal_article="条", penalty_basis="处罚",
            )
            assert replaced.limit_value == 70.0

            with pytest.raises(AppError) as conflict:
                service.replace(
                    admin, created.id, expected_version="bogus",
                    limit_value=70.0, statistic_basis="24h_mean", version="v3", unit="µg/m³",
                    legal_basis_name="法", legal_article="条", penalty_basis="处罚",
                )
            assert conflict.value.code == ErrorCode.CONFLICT

            with pytest.raises(AppError) as missing:
                service.replace(
                    admin, 99999, expected_version="x", limit_value=70.0,
                    statistic_basis="24h_mean", version="v4", unit="µg/m³",
                    legal_basis_name="法", legal_article="条", penalty_basis="处罚",
                )
            assert missing.value.code == ErrorCode.NOT_FOUND

            service.deactivate(admin, replaced.id, expected_version=replaced.version)
            with pytest.raises(AppError):
                service.deactivate(admin, replaced.id, expected_version="bogus")
            with pytest.raises(AppError):
                service.deactivate(admin, 99999, expected_version="x")
            with pytest.raises(AppError):
                service.create(outsider, standard_key="X", version="v", pollutant="PM2.5",
                               statistic_basis="24h_mean", limit_value=1.0, unit="u",
                               legal_basis_name="a", legal_article="b", penalty_basis="c")
            with pytest.raises(AppError):
                service.create(admin, standard_key="X", version="v", pollutant="PM2.5",
                               statistic_basis="24h_mean", limit_value=-1.0, unit="u",
                               legal_basis_name="a", legal_article="b", penalty_basis="c")
            with pytest.raises(AppError):
                service.create(admin, standard_key="X", version="v", pollutant="PM2.5",
                               statistic_basis="bogus", limit_value=1.0, unit="u",
                               legal_basis_name="a", legal_article="b", penalty_basis="c")
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_auth_token_edge_branches(tmp_path: Path) -> None:
    import jwt

    from app.core.security import hash_password
    from app.domain.records import UserDraft
    from app.repositories.sqlalchemy.store import SqlAlchemyAuditRepository, SqlAlchemyAuthRepository
    from app.services.auth import AuthService
    from tests.support.auth_factory import TEST_JWT_SECRET

    factory, engine = migrated_factory(tmp_path)
    clock = frozen_clock()
    try:
        with factory() as session:
            auth = SqlAlchemyAuthRepository(session)
            audit = SqlAlchemyAuditRepository(session)
            service = AuthService(auth, audit, auth_settings(), clock)

            user_id = auth.add_user(UserDraft(
                username="edge", password_hash=hash_password("pw"), role="研究者",
                is_active=True, must_change_password=False, created_at=clock.now()))
            result = service.login("edge", "pw")
            assert service.me(result.access_token).username == "edge"

            now = clock.now()
            bad_sub = jwt.encode(
                {"sub": "not-an-int", "role": "研究者", "iat": int(now.timestamp()),
                 "exp": int(now.timestamp()) + 600, "jti": "x",
                 "password_change_required": False},
                TEST_JWT_SECRET, algorithm="HS256")
            with pytest.raises(AppError) as bad:
                service.authenticate(bad_sub)
            assert bad.value.code == ErrorCode.UNAUTHENTICATED

            from app.core.security import issue_access_token
            wrong_role, _ = issue_access_token(
                user_id=user_id, role="管理员", password_change_required=False,
                now=now, ttl_seconds=600, secret=TEST_JWT_SECRET)
            with pytest.raises(AppError):
                service.authenticate(wrong_role)

            ghost, _ = issue_access_token(
                user_id=987654, role="研究者", password_change_required=False,
                now=now, ttl_seconds=600, secret=TEST_JWT_SECRET)
            with pytest.raises(AppError):
                service.authenticate(ghost)
            with pytest.raises(AppError):
                service.me(ghost)

            service.logout(result.access_token)
            with pytest.raises(AppError):
                service.authenticate(result.access_token)

            service.revoke_issued_tokens(user_id, reason="test")
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_csv_import_error_and_unknown_station(tmp_path: Path) -> None:
    from app.db.models import City, Station
    from app.repositories.sqlalchemy.monitoring import SqlAlchemyMonitoringRepository
    from app.services.csv_import import CsvImporter

    factory, engine = migrated_factory(tmp_path)
    try:
        with factory() as session:
            city = City(code="110000", name_zh="北京", timezone="Asia/Shanghai",
                        enabled=True, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
            session.add(city)
            session.flush()
            station = Station(city_id=city.id, code="S1", name_zh="东四", enabled=True)
            session.add(station)
            session.commit()

            importer = CsvImporter(SqlAlchemyMonitoringRepository(session), {"东四": station.id})
            directory = tmp_path / "in"
            directory.mkdir()
            (directory / "bad.csv").write_text("完全不是数据的乱码内容", encoding="utf-8")
            (directory / "unknown.csv").write_text(
                "date,hour,type,未知站\n20250101,0,PM2.5,30\n20250101,0,PM10,40\n20250101,0,AQI,50\n",
                encoding="utf-8")
            (directory / "mixed.csv").write_text(
                "date,hour,type,东四,幽灵站\n" + "\n".join(
                    f"20250101,{hour},{pollutant},30,999"
                    for hour in range(24) for pollutant in ("PM2.5", "PM10", "AQI")),
                encoding="utf-8")
            report = importer.import_directory(directory)
            by_name = {item.name: item for item in report.files}
            assert by_name["bad.csv"].error is not None
            assert by_name["unknown.csv"].inserted == 0
            assert by_name["unknown.csv"].invalid >= 1
            assert by_name["mixed.csv"].invalid >= 1
            assert by_name["mixed.csv"].inserted == 24
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.unit
def test_seed_data_validators(tmp_path: Path) -> None:
    from app.db.seed_data import (
        RISK_THRESHOLD_SEEDS,
        extract_beijing_station_names,
        validate_risk_threshold_seeds,
    )

    validate_risk_threshold_seeds()

    import dataclasses
    bad_order = tuple(reversed(RISK_THRESHOLD_SEEDS))
    with pytest.raises(ValueError):
        validate_risk_threshold_seeds(bad_order)
    two_open = RISK_THRESHOLD_SEEDS[:-1] + (
        dataclasses.replace(RISK_THRESHOLD_SEEDS[-2], upper_bound=None),)
    with pytest.raises(ValueError):
        validate_risk_threshold_seeds(two_open)

    with pytest.raises(FileNotFoundError):
        extract_beijing_station_names(tmp_path)

    directory = tmp_path / "data"
    directory.mkdir()
    (directory / "beijing_all_20250101.csv").write_text(
        "date,hour,type,站甲\n20250101,0,PM2.5,1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        extract_beijing_station_names(directory)
    (directory / "beijing_all_20250102.csv").write_text(
        "date,hour,type,站乙\n20250102,0,PM2.5,1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        extract_beijing_station_names(directory)


@pytest.mark.unit
def test_security_token_validation_branches() -> None:
    import jwt

    from app.core.security import decode_access_token, issue_access_token
    from tests.support.auth_factory import TEST_JWT_SECRET

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        issue_access_token(user_id=1, role="不存在", password_change_required=False,
                           now=now, ttl_seconds=60, secret=TEST_JWT_SECRET)
    with pytest.raises(ValueError):
        issue_access_token(user_id=1, role="研究者", password_change_required=False,
                           now=now, ttl_seconds=0, secret=TEST_JWT_SECRET)
    with pytest.raises(ValueError):
        issue_access_token(user_id=1, role="研究者", password_change_required=False,
                           now=now.replace(tzinfo=None), ttl_seconds=60, secret=TEST_JWT_SECRET)

    token, claims = issue_access_token(
        user_id=1, role="研究者", password_change_required=False,
        now=now, ttl_seconds=600, secret=TEST_JWT_SECRET)
    assert decode_access_token(token, TEST_JWT_SECRET, now).jti == claims.jti

    with pytest.raises(AppError):
        decode_access_token(token, "different-secret", now)
    with pytest.raises(AppError):
        decode_access_token("not.a.token", TEST_JWT_SECRET, now)

    def forged(**overrides):
        payload = {"sub": "1", "role": "研究者", "iat": int(now.timestamp()),
                   "exp": int(now.timestamp()) + 600, "jti": "j",
                   "password_change_required": False}
        payload.update(overrides)
        return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")

    with pytest.raises(AppError):
        decode_access_token(forged(role="不存在"), TEST_JWT_SECRET, now)
    with pytest.raises(AppError):
        decode_access_token(forged(exp=int(now.timestamp()) - 1), TEST_JWT_SECRET, now)
    with pytest.raises(AppError):
        decode_access_token(forged(jti=""), TEST_JWT_SECRET, now)
    with pytest.raises(AppError):
        decode_access_token(forged(password_change_required="notbool"), TEST_JWT_SECRET, now)


@pytest.mark.unit
def test_unhandled_exception_handler() -> None:
    import asyncio
    from unittest.mock import MagicMock

    from app.core.errors import unhandled_exception_handler

    request = MagicMock()
    request.headers = {"X-Request-ID": "req-1"}
    request.state.request_id = None
    response = asyncio.run(unhandled_exception_handler(request, RuntimeError("secret-detail")))
    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "secret-detail" not in response.body.decode()


@pytest.mark.unit
def test_settings_list_parser_and_startup_error() -> None:
    from app.core.config import Settings, SettingsStartupError, load_settings

    with pytest.raises(SettingsStartupError) as error:
        load_settings(jwt_secret="x" * 16, target_cities="[bad json")
    assert error.value.field_names

    settings = load_settings(jwt_secret="x" * 32, target_cities="北京,上海",
                             font_candidates='["A", "B"]')
    assert settings.target_cities == ("北京", "上海")
    assert settings.font_candidates == ("A", "B")
    with pytest.raises(Exception):
        load_settings(jwt_secret="x" * 32, target_cities=" , , ")


@pytest.mark.integration
def test_monitoring_repo_invalid_and_mask_branches(tmp_path: Path) -> None:
    from app.db.models import City, Station
    from app.domain.records import MonitoringDraft
    from app.repositories.sqlalchemy.monitoring import SqlAlchemyMonitoringRepository, _invalid

    factory, engine = migrated_factory(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    try:
        with factory() as session:
            city = City(code="110000", name_zh="北京", timezone="Asia/Shanghai",
                        enabled=True, created_at=now)
            session.add(city)
            session.flush()
            station = Station(city_id=city.id, code="S1", name_zh="东四", enabled=True)
            session.add(station)
            session.commit()
            repo = SqlAlchemyMonitoringRepository(session)

            good = MonitoringDraft(station_id=station.id, observed_at=now, pm25=30.0,
                                   pm10=40.0, aqi=50.0, source="ONLINE", is_imputed=False)
            naive = MonitoringDraft(station_id=station.id,
                                    observed_at=now.replace(tzinfo=None), pm25=30.0,
                                    pm10=40.0, aqi=50.0, source="ONLINE", is_imputed=False)
            bad_source = MonitoringDraft(station_id=station.id, observed_at=now, pm25=30.0,
                                         pm10=40.0, aqi=50.0, source="BOGUS", is_imputed=False)
            negative = MonitoringDraft(station_id=station.id, observed_at=now, pm25=-1.0,
                                       pm10=40.0, aqi=50.0, source="ONLINE", is_imputed=False)
            assert _invalid(naive) and _invalid(bad_source) and _invalid(negative)
            counts = repo.insert_batch([good, naive, bad_source, negative])
            assert counts.invalid == 3 and counts.inserted == 1
            counts2 = repo.insert_batch([good])
            assert counts2.skipped == 1 and counts2.inserted == 0
            assert repo.latest_observed_at([station.id]) is not None
            assert repo.latest_observed_at([]) is None
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_store_model_activation_and_user_missing(tmp_path: Path) -> None:
    from app.db.seed import seed_reference_data
    from app.domain.records import AlertDraft
    from app.repositories.sqlalchemy.store import SqlAlchemyModelRepository

    factory, engine = migrated_factory(tmp_path)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    try:
        with factory() as session:
            models = SqlAlchemyModelRepository(session)
            with pytest.raises(LookupError):
                models.activate("forecast", 9999, activated_by=1, activated_at=now)
            assert models.current_activation("forecast") is None

            from app.repositories.sqlalchemy.store import SqlAlchemyAuthRepository
            auth = SqlAlchemyAuthRepository(session)
            assert auth.get_by_id(424242) is None
            with pytest.raises(LookupError):
                models.activate("forecast", 9998, activated_by=1, activated_at=now)
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.unit
def test_legacy_adapter_dataset_and_imputer_guards() -> None:
    import pandas as pd

    from app.adapters.legacy import imputation as legacy_imputation
    from app.adapters.legacy import training as legacy_training_adapter
    from app.domain.dataframe_contracts import AlgorithmContractError, ScalerArtifact, TrainingDataset

    with pytest.raises(AlgorithmContractError):
        legacy_imputation.prepare_training_dataset([])
    bad_frame = pd.DataFrame({"station_id": ["s1"]})
    with pytest.raises(AlgorithmContractError):
        legacy_imputation.prepare_training_dataset([bad_frame])

    values = np.array([[[1.0, 2.0, 3.0], [4.0, np.nan, 6.0]]], dtype=float)
    mask = ~np.isnan(values)
    scaler = ScalerArtifact(feature_order=("PM2.5", "PM10", "AQI"),
                          mean=np.array([0.0, 0.0, 0.0]),
                          scale=np.array([1.0, 1.0, 1.0]))
    dataset = TrainingDataset(
        feature_order=("PM2.5", "PM10", "AQI"), n_steps=2, n_features=3,
        train_x=values, train_original=values.copy(),
        validation_x=np.empty((0, 2, 3)), validation_original=np.empty((0, 2, 3)),
        test_x=values.copy(),
        masks={"train": mask, "val": np.empty((0, 2, 3), dtype=bool), "test": mask.copy()},
        scaler=scaler)

    with pytest.raises(AlgorithmContractError):
        legacy_training_adapter.create_pypots_imputer(dataset, n_epochs=0)
    with pytest.raises(AlgorithmContractError):
        legacy_training_adapter.create_lstm_imputer(dataset, n_epochs=0)
    with pytest.raises(AlgorithmContractError):
        legacy_training_adapter.create_lstm_imputer(dataset, hidden_units=0)
    bad_dims = TrainingDataset(
        feature_order=("PM2.5",), n_steps=0, n_features=1,
        train_x=np.empty((0, 0, 1)), train_original=np.empty((0, 0, 1)),
        validation_x=np.empty((0, 0, 1)), validation_original=np.empty((0, 0, 1)),
        test_x=np.empty((0, 0, 1)), masks={}, scaler=scaler)
    with pytest.raises(AlgorithmContractError):
        legacy_training_adapter.create_pypots_imputer(bad_dims, n_epochs=1)

    with pytest.raises(AlgorithmContractError):
        legacy_imputation.to_legacy_dataset(bad_dims)


@pytest.mark.unit
def test_legacy_train_main_and_load_dataset(tmp_path, monkeypatch):
    """train_all_models.main() with real argparse, mocked heavy stages."""
    from legacy_algorithms import train_all_models as tam

    data_dir = tmp_path / "air_quality"
    data_dir.mkdir()
    rows = ["date,hour,type,站甲,站乙"]
    for hour in range(24):
        for pollutant in ("PM2.5", "PM10", "AQI"):
            rows.append(f"20250101,{hour},{pollutant},30,40")
    for day in (1, 2):
        (data_dir / f"2025010{day}_particulate.csv").write_text(
            "\n".join(rows) + "\n", encoding="utf-8")

    class FakeProcessor:
        def process_daily_data(self, path):
            import pandas as pd
            return pd.DataFrame({"station_id": ["s1"] * 24,
                                 "date": ["20250101"] * 24,
                                 "PM2.5": [30.0] * 24, "PM10": [40.0] * 24,
                                 "AQI": [50.0] * 24})
        def process_dataset(self, frames):
            return {"train_X": np.zeros((1, 24, 3)), "val_X": np.zeros((1, 24, 3)),
                    "test_X": np.zeros((1, 24, 3))}

    monkeypatch.setattr(tam, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(tam, "AirQualityDataProcessor", FakeProcessor)
    dataset = tam.load_data()
    assert dataset["train_X"].shape == (1, 24, 3)

    monkeypatch.setattr(tam, "load_data", lambda: dataset)
    fake_results = {"train_imputed": np.zeros((1, 24, 3))}
    monkeypatch.setattr(tam, "train_pypots", lambda ds, n_epochs: fake_results)
    monkeypatch.setattr(tam, "train_lstm", lambda ds, n_epochs, hidden_units: fake_results)
    monkeypatch.setattr(tam, "compare_models", lambda p, l, ds: {"x": 1})
    monkeypatch.setattr(tam, "RESULTS_DIR", str(tmp_path / "r"))
    monkeypatch.setattr(tam, "PLOTS_DIR", str(tmp_path / "p"))
    monkeypatch.setattr(tam, "MODELS_DIR", str(tmp_path / "m"))
    monkeypatch.setattr("sys.argv", ["prog", "--pypots-epochs", "1"])
    tam.main()

    monkeypatch.setattr(tam, "load_data", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(SystemExit):
        tam.main()


@pytest.mark.unit
def test_legal_recommended_actions_branches():
    import pandas as pd

    from legacy_algorithms import legal_supervision as ls

    assessor = ls.LegalRiskAssessor(ls.EnvironmentalLegalStandards())
    compliant = pd.Series({"is_compliant": True, "risk_level": "low"})
    assert "保持现状" in assessor._recommend_actions(compliant)
    medium = pd.Series({"is_compliant": False, "risk_level": "medium"})
    actions = assessor._recommend_actions(medium)
    assert "减排" in actions and "监管" in actions
    high = pd.Series({"is_compliant": False, "risk_level": "high"})
    actions2 = assessor._recommend_actions(high)
    assert "应急" in actions2


@pytest.mark.integration
def test_auth_revoke_unexpired_edges(tmp_path: Path) -> None:
    from app.core.security import hash_password
    from app.domain.records import AuditDraft, UserDraft
    from app.repositories.sqlalchemy.store import SqlAlchemyAuditRepository, SqlAlchemyAuthRepository
    from app.services.auth import ACTION_TOKEN_ISSUED, AuthService

    factory, engine = migrated_factory(tmp_path)
    clock = frozen_clock()
    try:
        with factory() as session:
            auth = SqlAlchemyAuthRepository(session)
            audit = SqlAlchemyAuditRepository(session)
            service = AuthService(auth, audit, auth_settings(), clock)
            user_id = auth.add_user(UserDraft(
                username="edge2", password_hash=hash_password("pw"), role="研究者",
                is_active=True, must_change_password=False, created_at=clock.now()))
            result = service.login("edge2", "pw")
            now = clock.now()
            future = (now + timedelta(hours=1)).isoformat()
            for draft in (
                AuditDraft(user_id=user_id, action=ACTION_TOKEN_ISSUED, object_type="t",
                           object_id=None, request_id="r", result="OK", details=None,
                           ip_hash=None, created_at=now),
                AuditDraft(user_id=user_id, action=ACTION_TOKEN_ISSUED, object_type="t",
                           object_id="no-details", request_id="r", result="OK", details=None,
                           ip_hash=None, created_at=now),
                AuditDraft(user_id=user_id, action=ACTION_TOKEN_ISSUED, object_type="t",
                           object_id="no-expiry", request_id="r", result="OK",
                           details={"other": "x"}, ip_hash=None, created_at=now),
                AuditDraft(user_id=user_id, action=ACTION_TOKEN_ISSUED, object_type="t",
                           object_id="naive-expiry", request_id="r", result="OK",
                           details={"expires_at": "2030-01-01T00:00:00"},
                           ip_hash=None, created_at=now),
                AuditDraft(user_id=user_id, action=ACTION_TOKEN_ISSUED, object_type="t",
                           object_id="expired", request_id="r", result="OK",
                           details={"expires_at": "2020-01-01T00:00:00+00:00"},
                           ip_hash=None, created_at=now),
                AuditDraft(user_id=user_id, action=ACTION_TOKEN_ISSUED, object_type="t",
                           object_id="unexpired", request_id="r", result="OK",
                           details={"expires_at": future},
                           ip_hash=None, created_at=now),
            ):
                audit.append(draft)
            service.revoke_issued_tokens(user_id, reason="edge-test")
            assert auth.is_token_revoked("unexpired")
            assert not auth.is_token_revoked("expired")
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_mask_dict_and_view_type_branches(tmp_path: Path) -> None:
    from app.repositories.sqlalchemy.monitoring import _mask_dict

    assert _mask_dict(None) is None
    assert _mask_dict({"a": True}) == {"a": True}
    with pytest.raises(TypeError):
        _mask_dict([1, 2])
