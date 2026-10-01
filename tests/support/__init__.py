"""In-memory auth and audit repositories for tests that do not need SQLite."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from app.domain.errors import DuplicateUsernameError, UserNotFoundError
from app.domain.records import (
    AuditDraft,
    AuditRecord,
    Page,
    RevokedTokenDraft,
    UserDraft,
    UserRecord,
)


class MemoryAuthRepository:
    def __init__(self) -> None:
        self.users: dict[int, UserRecord] = {}
        self._by_name: dict[str, int] = {}
        self.revoked: dict[str, RevokedTokenDraft] = {}
        self._next_id = 1

    def add_user(self, draft: UserDraft) -> int:
        if draft.username in self._by_name:
            raise DuplicateUsernameError()
        user_id = self._next_id
        self._next_id += 1
        self.users[user_id] = UserRecord(
            id=user_id,
            username=draft.username,
            password_hash=draft.password_hash,
            role=draft.role,
            is_active=draft.is_active,
            must_change_password=draft.must_change_password,
            failed_login_count=0,
            locked_until=None,
        )
        self._by_name[draft.username] = user_id
        return user_id

    def get_by_username(self, username: str) -> UserRecord | None:
        user_id = self._by_name.get(username)
        if user_id is None:
            return None
        return self.users[user_id]

    def get_by_id(self, user_id: int) -> UserRecord | None:
        return self.users.get(user_id)

    def list_users(self, page: int, page_size: int) -> Page[UserRecord]:
        ordered = tuple(self.users[key] for key in sorted(self.users))
        start = (page - 1) * page_size
        return Page(
            items=ordered[start : start + page_size],
            page=page,
            page_size=page_size,
            total=len(ordered),
        )

    def save_login_failure(
        self,
        user_id: int,
        *,
        failed_login_count: int,
        last_failed_at: datetime,
        locked_until: datetime | None,
        updated_at: datetime,
    ) -> None:
        current = self._require(user_id)
        self.users[user_id] = replace(
            current,
            failed_login_count=failed_login_count,
            last_failed_at=last_failed_at,
            locked_until=locked_until,
        )
        del updated_at

    def clear_login_failures(self, user_id: int, *, updated_at: datetime) -> None:
        current = self._require(user_id)
        self.users[user_id] = replace(
            current,
            failed_login_count=0,
            last_failed_at=None,
            locked_until=None,
        )
        del updated_at

    def change_password(
        self,
        user_id: int,
        *,
        password_hash: str,
        must_change_password: bool,
        password_changed_at: datetime,
        updated_at: datetime,
    ) -> None:
        current = self._require(user_id)
        self.users[user_id] = replace(
            current,
            password_hash=password_hash,
            must_change_password=must_change_password,
            password_changed_at=password_changed_at,
        )
        del updated_at

    def update_account(
        self,
        user_id: int,
        *,
        role: str | None,
        is_active: bool | None,
        updated_at: datetime,
    ) -> None:
        current = self._require(user_id)
        self.users[user_id] = replace(
            current,
            role=current.role if role is None else role,
            is_active=current.is_active if is_active is None else is_active,
        )
        del updated_at

    def revoke_token(self, draft: RevokedTokenDraft) -> int:
        self.revoked[draft.jti] = draft
        return len(self.revoked)

    def is_token_revoked(self, jti: str) -> bool:
        return jti in self.revoked

    def _require(self, user_id: int) -> UserRecord:
        row = self.users.get(user_id)
        if row is None:
            raise UserNotFoundError()
        return row


class MemoryAuditRepository:
    def __init__(self) -> None:
        self.entries: list[AuditRecord] = []

    def append(self, draft: AuditDraft) -> int:
        record = AuditRecord(
            id=len(self.entries) + 1,
            user_id=draft.user_id,
            action=draft.action,
            object_type=draft.object_type,
            object_id=draft.object_id,
            result=draft.result,
            created_at=draft.created_at,
            details=None if draft.details is None else dict(draft.details),
        )
        self.entries.append(record)
        return record.id

    def list_entries(self, page: int, page_size: int) -> Page[AuditRecord]:
        start = (page - 1) * page_size
        window = tuple(self.entries[start : start + page_size])
        return Page(items=window, page=page, page_size=page_size, total=len(self.entries))

    def list_by_user_action(self, user_id: int, action: str) -> tuple[AuditRecord, ...]:
        return tuple(
            entry
            for entry in self.entries
            if entry.user_id == user_id and entry.action == action
        )
