"""Regression tests for the incremental modular-monolith foundation."""

import json
import hashlib
import tarfile
from tempfile import TemporaryDirectory
from pathlib import Path

import pytest

from app.v2.shared.job_contracts import ArtifactRef, JobKind, JobResult, JobSpec, JobState
from app.v2.domains.jobs.service import JobReadService, JobSubmissionService
from app.v2.domains.monitoring.service import (
    AqiFilter,
    EvaluationFilter,
    DashboardFilter,
    ForecastFilter,
    ImputationFilter,
    MonitoringService,
    ObservationFilter,
    QualityFilter,
    StationDetailFilter,
    StationFilter,
    TimeseriesFilter,
)
from app.v2.domains.collection.service import CollectionService
from app.v2.domains.enforcement.service import EnforcementReadService, EnforcementWriteService, ListFilter
from app.v2.domains.auth.service import AuthenticationService
from app.v2.domains.admin.service import AdminReadService, AdminWriteService, NewAccount, UserAdministrationService
from app.v2.shared.errors import DomainError
from app.v2.domains.ml.service import ModelExecutionService
from app.v2.domains.jobs.worker import artifact_references
from app.v2.shared.backup_repository import file_manifest, referenced_payload_files
from app.v2.config import Settings


def test_job_contracts_are_strict_and_serializable() -> None:
    spec = JobSpec(kind="export", target_key="abc", parameters={"format": "csv"})
    assert spec.model_dump() == {
        "kind": "export",
        "parameters": {"format": "csv"},
        "target_key": "abc",
        "owner_id": None,
        "idempotency_key": None,
    }
    result = JobResult(state=JobState.SUCCEEDED)
    assert result.model_dump(mode="json")["state"] == "succeeded"


def test_job_contract_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        JobSpec(kind="export", target_key="abc", unexpected=True)


def test_job_contract_rejects_non_sha256_artifact_and_source_references() -> None:
    with pytest.raises(ValueError):
        ArtifactRef(kind="export", key="exports/a.csv", sha256="not-a-digest")
    with pytest.raises(ValueError):
        JobResult(state=JobState.SUCCEEDED, source_hashes=["not-a-digest"])


def test_job_contract_rejects_unknown_task_kind() -> None:
    with pytest.raises(ValueError):
        JobSpec(kind="unknown", target_key="abc")
    assert JobSpec(kind=JobKind.IMPORT, target_key="abc").kind is JobKind.IMPORT


def test_job_artifacts_register_models_and_derived_results() -> None:
    model = artifact_references("train", {
        "artifact_key": "models/aa/model.json",
        "artifact_sha256": "a" * 64,
        "artifact_kind": "model",
        "artifact_media_type": "application/json",
    })
    forecast = artifact_references("forecast", {
        "artifact_key": "derived/bb/result.json",
        "artifact_sha256": "b" * 64,
        "artifact_kind": "forecast",
    })
    assert model[0].kind == "model" and model[0].sha256 == "a" * 64
    assert forecast[0].kind == "forecast" and forecast[0].key.endswith("result.json")


def test_backup_manifest_includes_contract_artifacts() -> None:
    payload = {
        "artifact_key": "derived/bb/result.json",
        "artifact_sha256": "b" * 64,
        "_contract": {"artifacts": [{"key": "models/aa/model.json", "sha256": "a" * 64}]},
    }
    assert referenced_payload_files(payload) == {
        "derived/bb/result.json": "b" * 64,
        "models/aa/model.json": "a" * 64,
    }


def test_backup_manifest_includes_license_confirmation_record(tmp_path) -> None:
    confirmation = tmp_path / "source-license-confirmation.json"
    confirmation.write_text('{"record_id":"change-1"}', encoding="utf-8")

    class EmptySession:
        def scalars(self, statement):
            return []

    class SessionContext:
        def __enter__(self):
            return EmptySession()

        def __exit__(self, *exc):
            return False

    class EmptyDatabase:
        def sessions(self):
            return SessionContext()

    class Store:
        root = tmp_path

    expected = hashlib.sha256(confirmation.read_bytes()).hexdigest()
    assert file_manifest(EmptyDatabase(), Store()) == {
        "source-license-confirmation.json": expected
    }


