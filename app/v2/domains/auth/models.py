"""ORM definitions owned by the auth domain; table names remain v2-compatible."""

from __future__ import annotations

from typing import Any
from datetime import datetime
from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.types import UtcDateTime
from app.v2.shared.persistence import Base, Entity


class User(Entity, Base):
    __tablename__ = "v2_users"
    username: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(UtcDateTime)


class LoginSession(Entity, Base):
    __tablename__ = "v2_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("v2_users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Audit(Entity, Base):
    __tablename__ = "v2_audits"
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("v2_users.id"))
    action: Mapped[str] = mapped_column(String(80), index=True)
    object_type: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64))


__all__ = ['User', 'LoginSession', 'Audit']
