import base64
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import LOCAL_URL, OTHER_USERNAME, _csrf, _login

PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


def _image_url(project_id: int) -> str:
    return f"/api/v1/projects/{project_id}/terminal/image"


def _register_project(client: TestClient, projects_root: Path) -> tuple[int, Path]:
    folder = projects_root / "image-repo"
    folder.mkdir()
    response = client.post(LOCAL_URL, json={"path": str(folder)}, headers=_csrf(client))
    assert response.status_code == 201, response.text
    return response.json()["id"], folder


def _payload(data: bytes = PNG_BYTES, media_type: str = "image/png") -> dict[str, str]:
    return {"media_type": media_type, "data": base64.b64encode(data).decode("ascii")}


def test_upload_requires_authentication(client: TestClient, projects_root: Path) -> None:
    assert client.post(_image_url(1), json=_payload()).status_code == 401


def test_upload_saves_image_in_project(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, folder = _register_project(client, projects_root)

    response = client.post(_image_url(project_id), json=_payload(), headers=_csrf(client))

    assert response.status_code == 201, response.text
    saved = Path(response.json()["path"])
    assert saved.is_relative_to(folder)
    assert saved.parent == folder / ".remote-coder" / "images"
    assert saved.read_bytes() == PNG_BYTES


def test_upload_adds_gitignore_entry(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, folder = _register_project(client, projects_root)

    client.post(_image_url(project_id), json=_payload(), headers=_csrf(client))
    client.post(_image_url(project_id), json=_payload(), headers=_csrf(client))

    lines = (folder / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(".remote-coder/") == 1


def test_upload_keeps_existing_gitignore(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, folder = _register_project(client, projects_root)
    (folder / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

    client.post(_image_url(project_id), json=_payload(), headers=_csrf(client))

    content = (folder / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in content
    assert ".remote-coder/" in content


def test_upload_rejects_unknown_media_type(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, _ = _register_project(client, projects_root)

    response = client.post(
        _image_url(project_id), json=_payload(media_type="text/plain"), headers=_csrf(client)
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TERMINAL_IMAGE_INVALID"


def test_upload_rejects_invalid_base64(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, _ = _register_project(client, projects_root)

    response = client.post(
        _image_url(project_id),
        json={"media_type": "image/png", "data": "not base64!!!"},
        headers=_csrf(client),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TERMINAL_IMAGE_INVALID"


def test_upload_scoped_to_project_owner(client: TestClient, projects_root: Path) -> None:
    _login(client)
    project_id, _ = _register_project(client, projects_root)
    client.cookies.clear()

    _login(client, username=OTHER_USERNAME)
    response = client.post(_image_url(project_id), json=_payload(), headers=_csrf(client))

    assert response.status_code == 404
