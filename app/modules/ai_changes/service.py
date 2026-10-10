import difflib
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, api_error
from app.modules.ai_changes.models import ChangeProposal, ProposalChangeType, ProposalStatus
from app.modules.ai_changes.schemas import ChangeProposalRead
from app.modules.ai_chat.models import Conversation
from app.modules.ai_chat.schemas import CommandPermission
from app.modules.auth.models import User
from app.modules.projects import service as project_service

MAX_PROPOSED_FILE_BYTES = 1_000_000
MAX_PROPOSAL_DIFF_CHARS = 24_000
DESTRUCTIVE_CHANGE_TYPES = frozenset(
    {
        ProposalChangeType.DELETE,
        ProposalChangeType.DELETE_DIRECTORY,
        ProposalChangeType.MOVE,
    }
)


def proposal_needs_review(change_type: ProposalChangeType, permission: CommandPermission) -> bool:
    """Whether a proposed change must wait for the user's explicit approval."""
    if permission is CommandPermission.ALLOW_ALL:
        return False
    if permission is CommandPermission.MANUAL:
        return True
    return change_type in DESTRUCTIVE_CHANGE_TYPES


def create_proposal(
    db: Session,
    user: User,
    project_id: int,
    conversation_id: str,
    path: str,
    proposed_content: str,
) -> ChangeProposalRead:
    conversation = _get_conversation(db, user.id, project_id, conversation_id)
    _validate_path(path)
    _validate_content(proposed_content)

    original = project_service.read_file(db, user, project_id, path)
    return _persist(
        db,
        ChangeProposal(
            owner_id=user.id,
            project_id=project_id,
            conversation_id=conversation.id,
            path=original.path,
            target_path=None,
            change_type=ProposalChangeType.MODIFY,
            original_hash=_content_hash(original.content),
            original_content=original.content,
            proposed_content=proposed_content,
            status=ProposalStatus.PENDING,
        ),
        original.content,
        proposed_content,
    )


def create_new_file_proposal(
    db: Session,
    user: User,
    project_id: int,
    conversation_id: str,
    path: str,
    proposed_content: str,
) -> ChangeProposalRead:
    conversation = _get_conversation(db, user.id, project_id, conversation_id)
    _validate_path(path)
    _validate_content(proposed_content)

    normalized = project_service.normalize_project_path(db, user, project_id, path)
    if project_service.path_exists(db, user, project_id, normalized):
        raise api_error(ErrorCode.FILE_ALREADY_EXISTS, status_code=409)
    return _persist(
        db,
        ChangeProposal(
            owner_id=user.id,
            project_id=project_id,
            conversation_id=conversation.id,
            path=normalized,
            target_path=None,
            change_type=ProposalChangeType.CREATE,
            original_hash="",
            original_content="",
            proposed_content=proposed_content,
            status=ProposalStatus.PENDING,
        ),
        "",
        proposed_content,
    )


def create_delete_file_proposal(
    db: Session, user: User, project_id: int, conversation_id: str, path: str
) -> ChangeProposalRead:
    conversation = _get_conversation(db, user.id, project_id, conversation_id)
    _validate_path(path)

    original = project_service.read_file(db, user, project_id, path)
    return _persist(
        db,
        ChangeProposal(
            owner_id=user.id,
            project_id=project_id,
            conversation_id=conversation.id,
            path=original.path,
            target_path=None,
            change_type=ProposalChangeType.DELETE,
            original_hash=_content_hash(original.content),
            original_content=original.content,
            proposed_content="",
            status=ProposalStatus.PENDING,
        ),
        original.content,
        "",
    )


def create_directory_proposal(
    db: Session, user: User, project_id: int, conversation_id: str, path: str
) -> ChangeProposalRead:
    conversation = _get_conversation(db, user.id, project_id, conversation_id)
    _validate_path(path)

    normalized = project_service.normalize_project_path(db, user, project_id, path)
    if project_service.path_exists(db, user, project_id, normalized):
        raise api_error(ErrorCode.FILE_ALREADY_EXISTS, status_code=409)
    return _persist(
        db,
        ChangeProposal(
            owner_id=user.id,
            project_id=project_id,
            conversation_id=conversation.id,
            path=normalized,
            target_path=None,
            change_type=ProposalChangeType.CREATE_DIRECTORY,
            original_hash="",
            original_content="",
            proposed_content="",
            status=ProposalStatus.PENDING,
        ),
        "",
        "",
    )


