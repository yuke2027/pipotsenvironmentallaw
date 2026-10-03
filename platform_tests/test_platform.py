from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import hashlib
import unittest

import httpx
from sqlalchemy import func, select

from app.v2.collection import collect_range, import_file, parse_wide
from app.v2.evaluation import daily_statistic, evaluate_range, subindex
from app.v2.jobs import enqueue
from app.v2.models import Audit, Evaluation, Job, LoginSession, Observation, Outbox, SourceFile, User, WorkflowEvent
from app.v2.scheduler import publish_outbox, recover_stalled
from app.v2.tasks import run_job
from platform_tests.support import DatabaseTest, PASSWORD, daily_csv


class AuthTests(DatabaseTest):
    def test_failed_login_count_and_audit_commit(self):
        with httpx.Client(): pass
        client = self.client()
        for _ in range(5):
            result = client.post("/api/v2/auth/login", json={"username": "officer", "password": "incorrect"})
            self.assertEqual(result.status_code, 401)
        with self.db.sessions() as session:
            user = session.get(User, self.users["officer"])
            self.assertEqual(user.failed_logins, 5)
            self.assertIsNotNone(user.locked_until)
            self.assertEqual(session.scalar(select(func.count()).select_from(Audit).where(Audit.action == "LOGIN_FAILED")), 5)
        self.assertEqual(client.post("/api/v2/auth/login", json={"username": "officer", "password": PASSWORD}).status_code, 401)

    def test_csrf_revocation_and_denied_audit(self):
        client = self.client("researcher")
        self.assertEqual(client.get("/api/v2/enterprises").status_code, 403)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Audit).where(Audit.action == "ACCESS_DENIED")), 1)
            event = session.scalar(select(Audit).where(Audit.action == "ACCESS_DENIED"))
            self.assertEqual(event.object_type, "route")
            self.assertEqual(event.detail, {"path": "/api/v2/enterprises"})
        csrf = client.headers.pop("X-CSRF-Token")
        self.assertEqual(client.post("/api/v2/auth/logout").status_code, 403)
        client.headers["X-CSRF-Token"] = csrf
        self.assertEqual(client.post("/api/v2/auth/logout").status_code, 204)
        self.assertEqual(client.get("/api/v2/auth/me").status_code, 401)

    def test_first_login_change_revokes_all(self):
        with self.db.transaction() as session: session.get(User, self.users["officer"]).must_change_password = True
        client = self.client("officer")
        self.assertEqual(client.get("/api/v2/stations").status_code, 403)
        result = client.post("/api/v2/auth/change-password", json={"current_password": PASSWORD, "new_password": "A-different-new-password!"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), {"message": "密码已更新，请重新登录"})
        self.assertEqual(client.get("/api/v2/auth/me").status_code, 401)


class DataTests(DatabaseTest):
    def test_duplicate_revision_and_expected_date(self):
        first = daily_csv(value=70)
        self.assertGreater(import_file(self.db, self.store, first, "all")["inserted"], 0)
        self.assertEqual(import_file(self.db, self.store, first, "all")["inserted"], 0)
        import_file(self.db, self.store, daily_csv(value=90), "all")
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(SourceFile)), 2)
            self.assertEqual(session.scalar(select(func.count()).select_from(SourceFile).where(SourceFile.is_current.is_(True))), 1)
        with self.assertRaises(ValueError): import_file(self.db, self.store, first, "all", expected_date=date(2026, 9, 29))
        result = self.client().get("/api/v2/observations?pollutant=PM2.5").json()
        self.assertTrue(all(r["value"] == 90 for r in result["items"]))
        self.assertNotIn("storage_key", str(result))

    def test_concurrent_import_is_idempotent(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: import_file(self.db, self.store, daily_csv(), "all"), range(2)))
        self.assertEqual(sum(r["inserted"] for r in results), 144)
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Observation)), 144)

    def test_standard_versions_incomplete_gases_and_aqi(self):
        for day in ["20250201", "20260930"]: import_file(self.db, self.store, daily_csv(day, value=70), "all")
        result = evaluate_range(self.db, date(2025, 2, 1), date(2025, 2, 1), "test", lambda _: None)
        evaluate_range(self.db, date(2026, 9, 30), date(2026, 9, 30), "test", lambda _: None)
        with self.db.sessions() as session:
            records = session.scalars(select(Evaluation).where(Evaluation.pollutant == "PM2.5")).all()
            self.assertEqual({r.status for r in records if r.local_date.year == 2025}, {"within"})
            self.assertEqual({r.status for r in records if r.local_date.year == 2026}, {"exceeded"})
            self.assertEqual(session.scalar(select(Evaluation.status).where(Evaluation.pollutant == "SO2").limit(1)), "insufficient")
        self.assertEqual(subindex("PM2.5", 60, date(2026, 3, 1)), 100)
        self.assertLess(subindex("PM2.5", 60, date(2026, 2, 28)), 100)
        self.assertEqual(daily_statistic("O3", dict.fromkeys(range(24), 160)), (160, 17))
        self.assertEqual(result["evaluations"], 12)

    def test_collection_missing_file_records_failure(self):
        def handler(request):
            if "extra" in str(request.url): return httpx.Response(404)
            return httpx.Response(200, content=daily_csv())
        client = httpx.Client(transport=httpx.MockTransport(handler))
        result = collect_range(self.db, self.store, self.settings, date(2026,9,30), date(2026,9,30), "test", lambda _: None, client)
        self.assertEqual(len(result["failures"]), 1)
        self.assertGreater(result["inserted"], 0)
        self.assertTrue(result["source_hashes"])

    def test_invalid_unit_is_not_silently_parsed(self):
        content = daily_csv().replace(b"PM2.5,80", b"PM2.5,80mg/m3")
        _, _, rows, invalid = parse_wide(content)
        self.assertGreater(invalid, 0)
        self.assertTrue(any(row["quality"] == "invalid" and row["value"] is None for row in rows))


