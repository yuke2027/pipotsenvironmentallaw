"""Shared offset/limit pagination for SQLAlchemy repositories."""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


def paginate(
    session: Session,
    statement: Select[Any],
    page: int,
    page_size: int,
) -> tuple[list[ModelT], int]:
    if page < 1 or page_size < 1:
        raise ValueError("page and page_size must be positive")
    total_value = session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    total = 0 if total_value is None else int(total_value)
    rows: list[ModelT] = list(session.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all())
    return rows, total
