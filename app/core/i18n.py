from contextvars import ContextVar

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "vi")

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "INVALID_CREDENTIALS": "Incorrect username or password",
        "INACTIVE_USER": "Inactive user",
        "NOT_AUTHENTICATED": "Could not validate credentials",
        "CSRF_INVALID": "CSRF token missing or invalid",
        "RATE_LIMITED": "Too many login attempts. Please try again later.",
        "VALIDATION_ERROR": "Invalid request",
        "PROJECT_NOT_FOUND": "Project not found",
        "INVALID_GITHUB_URL": "Not a valid GitHub repository URL",
        "PROJECT_PATH_INVALID": "Path must be an existing, accessible directory",
        "PROJECT_PATH_EXISTS": "A project already uses this path",
        "PROJECT_NAME_EXISTS": "A project with this name already exists",
        "PROJECT_CLONE_FAILED": "Could not clone the repository",
        "FILE_PATH_INVALID": "The file path is not allowed",
        "FILE_NOT_FOUND": "File not found",
        "FILE_TOO_LARGE": "The file is too large to open",
        "FILE_BINARY": "Binary files cannot be opened in the editor",
        "FILE_WRITE_FAILED": "Could not save the file",
        "SEARCH_QUERY_INVALID": "The search pattern is not a valid regular expression",
        "GIT_NOT_A_REPOSITORY": "Project is not a git repository",
        "GIT_COMMAND_FAILED": "Could not read git status",
        "GIT_INVALID_PATH": "One or more selected paths are invalid",
        "GIT_NOTHING_TO_COMMIT": "There are no staged changes to commit",
        "GIT_REMOTE_MISSING": "Project does not have a GitHub remote",
        "GIT_BRANCH_INVALID": "Branch name is invalid or already in use",
        "GIT_PUSH_FAILED": "Could not push the branch",
        "GIT_PULL_REQUEST_FAILED": "Could not create the pull request",
        "GIT_DISCARD_FAILED": "Could not discard the changes",
        "GIT_PULL_FAILED": "Could not pull the changes",
        "GIT_NO_UPSTREAM": "The current branch has no upstream to pull from",
        "GIT_WORKTREE_INVALID": "Worktree name is invalid",
        "GIT_WORKTREE_EXISTS": "A worktree with this name already exists",
        "GIT_WORKTREE_FAILED": "Could not create the worktree",
        "GIT_WORKTREE_NOT_FOUND": "Worktree not found",
        "GIT_WORKTREE_DELETE_FAILED": "Could not delete the worktree",
        "AGENT_NOT_FOUND": "Unknown agent",
        "AGENT_NOT_CONFIGURED": "No default agent is selected",
        "AGENT_UNSUPPORTED": "The default agent cannot generate commit messages",
        "AGENT_GENERATE_FAILED": "Could not generate a commit message",
        "VSCODE_DISABLED": "The VS Code server is disabled",
        "VSCODE_WORKTREE_NOT_FOUND": "Worktree not found",
        "VSCODE_START_FAILED": "Could not start the VS Code server",
        "VSCODE_PROXY_FAILED": "Could not reach the VS Code server",
        "VSCODE_FORBIDDEN": "Cross-site request rejected",
    },
    "vi": {
        "INVALID_CREDENTIALS": "Tên đăng nhập hoặc mật khẩu không đúng",
        "INACTIVE_USER": "Tài khoản không hoạt động",
        "NOT_AUTHENTICATED": "Không thể xác thực thông tin đăng nhập",
        "CSRF_INVALID": "Thiếu hoặc sai mã CSRF",
        "RATE_LIMITED": "Quá nhiều lần đăng nhập. Vui lòng thử lại sau.",
        "VALIDATION_ERROR": "Yêu cầu không hợp lệ",
        "PROJECT_NOT_FOUND": "Không tìm thấy dự án",
        "INVALID_GITHUB_URL": "URL repository GitHub không hợp lệ",
        "PROJECT_PATH_INVALID": "Đường dẫn phải là thư mục tồn tại và có quyền truy cập",
        "PROJECT_PATH_EXISTS": "Đã có dự án sử dụng đường dẫn này",
        "PROJECT_NAME_EXISTS": "Đã tồn tại dự án với tên này",
        "PROJECT_CLONE_FAILED": "Không thể clone repository",
        "FILE_PATH_INVALID": "Đường dẫn tệp không được phép",
        "FILE_NOT_FOUND": "Không tìm thấy tệp",
        "FILE_TOO_LARGE": "Tệp quá lớn để mở",
        "FILE_BINARY": "Không thể mở tệp nhị phân trong trình soạn thảo",
        "FILE_WRITE_FAILED": "Không thể lưu tệp",
        "SEARCH_QUERY_INVALID": "Mẫu tìm kiếm không phải là biểu thức chính quy hợp lệ",
        "GIT_NOT_A_REPOSITORY": "Dự án không phải là repository git",
        "GIT_COMMAND_FAILED": "Không thể đọc trạng thái git",
        "GIT_INVALID_PATH": "Một hoặc nhiều đường dẫn không hợp lệ",
        "GIT_NOTHING_TO_COMMIT": "Không có thay đổi nào đã stage để commit",
        "GIT_REMOTE_MISSING": "Dự án không có remote GitHub",
        "GIT_BRANCH_INVALID": "Tên nhánh không hợp lệ hoặc đã tồn tại",
        "GIT_PUSH_FAILED": "Không thể push nhánh",
        "GIT_PULL_REQUEST_FAILED": "Không thể tạo pull request",
        "GIT_DISCARD_FAILED": "Không thể hoàn tác thay đổi",
        "GIT_PULL_FAILED": "Không thể pull thay đổi",
        "GIT_NO_UPSTREAM": "Nhánh hiện tại không có upstream để pull",
        "GIT_WORKTREE_INVALID": "Tên worktree không hợp lệ",
        "GIT_WORKTREE_EXISTS": "Đã tồn tại worktree với tên này",
        "GIT_WORKTREE_FAILED": "Không thể tạo worktree",
        "GIT_WORKTREE_NOT_FOUND": "Không tìm thấy worktree",
        "GIT_WORKTREE_DELETE_FAILED": "Không thể xoá worktree",
        "AGENT_NOT_FOUND": "Agent không tồn tại",
        "AGENT_NOT_CONFIGURED": "Chưa chọn agent mặc định",
        "AGENT_UNSUPPORTED": "Agent mặc định không hỗ trợ tạo nội dung commit",
        "AGENT_GENERATE_FAILED": "Không thể tạo nội dung commit",
        "VSCODE_DISABLED": "VS Code server đang bị tắt",
        "VSCODE_WORKTREE_NOT_FOUND": "Không tìm thấy worktree",
        "VSCODE_START_FAILED": "Không thể khởi động VS Code server",
        "VSCODE_PROXY_FAILED": "Không thể kết nối tới VS Code server",
        "VSCODE_FORBIDDEN": "Từ chối yêu cầu cross-site",
    },
}

_language: ContextVar[str] = ContextVar("language", default=DEFAULT_LANGUAGE)


def resolve_language(accept_language: str | None) -> str:
    """Pick the first supported base language from an Accept-Language header."""
    if not accept_language:
        return DEFAULT_LANGUAGE

    for entry in accept_language.split(","):
        base = entry.split(";")[0].strip().lower().split("-")[0]
        if base in SUPPORTED_LANGUAGES:
            return base

    return DEFAULT_LANGUAGE


def set_language(language: str) -> None:
    _language.set(language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE)


def translate(code: str, default: str = "Unexpected error") -> str:
    return MESSAGES.get(_language.get(), {}).get(code, default)
