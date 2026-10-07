from app.errors import ErrorCode
from app.i18n import MESSAGES, SUPPORTED_LANGUAGES, resolve_language


def test_every_error_code_is_translated_in_every_language() -> None:
    for language in SUPPORTED_LANGUAGES:
        for code in ErrorCode:
            assert code.value in MESSAGES[language], (language, code.value)


def test_resolve_language_picks_first_supported_base() -> None:
    assert resolve_language("vi-VN,vi;q=0.9,en;q=0.8") == "vi"
    assert resolve_language("en-GB") == "en"


def test_resolve_language_falls_back_to_default() -> None:
    assert resolve_language(None) == "en"
    assert resolve_language("fr-FR,de;q=0.9") == "en"
