"""spec 0018: the translator's own field constraints — non-empty in, non-empty out."""

import pytest
from pydantic import ValidationError

from guidami_ai_patente.agents.explanation_translator.dto import (
    ExplanationTranslatorRequest,
    ExplanationTranslatorResponse,
)


def test_text_is_required() -> None:
    with pytest.raises(ValidationError):
        ExplanationTranslatorRequest()  # type: ignore[call-arg]


def test_an_empty_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ExplanationTranslatorRequest(text="")


def test_a_non_empty_text_is_accepted() -> None:
    request = ExplanationTranslatorRequest(text="La sosta è vietata.")

    assert request.text == "La sosta è vietata."


def test_an_empty_translated_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ExplanationTranslatorResponse(translated_text="")


def test_a_non_empty_translated_text_is_accepted() -> None:
    response = ExplanationTranslatorResponse(translated_text="Остановка запрещена.")

    assert response.translated_text == "Остановка запрещена."
