"""Application factory. Configuration and database upgrade finish before listen."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.v1.routes import pages, router
from app.core.config import Settings, load_settings
from app.core.errors import register_error_handlers
from app.runtime import bootstrap


def application_name() -> str:
    """Return the stable application identifier used by smoke checks."""
    return "environmental-supervision-platform"


def create_app(settings: Settings | None = None, *, admin_password: str | None = None) -> FastAPI:
    """Build the ASGI app after startup work that must happen before listen."""

    resolved = settings if settings is not None else load_settings()
    context = bootstrap(resolved, admin_password=admin_password)
    root = Path(__file__).resolve().parent

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        scheduler = app.state.context.scheduler
        if scheduler is not None:
            scheduler.start()
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="环境监督平台", lifespan=lifespan)
    app.state.context = context
    app.state.templates = Jinja2Templates(directory=str(root / "templates"))
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.include_router(pages)
    app.mount("/static", StaticFiles(directory=str(root / "static")), name="static")
    return app
