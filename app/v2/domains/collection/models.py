"""ORM definitions owned by the collection domain; table names remain v2-compatible."""
from __future__ import annotations
from datetime import date
from sqlalchemy import Boolean, Date, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.v2.shared.persistence import Base, Entity

from app.v2.domains.monitoring.models import Observation, Station, StationAlias


class SourceFile(Entity, Base):
    __tablename__ = "v2_source_files"
    __table_args__ = (UniqueConstraint("source_key", "sha256"), Index("ix_v2_source_current_date", "is_current", "local_date"))
    source_key: Mapped[str] = mapped_column(String(200), index=True)
    local_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))
    origin: Mapped[str] = mapped_column(String(20))
    url: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0)
    attribution: Mapped[str] = mapped_column(Text, default="Quotsoft / 北京市环境空气质量公开数据")


class SourceAttempt(Entity, Base):
    __tablename__ = "v2_source_attempts"
    __table_args__ = (Index("ix_v2_source_attempts_date_kind_status", "local_date", "kind", "status"),)
    local_date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[str | None] = mapped_column(String(36))


__all__ = ['SourceFile', 'SourceAttempt', 'Observation', 'Station', 'StationAlias']
