"""SQLAlchemy adapter for enforcement read models."""

from datetime import date
from pathlib import PurePath
from typing import Any

from sqlalchemy import Select, cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.v2.common import MANAGERS, REGULATORS, audit, fail, page, require_entity, serialize
from app.v2.domains.enforcement.service import ListFilter
from app.v2.domains.admin.models import Law, Notification
from app.v2.domains.auth.models import User
from app.v2.domains.enforcement.models import Attachment, Enterprise, EnterpriseRecord, Inspection, Lead, Rectification, WorkflowEvent
from app.v2.domains.monitoring.models import Evaluation, Station
from app.v2.shared.persistence import now

TRANSITIONS = {
    "start": ({"assigned"}, "inspection"), "rectify": ({"inspection"}, "rectification"),
    "submit_rectification": ({"rectification"}, "reinspection"),
    "reinspect": ({"reinspection"}, "reinspection"), "submit_review": ({"reinspection"}, "review"),
    "no_rectification": ({"inspection"}, "review"), "approve": ({"review"}, "archived"),
    "return": ({"review"}, "inspection"), "reopen": ({"archived"}, "inspection"),
}


def notify(session: Session, user_id: str, title: str, body: str, inspection_id: str, key: str) -> None:
    """Compatibility helper for the scheduler and legacy task callers."""
    if not session.scalar(select(Notification.id).where(
        Notification.user_id == user_id, Notification.dedupe_key == key)):
        session.add(Notification(user_id=user_id, title=title, body=body,
                                 href=f"/inspections/{inspection_id}", dedupe_key=key))


def scope(statement: Select[Any], user: User) -> Select[Any]:
    """Compatibility query facade for the legacy export worker."""
    if user.role == "执法人员":
        return statement.where(or_(Inspection.assignee_id == user.id,
                                   cast(Inspection.collaborators, JSONB).contains([user.id])))
    return statement


class SqlAlchemyEnforcementReadPort:
    def __init__(self, session: Session, user: User | None) -> None:
        self.session, self.user = session, user

    def enterprises(self, filters: ListFilter) -> dict[str, Any]:
        statement = select(Enterprise)
        if filters.query:
            statement = statement.where(Enterprise.name.ilike(f"%{filters.query}%"))
        return page(self.session, statement.order_by(Enterprise.created_at.desc(), Enterprise.id),
                    filters.page_number, filters.page_size)

    def leads(self, filters: ListFilter) -> dict[str, Any]:
        statement = select(Lead)
        if filters.status:
            statement = statement.where(Lead.status == filters.status)
        if filters.query:
            statement = statement.where(Lead.title.ilike(f"%{filters.query}%"))
        return page(self.session, statement.order_by(Lead.created_at.desc(), Lead.id),
                    filters.page_number, filters.page_size)

    def inspections(self, filters: ListFilter) -> dict[str, Any]:
        statement = select(Inspection)
        if self.user is not None and self.user.role == "执法人员":
            statement = statement.where(or_(Inspection.assignee_id == self.user.id,
                                            cast(Inspection.collaborators, JSONB).contains([self.user.id])))
        if filters.status:
            statement = statement.where(Inspection.status == filters.status)
        if filters.query:
            statement = statement.where(Inspection.title.ilike(f"%{filters.query}%"))
        return page(self.session, statement.order_by(Inspection.created_at.desc(), Inspection.id),
                    filters.page_number, filters.page_size)


