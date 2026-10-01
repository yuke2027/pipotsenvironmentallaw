"""Administrator user lifecycle. Temporary passwords are returned once and never logged."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

from app.core.clock import Clock, SystemClock
from app.core.errors import AppError, ErrorCode, ErrorDetail, get_request_id
from app.core.security import hash_password
from app.domain.audit_actions import (
    ACTION_AUTHORIZATION_DENIED,
    ACTION_USER_CREATED,
    ACTION_USER_DEACTIVATED,
    ACTION_USER_REACTIVATED,
    ACTION_USER_ROLE_CHANGED,
)
from app.domain.enums import USER_ROLES
from app.domain.errors import DuplicateUsernameError, UserNotFoundError
from app.domain.permissions import ADMIN, Operation, is_allowed
from app.domain.principal import Principal
from app.domain.records import AuditDraft, Page, UserDraft, UserRecord
from app.domain.repositories import AuditRepository, AuthRepository
from app.services.auth import AuthService, UserView, normalize_username

_OBJECT_USER = "user"


@dataclass(frozen=True)
class CreatedUser:
    """One-time display of a temporary password. Later reads use ``UserView``."""

    id: int
    username: str
    role: str
    temporary_password: str

    def public_view(self) -> dict[str, str | int]:
        return {"id": self.id, "username": self.username, "role": self.role}


class UserService:
    def __init__(
        self,
        auth: AuthRepository,
        audit: AuditRepository,
        auth_service: AuthService,
        clock: Clock | None = None,
    ) -> None:
        self._auth = auth
        self._audit = audit
        self._auth_service = auth_service
        self._clock = clock if clock is not None else SystemClock()

    def create_user(
        self,
        actor: Principal,
        username: str,
        role: str,
        *,
        temporary_password: str | None = None,
    ) -> CreatedUser:
        self._require_admin(actor, Operation.USERS_WRITE)
        normalized = normalize_username(username)
        if normalized == "" or len(normalized) > 64:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "用户名无效",
                details=(ErrorDetail(field="username", reason="required"),),
            )
        if role not in USER_ROLES:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "角色无效",
                details=(ErrorDetail(field="role", reason="unsupported role"),),
            )
        password = temporary_password if temporary_password is not None else secrets.token_urlsafe(18)
        if password == "":
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "临时口令无效",
                details=(ErrorDetail(field="temporary_password", reason="required"),),
            )
        now = self._clock.now()
        try:
            user_id = self._auth.add_user(
                UserDraft(
                    username=normalized,
                    password_hash=hash_password(password),
                    role=role,
                    is_active=True,
                    must_change_password=True,
                    created_at=now,
                )
            )
        except DuplicateUsernameError:
            raise AppError(ErrorCode.CONFLICT, "用户名已存在") from None
        self._audit.append(
            self._draft(
                actor.user_id,
                ACTION_USER_CREATED,
                str(user_id),
                now,
                {"role": role},
            )
        )
        return CreatedUser(
            id=user_id,
            username=normalized,
            role=role,
            temporary_password=password,
        )

    def change_role(self, actor: Principal, user_id: int, role: str) -> UserView:
        self._require_admin(actor, Operation.USERS_WRITE)
        if role not in USER_ROLES:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "角色无效",
                details=(ErrorDetail(field="role", reason="unsupported role"),),
            )
        user = self._require_user(user_id)
        now = self._clock.now()
        if user.role != role:
            self._auth.update_account(user_id, role=role, is_active=None, updated_at=now)
            self._auth_service.revoke_issued_tokens(user_id, "role_change")
            self._audit.append(
                self._draft(
                    actor.user_id,
                    ACTION_USER_ROLE_CHANGED,
                    str(user_id),
                    now,
                    {"role": role},
                )
            )
        updated = self._require_user(user_id)
        return _view(updated)

    def set_active(self, actor: Principal, user_id: int, *, is_active: bool) -> UserView:
        self._require_admin(actor, Operation.USERS_WRITE)
        self._require_user(user_id)
        now = self._clock.now()
        self._auth.update_account(user_id, role=None, is_active=is_active, updated_at=now)
        if not is_active:
            self._auth_service.revoke_issued_tokens(user_id, "deactivated")
        self._audit.append(
            self._draft(
                actor.user_id,
                ACTION_USER_DEACTIVATED if not is_active else ACTION_USER_REACTIVATED,
                str(user_id),
                now,
                None,
            )
        )
        return _view(self._require_user(user_id))

    def list_users(self, actor: Principal, page: int, page_size: int) -> Page[UserView]:
        self._require_admin(actor, Operation.USERS_READ)
        listed = self._auth.list_users(page, page_size)
        return Page(
            items=tuple(_view(item) for item in listed.items),
            page=listed.page,
            page_size=listed.page_size,
            total=listed.total,
        )

    def _require_admin(self, actor: Principal, operation: Operation) -> None:
        if is_allowed(actor.role, operation) and actor.role == ADMIN:
            return
        now = self._clock.now()
        self._audit.append(
            self._draft(
                actor.user_id,
                ACTION_AUTHORIZATION_DENIED,
                operation.value,
                now,
                {"role": actor.role},
            )
        )
        raise AppError(ErrorCode.FORBIDDEN, "权限不足")

    def _require_user(self, user_id: int) -> UserView:
        try:
            user = self._auth.get_by_id(user_id)
        except UserNotFoundError:
            user = None
        if user is None:
            raise AppError(ErrorCode.NOT_FOUND, "用户不存在")
        return _view(user)

    def _draft(
        self,
        user_id: int,
        action: str,
        object_id: str,
        created_at: datetime,
        details: dict[str, str] | None,
    ) -> AuditDraft:
        return AuditDraft(
            user_id=user_id,
            action=action,
            object_type=_OBJECT_USER if action != ACTION_AUTHORIZATION_DENIED else "operation",
            object_id=object_id,
            request_id=get_request_id(),
            result="DENIED" if action == ACTION_AUTHORIZATION_DENIED else "SUCCESS",
            details=details,
            ip_hash=None,
            created_at=created_at,
        )


def _view(user: UserRecord | UserView) -> UserView:
    if isinstance(user, UserView):
        return user
    return UserView(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
    )
