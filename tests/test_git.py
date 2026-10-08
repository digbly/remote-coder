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


def _staged_paths(client: TestClient, project_id: int) -> list[str]:
    body = client.get(f"{PROJECTS_URL}/{project_id}/git/status").json()
    return [change["path"] for change in body["staged"]]


def test_stage_and_unstage_paths(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]
    (repo / "tracked.txt").write_text("hello\nworld\n")

    staged = client.post(
        f"{PROJECTS_URL}/{project_id}/git/stage",
        json={"paths": ["tracked.txt"]},
        headers=_csrf(client),
    )
    assert staged.status_code == 200
    assert [change["path"] for change in staged.json()["staged"]] == ["tracked.txt"]

    unstaged = client.post(
        f"{PROJECTS_URL}/{project_id}/git/unstage",
        json={"paths": ["tracked.txt"]},
        headers=_csrf(client),
    )
    assert unstaged.status_code == 200
    assert unstaged.json()["staged"] == []
    assert [change["path"] for change in unstaged.json()["unstaged"]] == ["tracked.txt"]


def test_stage_rejects_invalid_path(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/stage",
        json={"paths": ["../outside.txt"]},
        headers=_csrf(client),
    )
    assert response.status_code == 400
    assert _error_code(response) == "GIT_INVALID_PATH"


def test_stage_requires_csrf(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/stage", json={"paths": ["tracked.txt"]}
    )
    assert response.status_code == 403
    assert _error_code(response) == "CSRF_INVALID"


def test_commit_requires_staged_changes(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/commit",
        json={"message": "nothing here"},
        headers=_csrf(client),
    )
    assert response.status_code == 400
    assert _error_code(response) == "GIT_NOTHING_TO_COMMIT"


def test_commit_creates_commit(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]
    (repo / "tracked.txt").write_text("hello\nworld\n")
    client.post(
        f"{PROJECTS_URL}/{project_id}/git/stage",
        json={"paths": ["tracked.txt"]},
        headers=_csrf(client),
    )

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/commit",
        json={"message": "update tracked"},
        headers=_csrf(client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["branch"] == "main"
    assert body["commit"]
    assert _staged_paths(client, project_id) == []
    subject = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert subject == "update tracked"


def test_pull_request_requires_github_remote(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/pull-request",
        json={"branch": "feature/x"},
        headers=_csrf(client),
    )
    assert response.status_code == 400
    assert _error_code(response) == "GIT_REMOTE_MISSING"


def test_pull_request_rejects_lookalike_remote(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    _git(repo, "remote", "add", "origin", "https://evil.example/github.com/repo.git")
    project_id = _register_local(client, repo)["id"]

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/pull-request",
        json={"branch": "feature/x"},
        headers=_csrf(client),
    )
    assert response.status_code == 400
    assert _error_code(response) == "GIT_REMOTE_MISSING"


def test_unstage_works_without_initial_commit(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "fresh"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    project_id = _register_local(client, repo)["id"]

    (repo / "new.txt").write_text("new\n")
    staged = client.post(
        f"{PROJECTS_URL}/{project_id}/git/stage",
        json={"paths": ["new.txt"]},
        headers=_csrf(client),
    )
    assert staged.status_code == 200
    assert [change["path"] for change in staged.json()["staged"]] == ["new.txt"]

    unstaged = client.post(
        f"{PROJECTS_URL}/{project_id}/git/unstage",
        json={"paths": ["new.txt"]},
        headers=_csrf(client),
    )
    assert unstaged.status_code == 200
    assert unstaged.json()["staged"] == []
    assert unstaged.json()["untracked"] == ["new.txt"]


def test_pull_request_creates_branch_and_pr(client: TestClient, projects_root, monkeypatch) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    _git(repo, "remote", "add", "origin", "https://github.com/example/myrepo.git")
    project_id = _register_local(client, repo)["id"]

    real_run = subprocess.run

    def fake_run(command, *args, **kwargs):
        if list(command[:2]) == ["git", "push"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] == "gh":
            return subprocess.CompletedProcess(
                command, 0, "https://github.com/example/myrepo/pull/1\n", ""
            )
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr("app.modules.git.service.subprocess.run", fake_run)

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/pull-request",
        json={"branch": "feature/x"},
        headers=_csrf(client),
    )

    assert response.status_code == 200
    assert response.json() == {
        "url": "https://github.com/example/myrepo/pull/1",
        "branch": "feature/x",
        "base": "main",
    }
    current = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert current == "feature/x"
