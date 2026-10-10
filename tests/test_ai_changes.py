import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.modules.ai_providers.base import ProviderModel, TextDelta, ToolCall, TurnComplete
from app.modules.ai_providers.openai import OpenAIAdapter
from app.modules.projects import service as project_service
from tests.conftest import LOCAL_URL, OTHER_USERNAME, _csrf, _login

PROVIDERS_URL = "/api/v1/ai-providers"


def _create_project(client: TestClient, folder: Path) -> int:
    folder.mkdir()
    response = client.post(LOCAL_URL, json={"path": str(folder)}, headers=_csrf(client))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_provider(client: TestClient) -> int:
    response = client.post(
        PROVIDERS_URL,
        json={"name": "OpenAI", "kind": "openai", "api_key": "provider-secret"},
        headers=_csrf(client),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _events(response) -> list[dict[str, object]]:
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines()]


def _create_proposal(
    client: TestClient,
    project_id: int,
    provider_id: int,
    monkeypatch,
) -> tuple[str, str, dict[str, object]]:
    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    calls = 0

    async def stream(self, *_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield ToolCall(
                "proposal-1",
                "propose_file_change",
                {"path": "main.py", "content": "print('updated')\n"},
            )
            yield TurnComplete("tool_calls")
        else:
            yield TextDelta("I prepared a diff for review.")
            yield TurnComplete("completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Update main.py",
            },
            headers=_csrf(client),
        )
    )
    start = events[0]
    proposal_event = next(event for event in events if event["type"] == "proposal")
    return start["conversation"]["id"], proposal_event["id"], proposal_event


def test_proposal_is_reviewable_and_does_not_write_before_approval(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    target = path / "main.py"
    target.write_text("print('original')\n", encoding="utf-8")

    conversation_id, proposal_id, event = _create_proposal(
        client, project_id, provider_id, monkeypatch
    )

    assert target.read_text(encoding="utf-8") == "print('original')\n"
    assert event["path"] == "main.py"
    assert "print('original')" in event["diff"]
    assert "print('updated')" in event["diff"]
    listed = client.get(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}/proposals"
    ).json()["proposals"]
    assert listed[0]["id"] == proposal_id
    assert listed[0]["status"] == "pending"


