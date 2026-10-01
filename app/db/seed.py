"""Idempotent reference seed for Beijing stations, standards, and the first admin."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import City, LegalStandard, RiskThreshold, Station, User
from app.db.seed_data import (
    BEIJING_CITY_NAME,
    BEIJING_TIMEZONE,
    INITIAL_ADMIN_ROLE,
    INITIAL_ADMIN_USERNAME,
    LEGAL_EFFECTIVE_FROM,
    LEGAL_STANDARD_SEEDS,
    RISK_THRESHOLD_SEEDS,
    LegalStandardSeed,
    RiskThresholdSeed,
    beijing_city_code,
    default_wide_table_directory,
    extract_beijing_station_names,
    validate_risk_threshold_seeds,
)
from app.db.types import utc_now

_HASHER = PasswordHasher()


@dataclass(frozen=True)
class SeedResult:
    """Outcome of one seed call. A generated password is returned only once."""

    city_code: str
    station_count: int
    admin_username: str
    generated_admin_password: str | None


def hash_password(password: str) -> str:
    """Return an Argon2id hash. The plaintext is not retained."""

    if password == "":
        raise ValueError("password must not be empty")
    return _HASHER.hash(password)


def seed_reference_data(
    session: Session,
    *,
    admin_username: str = INITIAL_ADMIN_USERNAME,
    admin_password: str | None = None,
    data_directory: Path | None = None,
) -> SeedResult:
    """Insert missing reference rows. Existing stable keys are left unchanged."""

    validate_risk_threshold_seeds()
    directory = data_directory or default_wide_table_directory()
    city_code = beijing_city_code(directory)
    station_names = extract_beijing_station_names(directory)
    city = _city(session, city_code)
    for name in station_names:
        _station(session, city, name)
    generated_password: str | None = None
    existing_admin = session.scalar(select(User).where(User.username == admin_username))
    if existing_admin is None:
        password = admin_password if admin_password is not None else secrets.token_urlsafe(24)
        if admin_password is None:
            generated_password = password
        _admin(session, admin_username, password)
        admin = session.scalar(select(User).where(User.username == admin_username))
    else:
        admin = existing_admin
    if admin is None:
        raise RuntimeError("initial admin row was not created")
    for standard in LEGAL_STANDARD_SEEDS:
        _standard(session, standard, admin.id)
    for threshold in RISK_THRESHOLD_SEEDS:
        _threshold(session, threshold, admin.id)
    session.flush()
    station_count = len(
        session.scalars(select(Station).where(Station.city_id == city.id)).all()
    )
    return SeedResult(
        city_code=city_code,
        station_count=station_count,
        admin_username=admin_username,
        generated_admin_password=generated_password,
    )


def _city(session: Session, code: str) -> City:
    city = session.scalar(select(City).where(City.code == code))
    if city is not None:
        return city
    city = City(
        code=code,
        name_zh=BEIJING_CITY_NAME,
        timezone=BEIJING_TIMEZONE,
        enabled=True,
        created_at=utc_now(),
    )
    session.add(city)
    session.flush()
    return city


def _station(session: Session, city: City, name: str) -> None:
    existing = session.scalar(
        select(Station).where(Station.city_id == city.id, Station.code == name)
    )
    if existing is not None:
        return
    session.add(
        Station(
            city_id=city.id,
            code=name,
            name_zh=name,
            latitude=None,
            longitude=None,
            enabled=True,
            provider_metadata={
                "wide_table_column": name,
                "source_file_pattern": "beijing_all_*.csv",
            },
        )
    )
    session.flush()


def _admin(session: Session, username: str, password: str) -> None:
    now = utc_now()
    session.add(
        User(
            username=username,
            password_hash=hash_password(password),
            role=INITIAL_ADMIN_ROLE,
            is_active=True,
            must_change_password=True,
            failed_login_count=0,
            last_failed_at=None,
            locked_until=None,
            password_changed_at=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()


def _standard(session: Session, seed: LegalStandardSeed, created_by: int) -> None:
    existing = session.scalar(
        select(LegalStandard).where(
            LegalStandard.standard_key == seed.standard_key,
            LegalStandard.version == seed.version,
        )
    )
    if existing is not None:
        return
    session.add(
        LegalStandard(
            standard_key=seed.standard_key,
            version=seed.version,
            pollutant=seed.pollutant,
            statistic_basis=seed.statistic_basis,
            limit_value=seed.limit_value,
            unit=seed.unit,
            legal_basis_name=seed.legal_basis_name,
            legal_article=seed.legal_article,
            penalty_basis=seed.penalty_basis,
            effective_from=LEGAL_EFFECTIVE_FROM,
            effective_to=None,
            is_active=True,
            supersedes_id=None,
            created_by=created_by,
            created_at=utc_now(),
        )
    )
    session.flush()


def _threshold(session: Session, seed: RiskThresholdSeed, created_by: int) -> None:
    existing = session.scalar(
        select(RiskThreshold).where(
            RiskThreshold.version == seed.version,
            RiskThreshold.level == seed.level,
        )
    )
    if existing is not None:
        return
    session.add(
        RiskThreshold(
            version=seed.version,
            level=seed.level,
            upper_bound=seed.upper_bound,
            description_zh=seed.description_zh,
            is_active=True,
            effective_from=LEGAL_EFFECTIVE_FROM,
            created_by=created_by,
        )
    )
    session.flush()
