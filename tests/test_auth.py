import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password

USERNAME = "alice"
PASSWORD = "secret123"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"


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


def test_login_success(client: TestClient) -> None:
    response = client.post(LOGIN_URL, json={"username": USERNAME, "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password(client: TestClient) -> None:
    response = client.post(LOGIN_URL, json={"username": USERNAME, "password": "wrong"})
    assert response.status_code == 401


def test_login_unknown_user(client: TestClient) -> None:
    response = client.post(LOGIN_URL, json={"username": "nobody", "password": PASSWORD})
    assert response.status_code == 401


def test_login_password_over_bcrypt_limit(client: TestClient) -> None:
    response = client.post(LOGIN_URL, json={"username": USERNAME, "password": "x" * 73})
    assert response.status_code == 422


def test_login_inactive_user(client: TestClient) -> None:
    response = client.post(LOGIN_URL, json={"username": "inactive", "password": PASSWORD})
    assert response.status_code == 403


def test_me_requires_token(client: TestClient) -> None:
    response = client.get(ME_URL)
    assert response.status_code == 401


def test_me_with_valid_token(client: TestClient) -> None:
    token = client.post(LOGIN_URL, json={"username": USERNAME, "password": PASSWORD}).json()[
        "access_token"
    ]
    response = client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == USERNAME
    assert body["is_active"] is True
    assert isinstance(body["id"], int)


def test_me_with_invalid_token(client: TestClient) -> None:
    response = client.get(ME_URL, headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401
