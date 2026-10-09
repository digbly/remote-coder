from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.modules.projects import service
from tests.conftest import (
    BROWSE_URL,
    GITHUB_URL,
    LOCAL_URL,
    OTHER_USERNAME,
    PROJECTS_URL,
    _csrf,
    _login,
)


def _error_code(response) -> str:
    return response.json()["detail"]["code"]


def _register_local(client: TestClient, path: Path, **extra) -> dict:
    response = client.post(LOCAL_URL, json={"path": str(path), **extra}, headers=_csrf(client))
    assert response.status_code == 201, response.text
    return response.json()


def test_projects_require_auth(client: TestClient) -> None:
    assert client.get(PROJECTS_URL).status_code == 401


def test_create_local_project(client: TestClient, projects_root) -> None:
    _login(client)
    folder = projects_root / "myrepo"
    folder.mkdir()

    response = client.post(LOCAL_URL, json={"path": str(folder)}, headers=_csrf(client))

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "myrepo"
    assert body["source"] == "local"
    assert body["remote_url"] is None
    assert body["path"] == str(folder.resolve())


def test_create_local_project_with_custom_name(client: TestClient, projects_root) -> None:
    _login(client)
    folder = projects_root / "myrepo"
    folder.mkdir()

    body = client.post(
        LOCAL_URL,
        json={"path": str(folder), "name": "custom"},
        headers=_csrf(client),
    ).json()
    assert body["name"] == "custom"


def test_create_local_project_outside_root(client: TestClient, tmp_path) -> None:
    _login(client)
    outside = tmp_path / "outside"
    outside.mkdir()

    response = client.post(LOCAL_URL, json={"path": str(outside)}, headers=_csrf(client))

    assert response.status_code == 201
    assert response.json()["path"] == str(outside.resolve())


def test_create_local_project_missing_path(client: TestClient, projects_root) -> None:
    _login(client)
    response = client.post(
        LOCAL_URL,
        json={"path": str(projects_root / "nope")},
        headers=_csrf(client),
    )
    assert response.status_code == 400
    assert _error_code(response) == "PROJECT_PATH_INVALID"


def test_create_local_project_requires_csrf(client: TestClient, projects_root) -> None:
    _login(client)
    folder = projects_root / "myrepo"
    folder.mkdir()
    response = client.post(LOCAL_URL, json={"path": str(folder)})
    assert response.status_code == 403
    assert _error_code(response) == "CSRF_INVALID"


def test_create_local_project_duplicate_path(client: TestClient, projects_root) -> None:
    _login(client)
    folder = projects_root / "myrepo"
    folder.mkdir()
    _register_local(client, folder)

    response = client.post(LOCAL_URL, json={"path": str(folder)}, headers=_csrf(client))
    assert response.status_code == 409
    assert _error_code(response) == "PROJECT_PATH_EXISTS"


def test_create_local_project_duplicate_name(client: TestClient, projects_root) -> None:
    _login(client)
    for name in ("a", "b"):
        (projects_root / name).mkdir()
    _register_local(client, projects_root / "a", name="same")

    response = client.post(
        LOCAL_URL,
        json={"path": str(projects_root / "b"), "name": "same"},
        headers=_csrf(client),
    )
    assert response.status_code == 409
    assert _error_code(response) == "PROJECT_NAME_EXISTS"


def test_create_local_project_derives_unique_name(client: TestClient, projects_root) -> None:
    _login(client)
    for parent in ("x", "y"):
        (projects_root / parent / "repo").mkdir(parents=True)

    first = _register_local(client, projects_root / "x" / "repo")
    second = _register_local(client, projects_root / "y" / "repo")

    assert first["name"] == "repo"
    assert second["name"] == "repo-2"


def test_create_github_project_invalid_url(client: TestClient) -> None:
    _login(client)
    response = client.post(
        GITHUB_URL,
        json={"repo_url": "https://gitlab.com/owner/repo"},
        headers=_csrf(client),
    )
    assert response.status_code == 400
    assert _error_code(response) == "INVALID_GITHUB_URL"