def create_delete_directory_proposal(
    db: Session, user: User, project_id: int, conversation_id: str, path: str
) -> ChangeProposalRead:
    conversation = _get_conversation(db, user.id, project_id, conversation_id)
    _validate_path(path)

    normalized = project_service.normalize_project_path(db, user, project_id, path)
    listing = project_service.list_directory_paths(db, user, project_id, normalized)
    if listing is None:
        raise api_error(ErrorCode.FILE_NOT_FOUND, status_code=404)
    preview = "\n".join(listing)
    return _persist(
        db,
        ChangeProposal(
            owner_id=user.id,
            project_id=project_id,
            conversation_id=conversation.id,
            path=normalized,
            target_path=None,
            change_type=ProposalChangeType.DELETE_DIRECTORY,
            original_hash="",
            original_content=preview,
            proposed_content="",
            status=ProposalStatus.PENDING,
        ),
        preview,
        "",
    )


def create_move_proposal(
    db: Session,
    user: User,
    project_id: int,
    conversation_id: str,
    path: str,
    target_path: str,
) -> ChangeProposalRead:
    conversation = _get_conversation(db, user.id, project_id, conversation_id)
    _validate_path(path)
    _validate_path(target_path)

    normalized = project_service.normalize_project_path(db, user, project_id, path)
    normalized_target = project_service.normalize_project_path(db, user, project_id, target_path)
    if normalized == normalized_target:
        raise api_error(ErrorCode.FILE_PATH_INVALID, status_code=400)
    if project_service.path_exists(db, user, project_id, normalized_target):
        raise api_error(ErrorCode.FILE_ALREADY_EXISTS, status_code=409)

    original_content = ""
    original_hash = ""
    if not project_service.directory_exists(db, user, project_id, normalized):
        original = project_service.read_file(db, user, project_id, normalized)
        original_content = original.content
        original_hash = _content_hash(original.content)
    return _persist(
        db,
        ChangeProposal(
            owner_id=user.id,
            project_id=project_id,
            conversation_id=conversation.id,
            path=normalized,
            target_path=normalized_target,
            change_type=ProposalChangeType.MOVE,
            original_hash=original_hash,
            original_content=original_content,
            proposed_content="",
            status=ProposalStatus.PENDING,
        ),
        "",
        "",
    )


def _validate_path(path: str) -> None:
    if not isinstance(path, str) or not path or len(path) > 4096:
        raise api_error(ErrorCode.FILE_PATH_INVALID, status_code=400)


def _validate_content(content: str) -> None:
    if not isinstance(content, str):
        raise api_error(ErrorCode.VALIDATION_ERROR, status_code=422)
    if len(content.encode("utf-8")) > MAX_PROPOSED_FILE_BYTES:
        raise api_error(ErrorCode.FILE_TOO_LARGE, status_code=400)


def _ensure_diff_size(diff: str) -> None:
    if len(diff) > MAX_PROPOSAL_DIFF_CHARS:
        raise api_error(ErrorCode.AI_CHAT_LIMIT_EXCEEDED, status_code=413)


def _persist(
    db: Session, proposal: ChangeProposal, diff_original: str, diff_proposed: str
) -> ChangeProposalRead:
    _ensure_diff_size(_build_diff(diff_original, diff_proposed, proposal.path))
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

    applied = _apply_change(db, user, project_id, proposal)
    if not applied:
        proposal.status = ProposalStatus.STALE
        db.commit()
        raise api_error(ErrorCode.AI_CHANGE_PROPOSAL_STALE, status_code=409)

    proposal.status = ProposalStatus.APPLIED
    db.commit()
    db.refresh(proposal)
    return proposal_read(proposal)


def _apply_change(
    db: Session, user: User, project_id: int, proposal: ChangeProposal
) -> bool:
    change_type = proposal.change_type
    if change_type is ProposalChangeType.CREATE:
        return project_service.create_file_if_absent(
            db, user, project_id, proposal.path, proposal.proposed_content
        )
    if change_type is ProposalChangeType.DELETE:
        return project_service.delete_file_if_hash_matches(
            db, user, project_id, proposal.path, proposal.original_hash
        )
    if change_type is ProposalChangeType.CREATE_DIRECTORY:
        return project_service.create_directory_if_absent(db, user, project_id, proposal.path)
    if change_type is ProposalChangeType.DELETE_DIRECTORY:
        return project_service.delete_directory_if_exists(db, user, project_id, proposal.path)
    if change_type is ProposalChangeType.MOVE:
        if proposal.target_path is None:
            return False
        return project_service.move_entry_if_source_matches(
            db,
            user,
            project_id,
            proposal.path,
            proposal.target_path,
            proposal.original_hash,
            proposal.original_hash != "",
        )
    return project_service.write_file_if_hash_matches(
        db,
        user,
        project_id,
        proposal.path,
        proposal.original_hash,
        proposal.proposed_content,
    )


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
        target_path=proposal.target_path,
        change_type=proposal.change_type,
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
