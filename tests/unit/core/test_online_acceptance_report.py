import json
import time
from types import SimpleNamespace

from datetime import datetime, timezone

from scripts.online_acceptance_report import apply_acceptance_gates, earliest_review_at, latest_backup_evidence
from scripts.verify_acceptance import evaluate_report
from app.v2.shared.license import read_license_confirmation
from app.v2.config import Settings
from app.v2.domains.jobs import scheduler_worker
from app.v2.domains.jobs.scheduler_worker import schedule_daily


def test_latest_backup_evidence_returns_minimal_verified_summary(tmp_path):
    older = tmp_path / "older" / "restore-verification.json"
    newer = tmp_path / "newer" / "restore-verification.json"
    older.parent.mkdir(); newer.parent.mkdir()
    older.write_text(json.dumps({"restored_file_count": 1, "file_checksums": "verified"}), encoding="utf-8")
    time.sleep(0.01)
    newer.write_text(json.dumps({"restored_file_count": 7, "file_checksums": "all verified"}), encoding="utf-8")
    result = latest_backup_evidence(tmp_path)
    assert result["available"] is True
    assert result["restored_file_count"] == 7
    assert result["checksums_verified"] is True
    assert "file_checksums" not in result


def test_latest_backup_evidence_reports_missing_artifact(tmp_path):
    assert latest_backup_evidence(tmp_path) == {"available": False}


def test_license_confirmation_requires_auditable_fields_and_timezone(tmp_path):
    path = tmp_path / "source-license-confirmation.json"
    path.write_text(json.dumps({
        "provider": "Quotsoft",
        "record_id": "change-2026-10-01",
        "confirmed_by": "deployment-owner",
        "confirmed_at": "2026-10-01T12:00:00+00:00",
        "scope": "continuous_business_use",
        "evidence_sha256": "a" * 64,
        "reference": "audit://change-2026-10-01",
    }), encoding="utf-8")
    result = read_license_confirmation(path)
    assert result["valid"] is True
    assert result["record_id"] == "change-2026-10-01"
    assert "evidence_sha256" not in result


def test_license_confirmation_rejects_missing_or_future_records(tmp_path):
    missing = read_license_confirmation(tmp_path / "missing.json")
    assert missing["valid"] is False
    assert missing["reason"] == "confirmation_file_missing"
    future = tmp_path / "future.json"
    future.write_text(json.dumps({
        "provider": "Quotsoft", "record_id": "future", "confirmed_by": "owner",
        "confirmed_at": "2999-01-01T00:00:00+00:00", "scope": "continuous_business_use",
        "evidence_sha256": "b" * 64, "reference": "audit://future",
    }), encoding="utf-8")
    result = read_license_confirmation(future)
    assert result["valid"] is False
    assert result["reason"] == "confirmed_at_is_in_the_future"


def test_settings_require_both_switch_and_confirmation_record(tmp_path):
    path = tmp_path / "source-license-confirmation.json"
    payload = {
        "provider": "Quotsoft",
        "record_id": "change-2026-10-01",
        "confirmed_by": "deployment-owner",
        "confirmed_at": "2026-10-01T12:00:00+00:00",
        "scope": "continuous_business_use",
        "evidence_sha256": "a" * 64,
        "reference": "audit://change-2026-10-01",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    settings = Settings(
        secret_key="x" * 32,
        environment="production",
        cookie_secure=True,
        source_license_confirmation_file=path,
        source_license_confirmed=False,
    )
    assert settings.source_license_ready() is False
    settings.source_license_confirmed = True
    assert settings.source_license_ready() is True


def test_production_scheduler_does_not_touch_database_without_license():
    class NoDatabaseAccess:
        def transaction(self):
            raise AssertionError("scheduler must stop before opening a transaction")

    settings = SimpleNamespace(environment="production", source_license_ready=lambda: False)
    schedule_daily(
        NoDatabaseAccess(),
        settings,
        local_now=datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc),
    )


