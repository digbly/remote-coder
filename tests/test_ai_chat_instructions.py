from pathlib import Path

from app.modules.ai_chat.instructions import (
    MAX_INSTRUCTIONS_CHARS,
    MAX_INSTRUCTIONS_FILE_CHARS,
    PROJECT_INSTRUCTIONS_NAME,
    load_agent_instructions,
    user_instructions_path,
)


def _home_with_user_instructions(tmp_path: Path, content: str) -> Path:
    home = tmp_path / "home"
    (home / ".config" / "agents").mkdir(parents=True)
    (home / ".config" / "agents" / PROJECT_INSTRUCTIONS_NAME).write_text(
        content, encoding="utf-8"
    )
    return home


def test_returns_empty_when_no_instruction_files_exist(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    project.mkdir()

    assert load_agent_instructions(project) == ""


def test_loads_project_instructions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    project.mkdir()
    (project / PROJECT_INSTRUCTIONS_NAME).write_text("Use tabs.\n", encoding="utf-8")

    result = load_agent_instructions(project)

    assert "Use tabs." in result
    assert "Project instructions" in result
    assert "User instructions" not in result


def test_loads_user_before_project_instructions(tmp_path, monkeypatch) -> None:
    home = _home_with_user_instructions(tmp_path, "Global rule.\n")
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "project"
    project.mkdir()
    (project / PROJECT_INSTRUCTIONS_NAME).write_text("Project rule.\n", encoding="utf-8")

    result = load_agent_instructions(project)

    assert "User instructions" in result
    assert "Project instructions" in result
    assert result.index("Global rule.") < result.index("Project rule.")
    assert user_instructions_path() == home / ".config" / "agents" / PROJECT_INSTRUCTIONS_NAME


def test_caps_the_combined_instructions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(_home_with_user_instructions(tmp_path, "x" * 20_000)))
    project = tmp_path / "project"
    project.mkdir()
    (project / PROJECT_INSTRUCTIONS_NAME).write_text("y" * 20_000, encoding="utf-8")

    result = load_agent_instructions(project)

    # Per-file read limit applies first, then the combined cap.
    assert result.count("x") == MAX_INSTRUCTIONS_FILE_CHARS
    assert len(result) == MAX_INSTRUCTIONS_CHARS
    assert result.startswith("# User instructions")


def test_skips_unreadable_instruction_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    project.mkdir()
    # A directory named like the file must be skipped, not raised.
    (project / PROJECT_INSTRUCTIONS_NAME).mkdir()

    assert load_agent_instructions(project) == ""


def test_accepts_a_missing_project_path(tmp_path, monkeypatch) -> None:
    home = _home_with_user_instructions(tmp_path, "Global rule.\n")
    monkeypatch.setenv("HOME", str(home))

    result = load_agent_instructions(None)

    assert "Global rule." in result
    assert "Project instructions" not in result


def test_does_not_send_absolute_server_paths(tmp_path, monkeypatch) -> None:
    home = _home_with_user_instructions(tmp_path, "Global rule.\n")
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "project"
    project.mkdir()
    (project / PROJECT_INSTRUCTIONS_NAME).write_text("Project rule.\n", encoding="utf-8")

    result = load_agent_instructions(project)

    assert str(home) not in result
    assert str(project) not in result
    assert "~/.config/agents/AGENTS.md" in result
    assert "(AGENTS.md)" in result
