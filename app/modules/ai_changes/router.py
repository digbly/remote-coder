from fastapi import APIRouter

from app.core.deps import DbDep
from app.core.errors import error_responses
from app.modules.ai_changes import service
from app.modules.ai_changes.schemas import (
    ProposalActionResponse,
    ProposalListResponse,
)
from app.modules.auth.deps import CsrfDep, CurrentUser

router = APIRouter(prefix="/conversations/{conversation_id}/proposals", tags=["ai-changes"])
_PROPOSAL_ERRORS = error_responses(401, 403, 404, 409, 413, 422)


@router.get("", response_model=ProposalListResponse, responses=_PROPOSAL_ERRORS)
def list_proposals(
    project_id: int,
    conversation_id: str,
    current_user: CurrentUser,
    db: DbDep,
) -> ProposalListResponse:
    return ProposalListResponse(
        proposals=service.list_proposals(db, current_user, project_id, conversation_id)
    )


@router.post(
    "/{proposal_id}/apply",
    response_model=ProposalActionResponse,
    responses=_PROPOSAL_ERRORS,
)
def apply_proposal(
    project_id: int,
    conversation_id: str,
    proposal_id: str,
    current_user: CurrentUser,
    db: DbDep,
    _csrf: CsrfDep,
) -> ProposalActionResponse:
    proposal = service.apply_proposal(db, current_user, project_id, conversation_id, proposal_id)
    return ProposalActionResponse(proposal=proposal)


@router.post(
    "/{proposal_id}/reject",
    response_model=ProposalActionResponse,
    responses=_PROPOSAL_ERRORS,
)
def reject_proposal(
    project_id: int,
    conversation_id: str,
    proposal_id: str,
    current_user: CurrentUser,
    db: DbDep,
    _csrf: CsrfDep,
) -> ProposalActionResponse:
    proposal = service.reject_proposal(db, current_user, project_id, conversation_id, proposal_id)
    return ProposalActionResponse(proposal=proposal)
