"""Opaque browser sessions; authentication failures commit before an HTTP error."""
from typing import Any

from hashlib import sha256
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from app.v2.shared.http_errors import ErrorCode
from app.v2.common import fail, serialize
from app.v2.domains.auth.repository import SqlAlchemyAuthenticationPort
from app.v2.domains.auth.service import AuthenticationService
from app.v2.domains.auth.models import User
from app.v2.shared.persistence import now
from app.v2.contracts import LoginResponse, UserView

router = APIRouter(prefix="/auth", tags=["认证"])
hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
dummy_hash = hasher.hash("unavailable-account-dummy")
COOKIE = "esp_session"
CSRF_COOKIE = "esp_csrf"


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def check_password(password: str, hashed: str) -> bool:
    try:
        return hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def get_user(request: Request) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        fail("请先登录", ErrorCode.UNAUTHENTICATED)
    with request.app.state.db.sessions() as session:
        service = AuthenticationService(SqlAlchemyAuthenticationPort(session))
        record, user = service.resolve_session(digest(token))
        if record is None or record.revoked or record.expires_at <= now():
            fail("登录已过期，请重新登录", ErrorCode.UNAUTHENTICATED)
        if user is None or not user.active:
            fail("登录已失效", ErrorCode.UNAUTHENTICATED)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            submitted = request.headers.get("X-CSRF-Token", "")
            if not submitted or not secrets.compare_digest(record.csrf_hash, digest(submitted)):
                fail("页面校验已失效，请刷新后重试", ErrorCode.FORBIDDEN)
            origin = request.headers.get("Origin")
            if origin and origin.rstrip("/") != request.app.state.settings.public_origin.rstrip("/"):
                fail("请求来源不匹配", ErrorCode.FORBIDDEN)
        if user.must_change_password and request.url.path not in {
            "/api/v2/auth/me", "/api/v2/auth/change-password", "/api/v2/auth/logout"
        }:
            fail("首次登录请先修改密码", ErrorCode.FORBIDDEN)
        request.state.session_id = record.id
        request.state.user_id = user.id
        return user


def authorize(*roles: str) -> Any:
    def dependency(request: Request, user: User = Depends(get_user)) -> User:
        if user.role not in roles:
            with request.app.state.db.transaction() as session:
                AuthenticationService(SqlAlchemyAuthenticationPort(session)).record_access_denied(
                    user.id, request.url.path
                )
            fail("当前账号没有此操作权限", ErrorCode.FORBIDDEN)
        return user
    return dependency


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class PasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=200)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginBody, request: Request, response: Response) -> dict[str, Any]:
    settings = request.app.state.settings
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") != settings.public_origin.rstrip("/"):
        fail("请求来源不匹配", ErrorCode.FORBIDDEN)
    with request.app.state.db.transaction() as session:
        outcome = AuthenticationService(SqlAlchemyAuthenticationPort(session)).login(
            body.username,
            body.password,
            dummy_hash=dummy_hash,
            session_hours=settings.session_hours,
            max_failures=settings.login_max_failures,
            lock_minutes=settings.login_lock_minutes,
            now=now,
            verify_password=check_password,
            new_token=iter((secrets.token_urlsafe(48), secrets.token_urlsafe(32))).__next__,
            digest=digest,
        )
        result = serialize(outcome.user) if outcome.user is not None else None
    token, csrf = outcome.token, outcome.csrf_token
    if not outcome.accepted or token is None or csrf is None:
        fail("用户名或密码不正确，或账号暂时不可用", ErrorCode.INVALID_CREDENTIALS)
    response.set_cookie(COOKIE, token, httponly=True, secure=settings.cookie_secure,
                        samesite="lax", max_age=settings.session_hours * 3600, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=settings.cookie_secure,
                        samesite="lax", max_age=settings.session_hours * 3600, path="/")
    return {"user": result, "csrf_token": csrf}


@router.get("/me", response_model=UserView)
def me(user: User = Depends(get_user)) -> dict[str, Any]:
    return serialize(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user: User = Depends(get_user)) -> None:
    with request.app.state.db.transaction() as session:
        AuthenticationService(SqlAlchemyAuthenticationPort(session)).logout(
            request.state.session_id, user.id
        )
    response.delete_cookie(COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.post("/change-password")
def change_password(body: PasswordBody, request: Request, response: Response,
                    user: User = Depends(get_user)) -> dict[str, Any]:
    with request.app.state.db.transaction() as session:
        outcome = AuthenticationService(SqlAlchemyAuthenticationPort(session)).change_password(
            user.id,
            user.password_hash,
            body.current_password,
            body.new_password,
            verify_password=check_password,
            hash_password=hasher.hash,
        )
    if outcome.reason == "invalid_current_password":
        fail("当前密码不正确")
    if outcome.reason == "same_password":
        fail("新密码不能与当前密码相同")
    response.delete_cookie(COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"message": "密码已更新，请重新登录"}
