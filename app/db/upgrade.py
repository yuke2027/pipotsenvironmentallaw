"""Upgrade an explicit database URL, backing up an existing SQLite file first."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.db.session import create_engine_from_url, sqlite_database_path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def alembic_config(database_url: str) -> Config:
    """Build Alembic config for one caller-supplied URL."""

    _guard_test_database(database_url)
    root = _project_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str((root / "app" / "db" / "migrations").resolve()))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def current_revision(database_url: str) -> str | None:
    """Read the applied revision without creating a missing SQLite file."""

    path = sqlite_database_path(database_url)
    if path is not None and not path.exists():
        return None
    engine = create_engine_from_url(database_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            revision = context.get_current_revision()
    finally:
        engine.dispose()
    return revision


def backup_sqlite_database(source: Path, backup_directory: Path) -> Path:
    """Copy a SQLite file with the sqlite3 backup API."""

    backup_directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_directory / f"{source.stem}-{stamp}.db"
    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        with destination_connection:
            source_connection.backup(destination_connection)
    finally:
        source_connection.close()
        destination_connection.close()
    return destination


def upgrade_database(
    database_url: str,
    *,
    backup_directory: Path,
    revision: str = "head",
) -> Path | None:
    """Upgrade to ``revision``. An existing database not already there is backed up."""

    config = alembic_config(database_url)
    script = ScriptDirectory.from_config(config)
    destination = script.get_current_head() if revision == "head" else revision
    applied = current_revision(database_url)
    backup_path: Path | None = None
    database_file = sqlite_database_path(database_url)
    if database_file is not None and database_file.exists() and applied != destination:
        backup_path = backup_sqlite_database(database_file, backup_directory)
    command.upgrade(config, revision)
    return backup_path


def _guard_test_database(database_url: str) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST") and "environmental_supervision.db" in database_url:
        raise RuntimeError("tests must not open the production database")
