"""SQLAlchemy adapters for administration use cases and catalog queries."""

from typing import Any

import json
from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy import select, text, update

from app.v2.common import REGULATORS, audit, page, require_entity, serialize
from app.v2.domains.admin.service import NewAccount
from app.v2.domains.admin.models import Channel, Delivery, Law, Notification
from app.v2.domains.auth.models import Audit, LoginSession, User
from app.v2.domains.collection.models import SourceFile
from app.v2.domains.ml.models import ModelActivation, ModelArtifact
from app.v2.domains.monitoring.models import City, Standard, Station, StationAlias
from app.v2.shared.persistence import now


class SqlAlchemyUserAdministrationPort:
    def __init__(self, session: Session) -> None:
        self.session = session

    def people(self) -> dict[str, Any]:
        statement = select(User).where(User.active.is_(True), User.role.in_(REGULATORS))
        return {"items": [{"id": item.id, "display_name": item.display_name, "role": item.role}
                          for item in self.session.scalars(statement.order_by(User.display_name))]}

    def users(self) -> dict[str, Any]:
        return page(self.session, select(User).order_by(User.created_at), 1, 1000)

    def audits(self, page_number: int) -> dict[str, Any]:
        return page(self.session, select(Audit).order_by(Audit.created_at.desc()), page_number, 50)

    def get_user(self, identifier: str) -> dict[str, Any] | None:
        account = self.session.get(User, identifier)
        return serialize(account) if account is not None else None

    def create_user(self, account: NewAccount) -> dict[str, Any]:
        item = User(username=account.username, display_name=account.display_name,
                    role=account.role, password_hash=account.password_hash)
        self.session.add(item)
        self.session.flush()
        return serialize(item)

    def update_user(self, identifier: str, role: str, active: bool) -> dict[str, Any]:
        item = require_entity(self.session, User, identifier)
        item.role, item.active = role, active
        return serialize(item)

    def revoke_user_sessions(self, identifier: str) -> None:
        self.session.execute(update(LoginSession).where(LoginSession.user_id == identifier).values(revoked=True))

    def audit(self, actor_id: str | None, action: str, identifier: str, detail: dict[str, Any] | None = None) -> None:
        audit(self.session, actor_id, action, "user", identifier, detail)


class SqlAlchemyAdminReadPort:
    def __init__(self, session: Session) -> None:
        self.session = session

    def standards(self) -> dict[str, Any]:
        return page(self.session, select(Standard).order_by(Standard.effective_from.desc(), Standard.pollutant), 1, 1000)

    def laws(self) -> dict[str, Any]:
        return page(self.session, select(Law).order_by(Law.effective_from.desc()), 1, 1000)

    def notifications(self, user_id: str) -> dict[str, Any]:
        statement = select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc())
        return page(self.session, statement, 1, 100)

    def sources(self, license_confirmed: bool) -> dict[str, Any]:
        files = page(self.session, select(SourceFile).order_by(SourceFile.created_at.desc()), 1, 100)
        return {"provider": "Quotsoft", "url": "https://quotsoft.net/air/", "schedule": "每日 03:30 Asia/Shanghai；重查最近七天",
                "license_confirmed": license_confirmed, "files": files,
                "observation_rule": "小时值与滚动均值分别存储；原始文件及修订不可覆盖"}

    def models(self) -> dict[str, Any]:
        artifacts = page(self.session, select(ModelArtifact).order_by(ModelArtifact.created_at.desc()), 1, 100)
        return {**artifacts, "activations": [serialize(item) for item in self.session.scalars(select(ModelActivation))]}

    def channels(self) -> dict[str, Any]:
        items = [serialize(item, ("credential_ref",)) for item in self.session.scalars(select(Channel))]
        deliveries = page(self.session, select(Delivery).order_by(Delivery.created_at.desc()), 1, 100)
        return {"items": items, "deliveries": deliveries}


