import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.modules.agent_sessions import service as sessions_service
from app.modules.agents.catalog import registry
from app.modules.agents.service import valid_session_id
from app.modules.agents.sessions import UNTITLED_SESSION, OpencodeSessionSource
from app.modules.ai_chat.schemas import ConversationRead
from tests.conftest import LOCAL_URL, PROJECTS_URL, _csrf, _login

SESSIONS_URL = f"{PROJECTS_URL}/{{project_id}}/agent-sessions"


def _write_opencode_db(database: Path, rows: list[tuple[str, str, str, int, int | None]]) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE session ("
        "id TEXT PRIMARY KEY, title TEXT, directory TEXT, "
        "time_updated INTEGER, time_archived INTEGER)"
    )
    connection.executemany("INSERT INTO session VALUES (?, ?, ?, ?, ?)", rows)
    connection.commit()
    connection.close()


def _register_local(client: TestClient, path: Path) -> dict:
    response = client.post(LOCAL_URL, json={"path": str(path)}, headers=_csrf(client))
    assert response.status_code == 201, response.text
    return response.json()


def test_opencode_source_matches_directory_and_skips_archived(tmp_path: Path) -> None:
    data_dir = tmp_path / "opencode"
    directory = tmp_path / "project"
    directory.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    _write_opencode_db(
        data_dir / "opencode.db",
        [
            ("ses_1", "First task", str(directory), 2_000, None),
            ("ses_2", "Elsewhere", str(other), 3_000, None),
            ("ses_3", "  ", str(directory), 1_000, None),
            ("ses_4", "Archived", str(directory), 5_000, 4_000),
        ],
    )

    sessions = OpencodeSessionSource(data_dir).list_sessions(directory, limit=10)

    assert [session.id for session in sessions] == ["ses_1", "ses_3"]
    assert sessions[0].title == "First task"
    assert sessions[1].title == UNTITLED_SESSION


def test_opencode_source_without_database_is_empty(tmp_path: Path) -> None:
    source = OpencodeSessionSource(tmp_path / "missing")
    assert source.list_sessions(tmp_path, limit=10) == []


def test_valid_session_id_accepts_agent_ids_and_rejects_shell_metacharacters() -> None:
    assert valid_session_id("ses_ed4cbe8acffenPv7zxEV0xTZhb")
    assert valid_session_id("abc-123.4:5")
    assert not valid_session_id("")
    assert not valid_session_id("has space")
    assert not valid_session_id("x; rm -rf /")
    assert not valid_session_id("x" * 129)


def test_build_resume_launch_for_opencode_and_unsupported_agent() -> None:
    opencode = registry.get("opencode")
    assert opencode.build_resume_launch("opencode", "--model fast", "ses_1") == (
        "opencode --model fast --session ses_1"
    )
    assert opencode.build_resume_launch("opencode", "", None) is None

    aider = registry.get("aider")
    assert aider.build_resume_launch("aider", "", "ses_1") is None


def test_agent_sessions_requires_authentication(client: TestClient) -> None:
    assert client.get(SESSIONS_URL.format(project_id=1)).status_code == 401


def test_agent_sessions_unknown_project(client: TestClient) -> None:
    _login(client)
    assert client.get(SESSIONS_URL.format(project_id=9999)).status_code == 404


def test_agent_sessions_lists_cli_and_chat(
    client: TestClient, projects_root: Path, tmp_path: Path, monkeypatch
) -> None:
    _login(client)
    project_dir = projects_root / "demo"
    project_dir.mkdir()
    project = _register_local(client, project_dir)

    data_dir = tmp_path / "opencode"
    _write_opencode_db(
        data_dir / "opencode.db",
        [("ses_abc", "Refactor browser tab", str(project_dir.resolve()), 1_700_000_000_000, None)],
    )
    settings = app.dependency_overrides[get_settings]()
    settings.opencode_data_dir = str(data_dir)

    now = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(
        sessions_service.chat_service,
        "list_conversations",
        lambda db, user, project_id: [
            ConversationRead(
                id="conv-1",
                project_id=project["id"],
                provider_id=None,
                model_id="gpt-test",
                title="Chat about tabs",
                created_at=now,
                updated_at=now,
            )
        ],
    )

    response = client.get(SESSIONS_URL.format(project_id=project["id"]))

    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert {session["source"] for session in sessions} == {"chat", "cli"}
    assert sessions[0]["source"] == "chat"
    cli = next(session for session in sessions if session["source"] == "cli")
    assert cli["agent_id"] == "opencode"
    assert cli["agent_label"] == "OpenCode"
    assert cli["title"] == "Refactor browser tab"
    assert cli["id"] == "ses_abc"
