"""Task 16.3: three-role API matrix, token lifecycle, audit and Chinese UI."""

from __future__ import annotations

import _socket
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import load_settings
from app.db.models import AuditLog, LegalStandard, User
from app.db.session import sqlite_file_url
from app.domain.audit_actions import ACTION_AUTHORIZATION_DENIED, ACTION_LOGOUT
from app.domain.permissions import ADMIN, RESEARCHER, SUPERVISOR, Operation, is_allowed
from app.legacy_main import create_app
from app.runtime import AppContext

_BOOT = "BootAdmin#2026"
_ADMIN_NEW = "AdminChanged#2026"
_ROLE_PASSWORD = "RolePass#2026"
_STANDARD = {
    "standard_key": "E2E-PM25",
    "version": "e2e-1",
    "pollutant": "PM2.5",
    "statistic_basis": "24h_mean",
    "limit_value": 70,
}


def _allow_loopback(self: socket.socket, address: object) -> None:
    host = address[0] if isinstance(address, tuple) and address else ""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise AssertionError("Real socket access is blocked in tests; use MockTransport or a fake adapter.")
    _socket.socket.connect(self, address)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(socket.socket, "connect", _allow_loopback)
    settings = load_settings(
        _env_file=None,
        jwt_secret="roles-ui-jwt-secret-value",
        database_url=sqlite_file_url(tmp_path / "roles.db"),
        project_root=tmp_path,
        database_path=tmp_path / "roles.db",
        login_max_failures=3,
    )
    with TestClient(create_app(settings, admin_password=_BOOT)) as test_client:
        yield test_client


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _context(client: TestClient) -> AppContext:
    context = client.app.state.context
    assert isinstance(context, AppContext)
    return context


@pytest.fixture
def tokens(client: TestClient) -> dict[str, str]:
    first = _login(client, "admin", _BOOT)
    assert client.post(
        "/api/v1/auth/change-password",
        headers=_headers(first),
        json={"current_password": _BOOT, "new_password": _ADMIN_NEW},
    ).status_code == 200
    admin = _login(client, "admin", _ADMIN_NEW)
    result = {ADMIN: admin}
    for username, role in (("sup-user", SUPERVISOR), ("res-user", RESEARCHER)):
        created = client.post(
            "/api/v1/users",
            headers=_headers(admin),
            json={"username": username, "role": role, "temporary_password": _ROLE_PASSWORD},
        )
        assert created.status_code == 201
        temp = _login(client, username, _ROLE_PASSWORD)
        assert client.post(
            "/api/v1/auth/change-password",
            headers=_headers(temp),
            json={"current_password": _ROLE_PASSWORD, "new_password": _ROLE_PASSWORD + "x"},
        ).status_code == 200
        result[role] = _login(client, username, _ROLE_PASSWORD + "x")
    return result


_CASES: list[tuple[str, str, Operation, dict[str, object] | None]] = [
    ("GET", "/api/v1/monitoring-records", Operation.MONITORING_READ, None),
    ("GET", "/api/v1/compliance-results", Operation.COMPLIANCE_READ, None),
    ("GET", "/api/v1/risk-assessments", Operation.RISK_READ, None),
    ("GET", "/api/v1/stations/1/forecasts", Operation.FORECAST_READ, None),
    ("GET", "/api/v1/standards", Operation.STANDARDS_READ, None),
    ("POST", "/api/v1/exports", Operation.EXPORT_CREATE, {}),
    ("GET", "/api/v1/alerts", Operation.ALERTS_READ, None),
    ("POST", "/api/v1/reports", Operation.REPORTS_CREATE, {}),
    ("GET", "/api/v1/jobs/abc", Operation.JOBS_READ, None),
    ("POST", "/api/v1/jobs/collection", Operation.COLLECTION_TRIGGER, {}),
    ("GET", "/api/v1/models", Operation.MODELS_READ, None),
    ("POST", "/api/v1/models/retrain", Operation.MODELS_RETRAIN, None),
    ("POST", "/api/v1/models/1/activate", Operation.MODELS_ACTIVATE, None),
    ("GET", "/api/v1/users", Operation.USERS_READ, None),
    ("GET", "/api/v1/alert-channels", Operation.ALERT_CHANNELS_WRITE, None),
]


@pytest.mark.integration
@pytest.mark.parametrize(("method", "path", "operation", "body"), _CASES)
def test_every_endpoint_matches_the_role_matrix(
    client: TestClient,
    tokens: dict[str, str],
    method: str,
    path: str,
    operation: Operation,
    body: dict[str, object] | None,
) -> None:
    unauthenticated = client.request(method, path, json=body)
    assert unauthenticated.status_code == 401
    for role, token in tokens.items():
        response = client.request(method, path, headers=_headers(token), json=body)
        expected_ok = is_allowed(role, operation)
        assert (response.status_code < 400) == expected_ok, (role, path, response.status_code)
        if not expected_ok:
            assert response.status_code == 403