def test_backup_manifest_uses_configured_license_confirmation_path(tmp_path) -> None:
    confirmation = tmp_path / "audits" / "quotsoft-confirmation.json"
    confirmation.parent.mkdir()
    confirmation.write_text('{"record_id":"change-2"}', encoding="utf-8")

    class EmptySession:
        def scalars(self, statement):
            return []

    class SessionContext:
        def __enter__(self):
            return EmptySession()

        def __exit__(self, *exc):
            return False

    class EmptyDatabase:
        def sessions(self):
            return SessionContext()

    class Store:
        root = tmp_path / "storage"

    expected = hashlib.sha256(confirmation.read_bytes()).hexdigest()
    assert file_manifest(EmptyDatabase(), Store(), confirmation_path=confirmation) == {
        "quotsoft-confirmation.json": expected
    }
    archive = tmp_path / "backup.tar.gz"
    from app.v2.shared.backup_repository import archive_files

    archive_files(EmptyDatabase(), Store(), archive, confirmation_path=confirmation)
    with tarfile.open(archive, "r:gz") as bundle:
        assert bundle.getnames() == ["quotsoft-confirmation.json"]


def test_domain_facades_import_without_web_application() -> None:
    pytest.importorskip("multipart")
    from app.v2.domains import admin, auth, enforcement, jobs, monitoring

    assert all(getattr(module, "router", None) is not None for module in (admin, auth, enforcement, jobs, monitoring))


def test_domain_model_facades_expose_only_their_aggregate_types() -> None:
    from app.v2.domains.enforcement.models import Attachment, Enterprise, Inspection
    from app.v2.domains.jobs.models import Job, Outbox
    from app.v2.domains.monitoring.models import Observation, Station

    assert {Attachment.__name__, Enterprise.__name__, Inspection.__name__} == {"Attachment", "Enterprise", "Inspection"}
    assert {Job.__name__, Outbox.__name__} == {"Job", "Outbox"}
    assert {Observation.__name__, Station.__name__} == {"Observation", "Station"}


def test_shared_contract_does_not_import_fastapi_or_sqlalchemy() -> None:
    source = Path(__file__).parents[3] / "app" / "v2" / "shared" / "job_contracts.py"
    import ast

    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        node.names[0].name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
    }
    imports.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert {"fastapi", "sqlalchemy"}.isdisjoint(imports)


def test_job_submission_service_is_idempotent_without_database() -> None:
    class Record:
        def __init__(self, identifier: str):
            self.id, self.status = identifier, "queued"

    class Port:
        def __init__(self):
            self.records = {}

        def find_existing(self, target_key, include_finished=False):
            return self.records.get(target_key)

        def create(self, spec):
            record = Record(str(len(self.records) + 1))
            self.records[spec.target_key] = record
            return record

    port = Port()
    service = JobSubmissionService(port)
    first = service.submit("export", {"format": "csv"}, "owner")
    second = service.submit("export", {"format": "csv"}, "owner")
    assert first.id == second.id
    assert service.submit("export", {"format": "csv"}, "owner", "request-1").id != first.id


def test_job_read_service_forwards_owner_scope_and_lifecycle() -> None:
    class Port:
        def list_jobs(self, status, owner_id, manager, page_number, page_size):
            return {"status": status, "owner_id": owner_id, "manager": manager, "page": page_number}

        def get_job(self, identifier, owner_id, manager):
            return {"id": identifier, "owner_id": owner_id, "manager": manager}

        def cancel_job(self, identifier, owner_id, manager, actor_id):
            return {"id": identifier, "actor_id": actor_id, "manager": manager}

    service = JobReadService(Port())
    assert service.list_jobs("queued", "user-1", False, 2, 20)["owner_id"] == "user-1"
    assert service.get_job("job-1", "admin", True)["manager"] is True
    assert service.cancel_job("job-1", "user-1", False, "user-1")["actor_id"] == "user-1"


