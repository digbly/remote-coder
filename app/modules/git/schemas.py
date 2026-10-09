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


class GitPathsUpdate(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=1000)


class GitCommitCreate(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


class GitCommitRead(BaseModel):
    commit: str
    branch: str | None = None


class GitCommitMessageRead(BaseModel):
    message: str
    agent_id: str


class GitPullRequestCreate(BaseModel):
    branch: str = Field(min_length=1, max_length=255)


class GitPullRequestRead(BaseModel):
    url: str
    branch: str
    base: str


class GitPullRequestSummary(BaseModel):
    number: int
    title: str
    url: str
    state: str
    is_draft: bool = False
    head: str | None = None
    base: str | None = None


class GitPullRequestStatusRead(BaseModel):
    pull_request: GitPullRequestSummary | None = None


class GitBranchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class GitBranchesRead(BaseModel):
    current: str | None = None
    branches: list[str] = Field(default_factory=list)


class GitWorktreeRead(BaseModel):
    name: str
    path: str
    branch: str | None = None
    is_primary: bool = False
