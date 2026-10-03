"""Stable contracts shared by HTTP, workers and scheduler code.

These models deliberately contain no FastAPI or SQLAlchemy dependencies so they
can be used by workers and legacy adapters without importing the web layer.
"""

from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobKind(str, Enum):
    """Task kinds understood by the shared worker contract."""

    COLLECT = "collect"
    IMPORT = "import"
    EVALUATE = "evaluate"
    EXPORT = "export"
    TRAIN = "train"
    FORECAST = "forecast"
    IMPUTE = "impute"


class JobSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: JobKind
    parameters: dict[str, Any] = Field(default_factory=dict)
    target_key: str = Field(min_length=1, max_length=160)
    owner_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=160)


class JobProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: JobState
    percent: int = Field(default=0, ge=0, le=100)
    stage: str | None = None
    message: str | None = None
    heartbeat_at: str | None = None


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=40)
    key: str = Field(min_length=1)
    sha256: Sha256 | None = None
    media_type: str | None = None


class JobResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: JobState
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    source_hashes: list[Sha256] = Field(default_factory=list)
