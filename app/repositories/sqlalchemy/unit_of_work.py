"""Transaction boundary that exposes repository protocols over one session."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from app.repositories.sqlalchemy.catalog import SqlAlchemyCatalogRepository
from app.repositories.sqlalchemy.monitoring import SqlAlchemyMonitoringRepository
from app.repositories.sqlalchemy.store import (
    SqlAlchemyAlertRepository,
    SqlAlchemyAnalysisRepository,
    SqlAlchemyAuditRepository,
    SqlAlchemyAuthRepository,
    SqlAlchemyJobRunRepository,
    SqlAlchemyModelRepository,
    SqlAlchemyStandardsRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._session = factory()
        self.monitoring = SqlAlchemyMonitoringRepository(self._session)
        self.catalog = SqlAlchemyCatalogRepository(self._session)
        self.standards = SqlAlchemyStandardsRepository(self._session)
        self.analysis = SqlAlchemyAnalysisRepository(self._session)
        self.models = SqlAlchemyModelRepository(self._session)
        self.alerts = SqlAlchemyAlertRepository(self._session)
        self.auth = SqlAlchemyAuthRepository(self._session)
        self.audit = SqlAlchemyAuditRepository(self._session)
        self.jobs = SqlAlchemyJobRunRepository(self._session)

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                self.rollback()
        finally:
            self.close()