def test_scheduler_daily_uses_local_previous_day_and_seven_day_window(monkeypatch):
    calls = []

    class Transaction:
        def __enter__(self):
            return object()

        def __exit__(self, *_):
            return False

    class Database:
        def transaction(self):
            return Transaction()

    settings = SimpleNamespace(environment="development", source_license_ready=lambda: False)
    monkeypatch.setattr(
        scheduler_worker,
        "enqueue",
        lambda session, kind, payload, dedupe: calls.append((kind, payload, dedupe)),
    )
    schedule_daily(
        Database(),
        settings,
        local_now=datetime(2026, 10, 3, 3, 30, tzinfo=timezone.utc),
    )

    assert calls == [
        (
            "collect",
            {"start": "2026-09-26", "end": "2026-10-02"},
            "daily:2026-10-03",
        )
    ]


def test_production_scheduler_allows_daily_collection_with_valid_license(monkeypatch):
    calls = []

    class Transaction:
        def __enter__(self):
            return object()

        def __exit__(self, *_):
            return False

    class Database:
        def transaction(self):
            return Transaction()

    settings = SimpleNamespace(environment="production", source_license_ready=lambda: True)
    monkeypatch.setattr(
        scheduler_worker,
        "enqueue",
        lambda session, kind, payload, dedupe: calls.append((kind, payload, dedupe)),
    )
    schedule_daily(
        Database(),
        settings,
        local_now=datetime(2026, 10, 3, 3, 30, tzinfo=timezone.utc),
    )

    assert calls and calls[0][0] == "collect"


def test_earliest_review_at_is_exactly_seven_days_after_window_start():
    since = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)
    assert earliest_review_at(since) == "2026-10-08T14:00:00+00:00"


def _report(elapsed=True, statuses=None):
    statuses = statuses or ["succeeded"] * 7
    return {"seven_full_days_elapsed": elapsed, "days": [
        {"collection_jobs": [{"status": status}], "source_attempt_counts": {"success": 1}}
        for status in statuses
    ], "backup_evidence": {"available": True, "checksums_verified": True}}


def test_acceptance_requires_seven_elapsed_days_and_one_job_each_day():
    result = apply_acceptance_gates(_report(elapsed=False), source_license_confirmed=True)
    assert result["collection_coverage_passed"] is False
    assert result["production_signoff_passed"] is False


def test_partial_jobs_count_as_covered_but_license_remains_independent():
    result = apply_acceptance_gates(_report(statuses=["partial"] * 7), source_license_confirmed=False)
    assert result["collection_coverage_passed"] is True
    assert result["license_gate_passed"] is False
    assert result["production_signoff_passed"] is False


def test_failed_or_missing_day_blocks_coverage_even_with_license():
    statuses = ["succeeded", "failed", "succeeded", "succeeded", "succeeded", "succeeded", "succeeded"]
    result = apply_acceptance_gates(_report(statuses=statuses), source_license_confirmed=True)
    assert result["collection_coverage_passed"] is False
    assert result["license_gate_passed"] is True
    assert result["production_signoff_passed"] is False


def test_missing_source_successes_block_coverage_even_with_successful_job():
    report = _report()
    report["days"][3]["source_attempt_counts"] = {"failed": 2}
    result = apply_acceptance_gates(report, source_license_confirmed=True)
    assert result["collection_coverage_passed"] is False
    assert result["production_signoff_passed"] is False


def test_all_gates_pass_only_when_coverage_and_license_are_true():
    result = apply_acceptance_gates(_report(), source_license_confirmed=True)
    assert result["production_signoff_passed"] is True
    assert "coverage alone does not approve production" in result["review_required"]


def test_missing_or_unverified_backup_blocks_production_signoff():
    report = _report()
    report["backup_evidence"] = {"available": True, "checksums_verified": False}
    result = apply_acceptance_gates(report, source_license_confirmed=True)
    assert result["backup_gate_passed"] is False
    assert result["production_signoff_passed"] is False


def test_license_boolean_cannot_override_invalid_evidence():
    report = _report()
    report["license_evidence"] = {"available": True, "valid": False}
    result = apply_acceptance_gates(report, source_license_confirmed=True)
    assert result["license_gate_passed"] is False
    assert result["production_signoff_passed"] is False


def test_verify_acceptance_reports_failed_gates_without_mutation():
    report = {gate: True for gate in (
        "seven_full_days_elapsed", "collection_coverage_passed", "license_gate_passed",
        "backup_gate_passed", "production_signoff_passed",
    )}
    report["license_gate_passed"] = False
    result = evaluate_report(report)
    assert result["passed"] is False
    assert result["failed_gates"] == ["license_gate_passed"]
    assert report["license_gate_passed"] is False
