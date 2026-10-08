from pydantic import BaseModel, Field


class GitChange(BaseModel):
    path: str
    status: str
    orig_path: str | None = None


class GitStatusRead(BaseModel):
    branch: str | None = None
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    staged: list[GitChange] = Field(default_factory=list)
    unstaged: list[GitChange] = Field(default_factory=list)
    untracked: list[str] = Field(default_factory=list)
    conflicted: list[str] = Field(default_factory=list)