def test_monitoring_service_uses_a_port_and_keeps_filters_explicit() -> None:
    class Port:
        def cities(self):
            return {"items": ["city"]}

        def stations(self, filters):
            return {"city_id": filters.city_id}

        def observations(self, filters):
            return {"pollutant": filters.pollutant, "page": filters.page_number}

        def station_detail(self, filters):
            return {"station_id": filters.station_id}

        def evaluations(self, filters):
            return {"status": filters.status, "page": filters.page_number}

        def quality(self, filters, license_confirmed):
            return {"city_id": filters.city_id, "license_confirmed": license_confirmed}

        def aqi(self, filters):
            return {"station_id": filters.station_id}

        def forecasts(self, filters):
            return {"job_id": filters.job_id}

        def imputations(self, filters):
            return {"station_id": filters.station_id}

        def timeseries(self, filters):
            return {"resolution": filters.resolution, "stations": filters.station_ids}

        def dashboard(self, filters):
            return {"city_id": filters.city_id, "include_pending": filters.include_pending}

    service = MonitoringService(Port())
    assert service.list_cities() == {"items": ["city"]}
    assert service.list_stations(StationFilter(city_id="beijing")) == {"city_id": "beijing"}
    assert service.list_observations(ObservationFilter(pollutant="PM2.5", page_number=2)) == {
        "pollutant": "PM2.5", "page": 2
    }
    assert service.get_station_detail(StationDetailFilter("station-1")) == {"station_id": "station-1"}
    assert service.list_evaluations(EvaluationFilter(status="warning", page_number=3)) == {
        "status": "warning", "page": 3
    }
    assert service.get_quality(QualityFilter(city_id="beijing"), True) == {
        "city_id": "beijing", "license_confirmed": True
    }
    assert service.list_aqi(AqiFilter("station-1", None, None)) == {"station_id": "station-1"}
    assert service.list_forecasts(ForecastFilter("station-1", job_id="job-1")) == {"job_id": "job-1"}
    assert service.list_imputations(ImputationFilter("station-1", None, None)) == {"station_id": "station-1"}
    assert service.get_timeseries(TimeseriesFilter(None, None, "PM2.5", ("station-1",))) == {
        "resolution": "hour", "stations": ("station-1",)
    }
    assert service.get_dashboard(DashboardFilter(city_id="beijing", include_pending=False)) == {
        "city_id": "beijing", "include_pending": False
    }


def test_collection_service_keeps_legacy_algorithm_behind_a_port() -> None:
    class Port:
        def collect(self, start, end, job_id, progress):
            progress(50)
            return {"job_id": job_id, "inserted": 1}

        def import_file(self, content, kind):
            return {"kind": kind, "bytes": len(content)}

    service = CollectionService(Port())
    assert service.collect(None, None, "job-1", lambda _: None)["inserted"] == 1
    assert service.import_file(b"csv", "all")["bytes"] == 3


def test_enforcement_read_service_forwards_explicit_filters() -> None:
    class Port:
        def enterprises(self, filters):
            return {"kind": "enterprise", "query": filters.query}

        def leads(self, filters):
            return {"kind": "lead", "status": filters.status}

        def inspections(self, filters):
            return {"kind": "inspection", "page": filters.page_number}

    service = EnforcementReadService(Port())
    assert service.list_enterprises(ListFilter(query="factory"))["query"] == "factory"
    assert service.list_leads(ListFilter(status="pending"))["status"] == "pending"
    assert service.list_inspections(ListFilter(page_number=2))["page"] == 2


def test_enforcement_write_service_forwards_workflow_commands() -> None:
    class Port:
        def create_enterprise(self, values, actor_id): return {"kind": "enterprise"}
        def enterprise_detail(self, identifier, user): return {"id": identifier}
        def update_enterprise(self, identifier, values, actor_id): return {"id": identifier}
        def add_enterprise_record(self, identifier, values, actor_id): return {"id": identifier}
        def create_lead(self, values, actor_id): return {"kind": "lead"}
        def assign_lead(self, identifier, values, actor_id): return {"id": identifier}
        def claim_lead(self, identifier, actor_id): return {"id": identifier}
        def reject_lead(self, identifier, reason, actor_id): return {"id": identifier}
        def inspection_detail(self, identifier, user): return {"id": identifier}
        def save_inspection(self, identifier, values, actor_id): return {"id": identifier}
        def transition(self, identifier, values, actor_id, manager): return {"id": identifier}
        def add_rectification(self, identifier, values, actor_id): return {"id": identifier}
        def update_rectification(self, identifier, rectification_id, values, actor_id): return {"id": rectification_id}
        def upload_attachment(self, content, filename, inspection_id, enterprise_id, replaces_id, actor_id): return {"filename": filename}
        def prepare_attachment_download(self, identifier, user): return {"id": identifier}

    service = EnforcementWriteService(Port())
    assert service.create_enterprise({}, "u")["kind"] == "enterprise"
    assert service.enterprise_detail("e", None)["id"] == "e"
    assert service.update_enterprise("e", {}, "u")["id"] == "e"
    assert service.add_enterprise_record("e", {}, "u")["id"] == "e"
    assert service.create_lead({}, "u")["kind"] == "lead"
    assert service.assign_lead("l", {}, "u")["id"] == "l"
    assert service.claim_lead("l", "u")["id"] == "l"
    assert service.reject_lead("l", "reason", "u")["id"] == "l"
    assert service.inspection_detail("i", None)["id"] == "i"
    assert service.save_inspection("i", {}, "u")["id"] == "i"
    assert service.transition("i", {}, "u", True)["id"] == "i"
    assert service.add_rectification("i", {}, "u")["id"] == "i"
    assert service.update_rectification("i", "r", {}, "u")["id"] == "r"
    assert service.upload_attachment(b"x", "a.txt", "i", None, None, "u")["filename"] == "a.txt"
    assert service.prepare_attachment_download("a", None)["id"] == "a"


