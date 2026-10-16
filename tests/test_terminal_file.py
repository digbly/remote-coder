import base64
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import LOCAL_URL, OTHER_USERNAME, _csrf, _login

TEXT_BYTES = b"hello from a dropped file\n"


def _file_url(project_id: int) -> str:
    return f"/api/v1/projects/{project_id}/terminal/file"


def _register_project(client: TestClient, projects_root: Path) -> tuple[int, Path]:
    folder = projects_root / "file-repo"
    folder.mkdir()
    response = client.post(LOCAL_URL, json={"path": str(folder)}, headers=_csrf(client))
    assert response.status_code == 201, response.text
    return response.json()["id"], folder


def _payload(
    data: bytes = TEXT_BYTES,
    name: str = "notes.txt",
) -> dict[str, str]:
    return {
        "name": name,
        "data": base64.b64encode(data).decode("ascii"),
    }


def test_upload_requires_authentication(client: TestClient, projects_root: Path) -> None:
    assert client.post(_file_url(1), json=_payload()).status_code == 401


def test_upload_saves_file_in_project(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, folder = _register_project(client, projects_root)

    response = client.post(_file_url(project_id), json=_payload(), headers=_csrf(client))

    assert response.status_code == 201, response.text
    saved = Path(response.json()["path"])
    assert saved.is_relative_to(folder)
    assert saved.parent == folder / ".remote-coder" / "uploads"
    assert saved.name.endswith("notes.txt")
    assert saved.read_bytes() == TEXT_BYTES


def test_upload_sanitizes_traversal_in_name(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, folder = _register_project(client, projects_root)

    response = client.post(
        _file_url(project_id), json=_payload(name="../../evil.sh"), headers=_csrf(client)
    )

    assert response.status_code == 201, response.text
    saved = Path(response.json()["path"])
    assert saved.parent == folder / ".remote-coder" / "uploads"
    assert ".." not in saved.name
    assert "/" not in saved.name


def test_upload_adds_gitignore_entry(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, folder = _register_project(client, projects_root)

    client.post(_file_url(project_id), json=_payload(), headers=_csrf(client))
    client.post(_file_url(project_id), json=_payload(), headers=_csrf(client))

    lines = (folder / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(".remote-coder/") == 1


def test_upload_rejects_invalid_base64(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, _ = _register_project(client, projects_root)

    response = client.post(
        _file_url(project_id),
        json={"name": "notes.txt", "data": "not base64!!!"},
        headers=_csrf(client),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TERMINAL_FILE_INVALID"


def test_upload_scoped_to_project_owner(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, _ = _register_project(client, projects_root)
    client.cookies.clear()

    _login(client, username=OTHER_USERNAME)
    response = client.post(_file_url(project_id), json=_payload(), headers=_csrf(client))

    assert response.status_code == 404
