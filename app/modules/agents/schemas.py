from pydantic import BaseModel, Field


class AgentStatus(BaseModel):
    command: str
    installed: bool
    path: str | None = None


class AgentListResponse(BaseModel):
    agents: list[AgentStatus]


class AgentSettingUpdate(BaseModel):
    command: str = Field(min_length=1, max_length=256)
    args: str = Field(default="", max_length=1024)


class AgentSettingItem(BaseModel):
    agent_id: str
    command: str
    args: str


class AgentSettingsResponse(BaseModel):
    settings: list[AgentSettingItem]
