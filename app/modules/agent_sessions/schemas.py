from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AgentSessionRead(BaseModel):
    """A resumable session, either an in-app chat or a host CLI agent session."""

    source: Literal["chat", "cli"]
    id: str
    title: str
    agent_id: str | None = None
    agent_label: str | None = None
    updated_at: datetime


class AgentSessionListResponse(BaseModel):
    sessions: list[AgentSessionRead]
