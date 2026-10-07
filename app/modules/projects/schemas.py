import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.modules.projects.models import ProjectSource

_NAME_PATTERN = re.compile(r"^(?!\.\.?$)[A-Za-z0-9._-]+$")


def validate_project_name(value: str) -> str:
    if not _NAME_PATTERN.match(value):
        raise ValueError("name may only contain letters, digits, '.', '_' and '-'")
    return value


ProjectName = Annotated[
    str, Field(min_length=1, max_length=100), AfterValidator(validate_project_name)
]


class GithubProjectCreate(BaseModel):
    repo_url: str = Field(min_length=1, max_length=500)
    name: ProjectName | None = None
    token: str | None = Field(default=None, min_length=1, max_length=255)
    branch: str | None = Field(default=None, min_length=1, max_length=255)


class LocalProjectCreate(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    name: ProjectName | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source: ProjectSource
    remote_url: str | None
    path: str
    created_at: datetime


class DirectoryEntry(BaseModel):
    name: str
    path: str


class DirectoryListing(BaseModel):
    root: str
    path: str
    parent: str | None
    directories: list[DirectoryEntry]