class JobTests(DatabaseTest):
    def test_production_collection_requires_auditable_license(self):
        self.settings.environment = "production"
        self.settings.source_license_confirmed = False
        client = self.client("admin")
        result = client.post("/api/v2/jobs", json={
            "kind": "collect",
            "start": "2026-09-30",
            "end": "2026-09-30",
        })
        self.assertEqual(result.status_code, 503, result.text)
        self.assertEqual(result.json()["error"]["code"], "CONFIGURATION_ERROR")
        with self.db.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Job)), 0)

    def test_job_idempotency_contract_and_cancellation(self):
        client = self.client("researcher")
        body = {"kind": "export", "start": "2026-09-30", "end": "2026-09-30"}
        first = client.post("/api/v2/jobs", json=body, headers={"Idempotency-Key": "cancel-me"})
        self.assertEqual(first.status_code, 202, first.text)
        second = client.post("/api/v2/jobs", json={**body, "format": "xlsx"},
                             headers={"Idempotency-Key": "cancel-me"})
        self.assertEqual(second.json()["job_id"], first.json()["job_id"])
        cancelled = client.post(f"/api/v2/jobs/{first.json()['job_id']}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        detail = client.get(f"/api/v2/jobs/{first.json()['job_id']}")
        self.assertEqual(detail.json()["status"], "cancelled")

    def test_outbox_duplicate_delivery_and_export_permission(self):
        import_file(self.db, self.store, daily_csv(), "all")
        client = self.client("researcher")
        body = {"kind": "export", "start": "2026-09-30", "end": "2026-09-30"}
        result = client.post("/api/v2/jobs", json=body)
        self.assertEqual(result.status_code, 202, result.text)
        identifier = result.json()["job_id"]
        self.assertEqual(client.post("/api/v2/jobs", json=body).json()["job_id"], identifier)
        self.assertEqual(client.post("/api/v2/jobs", json={**body, "report": "inspections"}).status_code, 403)
        published = []
        publish_outbox(self.db, lambda id, queue: published.append((id, queue)))
        publish_outbox(self.db, lambda id, queue: published.append((id, queue)))
        self.assertEqual(published, [(identifier, "io")])
        self.assertEqual(run_job(identifier, self.settings)["status"], "completed")
        self.assertEqual(run_job(identifier, self.settings)["status"], "already_finished")
        with self.db.sessions() as session:
            stored = session.get(Job, identifier)
            self.assertEqual(stored.status, "succeeded")
            self.assertEqual(stored.progress, 100)
            self.assertEqual(stored.progress_stage, "completed")
            self.assertEqual(stored.result["_contract"]["state"], "succeeded")
            self.assertTrue(stored.result["source_hashes"])
            self.assertEqual(stored.result["_contract"]["artifacts"][0]["kind"], "export")
        result = client.get(f"/api/v2/jobs/{identifier}/download")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn("来源文件SHA256", result.content.decode("utf-8-sig"))
        self.assertEqual(self.client("officer").get(f"/api/v2/jobs/{identifier}/download").status_code, 404)

    def test_dispatch_failure_keeps_outbox_pending(self):
        with self.db.transaction() as session: enqueue(session, "evaluate", {"start":"2026-09-30","end":"2026-09-30"}, self.users["admin"])
        def failed(*args): raise RuntimeError("broker unavailable")
        with self.assertRaises(RuntimeError): publish_outbox(self.db, failed)
        with self.db.sessions() as session: self.assertIsNone(session.scalar(select(Outbox)).sent_at)


class WorkflowTests(DatabaseTest):
    def test_full_rectification_scope_history_and_version(self):
        supervisor, officer, outsider, researcher = [self.client(u) for u in ["supervisor", "officer", "outsider", "researcher"]]
        enterprise = supervisor.post("/api/v2/enterprises", json={"name": "隔离测试企业"}).json()
        lead = supervisor.post("/api/v2/leads", json={"title":"测试环境异常", "description":"待核实的原始观测异常"}).json()
        assigned = supervisor.post(f'/api/v2/leads/{lead["id"]}/assign', json={"assignee_id":self.users["officer"],"enterprise_id":enterprise["id"],"due_date":"2026-10-30","note":"安排现场核查测试"})
        self.assertEqual(assigned.status_code, 201, assigned.text)
        task = assigned.json()
        path = f'/api/v2/inspections/{task["id"]}'
        self.assertEqual(outsider.get(path).status_code, 403)
        self.assertEqual(researcher.get(path).status_code, 403)
        self.assertEqual(outsider.get("/api/v2/inspections").json()["total"], 0)
        def transition(client, action):
            current = client.get(path).json()
            response = client.post(path+"/transition",json={"action":action,"version":current["version"],"note":"记录核查操作的依据与结果"})
            self.assertEqual(response.status_code,200,response.text)
            return response.json()
        transition(officer, "start")
        current = officer.get(path).json()
        self.assertEqual(officer.put(path, json={"version":1,"facts":"现场检查确认设备运行状态"}).status_code,409)
        saved = officer.put(path,json={"version":current["version"],"facts":"现场检查确认设备运行状态"})
        self.assertEqual(saved.status_code, 200, saved.text)
        added = officer.post(path+"/rectifications",json={"version":saved.json()["version"],"requirement":"完善监测设备维护记录并提供资料","due_date":"2026-10-20"})
        self.assertEqual(added.status_code,201,added.text)
        rect = added.json()
        upload = officer.post("/api/v2/attachments",data={"inspection_id":task["id"]},files={"file":("evidence.txt",b"observed facts","text/plain")})
        self.assertEqual(upload.status_code,201,upload.text)
        evidence = upload.json()
        self.assertEqual(researcher.get(f'/api/v2/attachments/{evidence["id"]}/download').status_code,403)
        self.assertEqual(outsider.get(f'/api/v2/attachments/{evidence["id"]}/download').status_code,403)
        self.assertEqual(officer.get(f'/api/v2/attachments/{evidence["id"]}/download').content,b"observed facts")
        transition(officer,"rectify")
        current = officer.get(path).json()
        updated = officer.put(path+f'/rectifications/{rect["id"]}',json={"version":current["version"],"response":"已补齐维护记录与校准资料"})
        self.assertEqual(updated.status_code,200,updated.text)
        transition(officer,"submit_rectification")
        current = officer.get(path).json()
        updated = officer.put(path+f'/rectifications/{rect["id"]}',json={"version":current["version"],"response":"已补齐维护记录与校准资料","review_note":"复查资料完整且与现场设备一致","verified":True})
        self.assertEqual(updated.status_code,200,updated.text)
        transition(officer,"submit_review")
        current = officer.get(path).json()
        self.assertEqual(officer.post(path+"/transition",json={"version":current["version"],"action":"approve","note":"越权归档不应成功"}).status_code,403)
        transition(supervisor,"approve")
        self.assertEqual(officer.post("/api/v2/attachments",data={"inspection_id":task["id"]},files={"file":("x",b"x")}).status_code,409)
        transition(supervisor,"reopen")
        self.assertEqual(len(supervisor.get(path).json()["history"]),9)


if __name__ == "__main__": unittest.main()
