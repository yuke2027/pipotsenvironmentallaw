from contextlib import contextmanager
from typing import Any
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.v2.config import Settings


class Database:
    def __init__(self, settings: Settings):
        sqlite = settings.database_url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if sqlite else {}
        engine_args = {"connect_args": connect_args, "pool_pre_ping": True}
        if not sqlite:
            engine_args.update(pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow)
        self.engine = create_engine(settings.database_url, **engine_args)
        if settings.database_url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def configure(connection: Any, _record: Any) -> None:
                connection.execute("PRAGMA foreign_keys=ON")
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with self.sessions() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
