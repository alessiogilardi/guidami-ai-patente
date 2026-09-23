"""TranslationRequest is the translation UseCase's frozen input (spec 0018, FR-8)."""

import pytest
from pydantic import ValidationError

from guidami_ai_patente.models import TranslationHint, TranslationRequest


def test_it_is_frozen() -> None:
    request = TranslationRequest(text="La sosta è vietata.")

    with pytest.raises(ValidationError):
        request.text = "Altro testo."  # type: ignore[misc]


def test_hints_default_to_empty() -> None:
    request = TranslationRequest(text="La sosta è vietata.")

    assert request.hints == ()


def test_an_empty_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TranslationRequest(text="")


def test_hints_are_carried_through() -> None:
    hint = TranslationHint(term="carreggiata", term_ru="проезжая часть")

    request = TranslationRequest(text="La carreggiata è stretta.", hints=(hint,))

    assert request.hints == (hint,)


def test_duplicate_hint_terms_are_rejected() -> None:
    hints = (
        TranslationHint(term="carreggiata", term_ru="проезжая часть"),
        TranslationHint(term="Carreggiata", term_ru="дорога"),
    )

    with pytest.raises(ValidationError):
        TranslationRequest(text="La carreggiata è stretta.", hints=hints)
