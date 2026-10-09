from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.db import Base, get_db
from app.main import app
from app.modules.auth import service
from app.modules.auth.models import RefreshToken, User
from app.modules.auth.rate_limit import limiter
from app.modules.auth.security import generate_refresh_token, hash_password, hash_refresh_token

USERNAME = "alice"
PASSWORD = "secret123"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
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


def test_login_success_sets_refresh_cookie(client: TestClient) -> None:
    _login(client)
    assert client.cookies.get("refresh_token")


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


def _refresh(client: TestClient, csrf: str):
    return client.post(REFRESH_URL, headers={"X-CSRF-Token": csrf})


def test_refresh_requires_csrf(client: TestClient) -> None:
    _login(client)
    assert client.post(REFRESH_URL).status_code == 403


def test_refresh_without_cookie(client: TestClient) -> None:
    _login(client)
    csrf = client.cookies.get("csrf_token")
    client.cookies.delete("refresh_token")
    assert _refresh(client, csrf).status_code == 401


def test_refresh_rotates_token(client: TestClient) -> None:
    _login(client)
    csrf = client.cookies.get("csrf_token")
    old_refresh = client.cookies.get("refresh_token")

    response = _refresh(client, csrf)
    assert response.status_code == 200
    assert response.json()["username"] == USERNAME

    new_refresh = client.cookies.get("refresh_token")
    assert new_refresh and new_refresh != old_refresh
    assert client.get(ME_URL).status_code == 200


def test_refresh_reuse_revokes_all_tokens(client: TestClient) -> None:
    _login(client)
    csrf = client.cookies.get("csrf_token")
    old_refresh = client.cookies.get("refresh_token")

    assert _refresh(client, csrf).status_code == 200
    new_refresh = client.cookies.get("refresh_token")
    csrf = client.cookies.get("csrf_token")

    client.cookies.set("refresh_token", old_refresh)
    assert _refresh(client, csrf).status_code == 401

    client.cookies.set("refresh_token", new_refresh)
    csrf = client.cookies.get("csrf_token")
    assert _refresh(client, csrf).status_code == 401


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    _login(client)
    csrf = client.cookies.get("csrf_token")
    refresh_token = client.cookies.get("refresh_token")

    client.post(LOGOUT_URL, headers={"X-CSRF-Token": csrf})

    client.cookies.set("refresh_token", refresh_token)
    client.cookies.set("csrf_token", "csrf")
    assert _refresh(client, "csrf").status_code == 401


def test_refresh_error_code(client: TestClient) -> None:
    _login(client)
    csrf = client.cookies.get("csrf_token")
    client.cookies.delete("refresh_token")
    assert _error_code(_refresh(client, csrf)) == "NOT_AUTHENTICATED"


def test_refresh_rate_limited(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        refresh_rate_limit_attempts=2,
        login_rate_limit_attempts=50,
    )
    try:
        _login(client)
        for _ in range(2):
            csrf = client.cookies.get("csrf_token")
            assert _refresh(client, csrf).status_code == 200

        csrf = client.cookies.get("csrf_token")
        blocked = _refresh(client, csrf)
        assert blocked.status_code == 429
        assert blocked.headers.get("Retry-After")
        assert _error_code(blocked) == "RATE_LIMITED"
    finally:
        app.dependency_overrides.pop(get_settings, None)


def _service_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _add_token(db, user_id: int, raw_token: str, expires_at: datetime) -> None:
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=expires_at,
        )
    )


def test_rotate_refresh_token_rejects_expired() -> None:
    db = _service_session()
    try:
        user = User(username="expired", hashed_password=hash_password(PASSWORD))
        db.add(user)
        db.commit()

        raw_token = generate_refresh_token()
        _add_token(db, user.id, raw_token, datetime.now(UTC) - timedelta(seconds=1))
        db.commit()

        with pytest.raises(HTTPException) as exc:
            service.rotate_refresh_token(db, raw_token, Settings())
        assert exc.value.status_code == 401
    finally:
        db.close()


def test_rotate_refresh_token_rejects_inactive_user() -> None:
    db = _service_session()
    try:
        user = User(
            username="inactive2",
            hashed_password=hash_password(PASSWORD),
            is_active=False,
        )
        db.add(user)
        db.commit()

        raw_token = generate_refresh_token()
        _add_token(db, user.id, raw_token, datetime.now(UTC) + timedelta(days=1))
        db.commit()

        with pytest.raises(HTTPException) as exc:
            service.rotate_refresh_token(db, raw_token, Settings())
        assert exc.value.status_code == 403
    finally:
        db.close()


def test_issue_refresh_token_prunes_only_expired() -> None:
    db = _service_session()
    try:
        user = User(username="prune", hashed_password=hash_password(PASSWORD))
        db.add(user)
        db.commit()

        expired = generate_refresh_token()
        active = generate_refresh_token()
        _add_token(db, user.id, expired, datetime.now(UTC) - timedelta(seconds=1))
        _add_token(db, user.id, active, datetime.now(UTC) + timedelta(days=1))
        db.commit()

        service.issue_refresh_token(db, user, Settings())

        hashes = set(db.scalars(select(RefreshToken.token_hash)).all())
        assert hash_refresh_token(expired) not in hashes
        assert hash_refresh_token(active) in hashes
    finally:
        db.close()


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


def test_login_error_message_localized_by_accept_language(client: TestClient) -> None:
    response = client.post(
        LOGIN_URL,
        json={"username": USERNAME, "password": "wrong"},
        headers={"Accept-Language": "vi"},
    )
    assert response.json()["detail"]["message"] == "Tên đăng nhập hoặc mật khẩu không đúng"


def test_login_validation_error_includes_field(client: TestClient) -> None:
    detail = _login(client, password="x" * 73).json()["detail"]
    assert detail["code"] == "VALIDATION_ERROR"
    assert detail["errors"][0]["field"] == "password"


def test_login_openapi_documents_error_schema(client: TestClient) -> None:
    responses = client.get("/openapi.json").json()["paths"]["/api/v1/auth/login"]["post"][
        "responses"
    ]
    for status_code in ("401", "403", "422", "429"):
        schema = responses[status_code]["content"]["application/json"]["schema"]
        assert schema["$ref"].endswith("/ErrorResponse")
