from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.mappers.knowledge import ArticleMapper
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle


def _article(**kwargs) -> Article:
    defaults = dict(
        number="1",
        title="Titolo articolo 1",
        text="Testo articolo 1.",
        paragraphs=["Comma 1.", "Comma 2."],
        url="https://example.com/art-1",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
    )
    return Article(**{**defaults, **kwargs})


def test_from_article_to_enriched_article_copies_all_common_fields() -> None:
    article = _article()

    result = ArticleMapper.from_article_to_enriched_article(article)

    assert isinstance(result, EnrichedArticle)
    assert result.number == article.number
    assert result.title == article.title
    assert result.text == article.text
    assert result.paragraphs == article.paragraphs
    assert result.url == article.url
    assert result.scraped_at == article.scraped_at
    assert result.repealed == article.repealed


def test_from_article_to_enriched_article_sets_empty_contexts() -> None:
    article = _article()

    result = ArticleMapper.from_article_to_enriched_article(article)

    assert result.contexts == {}


def test_from_article_to_enriched_article_preserves_repealed_flag() -> None:
    article = _article(repealed=True)

    result = ArticleMapper.from_article_to_enriched_article(article)

    assert result.contexts == {}
    assert result.repealed is True
