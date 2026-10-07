import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import User
from app.rate_limit import limiter
from app.security import hash_password

USERNAME = "alice"
PASSWORD = "secret123"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
LOGOUT_URL = "/api/v1/auth/logout"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        db.add(User(username=USERNAME, hashed_password=hash_password(PASSWORD)))
        db.add(
            User(
                username="inactive",
                hashed_password=hash_password(PASSWORD),
                is_active=False,
            )
        )
        db.commit()

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _login(client: TestClient, username: str = USERNAME, password: str = PASSWORD):
    return client.post(LOGIN_URL, json={"username": username, "password": password})


def _error_code(response) -> str:
    return response.json()["detail"]["code"]


def test_login_success_sets_httponly_cookie(client: TestClient) -> None:
    response = _login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == USERNAME
    assert body["is_active"] is True
    assert client.cookies.get("access_token")
    assert client.cookies.get("csrf_token")
    assert "HttpOnly" in response.headers["set-cookie"]


def test_login_wrong_password(client: TestClient) -> None:
    assert _login(client, password="wrong").status_code == 401


def test_login_unknown_user(client: TestClient) -> None:
    assert _login(client, username="nobody").status_code == 401


def test_login_inactive_user(client: TestClient) -> None:
    assert _login(client, username="inactive").status_code == 403


def test_login_password_over_bcrypt_limit(client: TestClient) -> None:
    assert _login(client, password="x" * 73).status_code == 422


def test_login_rate_limited(client: TestClient) -> None:
    for _ in range(5):
        assert _login(client, password="wrong").status_code == 401

    blocked = _login(client, password="wrong")
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get(ME_URL).status_code == 401


def test_me_with_cookie(client: TestClient) -> None:
    _login(client)
    response = client.get(ME_URL)
    assert response.status_code == 200
    assert response.json()["username"] == USERNAME


def test_logout_requires_csrf(client: TestClient) -> None:
    _login(client)
    assert client.post(LOGOUT_URL).status_code == 403


def test_logout_clears_session(client: TestClient) -> None:
    _login(client)
    csrf = client.cookies.get("csrf_token")
    response = client.post(LOGOUT_URL, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 204
    assert client.get(ME_URL).status_code == 401


def test_login_wrong_password_error_code(client: TestClient) -> None:
    assert _error_code(_login(client, password="wrong")) == "INVALID_CREDENTIALS"


def test_login_inactive_user_error_code(client: TestClient) -> None:
    assert _error_code(_login(client, username="inactive")) == "INACTIVE_USER"


def test_login_password_over_bcrypt_limit_error_code(client: TestClient) -> None:
    assert _error_code(_login(client, password="x" * 73)) == "VALIDATION_ERROR"


def test_me_requires_auth_error_code(client: TestClient) -> None:
    assert _error_code(client.get(ME_URL)) == "NOT_AUTHENTICATED"


def test_logout_requires_csrf_error_code(client: TestClient) -> None:
    _login(client)
    assert _error_code(client.post(LOGOUT_URL)) == "CSRF_INVALID"


def test_login_rate_limited_error_code(client: TestClient) -> None:
    for _ in range(5):
        _login(client, password="wrong")

    assert _error_code(_login(client, password="wrong")) == "RATE_LIMITED"
