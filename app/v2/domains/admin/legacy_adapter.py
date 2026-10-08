"""Temporary rollback adapter preserving the previous user mutation workflow."""

from typing import Any

from sqlalchemy.orm import Session

from app.v2.common import audit, fail, page, require_entity, serialize
from app.v2.domains.admin.repository import SqlAlchemyUserAdministrationPort
from app.v2.domains.admin.service import NewAccount
from sqlalchemy import select

from app.v2.domains.admin.models import Channel, Delivery, Law, Notification
from app.v2.domains.auth.models import User
from app.v2.domains.collection.models import SourceFile
from app.v2.domains.ml.models import ModelActivation, ModelArtifact
from app.v2.domains.monitoring.models import Standard


class LegacyUserAdministrationAdapter:
    def __init__(self, session: Session):
        self.session = session
        self.port = SqlAlchemyUserAdministrationPort(session)

    def list_people(self) -> dict[str, Any]:
        return self.port.people()

    def list_users(self) -> dict[str, Any]:
        return self.port.users()

    def list_audits(self, page_number: int) -> dict[str, Any]:
        return self.port.audits(page_number)

    def create_user(self, actor_id: str, account: NewAccount) -> dict[str, Any]:
        item = User(username=account.username, display_name=account.display_name,
                    role=account.role, password_hash=account.password_hash)
        self.session.add(item)
        self.session.flush()
        audit(self.session, actor_id, "CREATE_USER", "user", item.id, {"role": account.role})
        return serialize(item)

    def update_user(self, actor_id: str, identifier: str, role: str, active: bool) -> dict[str, Any]:
        item = require_entity(self.session, User, identifier)
        if identifier == actor_id and (not active or role != "管理员"):
            fail("不能禁用或降级当前管理员")
        item.role, item.active = role, active
        self.port.revoke_user_sessions(identifier)
        audit(self.session, actor_id, "UPDATE_USER", "user", identifier, {"role": role, "active": active})
        return serialize(item)

    def standards(self) -> dict[str, Any]:
        return page(self.session, select(Standard).order_by(Standard.effective_from.desc(), Standard.pollutant), 1, 1000)

    def laws(self) -> dict[str, Any]:
        return page(self.session, select(Law).order_by(Law.effective_from.desc()), 1, 1000)

    def notifications(self, user_id: str) -> dict[str, Any]:
        return page(self.session, select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc()), 1, 100)

    def sources(self, license_summary: dict[str, Any]) -> dict[str, Any]:
        return {"provider": "Quotsoft", "url": "https://quotsoft.net/air/", "schedule": "每日 03:30 Asia/Shanghai；重查最近七天",
                "license_confirmed": bool(license_summary.get("ready")), "license_state": license_summary.get("state"),
                "license_scope": license_summary.get("scope"), "license_valid_until": license_summary.get("valid_until"),
                "source_adapter": license_summary.get("source_provider"),
                "files": page(self.session, select(SourceFile).order_by(SourceFile.created_at.desc()), 1, 100),
                "observation_rule": "小时值与滚动均值分别存储；原始文件及修订不可覆盖"}

    def models(self) -> dict[str, Any]:
        return {**page(self.session, select(ModelArtifact).order_by(ModelArtifact.created_at.desc()), 1, 100),
                "activations": [serialize(item) for item in self.session.scalars(select(ModelActivation))]}

    def channels(self) -> dict[str, Any]:
        return {"items": [serialize(item, ("credential_ref",)) for item in self.session.scalars(select(Channel))],
                "deliveries": page(self.session, select(Delivery).order_by(Delivery.created_at.desc()), 1, 100)}


    # Service-contract aliases used by app.v2.admin route helpers.
    def list_standards(self) -> dict[str, Any]:
        return self.standards()

    def list_laws(self) -> dict[str, Any]:
        return self.laws()

    def list_notifications(self, user_id: str) -> dict[str, Any]:
        return self.notifications(user_id)

    def list_sources(self, license_summary: dict[str, Any]) -> dict[str, Any]:
        return self.sources(license_summary)

    def list_models(self) -> dict[str, Any]:
        return self.models()

    def list_channels(self) -> dict[str, Any]:
        return self.channels()
