"""Task 16.1: startup upgrade and seed lifecycle through ``bootstrap``."""

from __future__ import annotations

from pathlib import Path

import pytest
from argon2 import PasswordHasher
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.core.config import Settings, load_settings
from app.db.models import Base, City, LegalStandard, RiskThreshold, Station, User
from app.db.seed_data import EXPECTED_STATION_COUNT, LEGAL_STANDARD_SEEDS, RISK_THRESHOLD_SEEDS
from app.db.session import sqlite_file_url
from app.db.upgrade import current_revision, upgrade_database
from app.runtime import AppContext, bootstrap

_PASSWORD = "LifecycleAdmin#2026"
_HEAD = "0002_baseline"


def _settings(tmp_path: Path) -> Settings:
    return load_settings(
        _env_file=None,
        jwt_secret="lifecycle-test-jwt-secret",
        database_url=sqlite_file_url(tmp_path / "lifecycle.db"),
        project_root=tmp_path,
        database_path=tmp_path / "lifecycle.db",
        local_config_dir=tmp_path / "config",
        model_dir=tmp_path / "models",
        export_dir=tmp_path / "exports",
    )


def _counts(session: Session) -> dict[str, int]:
    return {
        table.name: int(session.scalar(select(func.count()).select_from(table)) or 0)
        for table in Base.metadata.sorted_tables
    }


def _dispose(context: AppContext) -> None:
    context.engine.dispose()


@pytest.mark.integration
def test_first_start_creates_schema_seed_and_admin(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    context = bootstrap(settings, admin_password=_PASSWORD)
    try:
        inspector = inspect(context.engine)
        assert set(Base.metadata.tables) <= set(inspector.get_table_names())
        for table in Base.metadata.tables.values():
            assert {fk["referred_table"] for fk in inspector.get_foreign_keys(table.name)} == {
                fk.column.table.name for column in table.columns for fk in column.foreign_keys
            }
        assert current_revision(settings.database_url or "") == _HEAD

        with context.sessions() as session:
            assert session.scalar(select(func.count()).select_from(Station)) == EXPECTED_STATION_COUNT == 35
            assert session.scalar(select(City.code)) == "beijing"
            standards = session.scalars(select(LegalStandard)).all()
            assert {(item.standard_key, item.version) for item in standards} >= {
                (seed.standard_key, seed.version) for seed in LEGAL_STANDARD_SEEDS
            }
            assert [row.level for row in session.scalars(select(RiskThreshold).order_by(RiskThreshold.id))] == [
                seed.level for seed in RISK_THRESHOLD_SEEDS
            ]
            admin = session.scalar(select(User).where(User.username == "admin"))
            assert admin is not None
            assert admin.must_change_password is True
            assert admin.role == "管理员"
            assert _PASSWORD not in admin.password_hash
            PasswordHasher().verify(admin.password_hash, _PASSWORD)
        assert context.health()["database"] == "ok"
        assert context.scheduler is not None
    finally:
        _dispose(context)


@pytest.mark.integration
def test_restart_is_idempotent_and_makes_no_backup(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first = bootstrap(settings, admin_password=_PASSWORD)
    try:
        with first.sessions() as session:
            before = _counts(session)
            admin_hash = session.scalar(select(User.password_hash).where(User.username == "admin"))
    finally:
        _dispose(first)

    second = bootstrap(settings, admin_password="DifferentPassword#2026")
    try:
        with second.sessions() as session:
            assert _counts(session) == before
            assert session.scalar(select(User.password_hash).where(User.username == "admin")) == admin_hash
    finally:
        _dispose(second)
    backups = tmp_path / "config" / "backups"
    assert not backups.exists() or not list(backups.glob("*.db"))


@pytest.mark.integration
def test_start_on_previous_revision_backs_up_then_upgrades_and_seeds(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    url = settings.database_url or ""
    upgrade_database(url, backup_directory=tmp_path / "ignored", revision="0001_empty")
    assert current_revision(url) == "0001_empty"

    context = bootstrap(settings, admin_password=_PASSWORD)
    try:
        assert current_revision(url) == _HEAD
        backups = list((tmp_path / "config" / "backups").glob("*.db"))
        assert len(backups) == 1
        assert current_revision(sqlite_file_url(backups[0])) == "0001_empty"
        with context.sessions() as session:
            assert session.scalar(select(func.count()).select_from(Station)) == 35
    finally:
        _dispose(context)
