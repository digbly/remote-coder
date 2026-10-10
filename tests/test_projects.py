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


def test_create_github_project_rejects_legacy_token(client: TestClient) -> None:
    _login(client)
    response = client.post(
        GITHUB_URL,
        json={"repo_url": "https://github.com/owner/private-repo", "token": "legacy-token"},
        headers=_csrf(client),
    )

    assert response.status_code == 422
    assert _error_code(response) == "VALIDATION_ERROR"
    assert any(error["field"] == "token" for error in response.json()["detail"]["errors"])
    assert "legacy-token" not in response.text


def test_create_github_project_success(client: TestClient, projects_root, monkeypatch) -> None:
    _login(client)
    captured: dict = {}

    def fake_clone(repository, destination, branch, settings):
        captured.update(repository=repository, destination=destination, branch=branch)
        destination.mkdir(parents=True)

    monkeypatch.setattr(service, "_clone_repository", fake_clone)

    response = client.post(
        GITHUB_URL,
        json={"repo_url": "https://github.com/owner/repo.git"},
        headers=_csrf(client),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "github"
    assert body["remote_url"] == "https://github.com/owner/repo.git"
    assert body["name"] == "repo"
    assert Path(body["path"]).is_dir()
    assert captured["repository"] == "owner/repo"
    assert captured["destination"].is_relative_to(projects_root)


def test_create_github_project_clone_failure(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)

    def failing_run(command, **kwargs):
        Path(command[4]).mkdir(parents=True)
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


def test_clone_repository_uses_gh_cli_and_branch(monkeypatch, tmp_path) -> None:
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(service.subprocess, "run", fake_run)

    service._clone_repository(
        "owner/repo",
        tmp_path / "repo",
        "feature/test",
        Settings(),
    )

    assert captured["command"] == [
        "gh",
        "repo",
        "clone",
        "owner/repo",
        str(tmp_path / "repo"),
        "--",
        "--depth",
        "1",
        "--branch",
        "feature/test",
    ]
    assert captured["env"]["GH_PROMPT_DISABLED"] == "1"


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

    def fake_clone(repository, destination, branch, settings):
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
    assert "children" not in directory


def test_project_files_lists_subdirectory(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.py").write_text("x")
    (repo / "src" / "sub").mkdir()
    (repo / "src" / "sub" / "deep.py").write_text("x")
    project_id = _register_local(client, repo)["id"]

    response = client.get(f"{PROJECTS_URL}/{project_id}/files", params={"path": "src"})

    assert response.status_code == 200
    body = response.json()
    assert [entry["name"] for entry in body["entries"]] == ["sub", "main.py"]
    assert "children" not in body["entries"][0]


def test_project_files_rejects_path_escape(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "repo"
    repo.mkdir()
    project_id = _register_local(client, repo)["id"]

    response = client.get(f"{PROJECTS_URL}/{project_id}/files", params={"path": "../"})

    assert response.status_code == 400
    assert _error_code(response) == "FILE_PATH_INVALID"


def test_project_files_missing_directory(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "repo"
    repo.mkdir()
    project_id = _register_local(client, repo)["id"]

    response = client.get(f"{PROJECTS_URL}/{project_id}/files", params={"path": "nope"})

    assert response.status_code == 404
    assert _error_code(response) == "FILE_NOT_FOUND"


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


def _register_repo_with_file(client: TestClient, root: Path, name: str, content: str) -> int:
    repo = root / name
    repo.mkdir()
    (repo / "main.py").write_text(content)
    return _register_local(client, repo)["id"]


def test_project_file_reads_content(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _register_repo_with_file(client, projects_root, "repo", "print('hi')\n")

    response = client.get(f"{PROJECTS_URL}/{project_id}/file", params={"path": "main.py"})

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "main.py"
    assert body["content"] == "print('hi')\n"
    assert body["size"] == len(b"print('hi')\n")


def test_project_file_reads_nested_content(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("x = 1\n")
    project_id = _register_local(client, repo)["id"]

    response = client.get(f"{PROJECTS_URL}/{project_id}/file", params={"path": "src/app.py"})

    assert response.status_code == 200
    assert response.json()["content"] == "x = 1\n"


def test_project_file_read_requires_auth(client: TestClient) -> None:
    assert client.get(f"{PROJECTS_URL}/1/file", params={"path": "a.txt"}).status_code == 401


def test_project_file_read_missing_returns_404(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _register_repo_with_file(client, projects_root, "repo", "x")

    response = client.get(f"{PROJECTS_URL}/{project_id}/file", params={"path": "nope.py"})

    assert response.status_code == 404
    assert _error_code(response) == "FILE_NOT_FOUND"


def test_project_file_read_scoped_to_owner(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _register_repo_with_file(client, projects_root, "repo", "secret")

    client.cookies.clear()
    _login(client, username=OTHER_USERNAME)

    response = client.get(f"{PROJECTS_URL}/{project_id}/file", params={"path": "main.py"})
    assert response.status_code == 404
    assert _error_code(response) == "PROJECT_NOT_FOUND"


def test_project_file_read_rejects_git_directory(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "config").write_text("[remote]\n")
    project_id = _register_local(client, repo)["id"]

    response = client.get(f"{PROJECTS_URL}/{project_id}/file", params={"path": ".git/config"})

    assert response.status_code == 400
    assert _error_code(response) == "FILE_PATH_INVALID"


def test_project_file_read_rejects_traversal(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _register_repo_with_file(client, projects_root, "repo", "x")
    (projects_root / "outside.txt").write_text("nope")

    for path in ("../outside.txt", "/etc/passwd", "~/outside.txt"):
        response = client.get(f"{PROJECTS_URL}/{project_id}/file", params={"path": path})
        assert response.status_code == 400, path
        assert _error_code(response) == "FILE_PATH_INVALID"


def test_project_file_read_rejects_binary(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "repo"
    repo.mkdir()
    (repo / "blob.bin").write_bytes(b"\x00\x01\x02")
    project_id = _register_local(client, repo)["id"]

    response = client.get(f"{PROJECTS_URL}/{project_id}/file", params={"path": "blob.bin"})

    assert response.status_code == 400
    assert _error_code(response) == "FILE_BINARY"


def test_project_file_read_rejects_oversized(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "repo"
    repo.mkdir()
    (repo / "big.txt").write_text("a" * (service.MAX_FILE_BYTES + 1))
    project_id = _register_local(client, repo)["id"]

    response = client.get(f"{PROJECTS_URL}/{project_id}/file", params={"path": "big.txt"})

    assert response.status_code == 400
    assert _error_code(response) == "FILE_TOO_LARGE"


def test_project_file_writes_content(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("old\n")
    project_id = _register_local(client, repo)["id"]

    response = client.put(
        f"{PROJECTS_URL}/{project_id}/file",
        json={"path": "main.py", "content": "new\n"},
        headers=_csrf(client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "new\n"
    assert (repo / "main.py").read_text() == "new\n"


def test_project_file_write_requires_csrf(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _register_repo_with_file(client, projects_root, "repo", "old")

    response = client.put(
        f"{PROJECTS_URL}/{project_id}/file",
        json={"path": "main.py", "content": "new"},
    )

    assert response.status_code == 403
    assert _error_code(response) == "CSRF_INVALID"


def test_project_file_write_rejects_traversal(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _register_repo_with_file(client, projects_root, "repo", "x")

    response = client.put(
        f"{PROJECTS_URL}/{project_id}/file",
        json={"path": "../evil.txt", "content": "boom"},
        headers=_csrf(client),
    )

    assert response.status_code == 400
    assert _error_code(response) == "FILE_PATH_INVALID"
    assert not (projects_root / "evil.txt").exists()


def test_project_file_write_rejects_oversized(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _register_repo_with_file(client, projects_root, "repo", "x")

    response = client.put(
        f"{PROJECTS_URL}/{project_id}/file",
        json={"path": "main.py", "content": "a" * (service.MAX_FILE_BYTES + 1)},
        headers=_csrf(client),
    )

    assert response.status_code == 400
    assert _error_code(response) == "FILE_TOO_LARGE"


def _register_search_repo(client: TestClient, root: Path) -> int:
    repo = root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.py").write_text("import os\n\nprint('Hello World')\n")
    (repo / "src" / "utils.py").write_text("def helper():\n    return 42\n")
    (repo / "README.md").write_text("# Project\nhello world\n")
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text("hello world\n")
    return _register_local(client, repo)["id"]


def test_project_search_names(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _register_search_repo(client, projects_root)

    response = client.get(
        f"{PROJECTS_URL}/{project_id}/search", params={"q": "main", "mode": "names"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["truncated"] is False
    assert [entry["path"] for entry in body["entries"]] == ["src/main.py"]
    assert body["entries"][0]["matches"] == []
    assert body["entries"][0]["spans"] == [{"start": 0, "end": 4}]


def test_project_search_names_is_case_insensitive_by_default(
    client: TestClient, projects_root
) -> None:
    _login(client)
    project_id = _register_search_repo(client, projects_root)

    body = client.get(
        f"{PROJECTS_URL}/{project_id}/search", params={"q": "MAIN", "mode": "names"}
    ).json()

    assert [entry["path"] for entry in body["entries"]] == ["src/main.py"]


def test_project_search_names_case_sensitive(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _register_search_repo(client, projects_root)

    body = client.get(
        f"{PROJECTS_URL}/{project_id}/search",
        params={"q": "MAIN", "mode": "names", "case_sensitive": "true"},
    ).json()

    assert body["entries"] == []


def test_project_search_names_respects_include_and_exclude(
    client: TestClient, projects_root
) -> None:
    _login(client)
    project_id = _register_search_repo(client, projects_root)

    included = client.get(
        f"{PROJECTS_URL}/{project_id}/search",
        params={"q": ".", "mode": "names", "include": "*.md"},
    ).json()
    assert [entry["path"] for entry in included["entries"]] == ["README.md"]

    excluded = client.get(
        f"{PROJECTS_URL}/{project_id}/search",
        params={"q": ".", "mode": "names", "exclude": "src/**"},
    ).json()
    assert [entry["path"] for entry in excluded["entries"]] == ["README.md"]


def test_project_search_contents_returns_line_matches(
    client: TestClient, projects_root
) -> None:
    _login(client)
    project_id = _register_search_repo(client, projects_root)

    response = client.get(
        f"{PROJECTS_URL}/{project_id}/search",
        params={"q": "hello world", "mode": "contents"},
    )

    assert response.status_code == 200
    body = response.json()
    paths = {entry["path"]: entry["matches"] for entry in body["entries"]}
    assert set(paths) == {"src/main.py", "README.md"}
    assert paths["README.md"] == [
        {"line": 2, "text": "hello world", "spans": [{"start": 0, "end": 11}]}
    ]
    assert paths["src/main.py"][0]["line"] == 3


def test_project_search_contents_skips_git_and_binary(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "repo"
    repo.mkdir()
    (repo / "binary.bin").write_bytes(b"match\x00here")
    (repo / "text.txt").write_text("a match here\n")
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text("match\n")
    project_id = _register_local(client, repo)["id"]

    body = client.get(
        f"{PROJECTS_URL}/{project_id}/search", params={"q": "match", "mode": "contents"}
    ).json()

    assert [entry["path"] for entry in body["entries"]] == ["text.txt"]


def test_project_search_contents_whole_word(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("cat category\n")
    project_id = _register_local(client, repo)["id"]

    body = client.get(
        f"{PROJECTS_URL}/{project_id}/search",
        params={"q": "cat", "mode": "contents", "whole_word": "true"},
    ).json()

    assert body["entries"][0]["matches"] == [
        {"line": 1, "text": "cat category", "spans": [{"start": 0, "end": 3}]}
    ]


def test_project_search_regex_and_invalid(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _register_search_repo(client, projects_root)

    valid = client.get(
        f"{PROJECTS_URL}/{project_id}/search",
        params={"q": "h.llo world", "mode": "contents", "regex": "true"},
    )
    assert valid.status_code == 200
    assert any(entry["path"] == "README.md" for entry in valid.json()["entries"])

    invalid = client.get(
        f"{PROJECTS_URL}/{project_id}/search",
        params={"q": "(unclosed", "mode": "contents", "regex": "true"},
    )
    assert invalid.status_code == 400
    assert _error_code(invalid) == "SEARCH_QUERY_INVALID"


def test_project_search_requires_auth(client: TestClient) -> None:
    assert client.get(f"{PROJECTS_URL}/1/search", params={"q": "x"}).status_code == 401


def test_project_search_scoped_to_owner(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _register_search_repo(client, projects_root)

    client.cookies.clear()
    _login(client, username=OTHER_USERNAME)

    response = client.get(f"{PROJECTS_URL}/{project_id}/search", params={"q": "main"})
    assert response.status_code == 404
    assert _error_code(response) == "PROJECT_NOT_FOUND"


def test_project_search_rejects_empty_query(client: TestClient, projects_root) -> None:
    _login(client)
    project_id = _register_search_repo(client, projects_root)

    response = client.get(f"{PROJECTS_URL}/{project_id}/search", params={"q": ""})

    assert response.status_code == 422
    assert _error_code(response) == "VALIDATION_ERROR"


def test_project_search_globstar_matches_nested_and_root(
    client: TestClient, projects_root
) -> None:
    _login(client)
    repo = projects_root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "deep.py").write_text("x\n")
    (repo / "root.py").write_text("x\n")
    (repo / "notes.md").write_text("x\n")
    project_id = _register_local(client, repo)["id"]

    included = client.get(
        f"{PROJECTS_URL}/{project_id}/search",
        params={"q": ".", "mode": "names", "include": "**/*.py"},
    ).json()
    assert sorted(entry["path"] for entry in included["entries"]) == [
        "root.py",
        "src/deep.py",
    ]

    excluded = client.get(
        f"{PROJECTS_URL}/{project_id}/search",
        params={"q": ".", "mode": "names", "exclude": "**/*.py"},
    ).json()
    assert [entry["path"] for entry in excluded["entries"]] == ["notes.md"]


def test_project_search_truncates_at_result_cap(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    monkeypatch.setattr(service, "MAX_SEARCH_RESULTS", 2)
    repo = projects_root / "repo"
    repo.mkdir()
    for index in range(5):
        (repo / f"file{index}.txt").write_text("hit\n")
    project_id = _register_local(client, repo)["id"]

    body = client.get(
        f"{PROJECTS_URL}/{project_id}/search", params={"q": "file", "mode": "names"}
    ).json()

    assert len(body["entries"]) == 2
    assert body["truncated"] is True


def test_project_search_ignores_heavy_directories_by_default(
    client: TestClient, projects_root
) -> None:
    _login(client)
    repo = projects_root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("needle\n")
    (repo / "node_modules" / "pkg").mkdir(parents=True)
    (repo / "node_modules" / "pkg" / "index.js").write_text("needle\n")
    project_id = _register_local(client, repo)["id"]

    body = client.get(
        f"{PROJECTS_URL}/{project_id}/search", params={"q": "needle", "mode": "contents"}
    ).json()

    assert [entry["path"] for entry in body["entries"]] == ["src/app.py"]


def test_project_search_include_overrides_heavy_directory_ignore(
    client: TestClient, projects_root
) -> None:
    _login(client)
    repo = projects_root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("needle\n")
    (repo / "node_modules" / "pkg").mkdir(parents=True)
    (repo / "node_modules" / "pkg" / "index.js").write_text("needle\n")
    project_id = _register_local(client, repo)["id"]

    body = client.get(
        f"{PROJECTS_URL}/{project_id}/search",
        params={"q": "needle", "mode": "contents", "include": "node_modules/**"},
    ).json()

    assert [entry["path"] for entry in body["entries"]] == ["node_modules/pkg/index.js"]


def test_project_search_ignores_gitignored_directories(
    client: TestClient, projects_root
) -> None:
    _login(client)
    repo = projects_root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("needle\n")
    (repo / "generated").mkdir()
    (repo / "generated" / "out.py").write_text("needle\n")
    (repo / "vendor" / "lib").mkdir(parents=True)
    (repo / "vendor" / "lib" / "dep.py").write_text("needle\n")
    (repo / ".gitignore").write_text("generated/\nvendor/lib/\n*.log\n")
    project_id = _register_local(client, repo)["id"]

    body = client.get(
        f"{PROJECTS_URL}/{project_id}/search", params={"q": "needle", "mode": "contents"}
    ).json()

    assert [entry["path"] for entry in body["entries"]] == ["src/app.py"]


def test_project_search_gitignore_override_via_include(
    client: TestClient, projects_root
) -> None:
    _login(client)
    repo = projects_root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("needle\n")
    (repo / "generated").mkdir()
    (repo / "generated" / "out.py").write_text("needle\n")
    (repo / ".gitignore").write_text("generated/\n")
    project_id = _register_local(client, repo)["id"]

    body = client.get(
        f"{PROJECTS_URL}/{project_id}/search",
        params={"q": "needle", "mode": "contents", "include": "generated/**"},
    ).json()

    assert [entry["path"] for entry in body["entries"]] == ["generated/out.py"]
