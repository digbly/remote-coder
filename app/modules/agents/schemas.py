from pydantic import BaseModel


class AgentStatus(BaseModel):
    command: str
    installed: bool
    path: str | None = None


class AgentListResponse(BaseModel):
    agents: list[AgentStatus]
