"""Login lockout, logout, and first-login route limits."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.api.dependencies.auth import access_protected
from app.core.errors import AppError
from app.core.security import hash_password
from app.domain.audit_actions import ACTION_CHANGE_PASSWORD, ACTION_LOGIN, ACTION_LOGOUT
from app.domain.permissions import Operation
from app.domain.records import UserDraft
from app.repositories.sqlalchemy.store import SqlAlchemyAuditRepository, SqlAlchemyAuthRepository
from app.services.auth import AuthService
from tests.support.auth_factory import auth_settings, frozen_clock, memory_service, migrated_factory


@pytest.mark.unit
def test_five_failures_lock_then_success_clears_the_counter() -> None:
    service, auth, _audit, clock = memory_service()
    auth.add_user(
        UserDraft(
            username="locked-user",
            password_hash=hash_password("right-password"),
            role="监管人员",
            is_active=True,
            must_change_password=False,
            created_at=clock.now(),
        )
    )
    for _ in range(4):
        with pytest.raises(AppError):
            service.login("locked-user", "wrong-password")
    assert auth.get_by_username("locked-user").locked_until is None  # type: ignore[union-attr]
    with pytest.raises(AppError):
        service.login("locked-user", "wrong-password")
    locked = auth.get_by_username("locked-user")
    assert locked is not None
    assert locked.failed_login_count == 5
    assert locked.locked_until == clock.now() + timedelta(seconds=15 * 60)
    with pytest.raises(AppError):
        service.login("locked-user", "right-password")
    clock.advance(15 * 60)
    result = service.login("locked-user", "right-password")
    cleared = auth.get_by_username("locked-user")
    assert cleared is not None
    assert cleared.failed_login_count == 0
    assert cleared.locked_until is None
    assert result.role == "监管人员"


@pytest.mark.unit
def test_inactive_user_and_unknown_user_share_the_credential_error() -> None:
    service, auth, _audit, clock = memory_service()
    auth.add_user(
        UserDraft(
            username="inactive-user",
            password_hash=hash_password("right-password"),
            role="研究者",
            is_active=False,
            must_change_password=False,
            created_at=clock.now(),
        )
    )
    with pytest.raises(AppError) as missing:
        service.login("missing-user", "right-password")
    with pytest.raises(AppError) as inactive:
        service.login("inactive-user", "right-password")
    assert missing.value.status_code == inactive.value.status_code == 401
    assert missing.value.code == inactive.value.code
    assert missing.value.message == inactive.value.message
    assert tuple(missing.value.details) == tuple(inactive.value.details)


@pytest.mark.unit
def test_first_login_token_can_only_reach_profile_password_and_logout() -> None:
    service, auth, audit, clock = memory_service()
    auth.add_user(
        UserDraft(
            username="first-user",
            password_hash=hash_password("temporary-password"),
            role="研究者",
            is_active=True,
            must_change_password=True,
            created_at=clock.now(),
        )
    )
    logged_in = service.login("first-user", "temporary-password")
    calls: list[str] = []

    def business(_payload: object) -> None:
        calls.append("called")

    with pytest.raises(AppError) as denied:
        access_protected(
            logged_in.access_token,
            Operation.MONITORING_READ,
            auth_service=service,
            audit=audit,
            clock=clock,
            business=business,  # type: ignore[arg-type]
        )
    assert denied.value.status_code == 403
    assert calls == []
    access_protected(
        logged_in.access_token,
        Operation.ME,
        auth_service=service,
        audit=audit,
        clock=clock,
        business=business,  # type: ignore[arg-type]
    )
    assert calls == ["called"]
    service.change_password(logged_in.access_token, "temporary-password", "replacement-password")
    with pytest.raises(AppError) as replay:
        service.me(logged_in.access_token)
    assert replay.value.status_code == 401
    refreshed = service.login("first-user", "replacement-password")
    assert refreshed.password_change_required is False
    access_protected(
        refreshed.access_token,
        Operation.MONITORING_READ,
        auth_service=service,
        audit=audit,
        clock=clock,
        business=business,  # type: ignore[arg-type]
    )


@pytest.mark.unit
def test_logout_replay_is_rejected_on_sqlite(tmp_path: Path) -> None:
    from app.core.security import hash_password

    factory, engine = migrated_factory(tmp_path)
    clock = frozen_clock()
    try:
        with factory() as session:
            service, auth = _sqlite_service(session, clock)
            auth.add_user(
                UserDraft(
                    username="sqlite-user",
                    password_hash=hash_password("right-password"),
                    role="管理员",
                    is_active=True,
                    must_change_password=False,
                    created_at=clock.now(),
                )
            )
            session.commit()
            logged_in = service.login("sqlite-user", "right-password")
            service.logout(logged_in.access_token)
            session.commit()
            with pytest.raises(AppError) as replay:
                service.me(logged_in.access_token)
            assert replay.value.status_code == 401
            actions = {entry.action for entry in SqlAlchemyAuditRepository(session).list_entries(1, 20).items}
            assert ACTION_LOGIN in actions
            assert ACTION_LOGOUT in actions
            service.login("sqlite-user", "right-password")
            current = service.login("sqlite-user", "right-password")
            service.change_password(current.access_token, "right-password", "next-password")
            session.commit()
            actions = {entry.action for entry in SqlAlchemyAuditRepository(session).list_entries(1, 50).items}
            assert ACTION_CHANGE_PASSWORD in actions
    finally:
        engine.dispose()


def _sqlite_service(session: Session, clock: object) -> tuple[AuthService, SqlAlchemyAuthRepository]:
    from app.core.clock import FrozenClock

    if not isinstance(clock, FrozenClock):
        raise TypeError("expected FrozenClock")
    auth = SqlAlchemyAuthRepository(session)
    audit = SqlAlchemyAuditRepository(session)
    return AuthService(auth, audit, auth_settings(), clock), auth
