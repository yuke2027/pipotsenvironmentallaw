"""Standard versioning. Limits stay in the database and out of the algorithms."""

from __future__ import annotations

import math
from datetime import datetime

from app.core.clock import Clock, SystemClock
from app.core.errors import AppError, ErrorCode, ErrorDetail, get_request_id
from app.domain.audit_actions import (
    ACTION_AUTHORIZATION_DENIED,
    ACTION_STANDARD_CREATED,
    ACTION_STANDARD_DEACTIVATED,
    ACTION_STANDARD_UPDATED,
)
from app.domain.errors import VersionConflictError
from app.domain.permissions import ADMIN, Operation, is_allowed
from app.domain.principal import Principal
from app.domain.records import AuditDraft, LegalStandardRecord, StandardDraft
from app.domain.repositories import AuditRepository, StandardsRepository

ALLOWED_BASES = frozenset(
    {
        "24h_mean",
        "annual_mean",
        "aqi_level_1",
        "aqi_level_2",
        "aqi_level_3",
        "aqi_level_4",
        "aqi_level_5",
        "aqi_level_6",
    }
)


class StandardsService:
    def __init__(
        self,
        standards: StandardsRepository,
        audit: AuditRepository,
        clock: Clock | None = None,
    ) -> None:
        self._standards = standards
        self._audit = audit
        self._clock = clock if clock is not None else SystemClock()

    def create(
        self,
        actor: Principal,
        *,
        standard_key: str,
        version: str,
        pollutant: str,
        statistic_basis: str,
        limit_value: float,
        unit: str,
        legal_basis_name: str,
        legal_article: str,
        penalty_basis: str,
    ) -> LegalStandardRecord:
        self._require_admin(actor)
        self._validate(limit_value, statistic_basis)
        now = self._clock.now()
        created_id = self._standards.insert_standard(
            _draft(
                standard_key=standard_key,
                version=version,
                pollutant=pollutant,
                statistic_basis=statistic_basis,
                limit_value=limit_value,
                unit=unit,
                legal_basis_name=legal_basis_name,
                legal_article=legal_article,
                penalty_basis=penalty_basis,
                effective_from=now,
                supersedes_id=None,
                created_by=actor.user_id,
                created_at=now,
            )
        )
        self._audit.append(_audit(actor.user_id, ACTION_STANDARD_CREATED, str(created_id), now))
        created = self._standards.get(created_id)
        if created is None:
            raise AppError(ErrorCode.SERVICE_UNAVAILABLE, "标准保存失败")
        return created

    def replace(
        self,
        actor: Principal,
        standard_id: int,
        *,
        expected_version: str,
        limit_value: float,
        statistic_basis: str,
        version: str,
        unit: str,
        legal_basis_name: str,
        legal_article: str,
        penalty_basis: str,
    ) -> LegalStandardRecord:
        self._require_admin(actor)
        self._validate(limit_value, statistic_basis)
        current = self._standards.get(standard_id)
        if current is None:
            raise AppError(ErrorCode.NOT_FOUND, "标准不存在")
        now = self._clock.now()
        try:
            self._standards.close_standard(
                standard_id, effective_to=now, expected_version=expected_version
            )
        except VersionConflictError:
            raise AppError(ErrorCode.CONFLICT, "标准版本冲突") from None
        created_id = self._standards.insert_standard(
            _draft(
                standard_key=current.standard_key,
                version=version,
                pollutant=current.pollutant,
                statistic_basis=statistic_basis,
                limit_value=limit_value,
                unit=unit,
                legal_basis_name=legal_basis_name,
                legal_article=legal_article,
                penalty_basis=penalty_basis,
                effective_from=now,
                supersedes_id=current.id,
                created_by=actor.user_id,
                created_at=now,
            )
        )
        self._audit.append(_audit(actor.user_id, ACTION_STANDARD_UPDATED, str(created_id), now))
        created = self._standards.get(created_id)
        if created is None:
            raise AppError(ErrorCode.SERVICE_UNAVAILABLE, "标准保存失败")
        return created

    def deactivate(self, actor: Principal, standard_id: int, *, expected_version: str) -> None:
        self._require_admin(actor)
        now = self._clock.now()
        try:
            self._standards.close_standard(
                standard_id, effective_to=now, expected_version=expected_version
            )
        except VersionConflictError:
            raise AppError(ErrorCode.CONFLICT, "标准版本冲突") from None
        except LookupError:
            raise AppError(ErrorCode.NOT_FOUND, "标准不存在") from None
        self._audit.append(_audit(actor.user_id, ACTION_STANDARD_DEACTIVATED, str(standard_id), now))

    def _require_admin(self, actor: Principal) -> None:
        if actor.role == ADMIN and is_allowed(actor.role, Operation.STANDARDS_WRITE):
            return
        self._audit.append(
            _audit(actor.user_id, ACTION_AUTHORIZATION_DENIED, Operation.STANDARDS_WRITE.value, self._clock.now())
        )
        raise AppError(ErrorCode.FORBIDDEN, "权限不足")

    def _validate(self, limit_value: float, statistic_basis: str) -> None:
        if not math.isfinite(limit_value) or limit_value <= 0:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "限值无效",
                details=(ErrorDetail(field="limit_value", reason="must be a positive finite number"),),
            )
        if statistic_basis not in ALLOWED_BASES:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "口径无效",
                details=(ErrorDetail(field="statistic_basis", reason="unsupported basis"),),
            )


def _draft(
    *,
    standard_key: str,
    version: str,
    pollutant: str,
    statistic_basis: str,
    limit_value: float,
    unit: str,
    legal_basis_name: str,
    legal_article: str,
    penalty_basis: str,
    effective_from: datetime,
    supersedes_id: int | None,
    created_by: int,
    created_at: datetime,
) -> StandardDraft:
    return StandardDraft(
        standard_key=standard_key,
        version=version,
        pollutant=pollutant,
        statistic_basis=statistic_basis,
        limit_value=limit_value,
        unit=unit,
        legal_basis_name=legal_basis_name,
        legal_article=legal_article,
        penalty_basis=penalty_basis,
        effective_from=effective_from,
        effective_to=None,
        is_active=True,
        supersedes_id=supersedes_id,
        created_by=created_by,
        created_at=created_at,
    )


def _audit(user_id: int, action: str, object_id: str, created_at: datetime) -> AuditDraft:
    return AuditDraft(
        user_id=user_id,
        action=action,
        object_type="operation" if action == ACTION_AUTHORIZATION_DENIED else "legal_standard",
        object_id=object_id,
        request_id=get_request_id(),
        result="DENIED" if action == ACTION_AUTHORIZATION_DENIED else "SUCCESS",
        details=None,
        ip_hash=None,
        created_at=created_at,
    )
