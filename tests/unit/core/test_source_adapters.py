"""Source adapter registry and per-source license gate tests."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.v2.config import Settings
from app.v2.domains.collection.adapters import (
    ADAPTERS,
    OfficialSourceAdapter,
    QuotsoftAdapter,
    SourceLicenseError,
    adapter_keys,
    resolve_adapter,
)
from app.v2.shared.license import license_state


def _record(tmp_path, **overrides):
    payload = {
        "provider": "Quotsoft",
        "record_id": "trial-2026-10",
        "confirmed_by": "deployment-owner",
        "confirmed_at": "2026-10-01T12:00:00+00:00",
        "scope": "continuous_business_use",
        "evidence_sha256": "a" * 64,
        "reference": "audit://trial-2026-10",
    }
    payload.update(overrides)
    path = tmp_path / "source-license-confirmation.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _settings(path, **overrides):
    values = {
        "environment": "development",
        "source_provider": "quotsoft",
        "source_license_confirmed": True,
        "source_license_confirmation_file": path,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_trial_scope_requires_valid_until(tmp_path):
    path = _record(tmp_path, scope="trial_operation")
    state = license_state(_settings(path))
    assert state["state"] == "blocked"
    assert state["reason"] == "trial_scope_requires_valid_until"


def test_trial_authorization_blocks_collection_after_expiry(tmp_path):
    expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    path = _record(tmp_path, scope="trial_operation", valid_until=expired)
    settings = _settings(path)
    state = license_state(settings)
    assert state["state"] == "blocked"
    assert state["reason"] == "valid_until_expired"
    adapter = QuotsoftAdapter(db=None, store=None, configuration=settings)
    with pytest.raises(SourceLicenseError, match="valid_until_expired"):
        adapter.collect(datetime(2026, 10, 1).date(), datetime(2026, 10, 1).date(), "job", lambda _: None)


def test_valid_trial_authorization_allows_collection_gate(tmp_path, monkeypatch):
    future = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    path = _record(tmp_path, scope="trial_operation", valid_until=future)
    settings = _settings(path)
    assert license_state(settings)["state"] == "ok"
    calls = []
    monkeypatch.setattr(
        "app.v2.domains.collection.adapters.collect_range",
        lambda *args, **kwargs: calls.append(args) or {"inserted": 0},
    )
    adapter = QuotsoftAdapter(db="db", store="store", configuration=settings)
    result = adapter.collect(datetime(2026, 10, 1).date(), datetime(2026, 10, 1).date(), "job", lambda _: None)
    assert result == {"inserted": 0}
    assert calls


def test_unconfigured_license_still_allowed_outside_production(tmp_path, monkeypatch):
    settings = _settings(tmp_path / "missing.json", source_license_confirmed=False)
    assert license_state(settings)["state"] == "unconfigured"
    monkeypatch.setattr(
        "app.v2.domains.collection.adapters.collect_range",
        lambda *args, **kwargs: {"inserted": 0},
    )
    adapter = QuotsoftAdapter(db="db", store="store", configuration=settings)
    assert adapter.collect(datetime(2026, 10, 1).date(), datetime(2026, 10, 1).date(), "job", lambda _: None)


def test_production_requires_confirmed_license(tmp_path):
    settings = _settings(tmp_path / "missing.json", environment="production")
    adapter = QuotsoftAdapter(db=None, store=None, configuration=settings)
    with pytest.raises(SourceLicenseError):
        adapter.collect(datetime(2026, 10, 1).date(), datetime(2026, 10, 1).date(), "job", lambda _: None)


def test_provider_mismatch_blocks_even_with_valid_record(tmp_path):
    path = _record(tmp_path)
    settings = _settings(path, source_provider="official")
    state = license_state(settings)
    assert state["state"] == "blocked"
    assert state["provider_match"] is False


def test_settings_license_ready_requires_provider_match(tmp_path):
    path = _record(tmp_path)
    settings = Settings(
        secret_key="x" * 32,
        environment="test",
        database_url="postgresql+psycopg://x:x@localhost/x",
        source_license_confirmation_file=path,
        source_license_confirmed=True,
        source_provider="official",
    )
    assert settings.source_license_ready() is False
    settings.source_provider = "quotsoft"
    assert settings.source_license_ready() is True


def test_resolve_adapter_rejects_unknown_source_without_fallback():
    with pytest.raises(ValueError, match="禁止自动回退"):
        resolve_adapter("unknown-source", db=None, store=None, configuration=None)
    assert adapter_keys() == sorted(ADAPTERS)


def test_official_adapter_fails_explicitly_until_integrated(tmp_path):
    future = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    payload = {
        "provider": "北京市生态环境监测中心官方接口",
        "record_id": "official-1",
        "confirmed_by": "owner",
        "confirmed_at": "2026-10-01T12:00:00+00:00",
        "scope": "trial_operation",
        "evidence_sha256": "b" * 64,
        "reference": "audit://official-1",
        "valid_until": future,
    }
    path = tmp_path / "license.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    settings = _settings(path, source_provider="official")
    adapter = resolve_adapter("official", db=None, store=None, configuration=settings)
    assert isinstance(adapter, OfficialSourceAdapter)
    with pytest.raises(NotImplementedError, match="尚未接入"):
        adapter.collect(datetime(2026, 10, 1).date(), datetime(2026, 10, 1).date(), "job", lambda _: None)
    with pytest.raises(NotImplementedError, match="尚未接入"):
        adapter.import_file(b"x", "all")
