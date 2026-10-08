"""ORM definitions owned by the ml domain; table names remain v2-compatible."""

from __future__ import annotations

from typing import Any
from datetime import datetime
from sqlalchemy import Float, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.v2.shared.utc_time import UtcDateTime
from app.v2.shared.persistence import Base, Entity, now


class ModelArtifact(Entity, Base):
    __tablename__ = "v2_models"
    __table_args__ = (Index("ix_v2_models_task_status", "task", "status"),)
    task: Mapped[str] = mapped_column(String(24))
    algorithm: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default="experimental")
    storage_key: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    job_id: Mapped[str] = mapped_column(ForeignKey("v2_jobs.id"))


class ModelActivation(Base):
    __tablename__ = "v2_model_activations"
    task: Mapped[str] = mapped_column(String(24), primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("v2_models.id"))
    previous_id: Mapped[str | None] = mapped_column(ForeignKey("v2_models.id"))
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=now)


class DerivedValue(Entity, Base):
    __tablename__ = "v2_derived_values"
    __table_args__ = (UniqueConstraint("job_id", "station_id", "observed_at", "pollutant", "kind"),)
    station_id: Mapped[str] = mapped_column(ForeignKey("v2_stations.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    pollutant: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(20))
    value: Mapped[float] = mapped_column(Float)
    lower: Mapped[float | None] = mapped_column(Float)
    upper: Mapped[float | None] = mapped_column(Float)
    model_id: Mapped[str | None] = mapped_column(ForeignKey("v2_models.id"))
    job_id: Mapped[str] = mapped_column(ForeignKey("v2_jobs.id"))
    data_cutoff: Mapped[datetime] = mapped_column(UtcDateTime)
    snapshot_hash: Mapped[str] = mapped_column(String(64))


__all__ = ['ModelArtifact', 'ModelActivation', 'DerivedValue']