class SqlAlchemyAdminWritePort:
    def __init__(self, session: Session, store: Any) -> None:
        self.session = session
        self.store = store

    def mark_notification_read(self, identifier: str, user_id: str) -> dict[str, Any] | None:
        item = self.session.get(Notification, identifier)
        if item is None or item.user_id != user_id:
            return None
        item.read_at = now()
        return serialize(item)

    def activate_model(self, identifier: str, actor_id: str) -> dict[str, Any]:
        self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('model-activation'))"))
        item = require_entity(self.session, ModelArtifact, identifier)
        if item.status != "validated":
            return {"_conflict": True}
        artifact = json.loads(self.store.verify(item.storage_key, item.sha256).read_text("utf-8"))
        if artifact.get("checkpoint"):
            checkpoint = artifact["checkpoint"]
            self.store.verify(checkpoint["storage_key"], checkpoint["sha256"])
        activation = self.session.get(ModelActivation, item.task)
        if activation is None:
            activation = ModelActivation(task=item.task, model_id=item.id)
            self.session.add(activation)
        elif activation.model_id != item.id:
            activation.previous_id, activation.model_id, activation.updated_at = activation.model_id, item.id, now()
        audit(self.session, actor_id, "MODEL_ACTIVATED", "model", identifier)
        self.session.flush()
        return serialize(activation)

    def rollback_model(self, task: str, actor_id: str) -> dict[str, Any]:
        self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('model-activation'))"))
        activation = self.session.scalar(select(ModelActivation).where(ModelActivation.task == task).with_for_update())
        if activation is None or activation.previous_id is None:
            return {"_conflict": True}
        previous = require_entity(self.session, ModelArtifact, activation.previous_id)
        artifact = json.loads(self.store.verify(previous.storage_key, previous.sha256).read_text("utf-8"))
        if artifact.get("checkpoint"):
            checkpoint = artifact["checkpoint"]
            self.store.verify(checkpoint["storage_key"], checkpoint["sha256"])
        activation.model_id, activation.previous_id = activation.previous_id, activation.model_id
        activation.updated_at = now()
        audit(self.session, actor_id, "MODEL_ROLLBACK", "model", activation.model_id)
        return serialize(activation)

    def add_law(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        item = Law(**values)
        self.session.add(item)
        self.session.flush()
        audit(self.session, actor_id, "ADD_LAW", "law", item.id)
        return serialize(item)

    def update_station(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        require_entity(self.session, City, values["city_id"])
        item = require_entity(self.session, Station, identifier)
        for key, value in values.items():
            setattr(item, key, value)
        audit(self.session, actor_id, "UPDATE_STATION", "station", identifier)
        return serialize(item)

    def add_alias(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('beijing-station-catalog'))"))
        require_entity(self.session, Station, identifier)
        overlap = self.session.scalar(select(StationAlias.id).where(
            StationAlias.external_name == values["external_name"],
            StationAlias.valid_from <= (values["valid_to"] or date.max),
            StationAlias.valid_to.is_(None) | (StationAlias.valid_to >= values["valid_from"]),
        ))
        if overlap:
            return {"_conflict": True}
        item = StationAlias(station_id=identifier, **values)
        self.session.add(item)
        self.session.flush()
        audit(self.session, actor_id, "ADD_ALIAS", "station", identifier)
        return serialize(item)

    def add_channel(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        item = Channel(**values)
        self.session.add(item)
        self.session.flush()
        audit(self.session, actor_id, "ADD_CHANNEL", "channel", item.id,
              {"kind": item.kind, "enabled": item.enabled})
        return serialize(item, ("credential_ref",))

    def toggle_channel(self, identifier: str, enabled: bool, actor_id: str) -> dict[str, Any]:
        item = require_entity(self.session, Channel, identifier)
        item.enabled = enabled
        audit(self.session, actor_id, "TOGGLE_CHANNEL", "channel", identifier, {"enabled": enabled})
        return serialize(item, ("credential_ref",))

    def end_standard(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('standard-version'))"))
        item = require_entity(self.session, Standard, identifier)
        if values["effective_to"] < item.effective_from:
            return {"_validation": True}
        if item.effective_to and values["effective_to"] > item.effective_to:
            return {"_conflict": True}
        previous = serialize(item)
        item.effective_to = values["effective_to"]
        audit(self.session, actor_id, "END_STANDARD_VERSION", "standard", identifier,
              {"before": previous, "reason": values["reason"], "effective_to": str(values["effective_to"])})
        return serialize(item)

    def end_law(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        item = require_entity(self.session, Law, identifier)
        if values["effective_to"] < item.effective_from:
            return {"_validation": True}
        previous = serialize(item)
        item.effective_to = values["effective_to"]
        audit(self.session, actor_id, "END_LAW_VERSION", "law", identifier,
              {"before": previous, "reason": values["reason"], "effective_to": str(values["effective_to"])})
        return serialize(item)

    def add_standard(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        self.session.execute(text("SELECT pg_advisory_xact_lock(hashtext('standard-version'))"))
        overlaps = self.session.scalars(select(Standard).where(
            Standard.pollutant == values["pollutant"], Standard.basis == values["basis"],
            Standard.grade == values["grade"], Standard.region == values["region"],
            Standard.enabled.is_(True), Standard.effective_from <= (values["effective_to"] or date.max),
            Standard.effective_to.is_(None) | (Standard.effective_to >= values["effective_from"]),
        )).all()
        if overlaps:
            return {"_conflict": True}
        item = Standard(**values)
        self.session.add(item)
        self.session.flush()
        audit(self.session, actor_id, "ADD_STANDARD", "standard", item.id)
        return serialize(item)
