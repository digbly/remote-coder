from pydantic import BaseModel, Field


class RunningTerminalsRead(BaseModel):
    """Project id -> worktrees that currently have a live terminal session."""

    projects: dict[int, list[str]] = Field(default_factory=dict)


class TerminalImageUpload(BaseModel):
    """A pasted image encoded as base64 for transport to the server."""

    media_type: str = Field(min_length=1, max_length=64)
    data: str = Field(min_length=1)


class TerminalImageRead(BaseModel):
    """Absolute path of the saved image, readable by the terminal's shell."""

    path: str


class TerminalFileUpload(BaseModel):
    """A file dropped onto the terminal, encoded as base64 for transport."""

    name: str = Field(min_length=1, max_length=255)
    data: str = Field(min_length=1)


class TerminalFileRead(BaseModel):
    """Absolute path of the saved file, readable by the terminal's shell."""

    path: str