def test_apply_requires_explicit_approval_and_writes_proposed_content(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    target = path / "main.py"
    target.write_text("print('original')\n", encoding="utf-8")
    conversation_id, proposal_id, _ = _create_proposal(client, project_id, provider_id, monkeypatch)

    response = client.post(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
        f"/proposals/{proposal_id}/apply",
        headers=_csrf(client),
    )

    assert response.status_code == 200
    assert response.json()["proposal"]["status"] == "applied"
    assert target.read_text(encoding="utf-8") == "print('updated')\n"


def test_reject_leaves_file_unchanged_and_proposal_cannot_be_reused(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    target = path / "main.py"
    target.write_text("print('original')\n", encoding="utf-8")
    conversation_id, proposal_id, _ = _create_proposal(client, project_id, provider_id, monkeypatch)
    endpoint = (
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
        f"/proposals/{proposal_id}"
    )

    rejected = client.post(f"{endpoint}/reject", headers=_csrf(client))
    second_action = client.post(f"{endpoint}/apply", headers=_csrf(client))

    assert rejected.status_code == 200
    assert rejected.json()["proposal"]["status"] == "rejected"
    assert target.read_text(encoding="utf-8") == "print('original')\n"
    assert second_action.status_code == 409
    assert second_action.json()["detail"]["code"] == "AI_CHANGE_PROPOSAL_NOT_PENDING"


def test_stale_or_foreign_proposals_cannot_be_applied(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    target = path / "main.py"
    target.write_text("print('original')\n", encoding="utf-8")
    conversation_id, proposal_id, _ = _create_proposal(client, project_id, provider_id, monkeypatch)
    endpoint = (
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
        f"/proposals/{proposal_id}/apply"
    )
    target.write_text("print('edited elsewhere')\n", encoding="utf-8")

    stale = client.post(endpoint, headers=_csrf(client))
    _login(client, OTHER_USERNAME)
    foreign = client.post(endpoint, headers=_csrf(client))

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "AI_CHANGE_PROPOSAL_STALE"
    assert target.read_text(encoding="utf-8") == "print('edited elsewhere')\n"
    assert foreign.status_code == 404


def _create_new_file_proposal(
    client: TestClient,
    project_id: int,
    provider_id: int,
    monkeypatch,
    *,
    path: str = "new_seo.tsx",
    content: str = "export const Seo = 1\n",
) -> tuple[str, str, dict[str, object]]:
    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    calls = 0

    async def stream(self, *_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield ToolCall("create-1", "create_project_file", {"path": path, "content": content})
        else:
            yield TextDelta("I proposed a new file.")
        yield TurnComplete("tool_calls" if calls == 1 else "completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Create a new file",
            },
            headers=_csrf(client),
        )
    )
    proposal_event = next(event for event in events if event["type"] == "proposal")
    return events[0]["conversation"]["id"], proposal_event["id"], proposal_event


def test_create_file_proposal_writes_only_after_apply(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    conversation_id, proposal_id, event = _create_new_file_proposal(
        client, project_id, provider_id, monkeypatch
    )
    target = path / "new_seo.tsx"

    assert not target.exists()
    assert event["path"] == "new_seo.tsx"
    assert "+export const Seo = 1" in event["diff"]

    response = client.post(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
        f"/proposals/{proposal_id}/apply",
        headers=_csrf(client),
    )

    assert response.status_code == 200
    assert response.json()["proposal"]["status"] == "applied"
    assert target.read_text(encoding="utf-8") == "export const Seo = 1\n"


def test_create_file_proposal_is_stale_when_file_appears(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    conversation_id, proposal_id, _ = _create_new_file_proposal(
        client, project_id, provider_id, monkeypatch
    )
    target = path / "new_seo.tsx"
    target.write_text("created elsewhere\n", encoding="utf-8")

    response = client.post(
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
        f"/proposals/{proposal_id}/apply",
        headers=_csrf(client),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "AI_CHANGE_PROPOSAL_STALE"
    assert target.read_text(encoding="utf-8") == "created elsewhere\n"


def test_create_file_proposal_rejects_existing_path(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    existing = path / "new_seo.tsx"
    existing.write_text("already here\n", encoding="utf-8")

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    tool_results: list[str] = []
    calls = 0

    async def stream(self, _client, _api_key, _model, _system, messages, _tools):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield ToolCall(
                "create-1", "create_project_file", {"path": "new_seo.tsx", "content": "x"}
            )
        else:
            tool_results.extend(message.content for message in messages if message.role == "tool")
            yield TextDelta("That file already exists.")
        yield TurnComplete("tool_calls" if calls == 1 else "completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    events = _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={
                "provider_id": provider_id,
                "model_id": "gpt-test",
                "message": "Create a new file",
            },
            headers=_csrf(client),
        )
    )

    assert all(event["type"] != "proposal" for event in events)
    assert tool_results and "FILE_ALREADY_EXISTS" in tool_results[0]
    assert existing.read_text(encoding="utf-8") == "already here\n"


def _run_tool_flow(
    client: TestClient,
    project_id: int,
    provider_id: int,
    monkeypatch,
    name: str,
    arguments: dict[str, object],
    *,
    permission: str | None = None,
    captured: list[str] | None = None,
) -> list[dict[str, object]]:
    if permission is not None:
        client.put(
            f"/api/v1/projects/{project_id}/ai-chat/command-permission",
            json={"mode": permission},
            headers=_csrf(client),
        )

    async def list_models(self, _client: AsyncClient, _api_key: str) -> list[ProviderModel]:
        return [ProviderModel("gpt-test", "GPT Test")]

    calls = 0

    async def stream(self, _client, _api_key, _model, _system, messages, _tools):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield ToolCall("call-1", name, arguments)
        else:
            if captured is not None:
                captured.extend(message.content for message in messages if message.role == "tool")
            yield TextDelta("done")
        yield TurnComplete("tool_calls" if calls == 1 else "completed")

    monkeypatch.setattr(OpenAIAdapter, "list_models", list_models)
    monkeypatch.setattr(OpenAIAdapter, "stream", stream)
    return _events(
        client.post(
            f"/api/v1/projects/{project_id}/ai-chat/messages/stream",
            json={"provider_id": provider_id, "model_id": "gpt-test", "message": "do it"},
            headers=_csrf(client),
        )
    )


def _apply_url(project_id: int, events: list[dict[str, object]], proposal_id: object) -> str:
    conversation_id = events[0]["conversation"]["id"]
    return (
        f"/api/v1/projects/{project_id}/ai-chat/conversations/{conversation_id}"
        f"/proposals/{proposal_id}/apply"
    )


def test_delete_file_proposal_is_removed_only_after_apply(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    target = path / "main.py"
    target.write_text("bye\n", encoding="utf-8")

    events = _run_tool_flow(
        client, project_id, provider_id, monkeypatch, "delete_project_file", {"path": "main.py"}
    )
    proposal = next(event for event in events if event["type"] == "proposal")

    assert proposal["change_type"] == "delete"
    assert proposal["status"] == "pending"
    assert "-bye" in proposal["diff"]
    assert target.exists()

    applied = client.post(_apply_url(project_id, events, proposal["id"]), headers=_csrf(client))
    assert applied.status_code == 200
    assert applied.json()["proposal"]["status"] == "applied"
    assert not target.exists()


def test_delete_directory_proposal_removes_the_tree(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    package = path / "pkg"
    package.mkdir()
    (package / "a.py").write_text("a", encoding="utf-8")
    (package / "b.py").write_text("b", encoding="utf-8")

    events = _run_tool_flow(
        client,
        project_id,
        provider_id,
        monkeypatch,
        "delete_project_directory",
        {"path": "pkg"},
    )
    proposal = next(event for event in events if event["type"] == "proposal")

    assert proposal["change_type"] == "delete_directory"
    assert "pkg/a.py" in proposal["diff"]
    assert package.exists()

    applied = client.post(_apply_url(project_id, events, proposal["id"]), headers=_csrf(client))
    assert applied.status_code == 200
    assert not package.exists()


def test_create_directory_proposal_makes_the_folder(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)

    events = _run_tool_flow(
        client,
        project_id,
        provider_id,
        monkeypatch,
        "create_project_directory",
        {"path": "assets"},
    )
    proposal = next(event for event in events if event["type"] == "proposal")

    assert proposal["change_type"] == "create_directory"
    assert not (path / "assets").exists()

    applied = client.post(_apply_url(project_id, events, proposal["id"]), headers=_csrf(client))
    assert applied.status_code == 200
    assert (path / "assets").is_dir()


def test_move_proposal_renames_the_entry(client: TestClient, projects_root, monkeypatch) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    (path / "a.py").write_text("payload\n", encoding="utf-8")

    events = _run_tool_flow(
        client,
        project_id,
        provider_id,
        monkeypatch,
        "move_project_entry",
        {"path": "a.py", "target_path": "b.py"},
    )
    proposal = next(event for event in events if event["type"] == "proposal")

    assert proposal["change_type"] == "move"
    assert proposal["target_path"] == "b.py"

    applied = client.post(_apply_url(project_id, events, proposal["id"]), headers=_csrf(client))
    assert applied.status_code == 200
    assert not (path / "a.py").exists()
    assert (path / "b.py").read_text(encoding="utf-8") == "payload\n"


def test_allow_all_permission_applies_create_immediately(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)

    events = _run_tool_flow(
        client,
        project_id,
        provider_id,
        monkeypatch,
        "create_project_file",
        {"path": "new.py", "content": "hello\n"},
        permission="allow_all",
    )
    proposal = next(event for event in events if event["type"] == "proposal")

    assert proposal["status"] == "applied"
    assert (path / "new.py").read_text(encoding="utf-8") == "hello\n"


def test_risky_permission_reviews_delete_but_applies_create(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    (path / "main.py").write_text("keep\n", encoding="utf-8")

    delete_events = _run_tool_flow(
        client,
        project_id,
        provider_id,
        monkeypatch,
        "delete_project_file",
        {"path": "main.py"},
        permission="risky",
    )
    assert next(e for e in delete_events if e["type"] == "proposal")["status"] == "pending"
    assert (path / "main.py").exists()

    create_events = _run_tool_flow(
        client,
        project_id,
        provider_id,
        monkeypatch,
        "create_project_file",
        {"path": "added.py", "content": "x"},
        permission="risky",
    )
    assert next(e for e in create_events if e["type"] == "proposal")["status"] == "applied"
    assert (path / "added.py").exists()


def test_list_project_files_tool_is_recursive(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    (path / "root.py").write_text("x", encoding="utf-8")
    package = path / "pkg"
    package.mkdir()
    (package / "nested.py").write_text("y", encoding="utf-8")

    captured: list[str] = []
    _run_tool_flow(
        client, project_id, provider_id, monkeypatch, "list_project_files", {}, captured=captured
    )

    assert captured and "pkg/nested.py" in captured[0]


def test_search_tool_reports_matching_lines(client: TestClient, projects_root, monkeypatch) -> None:
    _login(client)
    path = projects_root / "project"
    project_id = _create_project(client, path)
    provider_id = _create_provider(client)
    (path / "src.py").write_text("a needle here\n", encoding="utf-8")

    captured: list[str] = []
    _run_tool_flow(
        client,
        project_id,
        provider_id,
        monkeypatch,
        "search_project_files",
        {"query": "needle"},
        captured=captured,
    )

    assert captured and "needle" in captured[0]


def test_proposal_write_does_not_overwrite_concurrent_editor_save(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "main.py"
    original_content = "original"
    target.write_text(original_content, encoding="utf-8")
    monkeypatch.setattr(
        project_service,
        "_resolve_project_file",
        lambda _db, _owner, _project_id, _path: (tmp_path, target),
    )
    proposal_write_entered = Event()
    allow_proposal_write = Event()
    editor_write_started = Event()
    editor_write_entered = Event()
    write_resolved_file = project_service._write_resolved_file

    def pause_proposal_write(root: Path, path: Path, content: str):
        if content == "proposal":
            proposal_write_entered.set()
            if not allow_proposal_write.wait(timeout=2):
                raise TimeoutError("proposal write was not released")
        else:
            editor_write_entered.set()
        return write_resolved_file(root, path, content)

    monkeypatch.setattr(project_service, "_write_resolved_file", pause_proposal_write)

    def write_editor_save():
        editor_write_started.set()
        return project_service.write_file(None, None, 1, "main.py", "editor save")

    with ThreadPoolExecutor(max_workers=2) as executor:
        proposal_write = executor.submit(
            project_service.write_file_if_hash_matches,
            None,
            None,
            1,
            "main.py",
            hashlib.sha256(original_content.encode("utf-8")).hexdigest(),
            "proposal",
        )
        assert proposal_write_entered.wait(timeout=1)
        editor_write = executor.submit(write_editor_save)
        try:
            assert editor_write_started.wait(timeout=1)
            assert not editor_write_entered.wait(timeout=0.1)
        finally:
            allow_proposal_write.set()

        assert proposal_write.result(timeout=1) is True
        editor_write.result(timeout=1)

    assert target.read_text(encoding="utf-8") == "editor save"
