from datetime import datetime

import pytest

from domain.entities.knowledge import ArticleCommaEntity, ArticleEntity
from guidami_ai_patente_ingestor.mappers import ArticleMapper
from guidami_ai_patente_ingestor.models.knowledge import (
    CleanedArticleModel,
    EmbeddableArticleComma,
    ParsedArticleModel,
    ParsedComma,
)

_COMMAS = [ParsedComma(number="1", text="Comma 1."), ParsedComma(number="2", text="Comma 2.")]


def _article(**kwargs) -> ParsedArticleModel:
    defaults = dict(
        number="1",
        title="Titolo articolo 1",
        commas=_COMMAS,
        url="https://example.com/art-1",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
    )
    return ParsedArticleModel(**{**defaults, **kwargs})


def _cleaned(**kwargs) -> CleanedArticleModel:
    defaults = dict(
        number="1",
        title="Titolo articolo 1",
        commas=_COMMAS,
        url="https://example.com/art-1",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
        source="cds",
    )
    return CleanedArticleModel(**{**defaults, **kwargs})


# --- from_parsed_to_cleaned ---


def test_from_parsed_to_cleaned_sets_source() -> None:
    article = _article()

    result = ArticleMapper.from_parsed_to_cleaned(article, "cds")

    assert isinstance(result, CleanedArticleModel)
    assert result.source == "cds"
    assert result.number == article.number
    assert result.title == article.title
    assert result.commas == article.commas
    assert result.url == article.url
    assert result.scraped_at == datetime.fromisoformat(article.scraped_at)
    assert result.repealed == article.repealed


def test_from_parsed_to_cleaned_preserves_repealed_flag() -> None:
    article = _article(repealed=True)

    result = ArticleMapper.from_parsed_to_cleaned(article, "cap")

    assert result.repealed is True
    assert result.source == "cap"


def test_from_parsed_to_cleaned_accepts_reg_source() -> None:
    article = _article()

    result = ArticleMapper.from_parsed_to_cleaned(article, "reg")

    assert result.source == "reg"


# --- from_cleaned_to_article_entity (T-9) ---


def test_from_cleaned_to_article_entity() -> None:
    article = _cleaned(repealed=True)

    result = ArticleMapper.from_cleaned_to_article_entity(article)

    assert isinstance(result, ArticleEntity)
    assert result.source == article.source
    assert result.number == article.number
    assert result.title == article.title
    assert result.url == article.url
    assert result.scraped_at == article.scraped_at
    assert result.is_repealed is True


# --- from_cleaned_to_embeddable_commas ---
# The mapper only seeds `is_repealed` with the article-level flag; the per-comma
# text formula is applied afterwards by the `detect_comma_repeal` pipeline step
# (tests/guidami_ai_patente_ingestor/services/knowledge/test_comma_repeal_detector.py),
# not by this mapper.


def test_comma_repealed_when_article_repealed() -> None:
    article = _cleaned(repealed=True, commas=[ParsedComma(number="1", text="testo normale")])

    result = ArticleMapper.from_cleaned_to_embeddable_commas(article)

    assert len(result) == 1
    assert isinstance(result[0], EmbeddableArticleComma)
    assert result[0].is_repealed is True


def test_comma_not_repealed_by_text_formula_alone() -> None:
    """The mapper does not apply the text formula: that's detect_comma_repeal's job."""
    article = _cleaned(
        repealed=False,
        commas=[ParsedComma(number="3", text="COMMA ABROGATO DAL D.LGS. 15 MARZO 2010, N. 66 .")],
    )

    result = ArticleMapper.from_cleaned_to_embeddable_commas(article)

    assert result[0].is_repealed is False


def test_from_cleaned_to_embeddable_commas_maps_all_fields_in_position_order() -> None:
    article = _cleaned(
        number="142",
        title="Titolo",
        source="cap",
        repealed=False,
        commas=[
            ParsedComma(number="1", text="Primo comma."),
            ParsedComma(number="2", text="Secondo comma."),
        ],
    )

    result = ArticleMapper.from_cleaned_to_embeddable_commas(article)

    assert [c.position for c in result] == [0, 1]
    assert [c.comma_number for c in result] == ["1", "2"]
    assert [c.text for c in result] == ["Primo comma.", "Secondo comma."]
    assert all(c.source == "cap" for c in result)
    assert all(c.article_number == "142" for c in result)
    assert all(c.article_title == "Titolo" for c in result)
    assert all(c.embedding is None for c in result)


# --- from_embeddable_comma_to_article_comma ---


def _embeddable_comma(**kwargs) -> EmbeddableArticleComma:
    defaults = dict(
        source="cds",
        article_number="142",
        article_title="Titolo",
        comma_number="1",
        position=0,
        text="Testo del comma",
        is_repealed=False,
        embedding=[0.1, 0.2],
    )
    return EmbeddableArticleComma(**{**defaults, **kwargs})


def test_from_embeddable_comma_to_article_comma_resolves_article_id() -> None:
    comma = _embeddable_comma(article_number="142")

    result = ArticleMapper.from_embeddable_comma_to_article_comma(
        comma, article_id_by_number={"142": 7}
    )

    assert isinstance(result, ArticleCommaEntity)
    assert result.article_id == 7


def test_from_embeddable_comma_to_article_comma_maps_remaining_fields() -> None:
    comma = _embeddable_comma(
        comma_number="2-bis", position=3, text="Testo", is_repealed=True, embedding=[0.5]
    )

    result = ArticleMapper.from_embeddable_comma_to_article_comma(
        comma, article_id_by_number={"142": 1}
    )

    assert result.comma_number == "2-bis"
    assert result.position == 3
    assert result.text == "Testo"
    assert result.is_repealed is True
    assert result.embedding == [0.5]


def test_from_embeddable_comma_to_article_comma_unknown_article_number_raises() -> None:
    comma = _embeddable_comma(article_number="999")

    with pytest.raises(KeyError):
        ArticleMapper.from_embeddable_comma_to_article_comma(
            comma, article_id_by_number={"142": 1}
        )
