import difflib
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, api_error
from app.modules.ai_changes.models import ChangeProposal, ProposalStatus
from app.modules.ai_changes.schemas import ChangeProposalRead
from app.modules.ai_chat.models import Conversation
from app.modules.auth.models import User
from app.modules.projects import service as project_service

MAX_PROPOSED_FILE_BYTES = 1_000_000
MAX_PROPOSAL_DIFF_CHARS = 24_000


def create_proposal(
    db: Session,
    user: User,
    project_id: int,
    conversation_id: str,
    path: str,
    proposed_content: str,
) -> ChangeProposalRead:
    conversation = _get_conversation(db, user.id, project_id, conversation_id)
    if not isinstance(path, str) or not path or len(path) > 4096:
        raise api_error(ErrorCode.FILE_PATH_INVALID, status_code=400)
    if not isinstance(proposed_content, str):
        raise api_error(ErrorCode.VALIDATION_ERROR, status_code=422)
    proposed_bytes = proposed_content.encode("utf-8")
    if len(proposed_bytes) > MAX_PROPOSED_FILE_BYTES:
        raise api_error(ErrorCode.FILE_TOO_LARGE, status_code=400)

    original = project_service.read_file(db, user, project_id, path)
    diff = _build_diff(original.content, proposed_content, original.path)
    if len(diff) > MAX_PROPOSAL_DIFF_CHARS:
        raise api_error(ErrorCode.AI_CHAT_LIMIT_EXCEEDED, status_code=413)
    proposal = ChangeProposal(
        owner_id=user.id,
        project_id=project_id,
        conversation_id=conversation.id,
        path=original.path,
        original_hash=_content_hash(original.content),
        original_content=original.content,
        proposed_content=proposed_content,
        status=ProposalStatus.PENDING,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal_read(proposal)


def list_proposals(
    db: Session, user: User, project_id: int, conversation_id: str
) -> list[ChangeProposalRead]:
    _get_conversation(db, user.id, project_id, conversation_id)
    proposals = db.scalars(
        select(ChangeProposal)
        .where(
            ChangeProposal.owner_id == user.id,
            ChangeProposal.project_id == project_id,
            ChangeProposal.conversation_id == conversation_id,
        )
        .order_by(ChangeProposal.created_at, ChangeProposal.id)
    )
    return [proposal_read(proposal) for proposal in proposals]


def apply_proposal(
    db: Session, user: User, project_id: int, conversation_id: str, proposal_id: str
) -> ChangeProposalRead:
    proposal = _get_proposal(db, user.id, project_id, conversation_id, proposal_id)
    if proposal.status is not ProposalStatus.PENDING:
        raise api_error(ErrorCode.AI_CHANGE_PROPOSAL_NOT_PENDING, status_code=409)

    current = project_service.read_file(db, user, project_id, proposal.path)
    if _content_hash(current.content) != proposal.original_hash:
        proposal.status = ProposalStatus.STALE
        db.commit()
        raise api_error(ErrorCode.AI_CHANGE_PROPOSAL_STALE, status_code=409)

    project_service.write_file(db, user, project_id, proposal.path, proposal.proposed_content)
    proposal.status = ProposalStatus.APPLIED
    db.commit()
    db.refresh(proposal)
    return proposal_read(proposal)


def reject_proposal(
    db: Session, user: User, project_id: int, conversation_id: str, proposal_id: str
) -> ChangeProposalRead:
    proposal = _get_proposal(db, user.id, project_id, conversation_id, proposal_id)
    if proposal.status is not ProposalStatus.PENDING:
        raise api_error(ErrorCode.AI_CHANGE_PROPOSAL_NOT_PENDING, status_code=409)
    proposal.status = ProposalStatus.REJECTED
    db.commit()
    db.refresh(proposal)
    return proposal_read(proposal)


def proposal_read(proposal: ChangeProposal) -> ChangeProposalRead:
    return ChangeProposalRead(
        id=proposal.id,
        conversation_id=proposal.conversation_id,
        path=proposal.path,
        diff=_build_diff(proposal.original_content, proposal.proposed_content, proposal.path),
        status=proposal.status,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
    )


def _build_diff(original: str, proposed: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _get_conversation(
    db: Session, user_id: int, project_id: int, conversation_id: str
) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.owner_id == user_id,
            Conversation.project_id == project_id,
        )
    )
    if conversation is None:
        raise api_error(ErrorCode.AI_CHAT_CONVERSATION_NOT_FOUND, status_code=404)
    return conversation


def _get_proposal(
    db: Session, user_id: int, project_id: int, conversation_id: str, proposal_id: str
) -> ChangeProposal:
    proposal = db.scalar(
        select(ChangeProposal).where(
            ChangeProposal.id == proposal_id,
            ChangeProposal.owner_id == user_id,
            ChangeProposal.project_id == project_id,
            ChangeProposal.conversation_id == conversation_id,
        )
    )
    if proposal is None:
        raise api_error(ErrorCode.AI_CHANGE_PROPOSAL_NOT_FOUND, status_code=404)
    return proposal
