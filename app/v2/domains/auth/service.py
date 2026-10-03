"""Framework independent authentication use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from app.v2.domains.auth.models import LoginSession, User


class AuthenticationPort(Protocol):
    def find_user(self, username: str, *, for_update: bool = False) -> Any | None: ...

    def resolve_session(self, token_hash: str) -> tuple[LoginSession | None, User | None]: ...

    def create_session(self, user_id: str, token_hash: str, csrf_hash: str,
                       expires_at: datetime) -> Any: ...

    def revoke_session(self, session_id: str) -> None: ...

    def revoke_user_sessions(self, user_id: str) -> None: ...

    def update_password(self, user_id: str, password_hash: str) -> None: ...

    def audit(self, actor_id: str | None, action: str, detail: dict[str, Any] | None = None) -> None: ...


@dataclass(frozen=True)
class LoginOutcome:
    accepted: bool
    user: Any | None = None
    token: str | None = None
    csrf_token: str | None = None


@dataclass(frozen=True)
class PasswordChangeOutcome:
    changed: bool
    reason: str | None = None


class AuthenticationService:
    """Coordinate authentication state through an injected persistence port."""

    def __init__(self, port: AuthenticationPort):
        self.port = port

    def resolve_session(self, token_hash: str) -> tuple[LoginSession | None, User | None]:
        return self.port.resolve_session(token_hash)

    def login(
        self,
        username: str,
        password: str,
        *,
        dummy_hash: str,
        session_hours: int,
        max_failures: int,
        lock_minutes: int,
        now: Callable[[], datetime],
        verify_password: Callable[[str, str], bool],
        new_token: Callable[[], str],
        digest: Callable[[str], str],
    ) -> LoginOutcome:
        token, csrf = new_token(), new_token()
        user = self.port.find_user(username.strip(), for_update=True)
        valid = verify_password(password, user.password_hash if user else dummy_hash)
        current = now()
        locked = bool(user and user.locked_until and user.locked_until > current)
        if user is None or not valid or not user.active or locked:
            if user and user.active and not locked:
                user.failed_logins += 1
                if user.failed_logins >= max_failures:
                    user.locked_until = current + timedelta(minutes=lock_minutes)
            self.port.audit(user.id if user else None, "LOGIN_FAILED")
            return LoginOutcome(accepted=False)

        user.failed_logins = 0
        user.locked_until = None
        self.port.create_session(
            user.id,
            digest(token),
            digest(csrf),
            current + timedelta(hours=session_hours),
        )
        self.port.audit(user.id, "LOGIN")
        return LoginOutcome(accepted=True, user=user, token=token, csrf_token=csrf)

    def logout(self, session_id: str, user_id: str) -> None:
        self.port.revoke_session(session_id)
        self.port.audit(user_id, "LOGOUT")

    def change_password(
        self,
        user_id: str,
        current_hash: str,
        current_password: str,
        new_password: str,
        *,
        verify_password: Callable[[str, str], bool],
        hash_password: Callable[[str], str],
    ) -> PasswordChangeOutcome:
        if not verify_password(current_password, current_hash):
            return PasswordChangeOutcome(False, "invalid_current_password")
        if new_password == current_password:
            return PasswordChangeOutcome(False, "same_password")
        self.port.update_password(user_id, hash_password(new_password))
        self.port.revoke_user_sessions(user_id)
        self.port.audit(user_id, "PASSWORD_CHANGED")
        return PasswordChangeOutcome(True)

    def record_access_denied(self, user_id: str, path: str) -> None:
        self.port.audit(user_id, "ACCESS_DENIED", {"path": path})
