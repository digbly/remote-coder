from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.ai_changes import service as change_service
from app.modules.ai_changes.schemas import ChangeProposalRead
from app.modules.ai_chat.schemas import CommandPermission
from app.modules.auth.models import User
from app.modules.projects import service as project_service

MAX_PROJECT_FILES = 400
MAX_CONTEXT_FILE_CHARS = 24_000


@dataclass(frozen=True)
class ProjectContext:
    db: Session
    user: User
    project_id: int
    conversation_id: str = ""
    project_path: Path | None = None
    permission: CommandPermission = CommandPermission.MANUAL

    def list_files(self, path: str | None = None) -> dict[str, object]:
        tree = project_service.list_tree(
            self.db, self.user, self.project_id, path, limit=MAX_PROJECT_FILES
        )
        entries = [{"path": entry.path, "type": entry.type} for entry in tree.entries]
        return {"entries": entries, "truncated": tree.truncated}

    def read_file(self, path: str) -> dict[str, object]:
        file = project_service.read_file(self.db, self.user, self.project_id, path)
        content = file.content[:MAX_CONTEXT_FILE_CHARS]
        return {
            "path": file.path,
            "content": content,
            "truncated": len(file.content) > MAX_CONTEXT_FILE_CHARS,
        }

    def search_files(self, query: str, include: str | None = None) -> dict[str, object]:
        result = project_service.search_files(
            self.db, self.user, self.project_id, query=query, mode="contents", include=include
        )
        matches = [
            {
                "path": entry.path,
                "matches": [{"line": match.line, "text": match.text} for match in entry.matches],
            }
            for entry in result.entries
        ]
        return {"matches": matches, "truncated": result.truncated}

    def propose_change(self, path: str, content: str) -> ChangeProposalRead:
        return self._finalize(
            change_service.create_proposal(
                self.db, self.user, self.project_id, self.conversation_id, path, content
            )
        )

    def create_new_file(self, path: str, content: str) -> ChangeProposalRead:
        return self._finalize(
            change_service.create_new_file_proposal(
                self.db, self.user, self.project_id, self.conversation_id, path, content
            )
        )

    def delete_file(self, path: str) -> ChangeProposalRead:
        return self._finalize(
            change_service.create_delete_file_proposal(
                self.db, self.user, self.project_id, self.conversation_id, path
            )
        )

    def create_directory(self, path: str) -> ChangeProposalRead:
        return self._finalize(
            change_service.create_directory_proposal(
                self.db, self.user, self.project_id, self.conversation_id, path
            )
        )

    def delete_directory(self, path: str) -> ChangeProposalRead:
        return self._finalize(
            change_service.create_delete_directory_proposal(
                self.db, self.user, self.project_id, self.conversation_id, path
            )
        )

    def move_entry(self, path: str, target_path: str) -> ChangeProposalRead:
        return self._finalize(
            change_service.create_move_proposal(
                self.db, self.user, self.project_id, self.conversation_id, path, target_path
            )
        )

    def _finalize(self, proposal: ChangeProposalRead) -> ChangeProposalRead:
        """Apply immediately when the user's permission allows, otherwise leave pending."""
        if change_service.proposal_needs_review(proposal.change_type, self.permission):
            return proposal
        return change_service.apply_proposal(
            self.db, self.user, self.project_id, self.conversation_id, proposal.id
        )
