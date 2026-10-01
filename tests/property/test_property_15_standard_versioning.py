"""Property 15: only valid standards are saved, and edits keep the previous version."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.clock import FrozenClock
from app.core.errors import AppError
from app.domain.audit_actions import ACTION_STANDARD_UPDATED
from app.domain.principal import Principal
from app.domain.records import LegalStandardRecord, Page
from app.services.standards import ALLOWED_BASES, StandardsService

_WHEN = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Standards:
    def __init__(self) -> None:
        self.rows: dict[int, LegalStandardRecord] = {}
        self._next = 1

    def snapshot(self, at: datetime) -> object:
        del at
        raise AssertionError("not used")

    def list_standards(self, page: int, page_size: int, *, pollutant: str | None = None) -> Page[object]:
        del page, page_size, pollutant
        raise AssertionError("not used")

    def get(self, standard_id: int) -> LegalStandardRecord | None:
        return self.rows.get(standard_id)

    def insert_standard(self, draft: object) -> int:
        standard_id = self._next
        self._next += 1
        self.rows[standard_id] = LegalStandardRecord(
            id=standard_id,
            standard_key=getattr(draft, "standard_key"),
            version=getattr(draft, "version"),
            pollutant=getattr(draft, "pollutant"),
            statistic_basis=getattr(draft, "statistic_basis"),
            limit_value=getattr(draft, "limit_value"),
            unit=getattr(draft, "unit"),
            legal_basis_name=getattr(draft, "legal_basis_name"),
            legal_article=getattr(draft, "legal_article"),
            penalty_basis=getattr(draft, "penalty_basis"),
            effective_from=getattr(draft, "effective_from"),
            effective_to=getattr(draft, "effective_to"),
            is_active=getattr(draft, "is_active"),
        )
        return standard_id

    def close_standard(self, standard_id: int, *, effective_to: datetime, expected_version: str) -> None:
        from app.domain.errors import VersionConflictError

        current = self.rows[standard_id]
        if current.version != expected_version:
            raise VersionConflictError()
        self.rows[standard_id] = LegalStandardRecord(
            id=current.id,
            standard_key=current.standard_key,
            version=current.version,
            pollutant=current.pollutant,
            statistic_basis=current.statistic_basis,
            limit_value=current.limit_value,
            unit=current.unit,
            legal_basis_name=current.legal_basis_name,
            legal_article=current.legal_article,
            penalty_basis=current.penalty_basis,
            effective_from=current.effective_from,
            effective_to=effective_to,
            is_active=False,
        )


class _Audit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    def append(self, draft: object) -> int:
        self.actions.append(getattr(draft, "action"))
        return len(self.actions)

    def list_entries(self, page: int, page_size: int) -> object:
        raise AssertionError("not used")

    def list_by_user_action(self, user_id: int, action: str) -> tuple[object, ...]:
        raise AssertionError("not used")


def _actor() -> Principal:
    return Principal(1, "admin", "管理员", False, "jti", _WHEN)


@given(
    bad_limit=st.one_of(
        st.just(float("nan")),
        st.just(float("inf")),
        st.just(0.0),
        st.floats(max_value=0, allow_nan=False, allow_infinity=False),
    ),
    good_limit=st.floats(min_value=0.1, max_value=400, allow_nan=False, allow_infinity=False),
    bad_basis=st.text(min_size=1, max_size=12).filter(lambda value: value not in ALLOWED_BASES),
)
@pytest.mark.property
def test_property_15_standards_keep_history(bad_limit: float, good_limit: float, bad_basis: str) -> None:
    """Illegal values name the field; a legal edit keeps the old row and audits the new one.

    **Feature: environmental-supervision-platform, Property 15: 标准验证和版本保留**
    **Property 15：标准验证和版本保留**
    **Validates: Requirements 6.9, 6.10, 6.11, 15.7**
    """

    standards = _Standards()
    audit = _Audit()
    service = StandardsService(standards, audit, FrozenClock(_WHEN))  # type: ignore[arg-type]
    with pytest.raises(AppError) as invalid_limit:
        service.create(
            _actor(),
            standard_key="PM25",
            version="1",
            pollutant="PM2.5",
            statistic_basis="24h_mean",
            limit_value=bad_limit,
            unit="ug",
            legal_basis_name="GB",
            legal_article="article",
            penalty_basis="law",
        )
    assert any(detail.field == "limit_value" for detail in invalid_limit.value.details if hasattr(detail, "field"))
    with pytest.raises(AppError) as invalid_basis:
        service.create(
            _actor(),
            standard_key="PM25",
            version="1",
            pollutant="PM2.5",
            statistic_basis=bad_basis,
            limit_value=good_limit,
            unit="ug",
            legal_basis_name="GB",
            legal_article="article",
            penalty_basis="law",
        )
    assert any(detail.field == "statistic_basis" for detail in invalid_basis.value.details if hasattr(detail, "field"))
    assert standards.rows == {}
    created = service.create(
        _actor(),
        standard_key="PM25",
        version="1",
        pollutant="PM2.5",
        statistic_basis="24h_mean",
        limit_value=good_limit,
        unit="ug",
        legal_basis_name="GB",
        legal_article="article",
        penalty_basis="law",
    )
    updated = service.replace(
        _actor(),
        created.id,
        expected_version="1",
        limit_value=good_limit + 1,
        statistic_basis="24h_mean",
        version="2",
        unit="ug",
        legal_basis_name="GB",
        legal_article="article",
        penalty_basis="law",
    )
    assert standards.get(created.id) is not None
    assert standards.get(created.id).is_active is False  # type: ignore[union-attr]
    assert updated.is_active is True
    assert updated.id != created.id
    assert math.isfinite(updated.limit_value)
    assert ACTION_STANDARD_UPDATED in audit.actions
