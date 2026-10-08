import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.modules.git.service import parse_status
from tests.conftest import LOCAL_URL, OTHER_USERNAME, PROJECTS_URL, _csrf, _login


def _error_code(response) -> str:
    return response.json()["detail"]["code"]


def _register_local(client: TestClient, path: Path) -> dict:
    response = client.post(LOCAL_URL, json={"path": str(path)}, headers=_csrf(client))
    assert response.status_code == 201, response.text
    return response.json()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "tracked.txt").write_text("hello\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-qm", "init")


def test_parse_status_classifies_changes() -> None:
    output = (
        "# branch.oid abc\0"
        "# branch.head main\0"
        "# branch.upstream origin/main\0"
        "# branch.ab +2 -1\0"
        "1 .M N... 100644 100644 100644 a a tracked.txt\0"
        "1 M. N... 100644 100644 100644 b b staged.txt\0"
        "2 R. N... 100644 100644 100644 c c R100 new.txt\0old.txt\0"
        "? untracked.txt\0"
        "u UU N... 100644 100644 100644 100644 a a a conflict.txt\0"
    )

    result = parse_status(output)

    assert result.branch == "main"
    assert result.upstream == "origin/main"
    assert result.ahead == 2
    assert result.behind == 1
    assert [change.path for change in result.unstaged] == ["tracked.txt"]
    assert [change.path for change in result.staged] == ["staged.txt", "new.txt"]
    assert result.staged[1].orig_path == "old.txt"
    assert result.untracked == ["untracked.txt"]
    assert result.conflicted == ["conflict.txt"]


def test_parse_status_without_upstream() -> None:
    result = parse_status("# branch.head master\0")
    assert result.branch == "master"
    assert result.upstream is None
    assert result.ahead == 0
    assert result.behind == 0


def test_git_status_requires_auth(client: TestClient) -> None:
    assert client.get(f"{PROJECTS_URL}/1/git/status").status_code == 401


def test_git_status_reports_changes(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    (repo / "tracked.txt").write_text("hello\nworld\n")
    (repo / "staged.txt").write_text("staged\n")
    _git(repo, "add", "staged.txt")
    (repo / "untracked.txt").write_text("new\n")

    response = client.get(f"{PROJECTS_URL}/{project_id}/git/status")

    assert response.status_code == 200
    body = response.json()
    assert body["branch"] == "main"
    assert [change["path"] for change in body["unstaged"]] == ["tracked.txt"]
    assert [change["path"] for change in body["staged"]] == ["staged.txt"]
    assert body["untracked"] == ["untracked.txt"]
    assert body["conflicted"] == []


def test_git_status_not_a_repository(client: TestClient, projects_root) -> None:
    _login(client)
    folder = projects_root / "plain"
    folder.mkdir()
    project_id = _register_local(client, folder)["id"]

    response = client.get(f"{PROJECTS_URL}/{project_id}/git/status")

    assert response.status_code == 400
    assert _error_code(response) == "GIT_NOT_A_REPOSITORY"


def test_git_status_scoped_to_owner(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    client.cookies.clear()
    _login(client, username=OTHER_USERNAME)

    response = client.get(f"{PROJECTS_URL}/{project_id}/git/status")
    assert response.status_code == 404
    assert _error_code(response) == "PROJECT_NOT_FOUND"


def test_git_status_missing_project(client: TestClient) -> None:
    _login(client)
    response = client.get(f"{PROJECTS_URL}/9999/git/status")
    assert response.status_code == 404
    assert _error_code(response) == "PROJECT_NOT_FOUND"


def test_git_status_command_failure(client: TestClient, projects_root, monkeypatch) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    def failing_run(*args, **kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr("app.modules.git.service.subprocess.run", failing_run)

    response = client.get(f"{PROJECTS_URL}/{project_id}/git/status")
    assert response.status_code == 500
    assert _error_code(response) == "GIT_COMMAND_FAILED"
