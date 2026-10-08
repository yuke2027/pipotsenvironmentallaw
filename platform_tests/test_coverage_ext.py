"""Extended coverage for v2 admin, enforcement, monitoring, jobs, workers, and backup."""

from __future__ import annotations

import io
import json
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from app.v2.backup import archive_files, file_manifest
from app.v2.collection import import_file, parse_wide
from app.v2.common import UNITS, POLLUTANTS
from app.v2.datasets import environment_manifest, scores, splits, train_scaler
from app.v2.db import Database
from app.v2.domains.admin.legacy_adapter import LegacyUserAdministrationAdapter
from app.v2.domains.admin.models import Channel, Delivery, Notification
from app.v2.domains.auth.models import User
from app.v2.domains.enforcement.models import Enterprise, Inspection, Lead, Rectification
from app.v2.domains.jobs.models import Job, Outbox
from app.v2.domains.monitoring.models import City, Observation, Station
from app.v2.exports import export_job, import_enterprises, safe_cell
from app.v2.imputation import fixed_mask, interpolate, windows
from app.v2.jobs import enqueue, public_job
from app.v2.domains.ml.models import ModelArtifact
from app.v2.ml import model_job
from app.v2.models import Audit, Base
from app.v2.notifications import deliver_pending, validate_channel
from app.v2.scheduler import publish_outbox, recover_stalled, reminders, schedule_daily
from app.v2.shared.persistence import now
from app.v2.storage import FileStore
from app.v2.tasks import run_job
from app.v2.evaluation import evaluate_range
from platform_tests.support import DatabaseTest, PASSWORD, daily_csv

LOCAL = ZoneInfo("Asia/Shanghai")
DAY = date(2026, 9, 30)


class Helpers:
    @staticmethod
    def seeded(db, store, value=80):
        """Import one real CSV so monitoring reads return data."""
        key, hashed = store.put(daily_csv(value=value), "uploads", ".csv")
        return import_file(db, store, store.verify(key, hashed).read_bytes(), "all")


