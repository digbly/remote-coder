from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_directory(database_url: str) -> None:
    database = make_url(database_url).database
    if not database or database == ":memory:":
        return
    Path(database).parent.mkdir(parents=True, exist_ok=True)


def create_engine_for(settings: Settings):
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        _ensure_sqlite_directory(settings.database_url)
    return create_engine(settings.database_url, connect_args=connect_args)


engine = create_engine_for(get_settings())
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
