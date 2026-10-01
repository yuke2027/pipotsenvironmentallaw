"""Database engine and session construction.

SQLite foreign keys, WAL, and busy timeout are applied only from the connect
callback below. Business models do not contain dialect SQL.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

SQLITE_BUSY_TIMEOUT_MS = 5000


def sqlite_file_url(path: Path) -> str:
    """Build a SQLite URL for an explicit filesystem path."""

    return "sqlite:///" + path.resolve().as_posix()


def sqlite_database_path(database_url: str) -> Path | None:
    """Return the SQLite file path, or None for non-file databases."""

    parsed = make_url(database_url)
    if not parsed.drivername.startswith("sqlite"):
        return None
    database = parsed.database
    if database is None or database == ":memory:":
        return None
    return Path(database)


def _configure_sqlite_connection(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def create_engine_from_url(database_url: str) -> Engine:
    """Create an engine and, for SQLite, register the connect callback."""

    connect_args: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(database_url, connect_args=connect_args)
    if database_url.startswith("sqlite"):
        event.listen(engine, "connect", _configure_sqlite_connection)
    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory that flushes only when a repository asks."""

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
