"""Tests always create an isolated PostgreSQL schema and private temporary storage."""
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.v2.auth import hasher
from app.v2.config import Settings
from app.v2.main import create_app
from app.v2.models import Base, User
from app.v2.seed import seed

PASSWORD = "Isolated-test-password-2026!"


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        base = Settings()
        self.schema = "test_" + uuid4().hex
        self.admin_engine = create_engine(base.database_url)
        with self.admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        url = make_url(base.database_url).update_query_dict({"options": f"-csearch_path={self.schema}"})
        self.temporary = tempfile.TemporaryDirectory()
        self.settings = base.model_copy(update={"database_url": url.render_as_string(hide_password=False),
            "environment": "test", "storage_root": Path(self.temporary.name), "source_interval_seconds": 0.0})
        self.app = create_app(self.settings)
        self.db = self.app.state.db
        Base.metadata.create_all(self.db.engine)
        self.store = self.app.state.store
        password_hash = hasher.hash(PASSWORD)
        self.users = {}
        with self.db.transaction() as session:
            seed(session)
            for username, role in [("admin", "管理员"), ("supervisor", "监管主管"), ("officer", "执法人员"), ("outsider", "执法人员"), ("researcher", "研究者")]:
                user = User(username=username, display_name=username, role=role, password_hash=password_hash, must_change_password=False)
                session.add(user)
                session.flush()
                self.users[username] = user.id
        self.clients = []

    def client(self, username="admin"):
        client = TestClient(self.app, raise_server_exceptions=True)
        self.clients.append(client)
        result = client.post("/api/v2/auth/login", json={"username": username, "password": PASSWORD})
        self.assertEqual(200, result.status_code, result.text)
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        return client

    def tearDown(self):
        for client in self.clients: client.close()
        self.db.engine.dispose()
        assert self.schema.startswith("test_") and len(self.schema) == 37
        with self.admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        self.admin_engine.dispose()
        self.temporary.cleanup()


def daily_csv(day="20260930", kinds=("PM2.5", "PM10", "AQI"), value=80, hours=24, stations=("测试站甲", "测试站乙")):
    lines = ["date,hour,type," + ",".join(stations)]
    for hour in range(hours):
        for pollutant in kinds:
            lines.append(f"{day},{hour},{pollutant}," + ",".join(str(value) for _ in stations))
    return ("\n".join(lines) + "\n").encode()
