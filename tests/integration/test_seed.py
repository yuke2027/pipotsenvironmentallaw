"""Idempotent Beijing, standards, risk-threshold, and admin seed."""

from __future__ import annotations

from pathlib import Path

import pytest
from argon2 import PasswordHasher
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.db.models import Base, LegalStandard, RiskThreshold, Station, User
from app.db.seed import seed_reference_data
from app.db.seed_data import (
    EXPECTED_STATION_COUNT,
    LEGAL_STANDARD_SEEDS,
    RISK_THRESHOLD_SEEDS,
    default_wide_table_directory,
    extract_beijing_station_names,
)
from app.db.session import create_engine_from_url, session_factory, sqlite_file_url
from app.db.upgrade import upgrade_database

_PASSWORD = "TempAdmin#2026-initial"


def _counts(session: Session) -> dict[str, int]:
    totals: dict[str, int] = {}
    for table in Base.metadata.sorted_tables:
        value = session.scalar(select(func.count()).select_from(table))
        totals[table.name] = 0 if value is None else int(value)
    return totals


@pytest.mark.integration
def test_seed_matches_wide_table_and_is_idempotent(tmp_path: Path) -> None:
    url = sqlite_file_url(tmp_path / "seed.db")
    upgrade_database(url, backup_directory=tmp_path / "backups")
    engine = create_engine_from_url(url)
    try:
        factory = session_factory(engine)
        with factory() as session:
            first = seed_reference_data(session, admin_password=_PASSWORD)
            session.commit()
            original_counts = _counts(session)
            admin = session.scalar(select(User).where(User.username == "admin"))
            assert admin is not None
            original_hash = admin.password_hash

        assert first.city_code == "beijing"
        assert first.station_count == EXPECTED_STATION_COUNT
        assert first.generated_admin_password is None
        assert original_hash.startswith("$argon2id$")
        assert _PASSWORD not in original_hash
        PasswordHasher().verify(original_hash, _PASSWORD)

        with factory() as session:
            second = seed_reference_data(session, admin_password=_PASSWORD)
            session.commit()
            assert second.generated_admin_password is None
            assert _counts(session) == original_counts
            admin = session.scalar(select(User).where(User.username == "admin"))
            assert admin is not None
            assert admin.password_hash == original_hash
            assert admin.must_change_password is True
            assert admin.role == "管理员"
            columns = {column["name"] for column in inspect(engine).get_columns("users")}
            assert "password" not in columns
            assert "password_hash" in columns

            stored_names = tuple(session.scalars(select(Station.name_zh).order_by(Station.id)).all())
            assert stored_names == extract_beijing_station_names(default_wide_table_directory())
            assert len(stored_names) == 35
            assert all(station.latitude is None and station.longitude is None for station in session.scalars(select(Station)))

            for seed in LEGAL_STANDARD_SEEDS:
                row = session.scalar(
                    select(LegalStandard).where(
                        LegalStandard.standard_key == seed.standard_key,
                        LegalStandard.version == seed.version,
                    )
                )
                assert row is not None
                assert row.pollutant == seed.pollutant
                assert row.statistic_basis == seed.statistic_basis
                assert row.limit_value == seed.limit_value
                assert row.unit == seed.unit
                assert row.legal_basis_name == seed.legal_basis_name
                assert row.legal_article == seed.legal_article
                assert row.penalty_basis == seed.penalty_basis
                assert row.is_active is True
                assert row.created_by == admin.id

            thresholds = session.scalars(select(RiskThreshold).order_by(RiskThreshold.id)).all()
            assert [(row.level, row.upper_bound) for row in thresholds] == [
                (seed.level, seed.upper_bound) for seed in RISK_THRESHOLD_SEEDS
            ]
            finite = [row.upper_bound for row in thresholds if row.upper_bound is not None]
            assert finite == sorted(finite)
            assert len(finite) == len(set(finite))
            assert thresholds[-1].upper_bound is None
    finally:
        engine.dispose()


@pytest.mark.integration
def test_generated_admin_password_is_returned_once_and_only_hashed(tmp_path: Path) -> None:
    url = sqlite_file_url(tmp_path / "generated.db")
    upgrade_database(url, backup_directory=tmp_path / "backups")
    engine = create_engine_from_url(url)
    try:
        factory = session_factory(engine)
        with factory() as session:
            created = seed_reference_data(session, admin_password=None)
            session.commit()
        assert created.generated_admin_password
        with factory() as session:
            admin = session.scalar(select(User).where(User.username == created.admin_username))
            assert admin is not None
            assert admin.must_change_password is True
            assert created.generated_admin_password not in admin.password_hash
            PasswordHasher().verify(admin.password_hash, created.generated_admin_password)
        with factory() as session:
            repeated = seed_reference_data(session, admin_password=None)
            session.commit()
        assert repeated.generated_admin_password is None
    finally:
        engine.dispose()
