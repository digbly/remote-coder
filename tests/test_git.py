import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.modules.git.service import (
    _COMMIT_MESSAGE_MAX_CHARS,
    _clean_commit_message,
    parse_status,
    parse_worktrees,
)
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


def _add_bare_remote(repo: Path, projects_root) -> Path:
    bare = projects_root / "origin.git"
    _git(bare.parent, "init", "--bare", "-q", str(bare))
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", "main")
    return bare


def test_stage_all_stages_every_change(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]
    (repo / "tracked.txt").write_text("hello\nworld\n")
    (repo / "untracked.txt").write_text("new\n")

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/stage-all", headers=_csrf(client)
    )

    assert response.status_code == 200
    body = response.json()
    assert {change["path"] for change in body["staged"]} == {"tracked.txt", "untracked.txt"}
    assert body["unstaged"] == []
    assert body["untracked"] == []


def test_unstage_all_clears_the_index(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]
    (repo / "tracked.txt").write_text("hello\nworld\n")
    (repo / "untracked.txt").write_text("new\n")
    client.post(f"{PROJECTS_URL}/{project_id}/git/stage-all", headers=_csrf(client))

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/unstage-all", headers=_csrf(client)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["staged"] == []
    assert {change["path"] for change in body["unstaged"]} == {"tracked.txt"}
    assert body["untracked"] == ["untracked.txt"]


def test_discard_restores_tracked_and_removes_untracked(
    client: TestClient, projects_root
) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]
    (repo / "tracked.txt").write_text("hello\nworld\n")
    (repo / "untracked.txt").write_text("new\n")

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/discard",
        json={"paths": ["tracked.txt", "untracked.txt"]},
        headers=_csrf(client),
    )

    assert response.status_code == 200
    assert response.json()["unstaged"] == []
    assert response.json()["untracked"] == []
    assert (repo / "tracked.txt").read_text() == "hello\n"
    assert not (repo / "untracked.txt").exists()


def test_discard_removes_staged_new_file(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]
    (repo / "new.txt").write_text("new\n")
    _git(repo, "add", "new.txt")

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/discard",
        json={"paths": ["new.txt"]},
        headers=_csrf(client),
    )

    assert response.status_code == 200
    assert response.json()["staged"] == []
    assert not (repo / "new.txt").exists()


