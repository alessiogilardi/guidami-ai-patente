import pytest
from pydantic import ValidationError

from glossary.agents.glossary_term_translator.dto import TranslatedTermItemDto


def test_a_whitespace_only_term_ru_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        TranslatedTermItemDto(term_ru="   ")


def test_a_real_term_ru_is_accepted() -> None:
    dto = TranslatedTermItemDto(term_ru="проезжая часть")
    assert dto.term_ru == "проезжая часть"
