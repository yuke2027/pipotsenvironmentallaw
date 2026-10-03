"""ORM definitions owned by the enforcement domain; table names remain v2-compatible."""
from __future__ import annotations
from typing import Any

from datetime import date
from sqlalchemy import Date, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.v2.shared.persistence import Base, Entity


class Enterprise(Entity, Base):
    __tablename__ = "v2_enterprises"
    name: Mapped[str] = mapped_column(String(200), index=True)
    credit_code: Mapped[str | None] = mapped_column(String(18), unique=True)
    industry: Mapped[str] = mapped_column(String(100), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    contact: Mapped[str] = mapped_column(String(200), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey("v2_users.id"))


class EnterpriseRecord(Entity, Base):
    __tablename__ = "v2_enterprise_records"
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("v2_enterprises.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Lead(Entity, Base):
    __tablename__ = "v2_leads"
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    station_id: Mapped[str | None] = mapped_column(ForeignKey("v2_stations.id"))
    enterprise_id: Mapped[str | None] = mapped_column(ForeignKey("v2_enterprises.id"))
    evaluation_id: Mapped[str | None] = mapped_column(ForeignKey("v2_evaluations.id"), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("v2_users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    claimed_by: Mapped[str | None] = mapped_column(ForeignKey("v2_users.id"))


class Inspection(Entity, Base):
    __tablename__ = "v2_inspections"
    title: Mapped[str] = mapped_column(String(200))
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("v2_leads.id"), unique=True)
    enterprise_id: Mapped[str | None] = mapped_column(ForeignKey("v2_enterprises.id"))
    assignee_id: Mapped[str] = mapped_column(ForeignKey("v2_users.id"), index=True)
    collaborators: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(ForeignKey("v2_users.id"))
    status: Mapped[str] = mapped_column(String(32), default="assigned", index=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    facts: Mapped[str] = mapped_column(Text, default="")
    legal_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)


class WorkflowEvent(Entity, Base):
    __tablename__ = "v2_workflow_events"
    inspection_id: Mapped[str] = mapped_column(ForeignKey("v2_inspections.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("v2_users.id"))
    action: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text)


class Rectification(Entity, Base):
    __tablename__ = "v2_rectifications"
    inspection_id: Mapped[str] = mapped_column(ForeignKey("v2_inspections.id"), index=True)
    requirement: Mapped[str] = mapped_column(Text)
    due_date: Mapped[date] = mapped_column(Date)
    response: Mapped[str] = mapped_column(Text, default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="pending")


class Attachment(Entity, Base):
    __tablename__ = "v2_attachments"
    inspection_id: Mapped[str | None] = mapped_column(ForeignKey("v2_inspections.id"), index=True)
    enterprise_id: Mapped[str | None] = mapped_column(ForeignKey("v2_enterprises.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("v2_users.id"))
    original_name: Mapped[str] = mapped_column(String(240))
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text)
    replaces_id: Mapped[str | None] = mapped_column(ForeignKey("v2_attachments.id"))


__all__ = ['Enterprise', 'EnterpriseRecord', 'Lead', 'Inspection', 'WorkflowEvent', 'Rectification', 'Attachment']