def test_discard_reverts_staged_rename(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]
    _git(repo, "mv", "tracked.txt", "renamed.txt")

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/discard",
        json={"paths": ["tracked.txt", "renamed.txt"]},
        headers=_csrf(client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["staged"] == []
    assert body["unstaged"] == []
    assert (repo / "tracked.txt").read_text() == "hello\n"
    assert not (repo / "renamed.txt").exists()


def test_discard_rejects_invalid_path(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/discard",
        json={"paths": ["../outside.txt"]},
        headers=_csrf(client),
    )
    assert response.status_code == 400
    assert _error_code(response) == "GIT_INVALID_PATH"


def test_push_publishes_branch(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    _add_bare_remote(repo, projects_root)
    project_id = _register_local(client, repo)["id"]
    (repo / "tracked.txt").write_text("hello\nworld\n")
    client.post(f"{PROJECTS_URL}/{project_id}/git/stage-all", headers=_csrf(client))
    client.post(
        f"{PROJECTS_URL}/{project_id}/git/commit",
        json={"message": "update"},
        headers=_csrf(client),
    )

    response = client.post(f"{PROJECTS_URL}/{project_id}/git/push", headers=_csrf(client))

    assert response.status_code == 200
    assert response.json()["ahead"] == 0


def test_pull_requires_upstream(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    response = client.post(f"{PROJECTS_URL}/{project_id}/git/pull", headers=_csrf(client))
    assert response.status_code == 400
    assert _error_code(response) == "GIT_NO_UPSTREAM"


def test_pull_fast_forwards_from_upstream(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    _add_bare_remote(repo, projects_root)
    project_id = _register_local(client, repo)["id"]

    calls: list[list[str]] = []
    real_run = subprocess.run

    def fake_run(command, *args, **kwargs):
        if list(command[:2]) == ["git", "pull"]:
            calls.append(list(command))
            return subprocess.CompletedProcess(command, 0, "Already up to date.\n", "")
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr("app.modules.git.service.subprocess.run", fake_run)

    response = client.post(f"{PROJECTS_URL}/{project_id}/git/pull", headers=_csrf(client))

    assert response.status_code == 200
    assert calls == [["git", "pull", "--ff-only"]]


def test_branches_list_create_and_checkout(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    listed = client.get(f"{PROJECTS_URL}/{project_id}/git/branches")
    assert listed.status_code == 200
    assert listed.json() == {"current": "main", "branches": ["main"]}

    created = client.post(
        f"{PROJECTS_URL}/{project_id}/git/branches",
        json={"name": "feature/x"},
        headers=_csrf(client),
    )
    assert created.status_code == 200
    assert created.json()["branch"] == "feature/x"

    listed_again = client.get(f"{PROJECTS_URL}/{project_id}/git/branches").json()
    assert listed_again["current"] == "feature/x"
    assert listed_again["branches"] == ["feature/x", "main"]

    switched = client.post(
        f"{PROJECTS_URL}/{project_id}/git/checkout",
        json={"name": "main"},
        headers=_csrf(client),
    )
    assert switched.status_code == 200
    assert switched.json()["branch"] == "main"


def test_parse_worktrees_marks_primary_and_sorts_first(tmp_path: Path) -> None:
    primary = tmp_path / "repo"
    linked = tmp_path / "zzz-agent"
    output = (
        f"worktree {linked}\n"
        "HEAD 1111111111111111111111111111111111111111\n"
        "branch refs/heads/agent\n"
        "\n"
        f"worktree {primary}\n"
        "HEAD 2222222222222222222222222222222222222222\n"
        "branch refs/heads/main\n"
        "\n"
    )

    result = parse_worktrees(output, primary=primary)

    assert [worktree.name for worktree in result] == ["repo", "zzz-agent"]
    assert result[0].is_primary is True
    assert result[1].is_primary is False
    assert result[0].branch == "main"
    assert result[1].branch == "agent"


def test_parse_worktrees_detached_head_has_no_branch(tmp_path: Path) -> None:
    primary = tmp_path / "repo"
    output = (
        f"worktree {primary}\n"
        "HEAD 2222222222222222222222222222222222222222\n"
        "detached\n"
    )

    result = parse_worktrees(output, primary=primary)

    assert result[0].branch is None
    assert result[0].is_primary is True


def test_list_worktrees(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    linked = projects_root / "myrepo-agent"
    _git(repo, "worktree", "add", "-b", "agent-setting", str(linked))
    project_id = _register_local(client, repo)["id"]

    response = client.get(f"{PROJECTS_URL}/{project_id}/git/worktrees")

    assert response.status_code == 200
    body = response.json()
    assert [worktree["name"] for worktree in body] == ["myrepo", "myrepo-agent"]
    assert body[0]["is_primary"] is True
    assert body[0]["branch"] == "main"
    assert body[1]["is_primary"] is False
    assert body[1]["branch"] == "agent-setting"


def test_list_worktrees_requires_auth(client: TestClient) -> None:
    assert client.get(f"{PROJECTS_URL}/1/git/worktrees").status_code == 401


def test_list_worktrees_scoped_to_owner(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    client.cookies.clear()
    _login(client, username=OTHER_USERNAME)

    response = client.get(f"{PROJECTS_URL}/{project_id}/git/worktrees")
    assert response.status_code == 404
    assert _error_code(response) == "PROJECT_NOT_FOUND"


def test_create_branch_rejects_invalid_name(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    response = client.post(
        f"{PROJECTS_URL}/{project_id}/git/branches",
        json={"name": "bad name"},
        headers=_csrf(client),
    )
    assert response.status_code == 400
    assert _error_code(response) == "GIT_BRANCH_INVALID"


def test_current_pull_request_without_remote(client: TestClient, projects_root) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]

    response = client.get(f"{PROJECTS_URL}/{project_id}/git/pull-request")

    assert response.status_code == 200
    assert response.json() == {"pull_request": None}


def test_current_pull_request_returns_summary(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    _git(repo, "remote", "add", "origin", "https://github.com/example/myrepo.git")
    project_id = _register_local(client, repo)["id"]

    real_run = subprocess.run

    def fake_run(command, *args, **kwargs):
        if command[0] == "gh":
            payload = {
                "number": 7,
                "title": "Add feature",
                "url": "https://github.com/example/myrepo/pull/7",
                "state": "OPEN",
                "isDraft": False,
                "headRefName": "feature/x",
                "baseRefName": "main",
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr("app.modules.git.service.subprocess.run", fake_run)

    response = client.get(f"{PROJECTS_URL}/{project_id}/git/pull-request")

    assert response.status_code == 200
    assert response.json() == {
        "pull_request": {
            "number": 7,
            "title": "Add feature",
            "url": "https://github.com/example/myrepo/pull/7",
            "state": "OPEN",
            "is_draft": False,
            "head": "feature/x",
            "base": "main",
        }
    }


def test_current_pull_request_absent_when_gh_fails(
    client: TestClient, projects_root, monkeypatch
) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    _git(repo, "remote", "add", "origin", "https://github.com/example/myrepo.git")
    project_id = _register_local(client, repo)["id"]

    real_run = subprocess.run

    def fake_run(command, *args, **kwargs):
        if command[0] == "gh":
            return subprocess.CompletedProcess(command, 1, "", "no pull requests found")
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr("app.modules.git.service.subprocess.run", fake_run)

    response = client.get(f"{PROJECTS_URL}/{project_id}/git/pull-request")

    assert response.status_code == 200
    assert response.json() == {"pull_request": None}


AGENTS_DEFAULT_URL = "/api/v1/agents/default"


def _set_default_agent(client: TestClient, agent_id: str) -> None:
    response = client.put(AGENTS_DEFAULT_URL, json={"agent_id": agent_id}, headers=_csrf(client))
    assert response.status_code == 200, response.text


def test_commit_message_requires_default_agent(client: TestClient, projects_root) -> None:
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

    response = client.post(f"{PROJECTS_URL}/{project_id}/git/commit-message", headers=_csrf(client))

    assert response.status_code == 400
    assert _error_code(response) == "AGENT_NOT_CONFIGURED"


def test_commit_message_reports_unsupported_agent(client: TestClient, projects_root) -> None:
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
    _set_default_agent(client, "aider")

    response = client.post(f"{PROJECTS_URL}/{project_id}/git/commit-message", headers=_csrf(client))

    assert response.status_code == 400
    assert _error_code(response) == "AGENT_UNSUPPORTED"


def test_commit_message_generates_with_default_agent(
    client: TestClient, projects_root, monkeypatch
) -> None:
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
    _set_default_agent(client, "claude")

    captured: dict = {}
    real_run = subprocess.run

    def fake_run(argv, *args, **kwargs):
        if argv and argv[0] == "claude":
            captured["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, "feat: update tracked\n", "")
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr("app.modules.agents.service.subprocess.run", fake_run)

    response = client.post(f"{PROJECTS_URL}/{project_id}/git/commit-message", headers=_csrf(client))

    assert response.status_code == 200, response.json()
    assert response.json() == {"message": "feat: update tracked", "agent_id": "claude"}
    assert captured["argv"][:2] == ["claude", "-p"]
    assert "hello" in captured["argv"][2]


def test_commit_message_requires_staged_or_working_changes(
    client: TestClient, projects_root
) -> None:
    _login(client)
    repo = projects_root / "myrepo"
    _init_repo(repo)
    project_id = _register_local(client, repo)["id"]
    _set_default_agent(client, "claude")

    response = client.post(f"{PROJECTS_URL}/{project_id}/git/commit-message", headers=_csrf(client))

    assert response.status_code == 400
    assert _error_code(response) == "GIT_NOTHING_TO_COMMIT"


def test_clean_commit_message_strips_code_fences() -> None:
    assert _clean_commit_message("```\nfeat: add thing\n```\n") == "feat: add thing"
    assert _clean_commit_message("```text\nfix: bug\n\nbody\n```") == "fix: bug\n\nbody"


def test_clean_commit_message_caps_length() -> None:
    assert len(_clean_commit_message("a" * (_COMMIT_MESSAGE_MAX_CHARS + 500))) == (
        _COMMIT_MESSAGE_MAX_CHARS
    )