def test_create_project_rejects_unsafe_name(client: TestClient) -> None:
    _login(client)
    response = client.post(
        GITHUB_URL,
        json={"repo_url": "https://github.com/owner/repo", "name": "../../evil"},
        headers=_csrf(client),
    )
    assert response.status_code == 422
    assert _error_code(response) == "VALIDATION_ERROR"


def test_create_github_project_success(client: TestClient, projects_root, monkeypatch) -> None:
    _login(client)
    captured: dict = {}

    def fake_clone(remote_url, destination, branch, token, settings):
        captured.update(remote_url=remote_url, destination=destination, branch=branch, token=token)
        destination.mkdir(parents=True)

    monkeypatch.setattr(service, "_clone_repository", fake_clone)

    response = client.post(
        GITHUB_URL,
        json={"repo_url": "https://github.com/owner/repo.git", "token": "abc"},
        headers=_csrf(client),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "github"
    assert body["remote_url"] == "https://github.com/owner/repo.git"
    assert body["name"] == "repo"
    assert Path(body["path"]).is_dir()
    assert captured["remote_url"] == "https://github.com/owner/repo.git"
    assert captured["token"] == "abc"
    assert captured["destination"].is_relative_to(projects_root)


def test_create_github_project_clone_failure(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)

    def failing_run(command, **kwargs):
        Path(command[-1]).mkdir(parents=True)
        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(service.subprocess, "run", failing_run)

    response = client.post(
        GITHUB_URL,
        json={"repo_url": "git@github.com:owner/repo.git"},
        headers=_csrf(client),
    )

    assert response.status_code == 400
    assert _error_code(response) == "PROJECT_CLONE_FAILED"
    assert not (projects_root / "1" / "repo").exists()
    assert list((projects_root / "1").glob(".repo.cloning-*")) == []


def test_clone_repository_keeps_token_out_of_argv(monkeypatch) -> None:
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(service.subprocess, "run", fake_run)

    service._clone_repository(
        "https://github.com/owner/repo.git",
        Path("/tmp/repo"),
        None,
        "secret-token",
        Settings(),
    )

    assert "secret-token" not in " ".join(captured["command"])
    assert captured["env"]["GIT_CONFIG_VALUE_0"] == "Authorization: Bearer secret-token"
    assert captured["env"]["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_list_projects_scoped_to_owner(client: TestClient, projects_root) -> None:
    _login(client)
    folder = projects_root / "myrepo"
    folder.mkdir()
    _register_local(client, folder)

    assert len(client.get(PROJECTS_URL).json()) == 1

    client.cookies.clear()
    _login(client, username=OTHER_USERNAME)
    assert client.get(PROJECTS_URL).json() == []


def test_list_projects_paginates(client: TestClient, projects_root) -> None:
    _login(client)
    for index in range(3):
        folder = projects_root / f"repo{index}"
        folder.mkdir()
        _register_local(client, folder)

    assert len(client.get(PROJECTS_URL, params={"limit": 2}).json()) == 2
    assert len(client.get(PROJECTS_URL, params={"limit": 2, "offset": 2}).json()) == 1
    assert client.get(PROJECTS_URL, params={"limit": 0}).status_code == 422


def test_read_other_users_project_returns_404(client: TestClient, projects_root) -> None:
    _login(client)
    folder = projects_root / "myrepo"
    folder.mkdir()
    project_id = _register_local(client, folder)["id"]

    client.cookies.clear()
    _login(client, username=OTHER_USERNAME)
    response = client.get(f"{PROJECTS_URL}/{project_id}")
    assert response.status_code == 404
    assert _error_code(response) == "PROJECT_NOT_FOUND"


def test_delete_project(client: TestClient, projects_root) -> None:
    _login(client)
    folder = projects_root / "myrepo"
    folder.mkdir()
    project_id = _register_local(client, folder)["id"]

    assert client.delete(f"{PROJECTS_URL}/{project_id}").status_code == 403
    assert client.delete(f"{PROJECTS_URL}/{project_id}", headers=_csrf(client)).status_code == 204
    assert client.get(f"{PROJECTS_URL}/{project_id}").status_code == 404
    assert folder.is_dir()


def test_delete_github_project_removes_clone(client: TestClient, monkeypatch) -> None:
    _login(client)

    def fake_clone(remote_url, destination, branch, token, settings):
        destination.mkdir(parents=True)

    monkeypatch.setattr(service, "_clone_repository", fake_clone)

    body = client.post(
        GITHUB_URL,
        json={"repo_url": "https://github.com/owner/repo"},
        headers=_csrf(client),
    ).json()
    clone_dir = Path(body["path"])
    assert clone_dir.is_dir()

    response = client.delete(f"{PROJECTS_URL}/{body['id']}", headers=_csrf(client))
    assert response.status_code == 204
    assert not clone_dir.exists()


def test_browse_requires_auth(client: TestClient) -> None:
    assert client.get(BROWSE_URL).status_code == 401


def test_browse_defaults_to_home(
    client: TestClient, monkeypatch, tmp_path
) -> None:
    _login(client)
    home = tmp_path / "home"
    home.mkdir()
    (home / "proj").mkdir()
    (home / "afile.txt").write_text("x")
    monkeypatch.setenv("HOME", str(home))

    body = client.get(BROWSE_URL).json()

    assert body["root"] == str(home.resolve())
    assert body["path"] == str(home.resolve())
    assert [entry["name"] for entry in body["directories"]] == ["proj"]


def test_browse_lists_any_directory(client: TestClient, projects_root) -> None:
    _login(client)
    for name in ("beta", "alpha"):
        (projects_root / name).mkdir()
    (projects_root / "afile.txt").write_text("x")

    body = client.get(BROWSE_URL, params={"path": str(projects_root)}).json()

    assert body["path"] == str(projects_root.resolve())
    assert body["parent"] == str(projects_root.parent.resolve())
    assert [entry["name"] for entry in body["directories"]] == ["alpha", "beta"]


def test_browse_navigates_subdirectory_and_parent(
    client: TestClient, projects_root
) -> None:
    _login(client)
    nested = projects_root / "alpha" / "nested"
    nested.mkdir(parents=True)
    (nested / "leaf").mkdir()

    body = client.get(BROWSE_URL, params={"path": str(nested)}).json()

    assert body["path"] == str(nested.resolve())
    assert body["parent"] == str((projects_root / "alpha").resolve())
    assert [entry["name"] for entry in body["directories"]] == ["leaf"]


def test_browse_rejects_missing_path(client: TestClient, tmp_path) -> None:
    _login(client)

    response = client.get(BROWSE_URL, params={"path": str(tmp_path / "nope")})

    assert response.status_code == 400
    assert _error_code(response) == "PROJECT_PATH_INVALID"


def test_openapi_documents_projects_paths(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert GITHUB_URL in paths
    assert LOCAL_URL in paths
    responses = paths[GITHUB_URL]["post"]["responses"]
    for status_code in ("400", "401", "403", "409", "422"):
        schema = responses[status_code]["content"]["application/json"]["schema"]
        assert schema["$ref"].endswith("/ErrorResponse")


def test_project_files_lists_tree(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.py").write_text("x")
    (repo / "README.md").write_text("x")
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text("x")
    project_id = _register_local(client, repo)["id"]

    response = client.get(f"{PROJECTS_URL}/{project_id}/files")

    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is False
    assert [entry["name"] for entry in body["entries"]] == ["src", "README.md"]
    directory = body["entries"][0]
    assert directory["type"] == "directory"
    assert directory["path"] == "src"
    assert [child["name"] for child in directory["children"]] == ["main.py"]


def test_project_files_requires_auth(client: TestClient) -> None:
    assert client.get(f"{PROJECTS_URL}/1/files").status_code == 401


def test_project_files_scoped_to_owner(client: TestClient, projects_root) -> None:
    _login(client)
    folder = projects_root / "repo"
    folder.mkdir()
    (folder / "a.txt").write_text("x")
    project_id = _register_local(client, folder)["id"]

    client.cookies.clear()
    _login(client, username=OTHER_USERNAME)

    response = client.get(f"{PROJECTS_URL}/{project_id}/files")
    assert response.status_code == 404
    assert _error_code(response) == "PROJECT_NOT_FOUND"
