import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.modules.ai_chat import approvals
from app.modules.ai_chat.commands import (
    command_needs_approval,
    execute_project_command,
    is_read_only_command,
)
from app.modules.ai_chat.schemas import CommandPermission
from tests.conftest import LOCAL_URL, OTHER_USERNAME, _csrf, _login


def _create_project(client: TestClient, path: Path) -> int:
    path.mkdir()
    response = client.post(LOCAL_URL, json={"path": str(path)}, headers=_csrf(client))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_command_permission_is_persisted_per_user(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "alice")
    url = f"/api/v1/projects/{project_id}/ai-chat/command-permission"

    assert client.get(url).json() == {"mode": "manual"}
    response = client.put(url, json={"mode": "risky"}, headers=_csrf(client))
    assert response.status_code == 200
    assert response.json() == {"mode": "risky"}
    assert client.get(url).json() == {"mode": "risky"}
    another_project_id = _create_project(client, projects_root / "alice-second")
    assert (
        client.get(
            f"/api/v1/projects/{another_project_id}/ai-chat/command-permission"
        ).json()
        == {"mode": "risky"}
    )
    response = client.put(url, json={"mode": "allow_all"}, headers=_csrf(client))
    assert response.status_code == 200
    assert (
        client.get(
            f"/api/v1/projects/{another_project_id}/ai-chat/command-permission"
        ).json()
        == {"mode": "allow_all"}
    )

    assert (
        client.put(url, json={"mode": "invalid"}, headers=_csrf(client)).status_code
        == 422
    )

    client.cookies.clear()
    _login(client, OTHER_USERNAME)
    other_project_id = _create_project(client, projects_root / "bob")
    other_url = f"/api/v1/projects/{other_project_id}/ai-chat/command-permission"
    assert client.get(other_url).json() == {"mode": "manual"}


def test_risky_classifier_only_accepts_simple_read_only_commands() -> None:
    assert is_read_only_command("pwd")
    assert is_read_only_command("ls -la src")
    assert not is_read_only_command("git status --short")
    assert not is_read_only_command("rm -rf src")
    assert not is_read_only_command("git clean -fd")
    assert not is_read_only_command("ls; rm -rf src")
    assert not is_read_only_command("cat /etc/passwd")
    assert not is_read_only_command("ls --output=/tmp/result")
    assert not is_read_only_command("ls $(echo src)")

    assert not command_needs_approval("pwd", CommandPermission.RISKY)
    assert command_needs_approval("rm file", CommandPermission.RISKY)
    assert command_needs_approval("pwd", CommandPermission.MANUAL)
    assert not command_needs_approval("rm file", CommandPermission.ALLOW_ALL)


def test_command_runner_uses_project_directory_and_reports_exit_code(tmp_path: Path) -> None:
    result = asyncio.run(execute_project_command(tmp_path, "pwd"))
    payload = json.loads(result)

    assert payload["output"].strip() == str(tmp_path)
    assert payload["exit_code"] == 0
    assert payload["truncated"] is False


def test_command_runner_rejects_null_bytes(tmp_path: Path) -> None:
    result = asyncio.run(execute_project_command(tmp_path, "pwd\x00"))

    assert json.loads(result) == {"error": "invalid_command"}


def test_command_runner_does_not_inherit_application_secrets(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    result = asyncio.run(execute_project_command(tmp_path, "printf '%s' \"$SECRET_KEY\""))

    assert json.loads(result)["output"] == ""


def test_command_runner_times_out(monkeypatch, tmp_path: Path) -> None:
    from app.modules.ai_chat import commands

    monkeypatch.setattr(commands, "COMMAND_TIMEOUT_SECONDS", 0.01)
    result = asyncio.run(execute_project_command(tmp_path, "sleep 1"))

    assert json.loads(result)["error"] == "command_timed_out"


def test_command_runner_caps_output(monkeypatch, tmp_path: Path) -> None:
    from app.modules.ai_chat import commands

    monkeypatch.setattr(commands, "COMMAND_OUTPUT_BYTES", 3)
    result = asyncio.run(execute_project_command(tmp_path, "printf 'abcdef'"))
    payload = json.loads(result)

    assert payload["output"] == "abc"
    assert payload["truncated"] is True


def test_approval_is_bound_to_user_and_project() -> None:
    async def exercise() -> None:
        pending = approvals.create_approval(10, 20, "pwd")
        waiting = asyncio.create_task(approvals.wait_for_decision(pending))
        await asyncio.sleep(0)

        assert not approvals.resolve_approval(pending.approval_id, 11, 20, True)
        assert not approvals.resolve_approval(pending.approval_id, 10, 21, True)
        assert approvals.resolve_approval(pending.approval_id, 10, 20, True)
        assert await waiting
        assert not approvals.resolve_approval(pending.approval_id, 10, 20, True)

    asyncio.run(exercise())


def test_approval_route_authorizes_project_and_resolves_pending_request(
    client: TestClient, projects_root: Path
) -> None:
    _login(client)
    project_id = _create_project(client, projects_root / "approval-project")
    pending = approvals.create_approval(1, project_id, "pwd")
    url = f"/api/v1/projects/{project_id}/ai-chat/commands/{pending.approval_id}"

    wrong_project = client.post(
        f"/api/v1/projects/{project_id + 999}/ai-chat/commands/{pending.approval_id}",
        json={"approved": True},
        headers=_csrf(client),
    )
    assert wrong_project.status_code == 404
    assert not pending.decision.done()

    response = client.post(url, json={"approved": False}, headers=_csrf(client))
    try:
        assert response.status_code == 204, response.text
        assert pending.decision.result() is False
    finally:
        approvals.discard_approval(pending)
