import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings, get_settings
from app.core.db import Base, get_db
from app.main import app
from app.modules.auth.models import User
from app.modules.auth.rate_limit import limiter
from app.modules.auth.security import hash_password
from app.modules.terminal import service as terminal_service
from app.modules.vscode import service as vscode_service

USERNAME = "alice"
OTHER_USERNAME = "bob"
PASSWORD = "secret123"
LOGIN_URL = "/api/v1/auth/login"
PROJECTS_URL = "/api/v1/projects"
BROWSE_URL = "/api/v1/projects/browse"
GITHUB_URL = "/api/v1/projects/github"
LOCAL_URL = "/api/v1/projects/local"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def projects_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    return root


@pytest.fixture
def client(projects_root) -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        db.add(User(username=USERNAME, hashed_password=hash_password(PASSWORD)))
        db.add(User(username=OTHER_USERNAME, hashed_password=hash_password(PASSWORD)))
        db.commit()

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    settings = Settings(projects_root=str(projects_root))
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        yield TestClient(app)
    finally:
        terminal_service.manager.kill_all()
        vscode_service.manager.kill_all()
        app.dependency_overrides.clear()


def _login(client: TestClient, username: str = USERNAME) -> None:
    response = client.post(LOGIN_URL, json={"username": username, "password": PASSWORD})
    assert response.status_code == 200


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("csrf_token")}


def assert_ws_close(
    client: TestClient,
    url: str,
    code: int,
    headers: dict[str, str] | None = None,
) -> None:
    """Assert the socket is accepted and then closed with ``code``.

    The server accepts before rejecting so browsers receive the application
    close code instead of an opaque 1006, so the code arrives after the
    handshake and must be read from the stream.
    """
    kwargs = {"headers": headers} if headers is not None else {}
    with client.websocket_connect(url, **kwargs) as websocket:
        with pytest.raises(WebSocketDisconnect) as exc:
            websocket.receive_text()
    assert exc.value.code == code