@pytest.mark.integration
def test_denied_writes_have_no_side_effects_and_are_audited(client: TestClient, tokens: dict[str, str]) -> None:
    context = _context(client)

    def counts() -> tuple[int, int]:
        with context.sessions() as session:
            return (
                int(session.scalar(select(func.count()).select_from(LegalStandard)) or 0),
                int(session.scalar(select(func.count()).select_from(User)) or 0),
            )

    def denied() -> int:
        with context.sessions() as session:
            return int(
                session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == ACTION_AUTHORIZATION_DENIED))
                or 0
            )

    before, audited = counts(), denied()
    attempts = 0
    for role in (SUPERVISOR, RESEARCHER):
        headers = _headers(tokens[role])
        for method, path, body in (
            ("POST", "/api/v1/standards", _STANDARD),
            ("POST", "/api/v1/users", {"username": "intruder", "role": ADMIN}),
            ("POST", "/api/v1/alert-channels", {"name": "x", "channel_type": "webhook"}),
        ):
            assert client.request(method, path, headers=headers, json=body).status_code == 403
            attempts += 1
    assert counts() == before
    assert denied() == audited + attempts


@pytest.mark.integration
def test_admin_writes_standard_user_and_channel_without_echoing_credentials(
    client: TestClient, tokens: dict[str, str]
) -> None:
    headers = _headers(tokens[ADMIN])
    created = client.post("/api/v1/standards", headers=headers, json=_STANDARD)
    assert created.status_code == 201
    listed = client.get("/api/v1/standards", headers=_headers(tokens[RESEARCHER])).json()
    assert any(item["version"] == "e2e-1" for item in listed["items"])

    channel = client.post(
        "/api/v1/alert-channels",
        headers=headers,
        json={
            "name": "ops-hook",
            "channel_type": "webhook",
            "non_secret_config": {"url": "https://hooks.example.test/x"},
            "credential_ref": "OPS_HOOK_SECRET",
        },
    )
    assert channel.status_code == 201
    assert "OPS_HOOK_SECRET_VALUE" not in channel.text
    assert "secret" not in {key.lower() for key in channel.json()}

    assert client.patch("/api/v1/users/1", headers=headers, json={}).status_code in {400, 422}
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["role"] == ADMIN
    assert "users.write" in me["permissions"]
    researcher_me = client.get("/api/v1/auth/me", headers=_headers(tokens[RESEARCHER])).json()
    assert "users.write" not in researcher_me["permissions"]


@pytest.mark.integration
def test_deactivated_user_loses_access_and_logout_blocks_replay(client: TestClient, tokens: dict[str, str]) -> None:
    admin = _headers(tokens[ADMIN])
    users = client.get("/api/v1/users", headers=admin).json()["items"]
    researcher_id = next(item["id"] for item in users if item["username"] == "res-user")
    assert client.patch(f"/api/v1/users/{researcher_id}", headers=admin, json={"is_active": False}).status_code == 200
    assert client.get("/api/v1/monitoring-records", headers=_headers(tokens[RESEARCHER])).status_code == 401
    refused = client.post("/api/v1/auth/login", json={"username": "res-user", "password": _ROLE_PASSWORD + "x"})
    assert refused.status_code == 401

    supervisor = _headers(tokens[SUPERVISOR])
    assert client.get("/api/v1/alerts", headers=supervisor).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=supervisor).status_code == 204
    assert client.get("/api/v1/alerts", headers=supervisor).status_code == 401
    assert client.get("/api/v1/auth/me", headers=supervisor).status_code == 401
    with _context(client).sessions() as session:
        assert session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == ACTION_LOGOUT)) >= 1


@pytest.mark.integration
def test_first_login_token_only_reaches_me_logout_and_change_password(client: TestClient) -> None:
    first = _headers(_login(client, "admin", _BOOT))
    assert client.get("/api/v1/auth/me", headers=first).status_code == 200
    assert client.get("/api/v1/users", headers=first).status_code == 403
    assert client.post("/api/v1/standards", headers=first, json=_STANDARD).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=first).status_code == 204


@pytest.mark.integration
def test_login_failures_are_uniform_and_lock_the_account(client: TestClient, tokens: dict[str, str]) -> None:
    del tokens
    unknown = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "wrong-password"})
    wrong = client.post("/api/v1/auth/login", json={"username": "sup-user", "password": "wrong-password"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["code"] == wrong.json()["error"]["code"]
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]
    for _ in range(3):
        client.post("/api/v1/auth/login", json={"username": "sup-user", "password": "wrong-password"})
    locked = client.post("/api/v1/auth/login", json={"username": "sup-user", "password": _ROLE_PASSWORD + "x"})
    assert locked.status_code in {401, 423, 429}


@pytest.mark.integration
def test_chinese_pages_and_offline_static_assets(client: TestClient) -> None:
    for key, title in (
        ("overview", "总览"),
        ("monitoring", "监测历史"),
        ("compliance", "合规结果"),
        ("risk", "风险评估"),
        ("trend", "趋势预测"),
        ("alerts", "告警历史"),
        ("export", "数据导出"),
        ("report", "监督报告"),
        ("standards", "法律标准"),
        ("models", "模型管理"),
        ("users", "用户管理"),
        ("status", "系统状态"),
    ):
        page = client.get(f"/ui/{key}?role=管理员")
        assert page.status_code == 200
        assert title in page.text
        assert "cdn" not in page.text.lower()
    assert "环境监督平台" in client.get("/").text
    assert "登录" in client.get("/login").text
    assert "总览" in client.get("/ui/does-not-exist").text
    assert "预估结果，非执法依据" in client.get("/ui/report").text
    assert "模型不可用" in client.get("/ui/models").text