def test_collection_and_evaluation_compatibility_facades_do_not_construct_sql() -> None:
    import ast

    for relative in ("collection.py", "evaluation.py", "ml.py", "exports.py", "datasets.py", "tasks.py", "scheduler.py", "notifications.py", "seed.py", "backup.py"):
        source = Path(__file__).parents[3] / "app" / "v2" / relative
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imports = {
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "sqlalchemy" not in imports
        assert not any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"select", "text", "update"}
            for node in ast.walk(tree)
        )


def test_all_compatibility_routers_keep_sql_out_of_the_http_boundary() -> None:
    """Every v2 HTTP facade must delegate SQL to a domain adapter."""
    import ast

    root = Path(__file__).parents[3] / "app" / "v2"
    router_files = {
        "admin.py", "auth.py", "collection.py", "datasets.py", "enforcement.py",
        "evaluation.py", "exports.py", "forecasting.py", "imputation.py", "jobs.py",
        "ml.py", "monitoring.py", "notifications.py", "scheduler.py", "seed.py", "tasks.py",
    }
    violations = []
    for name in router_files:
        source = root / name
        tree = ast.parse(source.read_text(encoding="utf-8"))
        if any(
            isinstance(node, (ast.Import, ast.ImportFrom))
            and ((isinstance(node, ast.Import) and any(alias.name == "sqlalchemy" for alias in node.names))
                 or (isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("sqlalchemy")))
            for node in ast.walk(tree)
        ):
            violations.append(f"{name}: sqlalchemy import")
        if any(
            isinstance(node, ast.Call)
            and ((isinstance(node.func, ast.Name) and node.func.id in {"select", "text", "update", "delete"})
                 or (isinstance(node.func, ast.Attribute) and node.func.attr in {"execute", "scalar", "scalars", "add", "flush"}))
            for node in ast.walk(tree)
        ):
            violations.append(f"{name}: SQL/session call")
    assert not violations, violations


def test_application_services_do_not_import_web_or_orm_layers() -> None:
    import ast

    services_root = Path(__file__).parents[3] / "app" / "v2" / "domains"
    for source in sorted(services_root.glob("*/service.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imports = {
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert {"fastapi", "sqlalchemy"}.isdisjoint(imports), source


def test_http_facades_do_not_import_legacy_query_modules_directly() -> None:
    """Legacy algorithms enter through an explicit adapter/repository seam."""
    import ast

    root = Path(__file__).parents[3] / "app" / "v2"
    router_files = {
        "admin.py", "auth.py", "collection.py", "datasets.py", "enforcement.py",
        "evaluation.py", "exports.py", "forecasting.py", "imputation.py", "jobs.py",
        "ml.py", "monitoring.py", "notifications.py", "scheduler.py", "seed.py", "tasks.py",
    }
    violations = []
    for name in router_files:
        source = root / name
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith(".legacy"):
                violations.append(f"{name}: {node.module}")
    assert not violations, violations


def test_monitoring_router_delegates_query_construction_to_the_read_port() -> None:
    import ast

    source = Path(__file__).parents[3] / "app" / "v2" / "monitoring.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "sqlalchemy" not in imports
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"select", "func"}
        for node in ast.walk(tree)
    )


def test_jobs_router_delegates_lifecycle_queries_to_the_read_port() -> None:
    import ast

    source = Path(__file__).parents[3] / "app" / "v2" / "jobs.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "sqlalchemy" not in imports
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"select", "func"}
        for node in ast.walk(tree)
    )


