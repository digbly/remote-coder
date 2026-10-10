import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import inspect, text

from app.core.config import Settings, get_settings
from app.core.db import Base, SessionLocal, engine
from app.core.errors import validation_exception_handler
from app.core.i18n import resolve_language, set_language
from app.core.logging import configure_logging
from app.modules.agents.router import router as agents_router
from app.modules.ai_chat.approvals import cancel_all as cancel_pending_approvals
from app.modules.ai_chat.router import router as ai_chat_router
from app.modules.ai_providers.router import router as ai_providers_router
from app.modules.auth.router import router as auth_router
from app.modules.auth.service import ensure_admin_user
from app.modules.git.router import router as git_router
from app.modules.health.router import router as health_router
from app.modules.projects.router import router as projects_router
from app.modules.terminal import service as terminal_service
from app.modules.terminal.router import router as terminal_router
from app.modules.vscode import service as vscode_service
from app.modules.vscode.router import router as vscode_router
from app.modules.workspace.router import router as workspace_router

TERMINAL_REAP_INTERVAL_SECONDS = 300


def _add_column_if_missing(table: str, column: str, definition: str) -> None:
    columns = {item["name"] for item in inspect(engine).get_columns(table)}
    if column in columns:
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))


def _apply_lightweight_migrations() -> None:
    tables = set(inspect(engine).get_table_names())
    if "ai_chat_messages" in tables:
        _add_column_if_missing("ai_chat_messages", "thinking", "TEXT NOT NULL DEFAULT ''")
    if "ai_change_proposals" in tables:
        _add_column_if_missing(
            "ai_change_proposals", "change_type", "VARCHAR(16) NOT NULL DEFAULT 'modify'"
        )
        _add_column_if_missing("ai_change_proposals", "target_path", "VARCHAR(4096)")


def init_db(settings: Settings) -> None:
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()
    with SessionLocal() as db:
        ensure_admin_user(db, settings)


async def _reap_idle_sessions(settings: Settings) -> None:
    while True:
        await asyncio.sleep(TERMINAL_REAP_INTERVAL_SECONDS)
        await asyncio.to_thread(
            terminal_service.manager.reap_idle, settings.terminal_session_ttl_seconds
        )
        await asyncio.to_thread(
            vscode_service.manager.reap_idle, settings.vscode_session_ttl_seconds
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(settings)
        reaper = asyncio.create_task(_reap_idle_sessions(settings))
        try:
            yield
        finally:
            cancel_pending_approvals()
            reaper.cancel()
            with suppress(asyncio.CancelledError):
                await reaper
            await asyncio.to_thread(vscode_service.manager.kill_all)

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @app.middleware("http")
    async def _apply_accept_language(request: Request, call_next):
        set_language(resolve_language(request.headers.get("accept-language")))
        return await call_next(request)

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(projects_router, prefix=settings.api_prefix)
    app.include_router(git_router, prefix=settings.api_prefix)
    app.include_router(terminal_router, prefix=settings.api_prefix)
    app.include_router(vscode_router, prefix=settings.api_prefix)
    app.include_router(agents_router, prefix=settings.api_prefix)
    app.include_router(ai_providers_router, prefix=settings.api_prefix)
    app.include_router(ai_chat_router, prefix=settings.api_prefix)
    app.include_router(workspace_router, prefix=settings.api_prefix)
    return app


app = create_app()
