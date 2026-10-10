from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError

from app.modules.ai_providers import service
from app.modules.ai_providers.base import ProviderAPIError, ProviderModel
from app.modules.ai_providers.openai import OpenAIAdapter
from tests.conftest import OTHER_USERNAME, _csrf, _login

PROVIDERS_URL = "/api/v1/ai-providers"


def _create_provider(client: TestClient, *, shared: bool = False) -> dict:
    path = f"{PROVIDERS_URL}/shared" if shared else PROVIDERS_URL
    response = client.post(
        path,
        json={
            "name": "OpenAI team" if shared else "OpenAI personal",
            "kind": "openai",
            "api_key": "provider-secret",
        },
        headers=_csrf(client),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_personal_provider_credentials_are_masked_and_owner_scoped(client: TestClient) -> None:
    _login(client)
    provider = _create_provider(client)

    assert provider["credential_configured"] is True
    assert "api_key" not in provider
    assert "provider-secret" not in str(provider)

    _login(client, OTHER_USERNAME)

    assert client.get(PROVIDERS_URL).json() == {
        "providers": [],
        "can_manage_shared": False,
    }
    assert client.get(f"{PROVIDERS_URL}/{provider['id']}/models").status_code == 404


def test_shared_provider_is_visible_but_only_admin_can_manage(client: TestClient) -> None:
    _login(client)
    provider = _create_provider(client, shared=True)

    _login(client, OTHER_USERNAME)
    visible = client.get(PROVIDERS_URL).json()["providers"]
    assert [item["id"] for item in visible] == [provider["id"]]
    assert "provider-secret" not in str(visible)

    create_response = client.post(
        f"{PROVIDERS_URL}/shared",
        json={"name": "Another shared key", "kind": "openai", "api_key": "secret"},
        headers=_csrf(client),
    )
    update_response = client.patch(
        f"{PROVIDERS_URL}/shared/{provider['id']}",
        json={"name": "Changed"},
        headers=_csrf(client),
    )
    delete_response = client.delete(
        f"{PROVIDERS_URL}/shared/{provider['id']}",
        headers=_csrf(client),
    )

    assert create_response.status_code == 403
    assert update_response.status_code == 403
    assert delete_response.status_code == 403


def test_provider_model_list_and_connection_test_use_adapter(
    client: TestClient, monkeypatch
) -> None:
    _login(client)
    provider = _create_provider(client)
    calls = {"models": 0}

    async def list_models(self, _client: AsyncClient, api_key: str) -> list[ProviderModel]:
        calls["models"] += 1
        assert api_key == "provider-secret"
        return [ProviderModel("gpt-example", "GPT Example")]

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)

    models = client.get(f"{PROVIDERS_URL}/{provider['id']}/models")
    test_result = client.post(
        f"{PROVIDERS_URL}/{provider['id']}/test",
        headers=_csrf(client),
    )

    assert models.status_code == 200
    assert models.json() == {"models": [{"id": "gpt-example", "display_name": "GPT Example"}]}
    assert test_result.status_code == 200
    assert test_result.json() == {"ok": True, "model_count": 1}
    assert calls["models"] == 2


def test_provider_error_is_sanitized_and_explicit(client: TestClient, monkeypatch) -> None:
    _login(client)
    provider = _create_provider(client)

    async def fail(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        raise ProviderAPIError("openai", 401)

    monkeypatch.setattr(OpenAIAdapter, "list_models", fail)

    response = client.get(f"{PROVIDERS_URL}/{provider['id']}/models")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "AI_PROVIDER_FAILED"
    assert "provider-secret" not in response.text


def test_duplicate_provider_name_is_rejected(client: TestClient) -> None:
    _login(client)
    _create_provider(client)

    response = client.post(
        PROVIDERS_URL,
        json={"name": "OpenAI personal", "kind": "openai", "api_key": "another-secret"},
        headers=_csrf(client),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "AI_PROVIDER_NAME_EXISTS"


def test_duplicate_provider_name_race_is_rejected(client: TestClient, monkeypatch) -> None:
    _login(client)
    _create_provider(client)
    monkeypatch.setattr(service, "_ensure_unique_name", lambda *_args, **_kwargs: None)

    response = client.post(
        PROVIDERS_URL,
        json={"name": "OpenAI personal", "kind": "openai", "api_key": "another-secret"},
        headers=_csrf(client),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "AI_PROVIDER_NAME_EXISTS"


def test_provider_mutations_require_csrf(client: TestClient) -> None:
    _login(client)

    response = client.post(
        PROVIDERS_URL,
        json={"name": "OpenAI personal", "kind": "openai", "api_key": "provider-secret"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "CSRF_INVALID"


def test_unrelated_integrity_error_is_not_reported_as_duplicate_name() -> None:
    db = Mock()
    db.commit.side_effect = IntegrityError("insert", {}, Exception("foreign key failure"))

    with pytest.raises(IntegrityError, match="foreign key failure"):
        service._commit_provider(db, Mock())

    db.rollback.assert_called_once_with()
