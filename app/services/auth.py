"""Login, logout, password change, and token authentication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, ErrorDetail, get_request_id
from app.core.security import (
    AccessClaims,
    credentials_error,
    decode_access_token,
    expires_at_from_claims,
    hash_password,
    issue_access_token,
    unauthenticated_error,
    verify_password,
)
from app.domain.audit_actions import (
    ACTION_CHANGE_PASSWORD,
    ACTION_LOGIN,
    ACTION_LOGOUT,
    ACTION_TOKEN_ISSUED,
)
from app.domain.errors import UserNotFoundError
from app.domain.permissions import FIRST_LOGIN_OPERATIONS, Operation
from app.domain.principal import Principal
from app.domain.records import AuditDraft, RevokedTokenDraft
from app.domain.repositories import AuditRepository, AuthRepository

_OBJECT_USER = "user"
_OBJECT_TOKEN = "access_token"


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    token_type: str
    expires_at: datetime
    role: str
    password_change_required: bool
    user_id: int


@dataclass(frozen=True)
class UserView:
    """Caller-visible identity. Password hashes are not included."""

    id: int
    username: str
    role: str
    is_active: bool
    must_change_password: bool


def normalize_username(username: str) -> str:
    """Strip and case-fold a username so lockout counts one account."""

    return username.strip().casefold()


class AuthService:
    """Credential checks, lockout, and token lifecycle over repository protocols."""

    def __init__(
        self,
        auth: AuthRepository,
        audit: AuditRepository,
        settings: Settings,
        clock: Clock | None = None,
    ) -> None:
        self._auth = auth
        self._audit = audit
        self._settings = settings
        self._clock = clock if clock is not None else SystemClock()

    def login(self, username: str, password: str, *, ip_hash: str | None = None) -> LoginResult:
        """Authenticate a user or raise one identical credential error."""

        now = self._now()
        normalized = normalize_username(username)
        user = self._auth.get_by_username(normalized) if normalized else None
        if user is None:
            verify_password(password, None)
            self._audit_login(None, "FAILURE", now, ip_hash)
            raise credentials_error()
        if user.locked_until is not None and now < user.locked_until:
            verify_password(password, user.password_hash)
            self._audit_login(user.id, "FAILURE", now, ip_hash)
            raise credentials_error()

        password_ok = verify_password(password, user.password_hash)
        if not password_ok or not user.is_active:
            if user.is_active and not password_ok:
                self._record_failure(user.id, user.failed_login_count, now)
            self._audit_login(user.id, "FAILURE", now, ip_hash)
            raise credentials_error()

        self._auth.clear_login_failures(user.id, updated_at=now)
        token, claims = issue_access_token(
            user_id=user.id,
            role=user.role,
            password_change_required=user.must_change_password,
            now=now,
            ttl_seconds=self._settings.jwt_expire_seconds,
            secret=self._secret(),
        )
        expires_at = expires_at_from_claims(claims)
        self._audit.append(
            self._draft(
                user_id=user.id,
                action=ACTION_TOKEN_ISSUED,
                object_type=_OBJECT_TOKEN,
                object_id=claims.jti,
                result="SUCCESS",
                details={"expires_at": expires_at.isoformat()},
                created_at=now,
                ip_hash=ip_hash,
            )
        )
        self._audit_login(user.id, "SUCCESS", now, ip_hash)
        return LoginResult(
            access_token=token,
            token_type="bearer",
            expires_at=expires_at,
            role=user.role,
            password_change_required=user.must_change_password,
            user_id=user.id,
        )

    def authenticate(self, token: str | None) -> Principal:
        """Validate a bearer token before any business repository is touched."""

        if token is None or token.strip() == "":
            raise unauthenticated_error()
        claims = decode_access_token(token.strip(), self._secret(), self._now())
        if self._auth.is_token_revoked(claims.jti):
            raise unauthenticated_error()
        user = self._load_active_user(claims)
        if user.role != claims.role:
            raise unauthenticated_error()
        return Principal(
            user_id=user.id,
            username=user.username,
            role=user.role,
            password_change_required=claims.password_change_required or user.must_change_password,
            jti=claims.jti,
            expires_at=expires_at_from_claims(claims),
        )

    def logout(self, token: str, *, ip_hash: str | None = None) -> None:
        """Revoke the current token so the same ``jti`` cannot be replayed."""

        principal = self.authenticate(token)
        now = self._now()
        self._revoke_jti(
            jti=principal.jti,
            user_id=principal.user_id,
            expires_at=principal.expires_at,
            revoked_at=now,
            reason="logout",
        )
        self._audit.append(
            self._draft(
                user_id=principal.user_id,
                action=ACTION_LOGOUT,
                object_type=_OBJECT_TOKEN,
                object_id=principal.jti,
                result="SUCCESS",
                details=None,
                created_at=now,
                ip_hash=ip_hash,
            )
        )

    def change_password(
        self,
        token: str,
        current_password: str,
        new_password: str,
        *,
        ip_hash: str | None = None,
    ) -> None:
        """Replace the password hash, clear the first-login flag, and revoke tokens."""

        principal = self.authenticate(token)
        now = self._now()
        user = self._auth.get_by_id(principal.user_id)
        if user is None or not user.is_active:
            raise unauthenticated_error()
        if not verify_password(current_password, user.password_hash):
            raise credentials_error()
        if new_password == "" or new_password == current_password:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "新口令无效",
                details=(ErrorDetail(field="new_password", reason="must be a different non-empty password"),),
            )
        self._auth.change_password(
            user.id,
            password_hash=hash_password(new_password),
            must_change_password=False,
            password_changed_at=now,
            updated_at=now,
        )
        self._revoke_unexpired(user.id, now, "password_change")
        self._audit.append(
            self._draft(
                user_id=user.id,
                action=ACTION_CHANGE_PASSWORD,
                object_type=_OBJECT_USER,
                object_id=str(user.id),
                result="SUCCESS",
                details=None,
                created_at=now,
                ip_hash=ip_hash,
            )
        )

    def me(self, token: str) -> UserView:
        principal = self.authenticate(token)
        user = self._auth.get_by_id(principal.user_id)
        if user is None:
            raise unauthenticated_error()
        return UserView(
            id=user.id,
            username=user.username,
            role=user.role,
            is_active=user.is_active,
            must_change_password=user.must_change_password,
        )

    def allows_during_password_change(self, operation: Operation) -> bool:
        return operation in FIRST_LOGIN_OPERATIONS

    def revoke_issued_tokens(self, user_id: int, reason: str) -> None:
        """Revoke every unexpired token previously issued to ``user_id``."""

        self._revoke_unexpired(user_id, self._now(), reason)

    def _record_failure(self, user_id: int, previous_count: int, now: datetime) -> None:
        count = previous_count + 1
        locked_until = None
        if count >= self._settings.login_max_failures:
            locked_until = now + timedelta(seconds=self._settings.login_lock_seconds)
        self._auth.save_login_failure(
            user_id,
            failed_login_count=count,
            last_failed_at=now,
            locked_until=locked_until,
            updated_at=now,
        )

    def _revoke_unexpired(self, user_id: int, now: datetime, reason: str) -> None:
        issued = self._audit.list_by_user_action(user_id, ACTION_TOKEN_ISSUED)
        for entry in issued:
            if entry.object_id is None or entry.details is None:
                continue
            if self._auth.is_token_revoked(entry.object_id):
                continue
            raw_expiry = entry.details.get("expires_at")
            if raw_expiry is None:
                continue
            expires_at = datetime.fromisoformat(raw_expiry)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                continue
            self._revoke_jti(
                jti=entry.object_id,
                user_id=user_id,
                expires_at=expires_at,
                revoked_at=now,
                reason=reason,
            )

    def _revoke_jti(
        self,
        *,
        jti: str,
        user_id: int,
        expires_at: datetime,
        revoked_at: datetime,
        reason: str,
    ) -> None:
        if self._auth.is_token_revoked(jti):
            return
        self._auth.revoke_token(
            RevokedTokenDraft(
                jti=jti,
                user_id=user_id,
                expires_at=expires_at,
                revoked_at=revoked_at,
                reason=reason,
            )
        )

    def _load_active_user(self, claims: AccessClaims) -> UserView:
        try:
            user_id = int(claims.sub)
        except ValueError:
            raise unauthenticated_error() from None
        try:
            user = self._auth.get_by_id(user_id)
        except UserNotFoundError:
            raise unauthenticated_error() from None
        if user is None or not user.is_active:
            raise unauthenticated_error()
        return UserView(
            id=user.id,
            username=user.username,
            role=user.role,
            is_active=user.is_active,
            must_change_password=user.must_change_password,
        )

    def _audit_login(
        self,
        user_id: int | None,
        result: str,
        now: datetime,
        ip_hash: str | None,
    ) -> None:
        self._audit.append(
            self._draft(
                user_id=user_id,
                action=ACTION_LOGIN,
                object_type=_OBJECT_USER,
                object_id=None if user_id is None else str(user_id),
                result=result,
                details=None,
                created_at=now,
                ip_hash=ip_hash,
            )
        )

    def _draft(
        self,
        *,
        user_id: int | None,
        action: str,
        object_type: str,
        object_id: str | None,
        result: str,
        details: dict[str, str] | None,
        created_at: datetime,
        ip_hash: str | None,
    ) -> AuditDraft:
        return AuditDraft(
            user_id=user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            request_id=get_request_id(),
            result=result,
            details=details,
            ip_hash=ip_hash,
            created_at=created_at,
        )

    def _secret(self) -> str:
        return self._settings.jwt_secret.get_secret_value()

    def _now(self) -> datetime:
        current = self._clock.now()
        if current.tzinfo is None:
            raise ValueError("clock must return timezone-aware instants")
        return current.astimezone(timezone.utc)
