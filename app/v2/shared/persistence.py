"""One declarative registry and identity defaults for all v2 persistence adapters."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from app.v2.shared.utc_time import UtcDateTime


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Entity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=now)
