from pydantic import BaseModel, Field


class RunningTerminalsRead(BaseModel):
    """Project id -> worktrees that currently have a live terminal session."""

    projects: dict[int, list[str]] = Field(default_factory=dict)
