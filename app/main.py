from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from app.core.config import Settings, get_settings
from app.core.db import Base, SessionLocal, engine
from app.core.errors import validation_exception_handler
from app.core.i18n import resolve_language, set_language
from app.modules.auth.router import router as auth_router
from app.modules.auth.service import ensure_admin_user
from app.modules.health.router import router as health_router


def init_db(settings: Settings) -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_admin_user(db, settings)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(settings)
        yield

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
    return app


app = create_app()
