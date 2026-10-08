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
        "GIT_NOT_A_REPOSITORY": "Project is not a git repository",
        "GIT_COMMAND_FAILED": "Could not read git status",
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
        "GIT_NOT_A_REPOSITORY": "Dự án không phải là repository git",
        "GIT_COMMAND_FAILED": "Không thể đọc trạng thái git",
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
