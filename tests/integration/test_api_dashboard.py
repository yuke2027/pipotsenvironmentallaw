"""API and dashboard checks against a temporary database."""

from __future__ import annotations

import _socket
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import SettingsStartupError, load_settings
from app.db.session import sqlite_file_url
from app.main import create_app

_PASSWORD = "AdminPass#2026"


def _allow_loopback(self: socket.socket, address: object) -> None:
    """Allow the in-process test portal on loopback and nowhere else."""

    host = address[0] if isinstance(address, tuple) and address else ""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise AssertionError("Real socket access is blocked in tests; use MockTransport or a fake adapter.")
    _socket.socket.connect(self, address)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(socket.socket, "connect", _allow_loopback)
    settings = load_settings(
        _env_file=None,
        jwt_secret="unit-test-jwt-secret-value",
        database_url=sqlite_file_url(tmp_path / "app.db"),
        project_root=tmp_path,
        database_path=tmp_path / "app.db",
    )
    app = create_app(settings, admin_password=_PASSWORD)
    with TestClient(app) as test_client:
        yield test_client


def _token(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _admin_token(client: TestClient) -> str:
    first = _token(client, "admin", _PASSWORD)
    changed = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {first}"},
        json={"current_password": _PASSWORD, "new_password": "AdminPass#changed"},
    )
    assert changed.status_code == 200
    return _token(client, "admin", "AdminPass#changed")


@pytest.mark.integration
def test_health_login_and_first_password_change(client: TestClient) -> None:
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.json()
    assert body["service"] == "ok"
    assert body["database"] == "ok"
    assert body["models"]["saits"] is None
    assert body["imputation_available"] is False
    first = _token(client, "admin", _PASSWORD)
    denied = client.get("/api/v1/monitoring-records", headers={"Authorization": f"Bearer {first}"})
    assert denied.status_code == 403
    admin = _admin_token(client)
    allowed = client.get("/api/v1/monitoring-records", headers={"Authorization": f"Bearer {admin}"})
    assert allowed.status_code == 200
    assert allowed.json()["total"] == 0
    missing = client.get("/api/v1/standards")
    assert missing.status_code == 401


@pytest.mark.integration
def test_role_matrix_retrain_and_dashboard(client: TestClient) -> None:
    admin = _admin_token(client)
    headers = {"Authorization": f"Bearer {admin}"}
    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={"username": "researcher-one", "role": "研究者", "temporary_password": "TempPass#2026"},
    )
    assert created.status_code == 201
    assert created.json()["temporary_password"] == "TempPass#2026"
    researcher_first = _token(client, "researcher-one", "TempPass#2026")
    client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {researcher_first}"},
        json={"current_password": "TempPass#2026", "new_password": "Research#2026"},
    )
    researcher = _token(client, "researcher-one", "Research#2026")
    forbidden = client.post(
        "/api/v1/standards",
        headers={"Authorization": f"Bearer {researcher}"},
        json={
            "standard_key": "PM25",
            "version": "9",
            "pollutant": "PM2.5",
            "statistic_basis": "24h_mean",
            "limit_value": 75,
        },
    )
    assert forbidden.status_code == 403
    standards = client.get("/api/v1/standards", headers={"Authorization": f"Bearer {researcher}"})
    assert standards.status_code == 200
    assert standards.json()["total"] > 0
    retrain = client.post("/api/v1/models/retrain", headers=headers)
    assert retrain.status_code == 202
    assert retrain.json()["job_id"]
    home = client.get("/")
    assert home.status_code == 200
    assert "环境监督平台" in home.text
    assert "总览" in home.text
    risk = client.get("/ui/risk?role=监管人员")
    assert "预估结果，非执法依据" in risk.text
    assert "告警" in risk.text
    researcher_page = client.get("/ui/risk?role=研究者")
    assert "告警" not in researcher_page.text
    models = client.get("/ui/models?role=管理员")
    assert "模型不可用" in models.text
    chart = client.get("/static/chart.js")
    assert chart.status_code == 200
    assert "cdn" not in chart.text.lower()
    assert "Chart" in chart.text


@pytest.mark.unit
def test_missing_jwt_secret_fails_before_the_app_is_built(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("ESP_JWT_SECRET", raising=False)
    with pytest.raises(SettingsStartupError) as caught:
        load_settings(_env_file=None)
    assert "JWT_SECRET" in caught.value.field_names
