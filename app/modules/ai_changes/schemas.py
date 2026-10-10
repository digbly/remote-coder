from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.ai_changes.models import ProposalStatus


class ChangeProposalRead(BaseModel):
    id: str
    conversation_id: str
    path: str
    diff: str
    status: ProposalStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProposalListResponse(BaseModel):
    proposals: list[ChangeProposalRead]


class ProposalActionResponse(BaseModel):
    proposal: ChangeProposalRead
