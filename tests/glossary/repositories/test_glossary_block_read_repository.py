from pathlib import Path

import pytest

from glossary.configs import GlossaryBlockConfig
from glossary.repositories import GlossaryBlockReadRepository

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _repository() -> GlossaryBlockReadRepository:
    return GlossaryBlockReadRepository(_FIXTURES)


def test_it_selects_the_configured_comma_and_strips_inline_markup() -> None:
    block = _repository().read(
        GlossaryBlockConfig(
            source="cds", file="sample_article.json", article_number="9", comma_number="2"
        )
    )
    assert block.text == "Seconda nota interna definizione senza numeri."


def test_it_concatenates_every_comma_when_comma_number_is_absent() -> None:
    block = _repository().read(
        GlossaryBlockConfig(source="cds", file="sample_article.json", article_number="9")
    )
    assert "ALFA" in block.text
    assert "Seconda" in block.text
    assert len(block.comma_spans) == 2


def test_comma_number_at_resolves_an_offset_to_its_source_comma() -> None:
    block = _repository().read(
        GlossaryBlockConfig(source="cds", file="sample_article.json", article_number="9")
    )
    offset_in_second_comma = block.text.index("Seconda")
    assert block.get_comma_number_at(offset_in_second_comma) == "2"


def test_an_unknown_article_raises_a_clear_error() -> None:
    with pytest.raises(ValueError, match="article '404' not found"):
        _repository().read(
            GlossaryBlockConfig(source="cds", file="sample_article.json", article_number="404")
        )


def test_an_unknown_comma_raises_a_clear_error() -> None:
    with pytest.raises(ValueError, match="comma '99' not found"):
        _repository().read(
            GlossaryBlockConfig(
                source="cds", file="sample_article.json", article_number="9", comma_number="99"
            )
        )


def test_double_spaces_and_embedded_newlines_are_collapsed_to_a_single_space() -> None:
    block = _repository().read(
        GlossaryBlockConfig(
            source="cds",
            file="sample_article_whitespace.json",
            article_number="9",
            comma_number="1",
        )
    )
    assert block.text == "Prima definizione: con doppio spazio e a capo."
