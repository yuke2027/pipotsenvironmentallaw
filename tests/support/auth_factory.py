"""Shared builders for auth tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import FrozenClock
from app.core.config import Settings, load_settings
from app.db.session import create_engine_from_url, session_factory, sqlite_file_url
from app.db.upgrade import upgrade_database
from app.services.auth import AuthService
from tests.support.memory_auth import MemoryAuditRepository, MemoryAuthRepository

TEST_JWT_SECRET = "unit-test-jwt-secret-value"
_START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def auth_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "jwt_secret": TEST_JWT_SECRET,
        "login_max_failures": 5,
        "login_lock_seconds": 15 * 60,
        "jwt_expire_seconds": 8 * 60 * 60,
    }
    values.update(overrides)
    return load_settings(**values)


def frozen_clock() -> FrozenClock:
    return FrozenClock(_START)


def memory_service(
    *,
    settings: Settings | None = None,
    clock: FrozenClock | None = None,
) -> tuple[AuthService, MemoryAuthRepository, MemoryAuditRepository, FrozenClock]:
    auth = MemoryAuthRepository()
    audit = MemoryAuditRepository()
    current = clock if clock is not None else frozen_clock()
    service = AuthService(auth, audit, settings or auth_settings(), current)
    return service, auth, audit, current


def migrated_factory(tmp_path: Path) -> tuple[sessionmaker[Session], Engine]:
    url = sqlite_file_url(tmp_path / "auth.db")
    upgrade_database(url, backup_directory=tmp_path / "backups")
    engine = create_engine_from_url(url)
    return session_factory(engine), engine