class SqlAlchemyEnforcementWritePort:
    def __init__(self, session: Session, store: Any = None, db: Any = None) -> None:
        self.session, self.store, self.db = session, store, db

    @staticmethod
    def _version(item: Any, version: int) -> None:
        if item.version != version:
            fail("记录已被其他人更新，请刷新后重试", ErrorCode.CONFLICT)
        item.version += 1

    @staticmethod
    def _scope(statement: Select[Any], user: User) -> Select[Any]:
        if user.role == "执法人员":
            return statement.where(or_(Inspection.assignee_id == user.id,
                                       cast(Inspection.collaborators, JSONB).contains([user.id])))
        return statement

    def _accessible(self, identifier: str, user: User, lock: bool = False) -> Inspection:
        statement = select(Inspection).where(Inspection.id == identifier)
        item = self.session.scalar(statement.with_for_update() if lock else statement)
        if item is None:
            fail("核查任务不存在", ErrorCode.NOT_FOUND)
        if user.role not in MANAGERS and user.id not in [item.assignee_id, *item.collaborators]:
            if self.db is not None:
                with self.db.transaction() as audit_session:
                    audit(audit_session, user.id, "ACCESS_DENIED", "inspection", identifier)
            fail("无权访问该核查任务", ErrorCode.FORBIDDEN)
        return item

    def _notify(self, user_id: str, title: str, body: str, inspection_id: str, key: str) -> None:
        if not self.session.scalar(select(Notification.id).where(
            Notification.user_id == user_id, Notification.dedupe_key == key)):
            self.session.add(Notification(user_id=user_id, title=title, body=body,
                                          href=f"/inspections/{inspection_id}", dedupe_key=key))

    def create_enterprise(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        item = Enterprise(**values, created_by=actor_id)
        self.session.add(item); self.session.flush()
        audit(self.session, actor_id, "CREATE", "enterprise", item.id)
        return serialize(item)

    def enterprise_detail(self, identifier: str, user: User) -> dict[str, Any]:
        item = require_entity(self.session, Enterprise, identifier)
        return {**serialize(item),
                "records": [serialize(r) for r in self.session.scalars(
                    select(EnterpriseRecord).where(EnterpriseRecord.enterprise_id == identifier))],
                "attachments": [serialize(r) for r in self.session.scalars(
                    select(Attachment).where(Attachment.enterprise_id == identifier))],
                "inspections": [serialize(r) for r in self.session.scalars(
                    self._scope(select(Inspection).where(Inspection.enterprise_id == identifier), user))]}

    def update_enterprise(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        item = self.session.scalar(select(Enterprise).where(Enterprise.id == identifier).with_for_update())
        if item is None:
            fail("企业不存在", ErrorCode.NOT_FOUND)
        self._version(item, values.pop("version"))
        for key, value in values.items(): setattr(item, key, value)
        audit(self.session, actor_id, "UPDATE", "enterprise", identifier)
        return serialize(item)

    def add_enterprise_record(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        require_entity(self.session, Enterprise, identifier)
        item = EnterpriseRecord(enterprise_id=identifier, **values)
        self.session.add(item); self.session.flush()
        audit(self.session, actor_id, "ADD_RECORD", "enterprise", identifier, values)
        return serialize(item)

    def create_lead(self, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        for model, identifier in ((Station, values.get("station_id")), (Enterprise, values.get("enterprise_id")),
                                  (Evaluation, values.get("evaluation_id"))):
            if identifier: require_entity(self.session, model, identifier)
        item = Lead(**values, created_by=actor_id)
        self.session.add(item); self.session.flush()
        audit(self.session, actor_id, "CREATE", "lead", item.id)
        return serialize(item)

    def assign_lead(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        lead = self.session.scalar(select(Lead).where(Lead.id == identifier).with_for_update())
        if lead is None: fail("线索不存在", ErrorCode.NOT_FOUND)
        if lead.status != "pending": fail("线索已处理", ErrorCode.CONFLICT)
        for account_id in {values["assignee_id"], *values.get("collaborators", [])}:
            account = require_entity(self.session, User, account_id)
            if account.role not in REGULATORS or not account.active:
                fail("负责人和协作者必须为有效监管账号")
        if values.get("enterprise_id"):
            require_entity(self.session, Enterprise, values["enterprise_id"])
        lead.enterprise_id = values.get("enterprise_id") or lead.enterprise_id
        lead.status = "assigned"
        item = Inspection(title=lead.title, lead_id=lead.id, enterprise_id=lead.enterprise_id,
                          assignee_id=values["assignee_id"], collaborators=values.get("collaborators", []),
                          created_by=actor_id, due_date=values["due_date"])
        self.session.add(item); self.session.flush()
        self.session.add(WorkflowEvent(inspection_id=item.id, actor_id=actor_id, action="assign",
                                       from_status="pending", to_status="assigned", note=values["note"]))
        for recipient in {values["assignee_id"], *values.get("collaborators", [])}:
            self._notify(recipient, "新的核查任务", item.title, item.id, f"assign:{item.id}")
        audit(self.session, actor_id, "ASSIGN", "inspection", item.id)
        return serialize(item)

    def claim_lead(self, identifier: str, actor_id: str) -> dict[str, Any]:
        item = self.session.scalar(select(Lead).where(Lead.id == identifier).with_for_update())
        if item is None: fail("线索不存在", ErrorCode.NOT_FOUND)
        if item.status != "pending": fail("仅待研判线索可以认领", ErrorCode.CONFLICT)
        if item.claimed_by and item.claimed_by != actor_id:
            fail("线索已由其他人员认领", ErrorCode.CONFLICT)
        item.claimed_by = actor_id
        audit(self.session, actor_id, "CLAIM", "lead", identifier)
        return serialize(item)

    def reject_lead(self, identifier: str, reason: str, actor_id: str) -> dict[str, Any]:
        item = self.session.scalar(select(Lead).where(Lead.id == identifier).with_for_update())
        if item is None: fail("线索不存在", ErrorCode.NOT_FOUND)
        if item.status != "pending": fail("仅待研判线索可以驳回", ErrorCode.CONFLICT)
        item.status, item.reason = "rejected", reason
        audit(self.session, actor_id, "REJECT", "lead", item.id, {"reason": reason})
        return serialize(item)

    def inspection_detail(self, identifier: str, user: User) -> dict[str, Any]:
        item = self._accessible(identifier, user)
        result = serialize(item)
        for name, model in (("history", WorkflowEvent), ("rectifications", Rectification), ("attachments", Attachment)):
            result[name] = [serialize(row) for row in self.session.scalars(
                select(model).where(model.inspection_id == identifier).order_by(model.created_at))]
        result["assignee"] = serialize(self.session.get(User, item.assignee_id), ("failed_logins", "locked_until"))
        result["enterprise"] = serialize(self.session.get(Enterprise, item.enterprise_id)) if item.enterprise_id else None
        return result

    def save_inspection(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        item = self._accessible(identifier, values.pop("user"), True)
        if item.status in {"archived", "review"}: fail("审核或归档状态不可编辑", ErrorCode.CONFLICT)
        for reference in values["legal_references"]:
            law = require_entity(self.session, Law, reference.get("law_id", ""))
            if not reference.get("article") or not reference.get("reason"):
                fail("关联依据需填写条款和适用理由")
            reference["snapshot"] = serialize(law)
        self._version(item, values["version"])
        item.facts, item.legal_references = values["facts"], values["legal_references"]
        audit(self.session, actor_id, "SAVE_FACTS", "inspection", identifier, {"version": item.version})
        return serialize(item)

    def transition(self, identifier: str, values: dict[str, Any], actor_id: str, manager: bool) -> dict[str, Any]:
        user = values.pop("user")
        item = self._accessible(identifier, user, True)
        action = values["action"]; allowed, destination = TRANSITIONS[action]
        if action in {"approve", "return", "reopen"} and not manager:
            fail("仅主管可以审核、退回或重新开启", ErrorCode.FORBIDDEN)
        if item.status not in allowed: fail("当前状态不支持此操作", ErrorCode.CONFLICT)
        requirements = self.session.scalars(select(Rectification).where(Rectification.inspection_id == identifier)).all()
        if action in {"rectify", "no_rectification", "submit_review"} and len(item.facts.strip()) < 5:
            fail("请先保存核查事实")
        if action == "rectify" and not requirements: fail("请先添加整改要求和期限")
        if action == "no_rectification" and requirements: fail("存在整改事项，请完成整改流程")
        if action == "submit_rectification" and any(not r.response.strip() for r in requirements):
            fail("请填写每项整改的完成情况")
        if action == "submit_review" and any(r.status != "verified" or not r.review_note.strip() for r in requirements):
            fail("每项整改必须完成复查并记录结论")
        self._version(item, values["version"])
        before, item.status = item.status, destination
        self.session.add(WorkflowEvent(inspection_id=identifier, actor_id=actor_id, action=action,
                                       from_status=before, to_status=destination, note=values["note"]))
        if destination == "archived" and item.lead_id:
            require_entity(self.session, Lead, item.lead_id).status = "closed"
        if action == "reopen" and item.lead_id:
            require_entity(self.session, Lead, item.lead_id).status = "assigned"
        recipients = [u.id for u in self.session.scalars(select(User).where(
            User.role.in_(MANAGERS), User.active.is_(True)))] if destination == "review" else [item.assignee_id]
        for recipient in recipients:
            self._notify(recipient, "核查任务状态更新", f"{item.title}：{destination}", identifier,
                         f"transition:{identifier}:{item.version}")
        audit(self.session, actor_id, action.upper(), "inspection", identifier,
              {"from": before, "to": destination, "note": values["note"]})
        return serialize(item)

    def add_rectification(self, identifier: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        task = self._accessible(identifier, values.pop("user"), True)
        if task.status != "inspection": fail("仅现场核查阶段可以添加整改事项", ErrorCode.CONFLICT)
        self._version(task, values.pop("version"))
        item = Rectification(inspection_id=identifier, **values)
        self.session.add(item); self.session.flush()
        audit(self.session, actor_id, "ADD_RECTIFICATION", "inspection", identifier, {"requirement": item.requirement})
        return serialize(item)

    def update_rectification(self, identifier: str, rectification_id: str, values: dict[str, Any], actor_id: str) -> dict[str, Any]:
        task = self._accessible(identifier, values.pop("user"), True)
        item = require_entity(self.session, Rectification, rectification_id)
        if item.inspection_id != identifier: fail("整改事项不属于该任务", ErrorCode.NOT_FOUND)
        if task.status not in {"rectification", "reinspection"}: fail("当前阶段不可更新整改", ErrorCode.CONFLICT)
        if values["verified"] and (task.status != "reinspection" or len(values["review_note"]) < 5):
            fail("请在复查阶段填写复查结论")
        self._version(task, values.pop("version"))
        item.response, item.review_note = values["response"], values["review_note"]
        item.status = "verified" if values["verified"] else "responded"
        self.session.add(WorkflowEvent(inspection_id=identifier, actor_id=actor_id, action="rectification_updated",
                                       from_status=task.status, to_status=task.status,
                                       note=f"{item.requirement}\n整改情况：{values['response']}\n复查：{values['review_note']}"))
        audit(self.session, actor_id, "UPDATE_RECTIFICATION", "inspection", identifier)
        return serialize(item)

    def upload_attachment(self, content: bytes, filename: str, inspection_id: str | None,
                          enterprise_id: str | None, replaces_id: str | None, actor_id: str) -> dict[str, Any]:
        if bool(inspection_id) == bool(enterprise_id): fail("请选择一个附件归属")
        name = PurePath((filename or "attachment").replace("\\", "/")).name[:240]
        if inspection_id:
            task = self._accessible(inspection_id, require_entity(self.session, User, actor_id), True)
            if task.status in {"review", "archived"}: fail("审核或归档后不可追加证据", ErrorCode.CONFLICT)
        if enterprise_id: require_entity(self.session, Enterprise, enterprise_id)
        if replaces_id:
            old = require_entity(self.session, Attachment, replaces_id)
            if (old.inspection_id, old.enterprise_id) != (inspection_id, enterprise_id):
                fail("替换版本必须属于同一记录")
        key, hashed = self.store.put(content, "uploads", ".bin")
        item = Attachment(inspection_id=inspection_id, enterprise_id=enterprise_id, owner_id=actor_id,
                          original_name=name, mime="application/octet-stream", size=len(content), sha256=hashed,
                          storage_key=key, replaces_id=replaces_id)
        self.session.add(item); self.session.flush()
        audit(self.session, actor_id, "UPLOAD", "attachment", item.id, {"sha256": hashed, "size": len(content)})
        return serialize(item)

    def prepare_attachment_download(self, identifier: str, user: User) -> dict[str, Any]:
        item = require_entity(self.session, Attachment, identifier)
        if item.inspection_id: self._accessible(item.inspection_id, user)
        path = self.store.verify(item.storage_key, item.sha256)
        audit(self.session, user.id, "DOWNLOAD", "attachment", identifier)
        return {"path": path, "filename": item.original_name}
