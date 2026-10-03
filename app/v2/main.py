from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from app.core.errors import AppError, ErrorCode, app_error_handler, register_error_handlers
from app.core.logging import install_sensitive_data_filter
from app.v2.config import Settings
from app.v2.db import Database
from app.v2.storage import FileStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.prepare()
    database = Database(settings)
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        database.engine.dispose()
    app = FastAPI(title="环境监测与执法辅助平台", version="2.0.0", lifespan=lifespan,
                  docs_url="/api/v2/docs", openapi_url="/api/v2/openapi.json", redoc_url=None)
    app.state.settings, app.state.db, app.state.store = settings, database, FileStore(settings.storage_root)
    register_error_handlers(app)
    install_sensitive_data_filter()

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Any:
        code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.INVALID_REQUEST
        return await app_error_handler(request, AppError(code, "接口不存在" if exc.status_code == 404 else "请求方法或参数无效", status_code=exc.status_code))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Any:
        details = [{"field": ".".join(map(str, error["loc"])), "reason": error["msg"]} for error in exc.errors()]
        return await app_error_handler(request, AppError(ErrorCode.VALIDATION_ERROR, "输入内容有误", details=details))

    @app.exception_handler(IntegrityError)
    async def conflict(request: Request, exc: IntegrityError) -> Any:
        return await app_error_handler(request, AppError(ErrorCode.CONFLICT, "记录重复或关联记录已变更，请刷新后重试"))

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin"})
        if request.url.path.startswith("/api/"): response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health/live", include_in_schema=False)
    def live() -> dict[str, Any]: return {"status": "ok", "version": "2.0.0"}

    @app.get("/health/ready", include_in_schema=False)
    def ready() -> dict[str, str]:
        with database.sessions() as session:
            session.execute(text("SELECT version_num FROM v2_alembic_version"))
        return {"status": "ready"}

    # Import routers through domain facades.  The facades preserve the public
    # /api/v2 contract while allowing each domain to migrate independently.
    from app.v2 import admin, auth, enforcement, jobs, monitoring
    for router in [auth.router, monitoring.router, jobs.router, enforcement.router, admin.router]:
        app.include_router(router, prefix="/api/v2")
    return app
