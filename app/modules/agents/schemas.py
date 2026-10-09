from pydantic import BaseModel, Field


class AgentDefinition(BaseModel):
    id: str
    label: str
    command: str
    args: str
    description: str = ""
    homepage: str | None = None
    installed: bool
    path: str | None = None


class AgentListResponse(BaseModel):
    agents: list[AgentDefinition]


class AgentModelsResponse(BaseModel):
    models: list[str]


class AgentSettingUpdate(BaseModel):
    command: str = Field(min_length=1, max_length=256)
    args: str = Field(default="", max_length=1024)


class AgentSettingItem(BaseModel):
    agent_id: str
    command: str
    args: str


class AgentSettingsResponse(BaseModel):
    settings: list[AgentSettingItem]
