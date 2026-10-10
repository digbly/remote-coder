from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.ai_changes import service as change_service
from app.modules.ai_changes.schemas import ChangeProposalRead
from app.modules.auth.models import User
from app.modules.projects import service as project_service

MAX_PROJECT_FILES = 100
MAX_CONTEXT_FILE_CHARS = 24_000


@dataclass(frozen=True)
class ProjectContext:
    db: Session
    user: User
    project_id: int
    conversation_id: str = ""
    project_path: Path | None = None

    def list_files(self, path: str | None = None) -> dict[str, object]:
        tree = project_service.list_files(self.db, self.user, self.project_id, path)
        entries = [
            {"path": entry.path, "type": entry.type} for entry in tree.entries[:MAX_PROJECT_FILES]
        ]
        return {
            "entries": entries,
            "truncated": tree.truncated or len(tree.entries) > MAX_PROJECT_FILES,
        }

    def read_file(self, path: str) -> dict[str, object]:
        file = project_service.read_file(self.db, self.user, self.project_id, path)
        content = file.content[:MAX_CONTEXT_FILE_CHARS]
        return {
            "path": file.path,
            "content": content,
            "truncated": len(file.content) > MAX_CONTEXT_FILE_CHARS,
        }

    def propose_change(self, path: str, content: str) -> ChangeProposalRead:
        return change_service.create_proposal(
            self.db,
            self.user,
            self.project_id,
            self.conversation_id,
            path,
            content,
        )
