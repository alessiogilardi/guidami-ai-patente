"""TranslationHint is a frozen, length-bounded term/rendering pairing (spec 0018, FR-8)."""

import pytest
from pydantic import ValidationError

from guidami_ai_patente.models import TranslationHint


def test_it_is_frozen() -> None:
    hint = TranslationHint(term="carreggiata", term_ru="проезжая часть")

    with pytest.raises(ValidationError):
        hint.term = "banchina"  # type: ignore[misc]


def test_an_empty_term_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TranslationHint(term="", term_ru="проезжая часть")


def test_an_empty_term_ru_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TranslationHint(term="carreggiata", term_ru="")


def test_a_term_over_the_length_limit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TranslationHint(term="a" * 81, term_ru="проезжая часть")


def test_a_term_ru_over_the_length_limit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TranslationHint(term="carreggiata", term_ru="а" * 81)


def test_a_whitespace_only_term_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TranslationHint(term="   ", term_ru="проезжая часть")


def test_a_whitespace_only_term_ru_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TranslationHint(term="carreggiata", term_ru="   ")


def test_a_valid_hint_is_accepted() -> None:
    hint = TranslationHint(term="carreggiata", term_ru="проезжая часть")

    assert hint.term == "carreggiata"
    assert hint.term_ru == "проезжая часть"
