"""ORM definitions owned by the jobs domain; table names remain v2-compatible."""
from __future__ import annotations
from typing import Any

from datetime import datetime
from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.types import UtcDateTime
from app.v2.shared.persistence import Base, Entity


class Job(Entity, Base):
    __tablename__ = "v2_jobs"
    kind: Mapped[str] = mapped_column(String(40), index=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("v2_users.id"))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    progress_stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    progress_message: Mapped[str | None] = mapped_column(String(240), nullable=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    target_key: Mapped[str] = mapped_column(String(160), index=True)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    __table_args__ = (Index("ix_v2_jobs_status_heartbeat", "status", "heartbeat_at"),)


class Outbox(Entity, Base):
    __tablename__ = "v2_outbox"
    job_id: Mapped[str] = mapped_column(ForeignKey("v2_jobs.id"), unique=True)
    sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


__all__ = ['Job', 'Outbox']
