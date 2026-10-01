"""Process startup performed before the application listens."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.fonts import ChineseFontResolver, ChineseFontStatus
from app.core.paths import PathSettings
from app.db.seed import seed_reference_data
from app.db.session import create_engine_from_url, session_factory
from app.db.upgrade import upgrade_database
from app.lifecycle import ModelHealth, health_payload
from app.scheduler.jobs import STEP_NAMES, success
from app.scheduler.pipeline import Pipeline, build_scheduler


@dataclass
class AppContext:
    settings: Settings
    paths: PathSettings
    engine: Engine
    sessions: sessionmaker[Session]
    font: ChineseFontStatus
    saits: ModelHealth | None = None
    lstm: ModelHealth | None = None
    scheduler: object | None = field(default=None)

    def health(self) -> dict[str, object]:
        database_ok = False
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            database_ok = True
        except Exception:
            database_ok = False
        return health_payload(database_ok=database_ok, saits=self.saits, lstm=self.lstm)


def bootstrap(settings: Settings, *, admin_password: str | None = None) -> AppContext:
    """Validate paths, upgrade, seed, and resolve fonts before serving traffic."""

    paths = PathSettings.from_settings(settings)
    paths.ensure_directories()
    database_url = settings.database_url or paths.database_url
    upgrade_database(database_url, backup_directory=paths.local_config_dir / "backups")
    engine = create_engine_from_url(database_url)
    sessions = session_factory(engine)
    with sessions() as session:
        seed_reference_data(session, admin_password=admin_password)
        session.commit()
    try:
        font = ChineseFontResolver.from_settings(settings).resolve()
    except Exception:
        font = ChineseFontStatus.unavailable("中文字体不可用")
    context = AppContext(
        settings=settings,
        paths=paths,
        engine=engine,
        sessions=sessions,
        font=font,
    )
    pipeline = Pipeline({name: (lambda: success(no_op=True)) for name in STEP_NAMES})
    context.scheduler = build_scheduler(pipeline, settings.collection_interval_seconds)
    return context
