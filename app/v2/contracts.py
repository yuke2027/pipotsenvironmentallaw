"""Stable HTTP DTOs for the v2 API.

These classes are independent from SQLAlchemy. ``extra=allow`` preserves
compatibility while fields used by clients stay explicit in OpenAPI.
"""

from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict


class DTO(BaseModel):
    model_config = ConfigDict(extra="allow", from_attributes=True)


class UserView(DTO):
    id: str
    created_at: datetime
    username: str
    display_name: str
    role: str
    active: bool
    must_change_password: bool


class CityView(DTO):
    id: str
    created_at: datetime
    code: str
    name: str
    timezone: str


class StationView(DTO):
    id: str
    created_at: datetime
    city_id: str
    code: str
    name: str
    latitude: float | None = None
    longitude: float | None = None
    active: bool


class ObservationView(DTO):
    id: str
    created_at: datetime
    source_file_id: str
    station_id: str
    observed_at: datetime
    local_date: date
    pollutant: str
    basis: str
    value: float | None = None
    unit: str
    quality: str


class EvaluationView(DTO):
    id: str
    created_at: datetime
    station_id: str
    local_date: date
    pollutant: str
    basis: str
    standard_id: str
    standard_snapshot: dict[str, Any]
    snapshot_hash: str
    valid_points: int
    value: float | None = None
    exceed_ratio: float | None = None
    status: str
    is_current: bool
    job_id: str | None = None


class EnterpriseView(DTO):
    id: str
    created_at: datetime
    name: str
    credit_code: str | None = None
    industry: str
    address: str
    contact: str
    version: int
    created_by: str


class LeadView(DTO):
    id: str
    created_at: datetime
    title: str
    description: str
    station_id: str | None = None
    enterprise_id: str | None = None
    evaluation_id: str | None = None
    status: str
    priority: str
    created_by: str | None = None
    reason: str | None = None
    claimed_by: str | None = None


class InspectionView(DTO):
    id: str
    created_at: datetime
    title: str
    lead_id: str | None = None
    enterprise_id: str | None = None
    assignee_id: str
    collaborators: list[Any]
    created_by: str
    status: str
    due_date: date | None = None
    facts: str
    legal_references: list[Any]
    version: int


class AttachmentView(DTO):
    id: str
    created_at: datetime
    inspection_id: str | None = None
    enterprise_id: str | None = None
    owner_id: str
    original_name: str
    mime: str
    size: int
    sha256: str
    replaces_id: str | None = None


class JobView(DTO):
    id: str
    created_at: datetime
    kind: str
    owner_id: str | None = None
    parameters: dict[str, Any]
    status: str
    progress: int
    progress_stage: str | None = None
    progress_message: str | None = None
    result: dict[str, Any]
    error: str | None = None
    attempts: int
    target_key: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    download_available: bool = False


class ModelView(DTO):
    id: str
    created_at: datetime
    task: str
    algorithm: str
    status: str
    sha256: str
    manifest: dict[str, Any]
    metrics: dict[str, Any]
    job_id: str


class StandardView(DTO):
    id: str
    created_at: datetime
    code: str
    pollutant: str
    basis: str
    grade: str
    region: str
    limit_value: float
    unit: str
    min_points: int
    effective_from: date
    effective_to: date | None = None
    source_url: str
    article: str
    enabled: bool
    version: int


class LawView(DTO):
    id: str
    created_at: datetime
    title: str
    region: str
    effective_from: date
    effective_to: date | None = None
    source_url: str
    summary: str


T = TypeVar("T")


class Page(DTO, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    request_id: str


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user: UserView
    csrf_token: str


class Accepted(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    status: str
