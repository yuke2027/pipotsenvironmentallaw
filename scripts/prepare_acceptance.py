"""Seed only the explicitly isolated acceptance schema; never the live schema."""
import argparse
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select, text
from alembic import command
from alembic.config import Config
from app.v2.auth import hasher
from app.v2.collection import import_file
from app.v2.config import Settings
from app.v2.db import Database
from app.v2.evaluation import evaluate_range
from app.v2.domains.auth.models import User
from app.v2.domains.enforcement.models import Enterprise, Inspection, Lead, WorkflowEvent
from app.v2.shared.persistence import Base
from app.v2.seed import seed
from app.v2.storage import FileStore

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reset', action='store_true', help='recreate the isolated acceptance schema before seeding')
    args = parser.parse_args()
    settings = Settings()
    if settings.environment != "test" or "acceptance" not in settings.database_url:
        raise SystemExit("Requires ESP_ENVIRONMENT=test and isolated acceptance search_path")
    db = Database(settings)
    if args.reset:
        with db.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS acceptance CASCADE"))
            connection.execute(text("CREATE SCHEMA acceptance"))
    with db.engine.begin() as connection: connection.execute(text("CREATE SCHEMA IF NOT EXISTS acceptance"))
    command.upgrade(Config("alembic-v2.ini"), "head")
    settings.prepare()
    store = FileStore(settings.storage_root)
    with db.transaction() as session:
        seed(session)
        for username, display, role in [("admin", "测试管理员", "管理员"), ("supervisor", "核查主管", "监管主管"),
                                       ("officer", "现场核查员", "执法人员"), ("researcher", "环境研究员", "研究者")]:
            if not session.scalar(select(User).where(User.username == username)):
                session.add(User(username=username, display_name=display, role=role,
                    password_hash=hasher.hash("Acceptance-only-2026!"), must_change_password=False))
        session.flush()
        admin = session.scalar(select(User).where(User.username == "admin"))
        officer = session.scalar(select(User).where(User.username == "officer"))
        enterprise = session.scalar(select(Enterprise).where(Enterprise.name == "验收测试 · 城北设备维护单位"))
        if not enterprise:
            enterprise = Enterprise(name="验收测试 · 城北设备维护单位", industry="隔离验收数据", address="此记录仅用于隔离环境交互验收", created_by=admin.id)
            session.add(enterprise)
            session.flush()
            lead = Lead(title="验收测试 · 观测异常现场核查", description="此记录仅为业务流程验收，不代表真实企业违法事项。", created_by=admin.id, enterprise_id=enterprise.id, status="assigned")
            session.add(lead)
            session.flush()
            task = Inspection(title=lead.title, lead_id=lead.id, enterprise_id=enterprise.id, assignee_id=officer.id, created_by=admin.id, due_date=date.today()+timedelta(days=7), status="inspection", facts="现场记录待补充；这是隔离验收环境中的测试任务。")
            session.add(task)
            session.flush()
            session.add(WorkflowEvent(inspection_id=task.id, actor_id=admin.id, action="assign", from_status="pending", to_status="assigned", note="隔离环境业务流程验收"))
    # Reuse downloaded real files; no generated observation series on product pages.
    with db.sessions() as session:
        recent = session.execute(text("""SELECT storage_key,kind,local_date FROM public.v2_source_files
            WHERE is_current AND local_date >= (SELECT max(local_date)-6 FROM public.v2_source_files WHERE is_current)
            ORDER BY local_date,kind""")).all()
    for storage_key, kind, source_day in recent:
        filename = Path("/workspace/var/platform") / storage_key
        content = filename.read_bytes()
        result = import_file(db, store, content, kind, "ONLINE", "https://quotsoft.net/air/", expected_date=source_day)
        day = date.fromisoformat(result["date"])
        evaluate_range(db, day, day, None, lambda _: None)
    print("Isolated acceptance fixtures ready; test password is documented in this test-only script")

if __name__ == "__main__": main()