def test_admin_router_delegates_catalog_mutations_to_the_write_port() -> None:
    import ast

    source = Path(__file__).parents[3] / "app" / "v2" / "admin.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "sqlalchemy" not in imports
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"execute", "scalar", "scalars", "add", "flush"}
        for node in ast.walk(tree)
    )


def test_enforcement_router_delegates_workflow_queries_to_the_write_port() -> None:
    import ast

    source = Path(__file__).parents[3] / "app" / "v2" / "enforcement.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "sqlalchemy" not in imports
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"select", "func"}
        for node in ast.walk(tree)
    )


def test_authentication_service_commits_login_and_password_use_cases_without_orm() -> None:
    from datetime import datetime, timezone

    class User:
        id = "user-1"
        password_hash = "old-hash"
        active = True
        failed_logins = 0
        locked_until = None

    class Port:
        def __init__(self):
            self.user = User()
            self.sessions = []
            self.audit_events = []

        def find_user(self, username, *, for_update=False):
            return self.user if username == "alice" else None

        def resolve_session(self, token_hash):
            return None, None

        def create_session(self, user_id, token_hash, csrf_hash, expires_at):
            self.sessions.append((user_id, token_hash, csrf_hash, expires_at))

        def revoke_session(self, session_id):
            pass

        def revoke_user_sessions(self, user_id):
            self.sessions.clear()

        def update_password(self, user_id, password_hash):
            self.user.password_hash = password_hash

        def audit(self, actor_id, action, detail=None):
            self.audit_events.append((actor_id, action, detail))

    port = Port()
    service = AuthenticationService(port)
    current = lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)
    outcome = service.login(
        "alice", "secret", dummy_hash="dummy", session_hours=8,
        max_failures=5, lock_minutes=15, now=current,
        verify_password=lambda password, hashed: password == "secret" and hashed == "old-hash",
        new_token=iter(("token", "csrf")).__next__, digest=lambda value: f"hash:{value}",
    )
    assert outcome.accepted and len(port.sessions) == 1
    changed = service.change_password(
        "user-1", "old-hash", "secret", "new-secret",
        verify_password=lambda password, hashed: password == "secret" and hashed == "old-hash",
        hash_password=lambda value: f"hashed:{value}",
    )
    assert changed.changed and port.user.password_hash == "hashed:new-secret"
    assert [event[1] for event in port.audit_events] == ["LOGIN", "PASSWORD_CHANGED"]


def test_user_administration_service_audits_updates_and_protects_current_admin() -> None:
    class Port:
        def __init__(self):
            self.audit_events = []
            self.revoked = []

        def people(self): return {"items": []}
        def users(self): return {"items": []}
        def audits(self, page_number): return {"page": page_number}
        def get_user(self, identifier): return {"id": identifier}
        def create_user(self, account): return {"id": "new-user", "role": account.role}
        def update_user(self, identifier, role, active): return {"id": identifier, "role": role, "active": active}
        def revoke_user_sessions(self, identifier): self.revoked.append(identifier)
        def audit(self, actor_id, action, identifier, detail): self.audit_events.append((actor_id, action, identifier, detail))

    port = Port()
    service = UserAdministrationService(port)
    created = service.create_user("admin", NewAccount("alice", "Alice", "研究者", "hash"))
    assert created["id"] == "new-user"
    updated = service.update_user("admin", "user-2", "研究者", False)
    assert updated["active"] is False and port.revoked == ["user-2"]
    assert [event[1] for event in port.audit_events] == ["CREATE_USER", "UPDATE_USER"]

    with pytest.raises(DomainError, match="不能禁用"):
        service.update_user("admin", "admin", "研究者", True)


def test_admin_read_service_forwards_catalog_and_user_context() -> None:
    class Port:
        def standards(self): return {"kind": "standards"}
        def laws(self): return {"kind": "laws"}
        def notifications(self, user_id): return {"user_id": user_id}
        def sources(self, license_summary): return {"license_confirmed": license_summary["ready"]}
        def models(self): return {"kind": "models"}
        def channels(self): return {"kind": "channels"}

    service = AdminReadService(Port())
    assert service.list_standards()["kind"] == "standards"
    assert service.list_laws()["kind"] == "laws"
    assert service.list_notifications("user-1")["user_id"] == "user-1"
    assert service.list_sources({"ready": True})["license_confirmed"] is True
    assert service.list_models()["kind"] == "models"
    assert service.list_channels()["kind"] == "channels"