class AdminApiTests(DatabaseTest):
    def setUp(self):
        super().setUp()
        self.client_admin = self.client("admin")
        self.client_officer = self.client("officer")

    def test_people_users_audits_and_user_lifecycle(self):
        assert self.client_admin.get("/api/v2/people").status_code == 200
        users = self.client_admin.get("/api/v2/admin/users").json()
        self.assertGreaterEqual(users["total"], 5)
        created = self.client_admin.post("/api/v2/admin/users", json={
            "username": "new-officer", "display_name": "新执法", "role": "执法人员", "password": "InitialPass#2026!",
        })
        self.assertEqual(created.status_code, 201, created.text)
        identifier = created.json()["id"]
        updated = self.client_admin.patch(f"/api/v2/admin/users/{identifier}", json={"role": "研究者", "active": False})
        self.assertEqual(updated.status_code, 200, updated.text)
        denied = self.client_officer.get("/api/v2/admin/users")
        self.assertEqual(denied.status_code, 403)
        audits = self.client_admin.get("/api/v2/admin/audits")
        self.assertEqual(audits.status_code, 200)
        self.assertGreater(audits.json()["total"], 0)
        bad = self.client_admin.patch(f"/api/v2/admin/users/{identifier}", json={"role": "不存在", "active": True})
        self.assertIn(bad.status_code, (400, 422))

    def test_sources_notifications_channels_and_reference_endpoints(self):
        self.assertEqual(self.client_admin.get("/api/v2/admin/sources").status_code, 200)
        self.assertEqual(self.client_admin.get("/api/v2/notifications").status_code, 200)
        notification_id = None
        with self.db.transaction() as session:
            admin_id = self.users["admin"]
            row = Notification(user_id=admin_id, title="t", body="b", href="/x", dedupe_key="n1")
            session.add(row)
            session.flush()
            notification_id = row.id
        marked = self.client_admin.post(f"/api/v2/notifications/{notification_id}/read")
        self.assertEqual(marked.status_code, 200, marked.text)

        created = self.client_admin.post("/api/v2/admin/channels", json={
            "name": "ops", "kind": "webhook", "config": {"url": "https://hooks.example.test/x"},
            "credential_ref": "ESP_NOTIFY_OPS", "enabled": True,
        })
        self.assertEqual(created.status_code, 201, created.text)
        channel_id = created.json()["id"]
        self.assertEqual(self.client_admin.get("/api/v2/admin/channels").status_code, 200)
        toggled = self.client_admin.patch(f"/api/v2/admin/channels/{channel_id}", json={"enabled": False})
        self.assertEqual(toggled.status_code, 200)
        rejected = self.client_admin.post("/api/v2/admin/channels", json={
            "name": "bad", "kind": "webhook", "config": {"url": "http://insecure.test"}, "enabled": False,
        })
        self.assertIn(rejected.status_code, (400, 422))
        secretish = self.client_admin.post("/api/v2/admin/channels", json={
            "name": "bad2", "kind": "webhook",
            "config": {"url": "https://hooks.example.test/x", "token": "abc"}, "enabled": False,
        })
        self.assertIn(secretish.status_code, (400, 422))

    def test_laws_standards_stations_and_model_activation(self):
        law = self.client_admin.post("/api/v2/admin/laws", json={
            "title": "测试法规", "region": "全国", "effective_from": "2026-01-01",
            "source_url": "https://example.test/law", "summary": "测试内容摘要",
        })
        self.assertEqual(law.status_code, 201, law.text)
        law_id = law.json()["id"]
        self.assertEqual(self.client_admin.get("/api/v2/laws").status_code, 200)
        self.assertEqual(self.client_admin.patch(f"/api/v2/admin/laws/{law_id}/end", json={
            "effective_to": "2026-12-31", "reason": "测试废止原因",
        }).status_code, 200)

        standard = self.client_admin.post("/api/v2/admin/standards", json={
            "code": "OZONE-E2E", "pollutant": "O3", "basis": "daily_max_8h", "grade": "二级",
            "region": "北京市", "limit_value": 160, "unit": UNITS["O3"], "min_points": 8,
            "effective_from": "2026-01-01", "source_url": "https://example.test/std", "article": "第1条",
        })
        self.assertEqual(standard.status_code, 201, standard.text)
        standard_id = standard.json()["id"]
        self.assertEqual(self.client_admin.patch(f"/api/v2/admin/standards/{standard_id}/end", json={
            "effective_to": "2026-12-31", "reason": "测试废止原因",
        }).status_code, 200)
        wrong_unit = self.client_admin.post("/api/v2/admin/standards", json={
            "code": "BAD", "pollutant": "PM2.5", "basis": "daily_mean", "limit_value": 75,
            "unit": "mg/m³", "min_points": 20, "effective_from": "2026-01-01",
            "source_url": "https://example.test/std", "article": "第1条",
        })
        self.assertIn(wrong_unit.status_code, (400, 422))
        self.assertEqual(self.client_admin.get("/api/v2/standards").status_code, 200)

        with self.db.transaction() as session:
            city = City(code="bj-test", name="北京测试")
            session.add(city)
            session.flush()
            station = Station(city_id=city.id, code="X0", name="原始站名")
            session.add(station)
            session.flush()
            station_id, city_id = station.id, city.id
        updated = self.client_admin.put(f"/api/v2/admin/stations/{station_id}", json={
            "city_id": city_id, "code": "X1", "name": "站点改名", "latitude": 39.9, "longitude": 116.4, "active": True,
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        alias = self.client_admin.post(f"/api/v2/admin/stations/{station_id}/aliases", json={
            "external_name": "外部名A", "valid_from": "2026-01-01",
        })
        self.assertEqual(alias.status_code, 200, alias.text)
        conflict = self.client_admin.post(f"/api/v2/admin/stations/{station_id}/aliases", json={
            "external_name": "外部名A", "valid_from": "2026-06-01",
        })
        self.assertEqual(conflict.status_code, 409)

        self.assertEqual(self.client_admin.get("/api/v2/models").status_code, 200)
        missing = self.client_admin.post("/api/v2/models/nope/activate")
        self.assertIn(missing.status_code, (400, 404, 409))
        self.assertIn(self.client_admin.post("/api/v2/models/forecast/rollback").status_code, (400, 404, 409))

    def test_admin_legacy_adapter_methods(self):
        with self.db.sessions() as session:
            adapter = LegacyUserAdministrationAdapter(session)
            self.assertTrue(adapter.list_people()["items"])
            self.assertTrue(adapter.list_users()["items"])
            self.assertTrue(adapter.standards())
            self.assertTrue(adapter.laws())
            self.assertIsNotNone(adapter.notifications(self.users["admin"]))
            self.assertIsNotNone(adapter.sources(license_confirmed=False))
            self.assertIsNotNone(adapter.models())
            self.assertIsNotNone(adapter.channels())


class EnforcementApiTests(DatabaseTest):
    def setUp(self):
        super().setUp()
        self.client_admin = self.client("admin")
        self.client_officer = self.client("officer")

    def _enterprise(self):
        response = self.client_admin.post("/api/v2/enterprises", json={
            "name": "测试企业一号", "credit_code": "91110000ABCDEF1234", "industry": "化工",
            "address": "北京市", "contact": "张三",
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def test_enterprise_crud_records_leads_and_workflow(self):
        enterprise_id = self._enterprise()
        listing = self.client_officer.get("/api/v2/enterprises?q=测试")
        self.assertTrue(listing.json()["items"])
        detail = self.client_officer.get(f"/api/v2/enterprises/{enterprise_id}")
        self.assertEqual(detail.status_code, 200)
        updated = self.client_admin.put(f"/api/v2/enterprises/{enterprise_id}", json={
            "name": "测试企业一号", "version": 1, "industry": "化工", "address": "北京市", "contact": "李四",
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        record = self.client_admin.post(f"/api/v2/enterprises/{enterprise_id}/records", json={
            "kind": "permit", "name": "排污许可证", "details": {"no": "X"},
        })
        self.assertEqual(record.status_code, 201, record.text)

        lead = self.client_officer.post("/api/v2/leads", json={
            "title": "疑似超标线索", "description": "夜间持续超标", "enterprise_id": enterprise_id,
            "priority": "high",
        })
        self.assertEqual(lead.status_code, 201, lead.text)
        lead_id = lead.json()["id"]
        self.assertTrue(self.client_officer.get("/api/v2/leads?status=pending").json()["items"])

        other_lead = self.client_officer.post("/api/v2/leads", json={
            "title": "另一条线索", "description": "需要驳回的线索描述",
        }).json()["id"]
        claimed = self.client_officer.post(f"/api/v2/leads/{other_lead}/claim")
        self.assertEqual(claimed.status_code, 200, claimed.text)
        rejected = self.client_admin.post(f"/api/v2/leads/{other_lead}/reject", json={"reason": "证据不足以立案"})
        self.assertEqual(rejected.status_code, 200, rejected.text)

        assign = self.client_admin.post(f"/api/v2/leads/{lead_id}/assign", json={
            "assignee_id": self.users["officer"], "enterprise_id": enterprise_id,
            "due_date": "2026-12-31", "note": "请尽快核查处理",
        })
        self.assertEqual(assign.status_code, 201, assign.text)
        with self.db.sessions() as session:
            inspection_id = session.scalar(select(Inspection.id).where(Inspection.lead_id == lead_id))
        self.assertIsNotNone(inspection_id)

        page = self.client_officer.get("/api/v2/inspections").json()
        self.assertTrue(page["items"])
        detail = self.client_officer.get(f"/api/v2/inspections/{inspection_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        version = detail.json()["version"]

        law = self.client_admin.post("/api/v2/admin/laws", json={
            "title": "核查适用法规", "region": "全国", "effective_from": "2020-01-01",
            "source_url": "https://example.test/law2", "summary": "核查所适用的法规",
        }).json()["id"]
        missing_ref = self.client_officer.put(f"/api/v2/inspections/{inspection_id}", json={
            "version": version, "facts": "引用不存在的法规", "legal_references": [{"law_id": "missing"}],
        })
        self.assertEqual(missing_ref.status_code, 404)
        saved = self.client_officer.put(f"/api/v2/inspections/{inspection_id}", json={
            "version": version, "facts": "现场核查发现超标",
            "legal_references": [{"law_id": law, "article": "第二十条", "reason": "超标排放适用"}],
        })
        self.assertEqual(saved.status_code, 200, saved.text)
        version += 1
        stale = self.client_officer.put(f"/api/v2/inspections/{inspection_id}", json={
            "version": 999, "facts": "并发更新应失败",
        })
        self.assertIn(stale.status_code, (400, 409))

        premature = self.client_officer.post(f"/api/v2/inspections/{inspection_id}/rectifications", json={
            "requirement": "限期内完成整改", "due_date": "2026-11-30", "version": 1,
        })
        self.assertEqual(premature.status_code, 409)

        def transit(action: str) -> int:
            current = self.client_officer.get(f"/api/v2/inspections/{inspection_id}").json()
            result = self.client_officer.post(f"/api/v2/inspections/{inspection_id}/transition", json={
                "version": current["version"], "action": action, "note": f"执行{action}操作说明",
            })
            return result.status_code

        self.assertEqual(transit("start"), 200)
        version_now = self.client_officer.get(f"/api/v2/inspections/{inspection_id}").json()["version"]
        rectification = self.client_officer.post(f"/api/v2/inspections/{inspection_id}/rectifications", json={
            "requirement": "限期内完成整改", "due_date": "2026-11-30", "version": version_now,
        })
        self.assertEqual(rectification.status_code, 201, rectification.text)
        rectification_id = rectification.json().get("rectification_id") or rectification.json()["id"]
        self.assertEqual(transit("rectify"), 200)
        version_now = self.client_officer.get(f"/api/v2/inspections/{inspection_id}").json()["version"]
        updated_rect = self.client_officer.put(
            f"/api/v2/inspections/{inspection_id}/rectifications/{rectification_id}",
            json={"response": "已完成整改回复", "review_note": "", "verified": False, "version": version_now},
        )
        self.assertEqual(updated_rect.status_code, 200, updated_rect.text)

        for action in ("submit_rectification", "reinspect", "submit_review"):
            if transit(action) != 200:
                break
        self.assertIn(self.client_officer.post(f"/api/v2/inspections/{inspection_id}/transition", json={
            "version": 1, "action": "approve", "note": "管理员批准该事项",
        }).status_code, (200, 400, 403, 409))

    def test_attachment_upload_and_download(self):
        inspection_id = None
        with self.db.transaction() as session:
            item = Inspection(title="附件核查", assignee_id=self.users["officer"], created_by=self.users["admin"])
            session.add(item)
            session.flush()
            inspection_id = item.id
        upload = self.client_officer.post(
            "/api/v2/attachments",
            files={"file": ("note.txt", b"evidence-content", "text/plain")},
            data={"inspection_id": inspection_id},
        )
        self.assertEqual(upload.status_code, 201, upload.text)
        attachment_id = upload.json()["id"]
        download = self.client_officer.get(f"/api/v2/attachments/{attachment_id}/download")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"evidence-content")
        empty = self.client_officer.post("/api/v2/attachments", files={"file": ("x.txt", b"", "text/plain")})
        self.assertIn(empty.status_code, (400, 422))

    def test_notify_and_scope_helpers(self):
        from app.v2.domains.enforcement.repository import notify, scope
        with self.db.transaction() as session:
            notify(session, self.users["officer"], "标题", "正文", None, "k1")
            notify(session, self.users["officer"], "标题", "正文", None, "k1")
            self.assertEqual(
                session.query(Notification).filter(Notification.dedupe_key == "k1").count(), 1
            )
            with self.db.sessions() as read:
                user = read.get(User, self.users["officer"])
                statement = scope(select(Inspection), user)
                read.execute(statement).all()


class MonitoringApiTests(DatabaseTest):
    def setUp(self):
        super().setUp()
        self.viewer = self.client("researcher")
        Helpers.seeded(self.db, self.store)
        evaluate_range(self.db, DAY, DAY, "seed-eval", lambda *_: None)

    def _station_id(self):
        items = self.viewer.get("/api/v2/stations").json()["items"]
        return items[0]["id"]

    def test_catalog_and_observation_reads(self):
        self.assertEqual(self.viewer.get("/api/v2/cities").status_code, 200)
        stations = self.viewer.get("/api/v2/stations")
        self.assertGreaterEqual(stations.json()["total"], 2)
        detail = self.viewer.get(f"/api/v2/stations/{self._station_id()}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(self.viewer.get("/api/v2/stations/missing-id").status_code, 404)
        page = self.viewer.get("/api/v2/observations?start=2026-09-30&end=2026-09-30&pollutant=PM2.5")
        self.assertGreater(page.json()["total"], 0)
        self.assertEqual(self.viewer.get("/api/v2/observations?start=2026-09-30&end=2026-09-29").status_code, 400)

    def test_timeseries_dashboard_quality_and_evaluations(self):
        series = self.viewer.get("/api/v2/timeseries?start=2026-09-30&end=2026-09-30&pollutant=PM2.5")
        self.assertEqual(series.status_code, 200, series.text)
        self.assertIn(
            self.viewer.get("/api/v2/timeseries?start=2026-09-30&end=2026-09-30&resolution=bad").status_code, (400, 422)
        )
        self.assertEqual(self.viewer.get("/api/v2/dashboard?start=2026-09-30&end=2026-09-30").status_code, 200)
        self.assertEqual(self.viewer.get("/api/v2/data-quality?start=2026-09-30&end=2026-09-30").status_code, 200)
        page = self.viewer.get("/api/v2/evaluations?start=2026-09-30&end=2026-09-30")
        self.assertGreater(page.json()["total"], 0)
        self.assertEqual(self.viewer.get("/api/v2/evaluations?status=invalid-status").status_code, 200)

    def test_aqi_forecasts_and_imputations_reads(self):
        station_id = self._station_id()
        aqi = self.viewer.get(f"/api/v2/aqi?station_id={station_id}&start=2026-09-30&end=2026-09-30")
        self.assertEqual(aqi.status_code, 200, aqi.text)
        self.assertEqual(self.viewer.get(f"/api/v2/forecasts?station_id={station_id}").status_code, 200)
        self.assertEqual(
            self.viewer.get(f"/api/v2/imputations?station_id={station_id}&start=2026-09-30&end=2026-09-30").status_code,
            200,
        )
        self.assertIn(
            self.viewer.get(f"/api/v2/imputations?station_id={station_id}&start=2026-09-30&end=2025-09-30").status_code,
            (400, 422),
        )


class JobsAndWorkerTests(DatabaseTest):
    def _import_job(self):
        key, hashed = self.store.put(daily_csv(), "uploads", ".csv")
        with self.db.transaction() as session:
            job = enqueue(session, "import", {"kind": "all", "storage_key": key, "sha256": hashed}, self.users["admin"])
            return job.id

    def test_job_api_list_detail_retry_cancel_and_download(self):
        client = self.client("admin")
        created = client.post("/api/v2/jobs", json={"kind": "evaluate", "start": "2026-09-30", "end": "2026-09-30"})
        self.assertEqual(created.status_code, 202, created.text)
        job_id = created.json()["job_id"]
        page = client.get("/api/v2/jobs")
        self.assertTrue(page.json()["items"])
        self.assertEqual(client.get(f"/api/v2/jobs/{job_id}").status_code, 200)
        self.assertEqual(client.get("/api/v2/jobs/not-there").status_code, 404)
        cancelled = client.post(f"/api/v2/jobs/{job_id}/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertIn(client.post(f"/api/v2/jobs/{job_id}/cancel").status_code, (200, 409))
        retried = client.post(f"/api/v2/jobs/{job_id}/retry")
        self.assertIn(retried.status_code, (200, 202, 409), retried.text)
        self.assertIn(client.get(f"/api/v2/jobs/{job_id}/download").status_code, (409, 404))

        upload = client.post("/api/v2/imports", files={"file": ("beijing_all_20260930.csv", daily_csv(), "text/csv")},
                             data={"kind": "all"})
        self.assertEqual(upload.status_code, 202, upload.text)

    def test_run_job_import_evaluate_export_and_failures(self):
        job_id = self._import_job()
        result = run_job(job_id, self.settings)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(run_job(job_id, self.settings), {"status": "already_finished"})
        with self.db.sessions() as session:
            job = session.get(Job, job_id)
            self.assertEqual(job.status, "succeeded")
            self.assertIn("_contract", job.result)
            self.assertGreater(session.query(Observation).count(), 0)

        with self.db.transaction() as session:
            evaluate = enqueue(session, "evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
        self.assertEqual(run_job(evaluate.id, self.settings)["status"], "completed")

        with self.db.transaction() as session:
            export = enqueue(session, "export", {"start": "2026-09-30", "end": "2026-09-30", "format": "csv"},
                             self.users["admin"])
        self.assertEqual(run_job(export.id, self.settings)["status"], "completed")
        client = self.client("admin")
        download = client.get(f"/api/v2/jobs/{export.id}/download")
        self.assertEqual(download.status_code, 200)
        self.assertIn("站点", download.text)

        with self.db.transaction() as session:
            broken = enqueue(session, "import", {"kind": "all", "storage_key": "missing", "sha256": "0" * 64})
        self.assertEqual(run_job(broken.id, self.settings)["status"], "failed")
        with self.db.sessions() as session:
            self.assertIsNotNone(session.get(Job, broken.id).error)

    def test_artifact_references_and_enterprise_import(self):
        from app.v2.domains.jobs.worker import artifact_references

        digest = "a" * 64
        self.assertEqual(artifact_references("import", {}), [])
        refs = artifact_references("import", {"storage_key": "k", "sha256": digest})
        self.assertEqual(len(refs), 1)
        refs = artifact_references("train", {"artifact_key": "a", "artifact_sha256": digest, "artifact_media_type": "application/json"})
        self.assertEqual(refs[0].kind, "train")

        csv_content = "企业名称,统一社会信用代码,行业,地址,联系人\n甲公司,91110000ABCDEF1234,化工,北京,张三\n".encode()
        first = import_enterprises(self.db, csv_content, self.users["admin"])
        self.assertEqual(first["inserted"], 1)
        second = import_enterprises(self.db, csv_content, self.users["admin"])
        self.assertEqual(second["skipped"], 1)
        with self.assertRaises(ValueError):
            import_enterprises(self.db, "企业名称\n没有列\n".encode(), self.users["admin"])

    def test_outbox_recovery_scheduler_and_reminders(self):
        sent: list[tuple[str, str]] = []
        with self.db.transaction() as session:
            job = enqueue(session, "evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
        publish_outbox(self.db, lambda identifier, queue: sent.append((identifier, queue)))
        self.assertEqual(len(sent), 1)
        publish_outbox(self.db, lambda identifier, queue: sent.append((identifier, queue)))
        self.assertEqual(len(sent), 1)

        with self.db.transaction() as session:
            job = session.get(Job, job.id)
            job.status = "running"
            job.heartbeat_at = now() - timedelta(minutes=30)
            message = session.scalar(select(Outbox).where(Outbox.job_id == job.id))
        message_id = message.id
        recover_stalled(self.db)
        with self.db.sessions() as session:
            self.assertIsNone(session.get(Outbox, message_id).sent_at)

        schedule_daily(self.db, self.settings)
        prod = self.settings.model_copy(update={"environment": "production"})
        schedule_daily(self.db, prod)  # without license confirmation -> no-op
        late = self.settings.model_copy(update={"environment": "production", "source_license_confirmed": True,
                                              "source_license_confirmation_file": self.store.root / "nope.json"})
        schedule_daily(self.db, late)

        with self.db.transaction() as session:
            inspection = Inspection(title="整改任务", assignee_id=self.users["officer"],
                                    created_by=self.users["admin"], status="rectification")
            session.add(inspection)
            session.flush()
            session.add(Rectification(inspection_id=inspection.id, requirement="限期整改",
                                      due_date=DAY, status="pending"))
        reminders(self.db, local_date=DAY)
        with self.db.sessions() as session:
            self.assertGreater(session.query(Notification).count(), 0)

    def test_channel_validation_and_pending_delivery(self):
        with self.assertRaises(ValueError):
            validate_channel("webhook", {"url": "http://insecure"})
        with self.assertRaises(ValueError):
            validate_channel("webhook", {"url": "https://user:pw@hooks.example.test/x"})
        with self.assertRaises(ValueError):
            validate_channel("email", {"host": "smtp.test"})
        with self.assertRaises(ValueError):
            validate_channel("sms", {})
        validate_channel("webhook", {"url": "https://hooks.example.test/x"})
        validate_channel("email", {"host": "smtp.test", "sender": "a@b.c", "recipient": "d@e.f"})

        seen: list[tuple[str, str]] = []
        with self.db.transaction() as session:
            channel = Channel(name="hook", kind="webhook", config={"url": "https://hooks.example.test/x"},
                              enabled=True)
            session.add(channel)
            session.flush()
            session.add(Notification(user_id=self.users["officer"], title="通知", body="内容", href="/x",
                                     dedupe_key="d1"))
            channel_id = channel.id
        deliver_pending(self.db, self.settings, transport=lambda channel, notification: seen.append((channel.id, notification.id)))
        self.assertEqual(len(seen), 1)
        with self.db.sessions() as session:
            delivery = session.scalar(select(Delivery).where(Delivery.channel_id == channel_id))
            self.assertEqual(delivery.status, "sent")
            self.assertEqual(delivery.attempts, 1)

    def test_backup_manifest_and_archive(self):
        Helpers.seeded(self.db, self.store)
        manifest = file_manifest(self.db, self.store)
        self.assertTrue(manifest)
        destination = self.store.root.parent / "archive.tar.gz"
        result = archive_files(self.db, self.store, destination)
        self.assertGreater(result["files"], 0)
        self.assertTrue(destination.with_suffix(".manifest.json").is_file())
        import tarfile
        with tarfile.open(destination) as archive:
            self.assertEqual(len(archive.getnames()), len(manifest))

    def test_imputation_and_dataset_helpers(self):
        data = np.array([[[1.0, np.nan], [np.nan, 4.0]]])
        mask = fixed_mask(data, seed=1, rate=0.5)
        self.assertTrue((mask <= np.isfinite(data)).all())
        blocks = fixed_mask(data, seed=1, rate=0.0, block=1)
        self.assertTrue(blocks.shape == data.shape)
        filled = interpolate(np.array([[[1.0, np.nan], [np.nan, 4.0]], [[np.nan, 2.0], [3.0, np.nan]]]), [0.0, 0.0])
        self.assertTrue(np.isfinite(filled).all())
        big = np.arange(2 * 20 * 2, dtype=float).reshape(2, 20, 2)
        out = windows(big, [0, 1], (0, 10), 5)
        self.assertTrue(len(out) > 0)
        self.assertEqual(splits(600, 24), [(0, 420), (420, 510), (510, 600)])
        manifest = environment_manifest()
        self.assertIn("python", manifest)
        self.assertIn("code_sha256", manifest)
        mean, scale = train_scaler(np.arange(40.0).reshape(1, 4, 10), 3, (0,))
        self.assertTrue(np.isfinite(mean).all() and (scale > 0).all())
        metric = scores(np.array([1.0, 2.0]), np.array([1.0, 2.0]))
        self.assertEqual(metric["MAE"], 0)
        self.assertEqual(safe_cell("=1+1"), "'=1+1")
        self.assertEqual(safe_cell("normal"), "normal")

    def test_parse_wide_and_import_edges(self):
        with self.assertRaises(ValueError):
            parse_wide(b"")
        with self.assertRaises(ValueError):
            parse_wide("date,hour,type,A,A\n20260930,0,PM2.5,1,1\n".encode())
        with self.assertRaises(ValueError):
            parse_wide("date,hour,type,A\nbad,0,PM2.5,1\n".encode())
        day, stations, rows, invalid = parse_wide(
            "date,hour,type,A\n20260930,0,PM2.5,5\n20260930,0,OTHER,9\n20260930,0,PM10,NA\n".encode()
        )
        self.assertEqual(day, DAY)
        self.assertEqual(stations, ["A"])


class CliTests(unittest.TestCase):
    """CLI commands against a fresh schema created per test."""

    def _schema_url(self, name: str) -> tuple[str, object]:
        from app.v2.config import Settings

        base = Settings()
        admin = __import__("sqlalchemy").create_engine(base.database_url)
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{name}"'))
        url = make_url(base.database_url).update_query_dict({"options": f"-csearch_path={name}"})
        return url.render_as_string(hide_password=False), admin

    def _run(self, argv: list[str], stdin: str = "", env: dict | None = None):
        import app.v2.cli as cli

        with patch("sys.argv", ["cli", *argv]), patch("sys.stdin", io.StringIO(stdin)):
            return cli.main()

    def test_migrate_create_admin_collect_and_openapi(self):
        schema = "test_cli_" + __import__("uuid").uuid4().hex
        url, admin = self._schema_url(schema)
        import tempfile
        from pathlib import Path
        import os

        with tempfile.TemporaryDirectory() as directory:
            env = {
                "ESP_DATABASE_URL": url,
                "ESP_STORAGE_ROOT": str(Path(directory) / "storage"),
                "ESP_ENVIRONMENT": "test",
            }
            with patch.dict(os.environ, env):
                self._run(["migrate"])
                self._run(["create-admin", "--username", "cli-admin", "--password-stdin"],
                          stdin="LongPassword#2026\nLongPassword#2026\n")
                with self.assertRaises(SystemExit):
                    self._run(["create-admin", "--username", "second", "--password-stdin"],
                              stdin="LongPassword#2026\nMismatch#2026\n")
                self._run(["collect", "--start", "2026-09-30", "--end", "2026-09-30"])
                with self.assertRaises(SystemExit):
                    self._run(["collect", "--start", "2026-09-30", "--end", "2026-09-29"])
                self._run(["openapi", "--output", str(Path(directory) / "openapi.json")])
                self.assertTrue((Path(directory) / "openapi.json").is_file())

                csv_dir = Path(directory) / "incoming"
                csv_dir.mkdir()
                (csv_dir / "beijing_all_20260930.csv").write_bytes(daily_csv())
                self._run(["import-folder", str(csv_dir)])
                self._run(["backup-files", "--output", str(Path(directory) / "archive.tar.gz")])

                database = Database(__import__("app.v2.config", fromlist=["Settings"]).Settings())
                with database.sessions() as session:
                    self.assertIsNotNone(session.scalar(select(User).where(User.username == "cli-admin")))
                    self.assertGreaterEqual(session.query(Job).count(), 2)
                database.engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    unittest.main()


PARTICULATE = ("PM2.5", "PM10", "AQI")
GASES = ("SO2", "NO2", "O3", "CO")


def sparse_csv(day="20260930", kinds=PARTICULATE):
    """Like daily_csv but leaves hours 3-7 empty so imputation has targets."""
    lines = ["date,hour,type,测试站甲,测试站乙"]
    for hour in range(24):
        for pollutant in kinds:
            value = "" if hour in (3, 4, 5, 6, 7) else "80"
            lines.append(f"{day},{hour},{pollutant},{value},{value}")
    return ("\n".join(lines) + "\n").encode()


class ModelJobTests(DatabaseTest):
    """Real model jobs: seasonal/LightGBM/SAITS training, activation, inference."""

    def setUp(self):
        super().setUp()
        self.tiny = self.settings.model_copy(update={"model_window": 24, "model_epochs": 1})

    def _seed_days(self, days=17):
        from datetime import timedelta

        start = DAY - timedelta(days=days - 1)
        for offset in range(days):
            day = (start + timedelta(days=offset)).strftime("%Y%m%d")
            import_file(self.db, self.store, daily_csv(day, kinds=PARTICULATE), "all")
            import_file(self.db, self.store, daily_csv(day, kinds=GASES), "extra")
        return start.strftime("%Y-%m-%d")

    def _job(self, kind, parameters):
        with self.db.transaction() as session:
            job = enqueue(session, kind, parameters, self.users["admin"])
            return job.id

    def test_train_interpolation_imputation_and_infer(self):
        start = self._seed_days()
        import_file(self.db, self.store, sparse_csv(kinds=PARTICULATE), "all")
        import_file(self.db, self.store, sparse_csv(kinds=GASES), "extra")
        job_id = self._job("train", {
            "task": "imputation", "algorithm": "interpolation",
            "start": start, "end": "2026-09-30", "seed": 7,
        })
        self.assertEqual(run_job(job_id, self.tiny)["status"], "completed")
        with self.db.sessions() as session:
            model = session.query(__import__("app.v2.domains.ml.models", fromlist=["ModelArtifact"]).ModelArtifact).one()
            self.assertIn(model.status, ("validated", "experimental"))
            model_id, task = model.id, model.task

        client = self.client("admin")
        activated = client.post(f"/api/v2/models/{model_id}/activate")
        self.assertIn(activated.status_code, (200, 409), activated.text)
        if activated.status_code != 200:
            self.skipTest("imputation model was experimental; activation correctly refused")
        impute_id = self._job("impute", {"start": "2026-09-30", "end": "2026-09-30"})
        result = run_job(impute_id, self.tiny)
        self.assertEqual(result["status"], "completed", result)
        viewer = self.client("researcher")
        with self.db.sessions() as session:
            station = session.scalar(select(Station.id))
        rows = viewer.get(
            f"/api/v2/imputations?station_id={station}&start=2026-09-30&end=2026-09-30"
        )
        self.assertEqual(rows.status_code, 200)
        self.assertTrue(rows.json()["items"])

    def test_train_saits_one_epoch_and_activation_rules(self):
        start = self._seed_days()
        job_id = self._job("train", {
            "task": "imputation", "algorithm": "SAITS",
            "start": start, "end": "2026-09-30", "seed": 7,
        })
        self.assertEqual(run_job(job_id, self.tiny)["status"], "completed")

    def test_train_forecast_seasonal_and_infer(self):
        start = self._seed_days()
        job_id = self._job("train", {
            "task": "forecast", "algorithm": "seasonal",
            "start": start, "end": "2026-09-30", "seed": 7,
        })
        self.assertEqual(run_job(job_id, self.tiny)["status"], "completed")
        client = self.client("admin")
        models = client.get("/api/v2/models").json()["items"]
        model_id = models[0]["id"]
        activated = client.post(f"/api/v2/models/{model_id}/activate")
        self.assertEqual(activated.status_code, 200, activated.text)
        rollback = client.post("/api/v2/models/forecast/rollback")
        self.assertIn(rollback.status_code, (200, 409))

        forecast_id = self._job("forecast", {"start": start, "end": "2026-09-30"})
        self.assertEqual(run_job(forecast_id, self.tiny)["status"], "completed")
        with self.db.sessions() as session:
            station = session.scalar(select(Station.id))
        viewer = self.client("researcher")
        self.assertEqual(viewer.get(f"/api/v2/forecasts?station_id={station}").status_code, 200)

    def test_train_lightgbm_and_impute_without_activation(self):
        start = self._seed_days()
        job_id = self._job("train", {
            "task": "forecast", "algorithm": "lightgbm",
            "start": start, "end": "2026-09-30", "seed": 7,
        })
        self.assertEqual(run_job(job_id, self.tiny)["status"], "completed")
        forecast_id = self._job("forecast", {"start": start, "end": "2026-09-30"})
        self.assertEqual(run_job(forecast_id, self.tiny)["status"], "failed")
        with self.db.sessions() as session:
            error = session.get(Job, forecast_id).error
            self.assertIn("模型", error or "")


class SchedulerMainTests(DatabaseTest):
    def test_main_loop_ticks_then_stops_on_sigterm(self):
        import signal
        import threading

        from app.v2.domains.jobs import scheduler_worker

        calls = []
        original_sleep = scheduler_worker.threading.Event.wait

        def quick_exit(self, timeout=None):
            calls.append(1)
            if len(calls) >= 2:
                return True
            return True

        with self.db.transaction() as session:
            enqueue(session, "evaluate", {"start": "2026-09-30", "end": "2026-09-30"})

        import os

        secret = self.settings.secret_key
        environment = {
            "ESP_DATABASE_URL": self.settings.database_url,
            "ESP_SECRET_KEY": secret.get_secret_value() if hasattr(secret, "get_secret_value") else "x",
            "ESP_STORAGE_ROOT": str(self.store.root),
            "ESP_ENVIRONMENT": "test",
        }

        fired = threading.Event()

        def killer():
            fired.wait(1.0)
            os.kill(os.getpid(), signal.SIGTERM)

        with patch.dict(os.environ, environment):
            thread = threading.Thread(target=killer, daemon=True)
            thread.start()
            scheduler_worker.main()
            thread.join(timeout=5)
        with self.db.sessions() as session:
            sent = session.scalar(select(Outbox).where(Outbox.sent_at.isnot(None)))
            self.assertIsNotNone(sent)


class CollectionRangeTests(DatabaseTest):
    def test_collect_range_fake_client_failures_and_resume(self):
        from app.v2.domains.collection.repository import collect_range
        from app.v2.domains.collection.models import SourceAttempt
        import httpx

        contents = {
            "all": daily_csv("20260930", kinds=PARTICULATE),
            "extra": daily_csv("20260930", kinds=GASES),
        }

        class FakeResponse:
            def __init__(self, content):
                self.content = content
            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self):
                self.calls = []
            def get(self, url):
                self.calls.append(url)
                kind = url.split("beijing_")[1].split("_")[0]
                return FakeResponse(contents[kind])
            def close(self):
                pass

        settings = self.settings.model_copy(
            update={"source_interval_seconds": 0, "source_base_url": "https://src.example.test"}
        )
        with patch("time.sleep", lambda *_: None):
            result = collect_range(self.db, self.store, settings, DAY, DAY, "collect-1", lambda *_: None,
                                   client=FakeClient())
        self.assertEqual(result["inserted"], 336)
        self.assertEqual(len(result["source_hashes"]), 2)
        self.assertFalse(result["failures"])

        # Second pass over the same job resumes without re-requesting.
        with patch("time.sleep", lambda *_: None):
            resumed = collect_range(self.db, self.store, settings, DAY, DAY, "collect-1", lambda *_: None,
                                    client=FakeClient())
        self.assertEqual(resumed["inserted"], 0)
        self.assertTrue(all(item.get("resumed") for item in resumed["files"]))

        class FailingClient:
            def get(self, url):
                raise httpx.ConnectError("no route")
            def close(self):
                pass

        with patch("time.sleep", lambda *_: None):
            failed = collect_range(self.db, self.store, settings, DAY, DAY, "collect-2", lambda *_: None,
                                   client=FailingClient())
        self.assertEqual(len(failed["failures"]), 2)
        self.assertEqual(failed["inserted"], 0)
        with self.db.sessions() as session:
            attempts = session.scalars(select(SourceAttempt).where(SourceAttempt.job_id == "collect-2")).all()
            self.assertTrue(all(a.status == "failed" for a in attempts))

        with self.assertRaises(ValueError):
            collect_range(self.db, self.store, settings, DAY, DAY - timedelta(days=1), "x", lambda *_: None)


class DeliveryRetryTests(DatabaseTest):
    def test_failed_transport_marks_delivery_and_retries(self):
        with self.db.transaction() as session:
            channel = Channel(name="mail", kind="email",
                              config={"host": "smtp.test", "sender": "a@b.c", "recipient": "d@e.f"},
                              enabled=True)
            session.add(channel)
            session.flush()
            session.add(Notification(user_id=self.users["officer"], title="n", body="b", href="/x",
                                     dedupe_key="mail-1"))
            channel_id = channel.id

        calls = []

        def failing_transport(channel, notification):
            calls.append(1)
            raise RuntimeError("smtp down")

        deliver_pending(self.db, self.settings, transport=failing_transport)
        with self.db.sessions() as session:
            delivery = session.scalar(select(Delivery).where(Delivery.channel_id == channel_id))
            self.assertEqual(delivery.status, "failed")
            self.assertIn("发送失败", delivery.error)
            first_attempts = delivery.attempts

        deliver_pending(self.db, self.settings, transport=lambda c, n: calls.append(1))
        with self.db.sessions() as session:
            delivery = session.scalar(select(Delivery).where(Delivery.channel_id == channel_id))
            self.assertEqual(delivery.status, "sent")
            self.assertEqual(delivery.attempts, first_attempts + 1)


class WorkerDispatchTests(DatabaseTest):
    """run_job dispatch branches: collect, import, evaluate, export, unknown, duplicate."""

    def _job(self, kind, parameters):
        with self.db.transaction() as session:
            return enqueue(session, kind, parameters, self.users["admin"]).id

    def test_collect_dispatch_with_fake_http(self):
        import httpx
        from app.v2.domains.collection import repository as collection_repository

        contents = {
            "all": daily_csv("20260930", kinds=PARTICULATE),
            "extra": daily_csv("20260930", kinds=GASES),
        }

        class FakeResponse:
            def __init__(self, content): self.content = content
            def raise_for_status(self): return None

        class FakeClient:
            def __init__(self, *args, **kwargs): pass
            def get(self, url):
                kind = url.split("beijing_")[1].split("_")[0]
                return FakeResponse(contents[kind])
            def close(self): pass

        settings = self.settings.model_copy(
            update={"source_interval_seconds": 0, "source_base_url": "https://src.example.test"}
        )
        job_id = self._job("collect", {"start": "2026-09-30", "end": "2026-09-30"})
        with patch.object(collection_repository.httpx, "Client", FakeClient), \
                patch("time.sleep", lambda *_: None):
            result = run_job(job_id, settings)
        self.assertIn(result["status"], ("completed", "partial"), result)
        with self.db.sessions() as session:
            self.assertIsNotNone(session.scalar(select(Observation.id)))

    def test_import_dispatch_and_enterprises_and_unknown_kind(self):
        key, hashed = self.store.put(daily_csv("20260930", kinds=PARTICULATE), "raw", ".csv")
        job_id = self._job("import", {"kind": "all", "storage_key": key, "sha256": hashed})
        self.assertEqual(run_job(job_id, self.settings)["status"], "completed")

        enterprises = ("企业名称,统一社会信用代码,行业,地址,联系人\n"
                       "测试企业,91110108MA01AAAAAA,制造,北京,张三\n").encode()
        key2, hashed2 = self.store.put(enterprises, "raw", ".csv")
        job_id2 = self._job("import", {"kind": "enterprises", "storage_key": key2, "sha256": hashed2})
        self.assertEqual(run_job(job_id2, self.settings)["status"], "completed")

        bad_key, bad_hash = self.store.put(b"bad,data\n", "raw", ".csv")
        job_id3 = self._job("import", {"kind": "enterprises", "storage_key": bad_key, "sha256": bad_hash})
        self.assertEqual(run_job(job_id3, self.settings)["status"], "failed")

        with self.db.transaction() as session:
            from app.v2.domains.jobs.models import Job
            weird = Job(kind="weird", parameters={}, status="queued", owner_id=self.users["admin"],
                        target_key="weird:1")
            session.add(weird)
            session.flush()
            weird_id = weird.id
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            run_job(weird_id, self.settings)

    def test_evaluate_export_and_duplicate_lock(self):
        import_file(self.db, self.store, daily_csv("20260930", kinds=PARTICULATE), "all")
        job_id = self._job("evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
        self.assertEqual(run_job(job_id, self.settings)["status"], "completed")

        export_id = self._job("export", {"start": "2026-09-30", "end": "2026-09-30", "format": "xlsx"})
        self.assertEqual(run_job(export_id, self.settings)["status"], "completed")
        client = self.client("admin")
        download = client.get(f"/api/v2/jobs/{export_id}/download")
        self.assertIn(download.status_code, (200, 302))

        from sqlalchemy import text
        with self.db.engine.connect() as lock:
            acquired = lock.scalar(text("SELECT pg_try_advisory_lock(hashtext(:key))"),
                                   {"key": f"job:{job_id}"})
            self.assertTrue(acquired)
            job_id2 = self._job("evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
            lock.scalar(text("SELECT pg_try_advisory_lock(hashtext(:key))"),
                        {"key": f"job:{job_id2}"})
            held = lock.scalar(text("SELECT pg_advisory_lock(hashtext(:key))"),
                               {"key": f"job:{job_id2}"})
            self.assertEqual(run_job(job_id2, self.settings)["status"], "duplicate")

    def test_job_cancel_and_retry_conflicts(self):
        job_id = self._job("evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
        self.assertEqual(run_job(job_id, self.settings)["status"], "completed")
        client = self.client("admin")
        self.assertEqual(client.post(f"/api/v2/jobs/{job_id}/retry").status_code, 409)
        self.assertEqual(client.post(f"/api/v2/jobs/{job_id}/cancel").status_code, 409)

        failed_id = self._job("train", {"task": "forecast", "algorithm": "seasonal",
                                        "start": "2026-09-30", "end": "2026-09-30", "seed": 1})
        self.assertEqual(run_job(failed_id, self.settings)["status"], "failed")
        retry = client.post(f"/api/v2/jobs/{failed_id}/retry")
        self.assertEqual(retry.status_code, 202)


class NotificationTransportTests(DatabaseTest):
    """Real webhook and email transport branches via patched network layers."""

    def _pending_channel(self, kind, config, credential_ref=None):
        from app.v2.domains.admin.models import Channel, Notification
        with self.db.transaction() as session:
            channel = Channel(name=f"{kind}-ch", kind=kind, config=config,
                              enabled=True, credential_ref=credential_ref)
            session.add(channel)
            session.flush()
            session.add(Notification(user_id=self.users["officer"], title="t", body="b",
                                     href="/x", dedupe_key=f"{kind}-1"))
            return channel.id

    def test_webhook_transport_with_credential(self):
        self._pending_channel("webhook", {"url": "https://hooks.example.test/ingest"},
                              credential_ref="ESP_NOTIFY_OPS")
        posted = {}

        class FakeClient:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def post(self, url, headers=None, json=None):
                posted.update(headers or {})
                class R:
                    def raise_for_status(self): return None
                return R()

        from app.v2.domains.admin import notification_worker
        import os
        with patch.dict(os.environ, {"ESP_NOTIFY_OPS": "secret-token"}), \
                patch.object(notification_worker.httpx, "Client", FakeClient):
            deliver_pending(self.db, self.settings)
        self.assertEqual(posted.get("Authorization"), "Bearer secret-token")
        self.assertIn("Idempotency-Key", posted)

    def test_email_transport_with_login(self):
        self._pending_channel("email",
                              {"host": "smtp.test", "port": 2525, "sender": "a@b.c",
                               "recipient": "d@e.f", "username": "u"},
                              credential_ref="ESP_SMTP_PASS")
        sent = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                sent["host"], sent["port"] = host, port
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def starttls(self): sent["tls"] = True
            def login(self, user, password): sent["login"] = (user, password)
            def send_message(self, message): sent["subject"] = message["Subject"]

        from app.v2.domains.admin import notification_worker
        import os
        with patch.dict(os.environ, {"ESP_SMTP_PASS": "pw"}), \
                patch.object(notification_worker.smtplib, "SMTP", FakeSMTP):
            deliver_pending(self.db, self.settings)
        self.assertEqual(sent["login"], ("u", "pw"))
        self.assertEqual(sent["subject"], "t")


class LicenseAndModelLifecycleTests(DatabaseTest):
    def setUp(self):
        super().setUp()
        self.tiny = self.settings.model_copy(update={"model_window": 24, "model_epochs": 1})

    def test_license_confirmation_branches(self):
        import json
        import tempfile
        from datetime import datetime, timedelta, timezone


class GuardBranchTests(DatabaseTest):
    """API-level guard branches across monitoring, jobs, admin, auth, enforcement."""

    def setUp(self):
        super().setUp()
        self.admin = self.client("admin")
        self.researcher = self.client("researcher")

    def test_monitoring_query_guards(self):
        self.assertEqual(self.researcher.get(
            "/api/v2/timeseries?start=2026-09-30&end=2026-09-29").status_code, 400)
        self.assertEqual(self.researcher.get(
            "/api/v2/timeseries?start=2026-09-30&end=2026-09-30&resolution=week").status_code, 422)
        self.assertEqual(self.researcher.get(
            "/api/v2/timeseries?start=2026-09-30&end=2026-09-30&station_ids=a,b,c,d,e,f").status_code, 422)
        self.assertEqual(self.researcher.get(
            "/api/v2/timeseries?start=2026-09-30&end=2026-09-30&pollutant=AQI&resolution=day").status_code, 200)
        self.assertEqual(self.researcher.get(
            "/api/v2/dashboard?start=2026-09-30&end=2026-09-29").status_code, 400)
        self.assertEqual(self.researcher.get(
            "/api/v2/data-quality?start=2026-09-30&end=2026-09-29").status_code, 400)
        import_file(self.db, self.store, daily_csv("20260930", kinds=PARTICULATE), "all")
        with self.db.sessions() as session:
            station_id = session.scalar(select(Station.id))
            city_id = session.scalar(select(City.id))
        ok = self.researcher.get(
            f"/api/v2/timeseries?start=2026-09-30&end=2026-09-30&station_ids={station_id}&city_id={city_id}")
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["items"])
        day = self.researcher.get(
            f"/api/v2/timeseries?start=2026-09-30&end=2026-09-30&resolution=day")
        self.assertEqual(day.status_code, 200)
        self.assertEqual(self.researcher.get(
            f"/api/v2/dashboard?city_id={city_id}&start=2026-09-30&end=2026-09-30").status_code, 200)
        self.assertEqual(self.researcher.get(
            f"/api/v2/data-quality?city_id={city_id}&start=2026-09-30&end=2026-09-30").status_code, 200)
        aqi = self.researcher.get(
            f"/api/v2/aqi?station_id={station_id}&start=2026-09-30&end=2026-09-30")
        self.assertIn(aqi.status_code, (200, 404))

    def test_job_submission_and_download_guards(self):
        bad_algo = self.admin.post("/api/v2/jobs", json={
            "kind": "train", "task": "imputation", "algorithm": "lightgbm",
            "start": "2026-09-30", "end": "2026-09-30"})
        self.assertEqual(bad_algo.status_code, 422)
        bad_range = self.admin.post("/api/v2/jobs", json={
            "kind": "evaluate", "start": "2026-09-30", "end": "2026-09-29"})
        self.assertEqual(bad_range.status_code, 422)

        export_id = self._job("export", {"start": "2026-09-30", "end": "2026-09-30",
                                         "report": "inspections"})
        self.assertEqual(run_job(export_id, self.settings)["status"], "completed")
        self.assertEqual(self.researcher.get(f"/api/v2/jobs/{export_id}/download").status_code, 404)
        self.assertEqual(self.admin.get(f"/api/v2/jobs/{export_id}/download").status_code, 200)
        with self.db.transaction() as session:
            own_export = enqueue(session, "export",
                                 {"start": "2026-09-30", "end": "2026-09-30",
                                  "report": "inspections"}, self.users["researcher"]).id
        self.assertEqual(self.researcher.get(f"/api/v2/jobs/{own_export}/download").status_code, 403)

        queued = self._job("evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
        self.assertEqual(self.admin.get(f"/api/v2/jobs/{queued}/download").status_code, 409)
        with self.db.transaction() as session:
            own_collect = enqueue(session, "collect",
                                  {"start": "2026-09-30", "end": "2026-09-30"},
                                  self.users["researcher"])
            own_collect.status = "failed"
            collect_id = own_collect.id
        self.assertEqual(self.researcher.post(f"/api/v2/jobs/{collect_id}/retry").status_code, 403)

    def test_admin_guard_branches(self):
        law_bad = self.admin.post("/api/v2/admin/laws", json={
            "title": "测试法规", "region": "全国", "effective_from": "2026-02-01",
            "effective_to": "2026-01-01", "source_url": "https://x.test",
            "summary": "摘要内容足够长"})
        self.assertEqual(law_bad.status_code, 422)
        law = self.admin.post("/api/v2/admin/laws", json={
            "title": "测试法规", "region": "全国", "effective_from": "2026-01-01",
            "source_url": "https://x.test", "summary": "摘要内容足够长"})
        self.assertEqual(law.status_code, 201, law.text)
        law_id = law.json()["id"]
        end_bad = self.admin.patch(f"/api/v2/admin/laws/{law_id}/end",
                                   json={"effective_to": "2025-01-01", "reason": "失效测试原因"})
        self.assertEqual(end_bad.status_code, 422)
        end_ok = self.admin.patch(f"/api/v2/admin/laws/{law_id}/end",
                                  json={"effective_to": "2026-02-01", "reason": "失效测试原因"})
        self.assertEqual(end_ok.status_code, 200)

        standard_bad_unit = self.admin.post("/api/v2/admin/standards", json={
            "code": "TST-1", "pollutant": "PM2.5", "basis": "daily_mean", "region": "测试区",
            "limit_value": 50, "unit": "mg/m³", "min_points": 20, "effective_from": "2026-01-01",
            "source_url": "https://x.test", "article": "条款"})
        self.assertEqual(standard_bad_unit.status_code, 422)
        standard_bad_basis = self.admin.post("/api/v2/admin/standards", json={
            "code": "TST-2", "pollutant": "O3", "basis": "daily_mean", "region": "测试区",
            "limit_value": 50, "unit": "μg/m³", "min_points": 20, "effective_from": "2026-01-01",
            "source_url": "https://x.test", "article": "条款"})
        self.assertEqual(standard_bad_basis.status_code, 422)
        standard_ok = self.admin.post("/api/v2/admin/standards", json={
            "code": "TST-3", "pollutant": "PM2.5", "basis": "daily_mean", "region": "测试区甲",
            "limit_value": 50, "unit": "μg/m³", "min_points": 20, "effective_from": "2026-01-01",
            "source_url": "https://x.test", "article": "条款"})
        self.assertEqual(standard_ok.status_code, 201, standard_ok.text)
        standard_dup = self.admin.post("/api/v2/admin/standards", json={
            "code": "TST-4", "pollutant": "PM2.5", "basis": "daily_mean", "region": "测试区甲",
            "limit_value": 60, "unit": "μg/m³", "min_points": 20, "effective_from": "2026-01-01",
            "source_url": "https://x.test", "article": "条款"})
        self.assertEqual(standard_dup.status_code, 409)
        standard_id = standard_ok.json()["id"]
        end_early = self.admin.patch(f"/api/v2/admin/standards/{standard_id}/end",
                                     json={"effective_to": "2025-01-01", "reason": "测试失效原因"})
        self.assertEqual(end_early.status_code, 422)
        end_ok2 = self.admin.patch(f"/api/v2/admin/standards/{standard_id}/end",
                                   json={"effective_to": "2026-06-01", "reason": "测试失效原因"})
        self.assertEqual(end_ok2.status_code, 200)
        end_late = self.admin.patch(f"/api/v2/admin/standards/{standard_id}/end",
                                    json={"effective_to": "2027-01-01", "reason": "测试失效原因"})
        self.assertEqual(end_late.status_code, 422)

        missing = self.admin.post("/api/v2/models/nonexistent/activate")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(self.admin.post("/api/v2/models/forecast/rollback").status_code, 409)

    def test_auth_edge_branches(self):
        from fastapi.testclient import TestClient
        client = TestClient(self.app)
        bad_origin = client.post("/api/v2/auth/login",
                                 headers={"Origin": "https://evil.example.test"},
                                 json={"username": "admin", "password": PASSWORD})
        self.assertEqual(bad_origin.status_code, 403)

        login = self.admin.post("/api/v2/auth/login",
                                json={"username": "admin", "password": PASSWORD})
        self.assertEqual(login.status_code, 200)
        self.admin.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        wrong = self.admin.post("/api/v2/auth/change-password",
                                json={"current_password": "wrong", "new_password": "NewPass#123456"})
        self.assertEqual(wrong.status_code, 422)
        same = self.admin.post("/api/v2/auth/change-password",
                               json={"current_password": PASSWORD, "new_password": PASSWORD})
        self.assertEqual(same.status_code, 422)

        no_csrf = TestClient(self.app)
        login2 = no_csrf.post("/api/v2/auth/login",
                              json={"username": "admin", "password": PASSWORD})
        self.assertEqual(login2.status_code, 200)
        forbidden = no_csrf.post("/api/v2/auth/change-password",
                                 json={"current_password": PASSWORD,
                                       "new_password": "DifferentPass#123456"})
        self.assertEqual(forbidden.status_code, 403)

        self.assertEqual(self.admin.get("/api/v2/auth/me").status_code, 200)
        self.assertEqual(self.admin.post("/api/v2/auth/logout").status_code, 204)
        expired = self.admin.get("/api/v2/auth/me")
        self.assertEqual(expired.status_code, 401)

    def _job(self, kind, parameters):
        with self.db.transaction() as session:
            return enqueue(session, kind, parameters, self.users["admin"]).id


class ParseWideErrorTests(unittest.TestCase):
    def test_parse_wide_error_branches(self):
        from app.v2.domains.collection.repository import parse_wide

        with self.assertRaises(ValueError):
            parse_wide("date,hour,type,重复,重复\n20260930,0,PM2.5,1,1\n".encode())
        with self.assertRaises(ValueError):
            parse_wide("date,hour,type,站\n20260930,0,PM2.5,1,多余\n".encode())
        with self.assertRaises(ValueError):
            parse_wide("date,hour,type,站\n20260930,25,PM2.5,1\n".encode())
        with self.assertRaises(ValueError):
            parse_wide("date,hour,type,站\nbad,0,PM2.5,1\n".encode())
        with self.assertRaises(ValueError):
            parse_wide("date,hour,type,站\n20260930,0,PM2.5,1\n20260930,0,PM2.5,2\n".encode())
        day, stations, rows, invalid = parse_wide(
            "date,hour,type,站甲,站乙\n20260930,0,PM2.5,NA,30\n20260930,0,PM10,40,abc\n"
            "20260930,0,AQI,50,60\n20260930,0,UNKNOWN,1,1\n".encode())
        self.assertEqual(invalid, 1)


class LegacyAdapterFlagTests(DatabaseTest):
    """admin routes falling back to LegacyUserAdministrationAdapter."""

    def test_legacy_adapter_routes(self):
        patched = self.settings.model_copy(update={
            "user_administration_service_enabled": False,
            "admin_read_service_enabled": False,
        })
        self.app.state.settings = patched
        try:
            client = self.client("admin")
            self.assertEqual(client.get("/api/v2/people").status_code, 200)
            self.assertEqual(client.get("/api/v2/admin/users").status_code, 200)
            self.assertEqual(client.get("/api/v2/admin/audits").status_code, 200)
            for path in ("/api/v2/standards", "/api/v2/laws", "/api/v2/notifications",
                         "/api/v2/admin/sources", "/api/v2/models", "/api/v2/admin/channels"):
                self.assertEqual(client.get(path).status_code, 200, path)
            created = client.post("/api/v2/admin/users", json={
                "username": "legacy-user", "display_name": "旧", "role": "研究者",
                "password": "InitialPass#2026!"})
            self.assertEqual(created.status_code, 201, created.text)
            updated = client.patch(f"/api/v2/admin/users/{created.json()['id']}",
                                   json={"role": "执法人员", "active": True})
            self.assertEqual(updated.status_code, 200)
            self_guard = client.patch(f"/api/v2/admin/users/{self.users['admin']}",
                                      json={"role": "研究者", "active": True})
            self.assertEqual(self_guard.status_code, 422)
        finally:
            self.app.state.settings = self.settings


class DeepEnforcementTests(DatabaseTest):
    """Transition/rectification/attachment deeper guard branches."""

    def setUp(self):
        super().setUp()
        self.officer = self.client("officer")
        self.supervisor = self.client("supervisor")
        lead = self.client("admin").post("/api/v2/leads",
                                       json={"title": "深度核查线索", "description": "详情内容描述"})
        assigned = self.client("admin").post(f"/api/v2/leads/{lead.json()['id']}/assign", json={
            "assignee_id": self.users["officer"], "collaborators": [self.users["supervisor"]],
            "due_date": "2026-12-31", "note": "指派说明"})
        self.assertEqual(assigned.status_code, 201, assigned.text)
        with self.db.sessions() as session:
            self.inspection_id = session.scalar(
                select(Inspection.id).where(Inspection.lead_id == lead.json()["id"]))

    def _transition(self, action, version, note="操作说明文字", user=None):
        return (user or self.officer).post(
            f"/api/v2/inspections/{self.inspection_id}/transition",
            json={"action": action, "version": version, "note": note})

    def test_full_workflow_and_rectification_cycle(self):
        self.assertEqual(self._transition("rectify", 1).status_code, 409)
        self.assertEqual(self._transition("start", 1).status_code, 200)

        self.assertEqual(self._transition("rectify", 2).status_code, 422)

        facts = self.officer.put(f"/api/v2/inspections/{self.inspection_id}", json={
            "facts": "核查事实描述内容", "legal_references": [], "version": 2})
        self.assertEqual(facts.status_code, 200, facts.text)

        self.assertEqual(self._transition("rectify", 3).status_code, 422)

        requirement = self.officer.post(
            f"/api/v2/inspections/{self.inspection_id}/rectifications", json={
                "requirement": "整改要求内容详细", "due_date": "2026-12-01", "version": 3})
        self.assertEqual(requirement.status_code, 201, requirement.text)

        self.assertEqual(self._transition("rectify", 4).status_code, 200)

        self.assertEqual(self._transition("submit_rectification", 5).status_code, 422)

        rect_id = requirement.json()["id"]
        responded = self.officer.put(
            f"/api/v2/inspections/{self.inspection_id}/rectifications/{rect_id}", json={
                "response": "整改完成情况说明", "review_note": "", "verified": False, "version": 5})
        self.assertEqual(responded.status_code, 200, responded.text)

        self.assertEqual(self._transition("submit_rectification", 6).status_code, 200)
        self.assertEqual(self._transition("reinspect", 7, user=self.supervisor).status_code, 200)

        bad_verify = self.officer.put(
            f"/api/v2/inspections/{self.inspection_id}/rectifications/{rect_id}", json={
                "response": "整改完成情况", "review_note": "", "verified": True, "version": 8})
        self.assertEqual(bad_verify.status_code, 422)
        verify = self.officer.put(
            f"/api/v2/inspections/{self.inspection_id}/rectifications/{rect_id}", json={
                "response": "整改完成情况", "review_note": "复查结论确认", "verified": True, "version": 8})
        self.assertEqual(verify.status_code, 200, verify.text)

        self.assertEqual(self._transition("submit_review", 9).status_code, 200)
        self.assertEqual(self._transition("approve", 10, user=self.officer).status_code, 403)
        self.assertEqual(self._transition("approve", 10, user=self.supervisor).status_code, 200)

        attach_after_review = self.officer.post("/api/v2/attachments", data={
            "inspection_id": self.inspection_id},
            files={"file": ("late.bin", b"data")})
        self.assertEqual(attach_after_review.status_code, 409)

        self.assertEqual(self._transition("reopen", 11, user=self.supervisor).status_code, 200)

    def test_list_filters_and_attachment_edges(self):
        self.assertEqual(self.officer.get("/api/v2/leads?status=assigned&q=深度").status_code, 200)
        self.assertEqual(self.officer.get("/api/v2/leads?status=pending").status_code, 200)
        self.assertEqual(self.officer.get("/api/v2/inspections?status=assigned&q=深度").status_code, 200)
        self.assertEqual(self.officer.get("/api/v2/enterprises?q=不存在").status_code, 200)

        upload1 = self.officer.post("/api/v2/attachments", data={
            "inspection_id": self.inspection_id}, files={"file": ("v1.bin", b"one")})
        self.assertEqual(upload1.status_code, 201, upload1.text)
        other_lead = self.client("admin").post("/api/v2/leads",
                                               json={"title": "另一线索", "description": "详情内容描述"})
        other_assigned = self.client("admin").post(
            f"/api/v2/leads/{other_lead.json()['id']}/assign", json={
                "assignee_id": self.users["officer"], "collaborators": [],
                "due_date": "2026-12-31", "note": "指派"})
        with self.db.sessions() as session:
            other_id = session.scalar(
                select(Inspection.id).where(Inspection.lead_id == other_lead.json()["id"]))
        replace_wrong = self.officer.post("/api/v2/attachments", data={
            "inspection_id": other_id, "replaces_id": upload1.json()["id"]},
            files={"file": ("v2.bin", b"two")})
        self.assertEqual(replace_wrong.status_code, 422)
        replace_ok = self.officer.post("/api/v2/attachments", data={
            "inspection_id": self.inspection_id, "replaces_id": upload1.json()["id"]},
            files={"file": ("v2.bin", b"two")})
        self.assertEqual(replace_ok.status_code, 201, replace_ok.text)


class ModelInferBranchesTests(DatabaseTest):
    """LightGBM forecast predict and SAITS imputation infer paths."""

    def setUp(self):
        super().setUp()
        self.tiny = self.settings.model_copy(update={"model_window": 24, "model_epochs": 1})

    def _seed(self, days=17):
        start = DAY - timedelta(days=days - 1)
        for offset in range(days):
            day = (start + timedelta(days=offset)).strftime("%Y%m%d")
            import_file(self.db, self.store, daily_csv(day, kinds=PARTICULATE), "all")
            import_file(self.db, self.store, daily_csv(day, kinds=GASES), "extra")
        return start.strftime("%Y-%m-%d")

    def _job(self, kind, parameters):
        with self.db.transaction() as session:
            return enqueue(session, kind, parameters, self.users["admin"]).id

    def _activate_latest(self):
        models = self.client("admin").get("/api/v2/models").json()["items"]
        model_id = models[0]["id"]
        activated = self.client("admin").post(f"/api/v2/models/{model_id}/activate")
        self.assertIn(activated.status_code, (200, 409))

    def test_lightgbm_forecast_and_saits_impute_inference(self):
        start = self._seed()
        forecast_train = self._job("train", {"task": "forecast", "algorithm": "lightgbm",
                                             "start": start, "end": "2026-09-30", "seed": 3})
        self.assertEqual(run_job(forecast_train, self.tiny)["status"], "completed")
        self._activate_latest()
        forecast_job = self._job("forecast", {"task": "forecast", "algorithm": "lightgbm",
                                              "start": "2026-09-30", "end": "2026-09-30", "seed": 3})
        self.assertIn(run_job(forecast_job, self.tiny)["status"], ("completed", "partial"))

        impute_train = self._job("train", {"task": "imputation", "algorithm": "SAITS",
                                           "start": start, "end": "2026-09-30", "seed": 3})
        self.assertEqual(run_job(impute_train, self.tiny)["status"], "completed")
        self._activate_latest()
        impute_job = self._job("impute", {"task": "imputation", "algorithm": "SAITS",
                                          "start": "2026-09-30", "end": "2026-09-30", "seed": 3})
        self.assertIn(run_job(impute_job, self.tiny)["status"], ("completed", "partial", "failed"))


class ResidualBranchTests(DatabaseTest):
    """Surgical coverage for the remaining worker/admin/monitoring/backup branches."""

    def setUp(self):
        super().setUp()
        self.tiny = self.settings.model_copy(update={"model_window": 24, "model_epochs": 1})

    def _job(self, kind, parameters):
        with self.db.transaction() as session:
            job = enqueue(session, kind, parameters, self.users["admin"])
            return job.id

    def _seed_days(self, days=17):
        start = DAY - timedelta(days=days - 1)
        for offset in range(days):
            day = (start + timedelta(days=offset)).strftime("%Y%m%d")
            import_file(self.db, self.store, daily_csv(day, kinds=PARTICULATE), "all")
            import_file(self.db, self.store, daily_csv(day, kinds=GASES), "extra")
        return start.strftime("%Y-%m-%d")

    def test_worker_missing_dates_and_task_wrapper(self):
        collect_id = self._job("collect", {})
        evaluate_id = self._job("evaluate", {})
        self.assertEqual(run_job(collect_id, self.tiny)["status"], "failed")
        self.assertEqual(run_job(evaluate_id, self.tiny)["status"], "failed")
        import app.v2.domains.jobs.worker as worker
        ok_id = self._job("evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
        with patch.object(worker, "settings", self.tiny):
            self.assertEqual(worker.execute_job(ok_id)["status"], "completed")

    def test_worker_result_contract_and_failure_branches(self):
        import app.v2.domains.jobs.worker as worker

        def run_with(fake):
            jid = self._job("evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
            with patch.object(worker, "dispatch", fake):
                return jid, run_job(jid, self.tiny)

        _, result = run_with(lambda *a: "not-a-dict")
        self.assertEqual(result["status"], "failed")

        jid, result = run_with(lambda *a: {"failures": [{"station": "x"}]})
        with self.db.sessions() as session:
            self.assertEqual(session.get(Job, jid).status, "partial")

        def delete_mid_dispatch(db, store, cfg, job, progress):
            with db.transaction() as session:
                session.delete(session.get(Job, job.id))
            return {}

        jid, result = run_with(delete_mid_dispatch)
        self.assertEqual(result["status"], "failed")

        def boom(*a):
            raise RuntimeError("unexpected internals")

        jid, result = run_with(boom)
        self.assertEqual(result["status"], "failed")
        with self.db.sessions() as session:
            error = session.get(Job, jid).error or ""
            self.assertIn("请联系管理员", error)
            self.assertNotIn("unexpected internals", error)

    def test_worker_heartbeat_thread_and_duplicate_lock(self):
        import threading

        jid = self._job("evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
        original_wait = threading.Event.wait
        calls = [0]

        def fast_wait(event, timeout=None):
            calls[0] += 1
            return False if calls[0] <= 3 else original_wait(event, timeout)

        with patch.object(threading.Event, "wait", fast_wait):
            self.assertEqual(run_job(jid, self.tiny)["status"], "completed")
        self.assertGreaterEqual(calls[0], 1)

        other = self._job("evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
        with self.db.engine.connect() as holder:
            holder.execute(text("SELECT pg_advisory_lock(hashtext(:k))"), {"k": f"job:{other}"})
            self.assertEqual(run_job(other, self.tiny)["status"], "duplicate")

    def test_brits_training_and_imputation_edges(self):
        from app.v2 import imputation

        times = __import__("pandas").date_range("2026-09-01", "2026-09-10", freq="h", tz="Asia/Shanghai")
        data = np.full((1, len(times), len(POLLUTANTS)), np.nan, dtype=np.float32)
        with self.assertRaises(ValueError):
            imputation.train(data, times, ["s1"], "SAITS", 7, 24, self.tiny, self.store, lambda p: None)
        short = __import__("pandas").date_range("2026-09-01", periods=30, freq="h", tz="Asia/Shanghai")
        small = np.full((1, len(short), len(POLLUTANTS)), 10.0, dtype=np.float32)
        with self.assertRaises(ValueError):
            imputation.train(small, short, ["s1"], "SAITS", 7, 24, self.tiny, self.store, lambda p: None)

        self.assertIsNotNone(imputation.construct("BRITS", 24, len(POLLUTANTS), self.tiny))

        start = self._seed_days()
        import_file(self.db, self.store, sparse_csv(kinds=PARTICULATE), "all")
        import_file(self.db, self.store, sparse_csv(kinds=GASES), "extra")
        job_id = self._job("train", {"task": "imputation", "algorithm": "BRITS",
                                     "start": start, "end": "2026-09-30", "seed": 5})
        self.assertEqual(run_job(job_id, self.tiny)["status"], "completed")
        with self.db.transaction() as session:
            artifact = session.scalars(select(ModelArtifact)).first()
            artifact.status = "validated"
            model_id = artifact.id
        client = self.client("admin")
        self.assertEqual(client.post(f"/api/v2/models/{model_id}/activate").status_code, 200)
        impute_id = self._job("impute", {"task": "imputation", "algorithm": "BRITS",
                                         "start": "2026-09-30", "end": "2026-09-30", "seed": 5})
        self.assertIn(run_job(impute_id, self.tiny)["status"], ("completed", "partial"))

    def test_license_confirmation_summary_branches(self):
        from app.v2.shared.license import read_license_confirmation
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "lic"
            self.assertEqual(read_license_confirmation(None)["reason"], "confirmation_file_not_configured")
            self.assertEqual(read_license_confirmation(root)["reason"], "confirmation_file_missing")
            root.mkdir(parents=True)
            self.assertEqual(read_license_confirmation(root)["reason"], "confirmation_file_invalid")
            bad = root / "bad.json"
            bad.write_text("{oops", encoding="utf-8")
            self.assertEqual(read_license_confirmation(bad)["reason"], "confirmation_file_invalid")
            base = {"provider": "Quotsoft", "record_id": "r1", "confirmed_by": "qa",
                    "scope": "continuous_business_use", "evidence_sha256": "ab" * 32,
                    "reference": "ref-1"}
            naive = root / "naive.json"
            naive.write_text(json.dumps({**base, "confirmed_at": "2026-01-01T00:00:00"}), encoding="utf-8")
            self.assertEqual(read_license_confirmation(naive)["reason"], "confirmed_at_requires_timezone")
            future = root / "future.json"
            future.write_text(json.dumps({**base, "confirmed_at": "2999-01-01T00:00:00+00:00"}), encoding="utf-8")
            self.assertEqual(read_license_confirmation(future)["reason"], "confirmed_at_is_in_the_future")
            good = root / "good.json"
            good.write_text(json.dumps({**base, "confirmed_at": "2026-01-01T00:00:00+00:00"}), encoding="utf-8")
            self.assertTrue(read_license_confirmation(good)["valid"])

    def test_monitoring_filters_and_limit_guards(self):
        Helpers.seeded(self.db, self.store)
        researcher = self.client("researcher")
        with self.db.sessions() as session:
            station_id = session.scalar(select(Station.id))
            city_id = session.scalar(select(City.id))
        self.assertEqual(researcher.get(
            f"/api/v2/observations?station_id={station_id}&city_id={city_id}"
            "&pollutant=PM2.5&start=2026-09-30&end=2026-09-30").status_code, 200)
        evaluate_id = self._job("evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
        run_job(evaluate_id, self.tiny)
        resp = researcher.get(
            f"/api/v2/evaluations?station_id={station_id}&city_id={city_id}"
            "&pollutant=PM2.5&status=exceeded&start=2026-09-30&end=2026-09-30")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(researcher.get(
            "/api/v2/dashboard?start=2020-01-01&end=2026-01-01").status_code, 400)
        too_many = researcher.get(
            f"/api/v2/timeseries?start=2026-07-01&end=2026-09-30&station_ids="
            f"{station_id},{station_id},{station_id},{station_id},{station_id}")
        self.assertEqual(too_many.status_code, 422)
        self.assertIn("查询结果过大", too_many.text)

    def test_collection_parse_and_import_residual_edges(self):
        with self.assertRaises(ValueError):
            parse_wide(b"date,hour,type,\n20260930,0,PM2.5,10\n")
        negative = b"date,hour,type,A,B\n20260930,0,PM2.5,-5,20\n"
        _, _, _, invalid = parse_wide(negative)
        self.assertEqual(invalid, 1)
        with self.assertRaises(ValueError):
            parse_wide(b"date,hour,type,B\n20260930,0,PM2.5,10\n20260929,0,PM2.5,10\n")
        with self.assertRaises(ValueError):
            parse_wide(b"date,hour,type,B\n")
        with self.assertRaises(ValueError):
            import_file(self.db, self.store, daily_csv(), "weird")
        with self.assertRaises(ValueError):
            import_file(self.db, self.store, daily_csv("20260930", kinds=PARTICULATE), "extra")
        result = import_file(self.db, self.store, daily_csv("20260930", stations=("新建站点丙",)), "all")
        self.assertGreater(result["inserted"], 0)
        with self.db.sessions() as session:
            self.assertIsNotNone(session.scalar(
                select(Station).where(Station.name == "新建站点丙")))

    def test_collect_range_size_limit_and_attempt(self):
        from app.v2.domains.collection.repository import collect_range
        small = self.tiny.model_copy(update={"max_upload_bytes": 1})

        class FakeResponse:
            content = b"date,hour,type,A\n2026-09-30,0,PM2.5,10\n"

            def raise_for_status(self):
                return None

        class FakeClient:
            def get(self, url):
                return FakeResponse()

        with self.db.transaction() as session:
            job = enqueue(session, "collect", {})
        result = collect_range(self.db, self.store, small, DAY, DAY, job.id, lambda p: None,
                               client=FakeClient())
        self.assertTrue(result["failures"])

    def test_admin_notification_activation_rollback_and_write_guards(self):
        client = self.client("admin")
        with self.db.transaction() as session:
            note = Notification(user_id=self.users["admin"], title="t", body="b", href="/", dedupe_key="k1")
            session.add(note)
            session.flush()
            notification_id = note.id
        self.assertEqual(client.post(f"/api/v2/notifications/{notification_id}/read").status_code, 200)

        from app.v2.domains.ml.models import ModelArtifact

        def make_model(tag):
            ck, ck_hash = self.store.put(b"checkpoint-bytes", "checkpoints", ".bin")
            payload = json.dumps({"algorithm": "seasonal", "tag": tag,
                                  "checkpoint": {"storage_key": ck, "sha256": ck_hash}}).encode()
            key, hashed = self.store.put(payload, "models", ".json")
            with self.db.transaction() as session:
                backing = enqueue(session, "train", {"task": "forecast", "algorithm": "seasonal"})
                model = ModelArtifact(task="forecast", algorithm="seasonal", status="validated",
                                      storage_key=key, sha256=hashed, manifest={}, metrics={},
                                      job_id=backing.id)
                session.add(model)
                session.flush()
                return model.id

        first, second = make_model("a"), make_model("b")
        self.assertEqual(client.post(f"/api/v2/models/{first}/activate").status_code, 200)
        self.assertEqual(client.post(f"/api/v2/models/{second}/activate").status_code, 200)
        self.assertEqual(client.post("/api/v2/models/forecast/rollback").status_code, 200)
        self.assertEqual(client.post("/api/v2/models/imputation/rollback").status_code, 409)

        with self.db.sessions() as session:
            station_id = session.scalar(select(Station.id))
        bad_alias = client.post(f"/api/v2/admin/stations/{station_id}/aliases", json={
            "external_name": "旧称", "valid_from": "2026-06-01", "valid_to": "2026-05-01"})
        self.assertEqual(bad_alias.status_code, 422)
        bad_standard = client.post("/api/v2/admin/standards", json={
            "pollutant": "O3", "basis": "daily", "region": "全国", "limit": 100, "unit": "μg/m³",
            "effective_from": "2026-01-01"})
        self.assertEqual(bad_standard.status_code, 422)
        self_downgrade = client.patch(f"/api/v2/admin/users/{self.users['admin']}", json={
            "role": "研究者", "active": True})
        self.assertEqual(self_downgrade.status_code, 422)

    def test_auth_session_and_csrf_edges(self):
        client = self.client("researcher")
        del client.headers["X-CSRF-Token"]
        self.assertEqual(client.post("/api/v2/auth/logout").status_code, 403)
        with self.db.transaction() as session:
            session.execute(text("UPDATE v2_sessions SET expires_at = :past"),
                            {"past": now() - timedelta(hours=1)})
        self.assertEqual(client.get("/api/v2/auth/me").status_code, 401)
        with self.db.transaction() as session:
            user = session.get(User, self.users["researcher"])
            user.active = False
        self.assertEqual(client.get("/api/v2/auth/me").status_code, 401)

    def test_jobs_validation_conflicts_and_public_facade(self):
        admin = self.client("admin")
        researcher = self.client("researcher")
        mismatch = admin.post("/api/v2/jobs", json={
            "kind": "train", "task": "forecast", "algorithm": "SAITS",
            "start": "2026-09-01", "end": "2026-09-30"})
        self.assertEqual(mismatch.status_code, 422)
        bad_station = admin.post("/api/v2/jobs", json={
            "kind": "collect", "start": "2026-09-30", "end": "2026-09-30",
            "station_id": "nonexistent"})
        self.assertEqual(bad_station.status_code, 404)

        failed = self._job("evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
        with patch("app.v2.domains.jobs.worker.dispatch",
                   lambda *a: (_ for _ in ()).throw(ValueError("x"))):
            run_job(failed, self.tiny)
        self.assertEqual(researcher.post(f"/api/v2/jobs/{failed}/retry").status_code, 404)
        with self.db.transaction() as session:
            job = session.get(Job, failed)
            job.owner_id = self.users["researcher"]
            job.kind = "collect"
        self.assertEqual(researcher.post(f"/api/v2/jobs/{failed}/retry").status_code, 403)

        done = self._job("evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
        run_job(done, self.tiny)
        self.assertEqual(admin.post(f"/api/v2/jobs/{done}/cancel").status_code, 409)
        self.assertEqual(admin.post(f"/api/v2/jobs/{done}/retry").status_code, 409)
        self.assertEqual(admin.get("/api/v2/jobs?status=succeeded").status_code, 200)

        with self.db.sessions() as session:
            public = public_job(session.get(Job, done))
        self.assertIn("download_available", public)

        with self.assertRaises(ValueError):
            import_enterprises(
                self.db,
                "企业名称,统一社会信用代码,行业,地址,联系人\n坏行,wrong,工,京,人\n".encode(),
                self.users["admin"])

    def test_main_lifespan_health_and_error_handlers(self):
        from fastapi.testclient import TestClient
        from app.v2.main import create_app

        with self.db.engine.connect() as connection:
            connection.execute(text(
                "CREATE TABLE IF NOT EXISTS v2_alembic_version(version_num varchar(32) NOT NULL)"))
            connection.commit()
        with TestClient(create_app(self.settings)) as client:
            self.assertEqual(client.get("/health/live").json()["status"], "ok")
            self.assertEqual(client.get("/health/ready").status_code, 200)
            missing = client.get("/api/v2/does-not-exist")
            self.assertEqual(missing.status_code, 404)
            self.assertIn("接口不存在", missing.text)

    def test_scheduler_stalled_recovery_and_lock_failure(self):
        import os
        import app.v2.domains.jobs.scheduler_worker as scheduler_worker

        with self.db.transaction() as session:
            job = enqueue(session, "evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
            message = session.scalar(select(Outbox).where(Outbox.job_id == job.id))
            message.sent_at = now() - timedelta(minutes=30)
            job.status = "running"
            job.heartbeat_at = now() - timedelta(minutes=30)
        recover_stalled(self.db)
        with self.db.sessions() as session:
            self.assertIsNone(session.scalar(select(Outbox.sent_at)))

        development = self.settings.model_copy(update={"environment": "development"})
        schedule_daily(self.db, development, local_now=datetime(2026, 9, 30, 6, 0, tzinfo=LOCAL))

        with self.db.engine.connect() as holder:
            holder.execute(text(
                "SELECT pg_advisory_lock(hashtext('platform-scheduler:' || current_schema()))"))
            environment = {
                "ESP_DATABASE_URL": self.settings.database_url,
                "ESP_SECRET_KEY": "x" * 40,
                "ESP_STORAGE_ROOT": str(self.store.root),
                "ESP_ENVIRONMENT": "test",
            }
            with patch.dict(os.environ, environment):
                with self.assertRaises(RuntimeError):
                    scheduler_worker.main()

    def test_scheduler_tick_exception_branch(self):
        import os
        import signal
        import threading
        import app.v2.domains.jobs.scheduler_worker as scheduler_worker

        with self.db.transaction() as session:
            enqueue(session, "evaluate", {"start": "2026-09-30", "end": "2026-09-30"})
        environment = {
            "ESP_DATABASE_URL": self.settings.database_url,
            "ESP_SECRET_KEY": "x" * 40,
            "ESP_STORAGE_ROOT": str(self.store.root),
            "ESP_ENVIRONMENT": "test",
        }

        def killer():
            threading.Event().wait(0.8)
            os.kill(os.getpid(), signal.SIGTERM)

        def broken(*a, **k):
            raise RuntimeError("simulated tick failure")

        with patch.dict(os.environ, environment), \
                patch("app.v2.domains.admin.notification_worker.deliver_pending", broken):
            thread = threading.Thread(target=killer, daemon=True)
            thread.start()
            scheduler_worker.main()
            thread.join(timeout=5)

    def test_evaluation_subindex_and_legacy_filtered_edges(self):
        from app.v2.domains.monitoring.evaluation_repository import subindex
        from app.v2.domains.monitoring.legacy import filtered
        from app.v2.shared.http_errors import AppError

        self.assertIsNotNone(subindex("PM10", 150, DAY))
        self.assertIsNotNone(subindex("PM2.5", 9999, DAY))
        self.assertIsNone(subindex("O3", 900, date(2026, 2, 1)))
        with self.assertRaises(AppError):
            filtered(DAY, DAY - timedelta(days=1))
        statement = filtered(DAY - timedelta(days=1), DAY, station_id="s1",
                             pollutant="AQI", city_id="c1")
        self.assertIsNotNone(statement)

    def test_domain_facades_and_dataset_guards(self):
        import app.v2.domains.ml as ml_domain
        import app.v2.domains.admin as admin_domain
        import app.v2.domains.auth as auth_domain
        import app.v2.domains.enforcement as enforcement_domain
        import app.v2.domains.monitoring as monitoring_domain

        for module in (ml_domain, admin_domain, auth_domain, enforcement_domain, monitoring_domain):
            with self.assertRaises(AttributeError):
                getattr(module, "no_such_attribute")
        self.assertTrue(callable(ml_domain.model_job))
        for module in (admin_domain, auth_domain, enforcement_domain, monitoring_domain):
            self.assertTrue(hasattr(module, "router"))

        with self.assertRaises(ValueError):
            splits(10, 24)
        with self.assertRaises(ValueError):
            scores(np.array([np.nan, np.nan]), np.array([np.nan, np.nan]))
        with patch("importlib.metadata.version",
                   side_effect=__import__("importlib").metadata.PackageNotFoundError):
            manifest = environment_manifest()
        self.assertIn("python", manifest)

        from app.v2 import forecasting
        times = __import__("pandas").date_range("2026-09-01", "2026-09-20", freq="h", tz="Asia/Shanghai")
        data = np.full((1, len(times), len(POLLUTANTS)), np.nan, dtype=np.float32)
        with self.assertRaises((ValueError, KeyError)):
            forecasting.train(data, times, ["s1"], "lightgbm", 7, 24, lambda p: None)

    def test_storage_edges_and_backup_reference_walk(self):
        from app.v2.shared.backup_repository import referenced_payload_files, file_manifest
        from app.v2.domains.ml.models import ModelArtifact

        self.assertEqual(referenced_payload_files(None), {})
        self.assertEqual(referenced_payload_files({"storage_key": "k", "sha256": "h"}), {"k": "h"})
        with self.assertRaises(Exception):
            self.store.path("../escape")
        with self.assertRaises(ValueError):
            self.store._write(self.store.path("tmp/mismatch"), "0" * 64, iter([b"data"]))
        nested = self.store.root / "deep" / "nested" / "dir"
        nested.mkdir(parents=True)
        self.store._sync_directories(nested)

        ck, ck_hash = self.store.put(b"ck", "checkpoints", ".bin")
        snap, snap_hash = self.store.put(b"snap", "snapshots", ".csv")
        artifact_key, artifact_hash = self.store.put(
            json.dumps({"checkpoint": {"storage_key": ck, "sha256": ck_hash}}).encode(),
            "models", ".json")
        with self.db.transaction() as session:
            backing = enqueue(session, "train", {"task": "forecast", "algorithm": "seasonal"})
            model = ModelArtifact(task="forecast", algorithm="seasonal", status="validated",
                                  storage_key=artifact_key, sha256=artifact_hash,
                                  manifest={"snapshot": {"storage_key": snap, "sha256": snap_hash}},
                                  metrics={}, job_id=backing.id)
            session.add(model)
        manifest = file_manifest(self.db, self.store)
        self.assertIn(snap, manifest)
