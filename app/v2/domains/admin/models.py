"""ORM definitions owned by the admin domain; table names remain v2-compatible."""

from __future__ import annotations

from typing import Any
from datetime import date, datetime
from sqlalchemy import Boolean, Date, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.types import UtcDateTime
from app.v2.shared.persistence import Base, Entity

from app.v2.domains.auth.models import Audit, User
from app.v2.domains.monitoring.models import Standard


class Law(Entity, Base):
    __tablename__ = "v2_laws"
    title: Mapped[str] = mapped_column(String(240), unique=True)
    region: Mapped[str] = mapped_column(String(80))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)


class Notification(Entity, Base):
    __tablename__ = "v2_notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("v2_users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    href: Mapped[str] = mapped_column(String(240))
    dedupe_key: Mapped[str] = mapped_column(String(200))
    read_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Channel(Entity, Base):
    __tablename__ = "v2_channels"
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    credential_ref: Mapped[str | None] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class Delivery(Entity, Base):
    __tablename__ = "v2_deliveries"
    __table_args__ = (UniqueConstraint("notification_id", "channel_id"),)
    notification_id: Mapped[str] = mapped_column(ForeignKey("v2_notifications.id"))
    channel_id: Mapped[str] = mapped_column(ForeignKey("v2_channels.id"))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


__all__ = ['Law', 'Notification', 'Channel', 'Delivery', 'Audit', 'User', 'Standard']