def test_admin_write_service_forwards_catalog_mutations() -> None:
    class Port:
        def mark_notification_read(self, identifier, user_id): return {"id": identifier, "user_id": user_id}
        def activate_model(self, identifier, actor_id): return {"id": identifier, "actor_id": actor_id}
        def rollback_model(self, task, actor_id): return {"task": task, "actor_id": actor_id}
        def add_law(self, values, actor_id): return {"kind": "law", "actor_id": actor_id}
        def update_station(self, identifier, values, actor_id): return {"id": identifier}
        def add_alias(self, identifier, values, actor_id): return {"id": identifier}
        def add_channel(self, values, actor_id): return {"kind": "channel"}
        def toggle_channel(self, identifier, enabled, actor_id): return {"enabled": enabled}
        def end_standard(self, identifier, values, actor_id): return {"id": identifier}
        def end_law(self, identifier, values, actor_id): return {"id": identifier}
        def add_standard(self, values, actor_id): return {"kind": "standard"}

    service = AdminWriteService(Port())
    assert service.mark_notification_read("n-1", "u-1")["user_id"] == "u-1"
    assert service.activate_model("m-1", "u-1")["actor_id"] == "u-1"
    assert service.rollback_model("forecast", "u-1")["task"] == "forecast"
    assert service.add_law({}, "u-1")["kind"] == "law"
    assert service.update_station("s-1", {}, "u-1")["id"] == "s-1"
    assert service.add_alias("s-1", {}, "u-1")["id"] == "s-1"
    assert service.add_channel({}, "u-1")["kind"] == "channel"
    assert service.toggle_channel("c-1", True, "u-1")["enabled"] is True
    assert service.end_standard("std-1", {}, "u-1")["id"] == "std-1"
    assert service.end_law("law-1", {}, "u-1")["id"] == "law-1"
    assert service.add_standard({}, "u-1")["kind"] == "standard"


def test_model_execution_service_keeps_legacy_algorithm_behind_a_port() -> None:
    class Port:
        def execute(self, db, store, settings, job, progress):
            progress(50)
            return {"job_id": job.id, "status": "validated"}

    class Job:
        id = "model-job-1"

    seen = []
    result = ModelExecutionService(Port()).execute(None, None, None, Job(), seen.append)
    assert result == {"job_id": "model-job-1", "status": "validated"}
    assert seen == [50]


def test_domain_and_compatibility_modules_do_not_bypass_domain_model_ownership() -> None:
    import ast

    root = Path(__file__).parents[3] / "app" / "v2"
    violations = []
    for source in root.rglob("*.py"):
        if source.name == "models.py" or "migrations" in source.parts or "__pycache__" in source.parts:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        if any(isinstance(node, ast.ImportFrom) and node.module == "app.v2.models"
               for node in ast.walk(tree)):
            violations.append(str(source.relative_to(root)))
    for source in (Path(__file__).parents[3] / "scripts").glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        if any(isinstance(node, ast.ImportFrom) and node.module == "app.v2.models"
               for node in ast.walk(tree)):
            violations.append(str(source.relative_to(Path(__file__).parents[3])))
    assert not violations, f"domain, compatibility and operational modules must import owning model modules directly: {violations}"


def test_runtime_openapi_matches_frontend_contract_snapshot() -> None:
    """Keep generated frontend paths and response status contracts in sync."""
    from app.v2.main import create_app

    repository = Path(__file__).parents[3]
    snapshot = json.loads((repository / "frontend" / "openapi.json").read_text(encoding="utf-8"))
    with TemporaryDirectory() as storage:
        settings = Settings(
            secret_key="local-development-secret-key-32-characters",
            database_url="sqlite+pysqlite:///:memory:",
            environment="test",
            storage_root=storage,
        )
        runtime = create_app(settings).openapi()

    assert runtime == snapshot


def test_v2_user_messages_contain_no_encoding_replacement_artifacts() -> None:
    """Keep the migrated HTTP surface readable after source-file rewrites."""
    root = Path(__file__).parents[3] / "app" / "v2"
    forbidden = ("??", "鏌", "浠", "杈", "�")
    violations = []
    for source in root.rglob("*.py"):
        if "__pycache__" in source.parts:
            continue
        contents = source.read_text(encoding="utf-8")
        if any(marker in contents for marker in forbidden):
            violations.append(str(source.relative_to(root)))
    assert not violations, f"v2 source contains encoding replacement artifacts: {violations}"
