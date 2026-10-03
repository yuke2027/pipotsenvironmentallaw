"""Dependency direction markers used by domain services and architecture tests."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session


@contextmanager
def transaction(session: Session) -> Iterator[Session]:
    """Commit a unit of work or roll it back atomically."""

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
