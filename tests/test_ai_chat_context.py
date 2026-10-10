from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.modules.ai_chat.context import MAX_PROJECT_FILES, ProjectContext
from app.modules.auth.models import User
from app.modules.auth.security import hash_password
from app.modules.projects.models import Project, ProjectSource


@pytest.fixture
def project_context(tmp_path: Path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        user = User(username="context-user", hashed_password=hash_password("secret123"))
        db.add(user)
        db.flush()
        project_path = tmp_path / "project"
        project_path.mkdir()
        project = Project(
            owner_id=user.id,
            name="project",
            source=ProjectSource.LOCAL,
            path=str(project_path),
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        yield ProjectContext(db, user, project.id), project_path
    engine.dispose()


def _error_code(exc: HTTPException) -> str:
    assert isinstance(exc.detail, dict)
    return exc.detail["code"]


def test_context_lists_only_project_relative_files_and_excludes_git(project_context) -> None:
    context, root = project_context
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("print('ok')", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("private", encoding="utf-8")

    result = context.list_files()

    assert result == {
        "entries": [{"path": "src", "type": "directory"}],
        "truncated": False,
    }
    with pytest.raises(HTTPException) as exc:
        context.read_file(".git/config")
    assert _error_code(exc.value) == "FILE_PATH_INVALID"


def test_context_rejects_traversal_and_symlink_escape(project_context, tmp_path: Path) -> None:
    context, root = project_context
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (root / "escape.txt").symlink_to(outside)

    for path in ("../outside.txt", str(outside), "escape.txt"):
        with pytest.raises(HTTPException) as exc:
            context.read_file(path)
        assert _error_code(exc.value) == "FILE_PATH_INVALID"


def test_context_bounds_file_and_directory_results(project_context) -> None:
    context, root = project_context
    for index in range(MAX_PROJECT_FILES + 5):
        (root / f"file-{index:03}.txt").write_text("x", encoding="utf-8")
    (root / "large.txt").write_text("x" * 1_000_001, encoding="utf-8")

    listing = context.list_files()

    assert len(listing["entries"]) == MAX_PROJECT_FILES
    assert listing["truncated"] is True
    with pytest.raises(HTTPException) as exc:
        context.read_file("large.txt")
    assert _error_code(exc.value) == "FILE_TOO_LARGE"
