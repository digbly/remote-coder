from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select

from app.config import Settings, get_settings
from app.db import Base, SessionLocal, engine
from app.errors import validation_exception_handler
from app.i18n import resolve_language, set_language
from app.models import User
from app.routers import auth, health
from app.security import hash_password


def init_db(settings: Settings) -> None:
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        exists = db.scalar(select(User).where(User.username == settings.admin_username))
        if exists is None:
            db.add(
                User(
                    username=settings.admin_username,
                    hashed_password=hash_password(settings.admin_password),
                )
            )
            db.commit()


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

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    return app


app = create_app()
