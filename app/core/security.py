"""Argon2id passwords and HS256 access tokens.

Hashes use a random salt. Verification of an unknown user still runs one
Argon2 check against a dummy hash so the two failure paths do the same work.
Secrets and plaintext passwords are never written to logs from this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import uuid4

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.errors import AppError, ErrorCode
from app.domain.enums import USER_ROLES

ALLOWED_JWT_ALGORITHMS: frozenset[str] = frozenset({"HS256"})
CREDENTIALS_MESSAGE = "用户名或口令不正确"
UNAUTHENTICATED_MESSAGE = "未认证"

_HASHER = PasswordHasher(
    time_cost=1,
    memory_cost=1024,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
_DUMMY_HASH = _HASHER.hash("platform-dummy-credential")
_verification_count = 0


def hash_password(password: str) -> str:
    """Return a salted Argon2id hash. The plaintext is not retained."""

    if password == "":
        raise ValueError("password must not be empty")
    return _HASHER.hash(password)


def verification_count() -> int:
    """How many Argon2 verifications this process has performed."""

    return _verification_count


def reset_verification_count() -> None:
    """Reset the verification counter. Tests use this to compare failure paths."""

    global _verification_count
    _verification_count = 0


def verify_password(password: str, password_hash: str | None) -> bool:
    """Check a password, always performing exactly one Argon2 verification."""

    global _verification_count
    _verification_count += 1
    candidate = password_hash if password_hash is not None else _DUMMY_HASH
    try:
        _HASHER.verify(candidate, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return password_hash is not None


def credentials_error() -> AppError:
    """Uniform credential failure. Callers must not vary the message or details."""

    return AppError(ErrorCode.INVALID_CREDENTIALS, CREDENTIALS_MESSAGE, details=())


def unauthenticated_error() -> AppError:
    """Uniform authentication failure used before any business repository call."""

    return AppError(ErrorCode.UNAUTHENTICATED, UNAUTHENTICATED_MESSAGE, details=())


@dataclass(frozen=True)
class AccessClaims:
    sub: str
    role: str
    iat: int
    exp: int
    jti: str
    password_change_required: bool


def issue_access_token(
    *,
    user_id: int,
    role: str,
    password_change_required: bool,
    now: datetime,
    ttl_seconds: int,
    secret: str,
) -> tuple[str, AccessClaims]:
    """Sign an HS256 token. ``secret`` is used only as the HMAC key."""

    if role not in USER_ROLES:
        raise ValueError("role is not a platform role")
    if ttl_seconds < 1:
        raise ValueError("ttl_seconds must be positive")
    if now.tzinfo is None:
        raise ValueError("token time must be timezone-aware")
    issued_at = int(now.timestamp())
    expires_at = issued_at + ttl_seconds
    claims = AccessClaims(
        sub=str(user_id),
        role=role,
        iat=issued_at,
        exp=expires_at,
        jti=str(uuid4()),
        password_change_required=password_change_required,
    )
    token = jwt.encode(
        {
            "sub": claims.sub,
            "role": claims.role,
            "iat": claims.iat,
            "exp": claims.exp,
            "jti": claims.jti,
            "password_change_required": claims.password_change_required,
        },
        secret,
        algorithm="HS256",
    )
    if not isinstance(token, str):
        raise RuntimeError("token encoder returned a non-text token")
    return token, claims


def decode_access_token(token: str, secret: str, now: datetime) -> AccessClaims:
    """Validate the algorithm allow-list, signature, and expiry against ``now``."""

    if now.tzinfo is None:
        raise ValueError("token time must be timezone-aware")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise unauthenticated_error() from None
    if not isinstance(header, dict) or header.get("alg") not in ALLOWED_JWT_ALGORITHMS:
        raise unauthenticated_error()
    try:
        decoded = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={
                "verify_exp": False,
                "require": ["sub", "role", "iat", "exp", "jti", "password_change_required"],
            },
        )
    except jwt.InvalidTokenError:
        raise unauthenticated_error() from None
    payload = cast(dict[str, Any], decoded)
    flag = payload.get("password_change_required")
    if not isinstance(flag, bool):
        raise unauthenticated_error()
    try:
        claims = AccessClaims(
            sub=str(payload["sub"]),
            role=str(payload["role"]),
            iat=int(payload["iat"]),
            exp=int(payload["exp"]),
            jti=str(payload["jti"]),
            password_change_required=flag,
        )
    except (TypeError, ValueError):
        raise unauthenticated_error() from None
    if claims.role not in USER_ROLES or claims.jti == "" or claims.sub == "":
        raise unauthenticated_error()
    if now.timestamp() >= claims.exp:
        raise unauthenticated_error()
    return claims


def expires_at_from_claims(claims: AccessClaims) -> datetime:
    """Return the claim expiry as an aware UTC instant."""

    return datetime.fromtimestamp(claims.exp, tz=timezone.utc)


def default_ttl_deadline(now: datetime, ttl_seconds: int) -> datetime:
    """Return ``now + ttl`` in UTC."""

    return now.astimezone(timezone.utc) + timedelta(seconds=ttl_seconds)
