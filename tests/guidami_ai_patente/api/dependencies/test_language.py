"""Unit tests for the translation endpoint's language gate (spec 0018, FR-2)."""

import pytest

from guidami_ai_patente.api.dependencies.language import require_supported_language
from guidami_ai_patente.exceptions import UnsupportedLanguageError


def test_ru_is_accepted() -> None:
    assert require_supported_language(lang="ru") == "ru"


def test_any_other_language_is_rejected() -> None:
    with pytest.raises(UnsupportedLanguageError):
        require_supported_language(lang="en")
