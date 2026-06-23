from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.mappers.knowledge import EnrichedArticleMapper
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


def test_to_enriched_article_copies_all_common_fields() -> None:
    article = _article()
    contexts = {0: "Contesto comma 1.", 1: "Contesto comma 2."}

    result = EnrichedArticleMapper.from_article_to_enriched_article(article, contexts)

    assert isinstance(result, EnrichedArticle)
    assert result.number == article.number
    assert result.title == article.title
    assert result.text == article.text
    assert result.paragraphs == article.paragraphs
    assert result.url == article.url
    assert result.scraped_at == article.scraped_at
    assert result.repealed == article.repealed


def test_to_enriched_article_sets_contexts() -> None:
    article = _article()
    contexts = {0: "Contesto comma 1."}

    result = EnrichedArticleMapper.from_article_to_enriched_article(article, contexts)

    assert result.contexts == contexts


def test_to_enriched_article_with_empty_contexts() -> None:
    article = _article(repealed=True)

    result = EnrichedArticleMapper.from_article_to_enriched_article(article, {})

    assert result.contexts == {}
    assert result.repealed is True
