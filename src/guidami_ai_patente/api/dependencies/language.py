"""Gates the translation endpoint's target language (spec 0018, FR-2)."""

from fastapi import Query

from guidami_ai_patente.exceptions import UnsupportedLanguageError

_SUPPORTED_LANGUAGES = frozenset({"ru"})


def require_supported_language(
    lang: str = Query(
        description="Target language for the translation. Only 'ru' is supported today."
    ),
) -> str:
    """Raises when `lang` names a language this endpoint cannot translate to (FR-2).

    A plain `Depends()` function rather than a check inline in the router body,
    matching `require_registered_user`'s shape: the router itself never raises
    (thin controller), and this needs no service — it depends on nothing but the
    query string itself.
    """
    if lang not in _SUPPORTED_LANGUAGES:
        raise UnsupportedLanguageError(lang)
    return lang
