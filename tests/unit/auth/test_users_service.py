"""Administrator user lifecycle examples."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import AppError, ErrorCode
from app.domain.enums import USER_ROLES
from app.domain.permissions import ALL_PROTECTED_OPERATIONS, Operation, is_allowed
from app.domain.principal import Principal
from app.domain.records import UserDraft
from app.repositories.sqlalchemy.store import SqlAlchemyAuditRepository, SqlAlchemyAuthRepository
from app.services.auth import AuthService
from app.services.users import UserService
from tests.support.auth_factory import auth_settings, frozen_clock, migrated_factory
from app.core.security import hash_password
from app.api.dependencies.auth import authorize_operation
from app.domain.audit_actions import ACTION_AUTHORIZATION_DENIED


def _stack(session: object, clock: object) -> tuple[UserService, SqlAlchemyAuthRepository, Principal]:
    from app.core.clock import FrozenClock
    from sqlalchemy.orm import Session

    if not isinstance(session, Session) or not isinstance(clock, FrozenClock):
        raise TypeError("expected a session and frozen clock")
    auth = SqlAlchemyAuthRepository(session)
    audit = SqlAlchemyAuditRepository(session)
    service = AuthService(auth, audit, auth_settings(), clock)
    users = UserService(auth, audit, service, clock)
    admin_id = auth.add_user(
        UserDraft(
            username="admin",
            password_hash=hash_password("admin-password"),
            role="管理员",
            is_active=True,
            must_change_password=False,
            created_at=clock.now(),
        )
    )
    actor = Principal(
        user_id=admin_id,
        username="admin",
        role="管理员",
        password_change_required=False,
        jti="admin-token",
        expires_at=clock.now(),
    )
    return users, auth, actor


@pytest.mark.unit
def test_admin_creates_each_role_and_shows_the_temporary_password_once(tmp_path: Path) -> None:
    factory, engine = migrated_factory(tmp_path)
    clock = frozen_clock()
    try:
        with factory() as session:
            users, auth, actor = _stack(session, clock)
            created = []
            for role in USER_ROLES:
                created.append(
                    users.create_user(actor, f"user-{role}", role, temporary_password=f"temp-{role}")
                )
            session.commit()
            assert [item.role for item in created] == list(USER_ROLES)
            for item in created:
                stored = auth.get_by_id(item.id)
                assert stored is not None
                assert stored.must_change_password is True
                assert item.temporary_password not in stored.password_hash
                assert "temporary_password" not in item.public_view()
                assert item.temporary_password not in item.public_view().values()
            with pytest.raises(AppError) as duplicate:
                users.create_user(actor, "user-管理员", "管理员", temporary_password="another-temp")
            assert duplicate.value.code == ErrorCode.CONFLICT
    finally:
        engine.dispose()


@pytest.mark.unit
def test_role_change_and_deactivation_revoke_tokens(tmp_path: Path) -> None:
    factory, engine = migrated_factory(tmp_path)
    clock = frozen_clock()
    try:
        with factory() as session:
            users, auth, actor = _stack(session, clock)
            created = users.create_user(
                actor, "researcher", "研究者", temporary_password="temporary-password"
            )
            session.commit()
            auth_service = users._auth_service
            logged_in = auth_service.login("researcher", "temporary-password")
            auth_service.change_password(
                logged_in.access_token, "temporary-password", "replacement-password"
            )
            active = auth_service.login("researcher", "replacement-password")
            users.change_role(actor, created.id, "监管人员")
            session.commit()
            with pytest.raises(AppError) as revoked:
                auth_service.me(active.access_token)
            assert revoked.value.status_code == 401
            refreshed = auth_service.login("researcher", "replacement-password")
            assert refreshed.role == "监管人员"
            users.set_active(actor, created.id, is_active=False)
            session.commit()
            with pytest.raises(AppError) as disabled:
                auth_service.me(refreshed.access_token)
            assert disabled.value.status_code == 401
            stored = auth.get_by_username("researcher")
            assert stored is not None
            assert stored.is_active is False
    finally:
        engine.dispose()


@pytest.mark.unit
@pytest.mark.parametrize("role", USER_ROLES)
@pytest.mark.parametrize("operation", ALL_PROTECTED_OPERATIONS)
def test_role_matrix_matches_every_protected_operation(role: str, operation: Operation) -> None:
    from app.core.clock import FrozenClock
    from datetime import datetime, timezone

    audit_box: list[str] = []
    writes: list[str] = []

    class _Audit:
        def append(self, draft: object) -> int:
            action = getattr(draft, "action")
            audit_box.append(action)
            return len(audit_box)

        def list_entries(self, page: int, page_size: int) -> object:
            raise AssertionError("not used")

        def list_by_user_action(self, user_id: int, action: str) -> tuple[object, ...]:
            raise AssertionError("not used")

    def business(payload: dict[str, str]) -> None:
        writes.append(payload["marker"])

    clock = FrozenClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    allowed = is_allowed(role, operation)
    if allowed:
        authorize_operation(
            role=role,
            operation=operation,
            user_id=1,
            password_change_required=False,
            payload={"marker": "ok"},
            audit=_Audit(),  # type: ignore[arg-type]
            clock=clock,
            business=business,
        )
        assert writes == ["ok"]
        assert ACTION_AUTHORIZATION_DENIED not in audit_box
        return
    with pytest.raises(AppError) as denied:
        authorize_operation(
            role=role,
            operation=operation,
            user_id=1,
            password_change_required=False,
            payload={"marker": "no"},
            audit=_Audit(),  # type: ignore[arg-type]
            clock=clock,
            business=business,
        )
    assert denied.value.status_code == 403
    assert writes == []
    assert audit_box == [ACTION_AUTHORIZATION_DENIED]
