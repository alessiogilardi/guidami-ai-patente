from commons.entities.knowledge import KnowledgeChunk
from guidami_ai_patente_ingestor.mappers.knowledge import ArticleMapper
from guidami_ai_patente_ingestor.models.knowledge import (
    EmbeddableChunkModel,
    EnrichedArticleModel,
    ParsedArticleModel,
)


def _article(**kwargs) -> ParsedArticleModel:
    defaults = dict(
        number="1",
        title="Titolo articolo 1",
        text="Testo articolo 1.",
        paragraphs=["Comma 1.", "Comma 2."],
        url="https://example.com/art-1",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
    )
    return ParsedArticleModel(**{**defaults, **kwargs})


def _embeddable_chunk(**kwargs) -> EmbeddableChunkModel:
    defaults = dict(
        source="cds",
        article_number="1",
        article_title="Titolo articolo 1",
        comma_index=0,
        chunk_text="Testo articolo 1.",
        context="",
        is_repealed=False,
        source_url="https://example.com/art-1",
        embedding=[0.1, 0.2],
    )
    return EmbeddableChunkModel(**{**defaults, **kwargs})


def test_from_parsed_to_enriched_copies_all_common_fields() -> None:
    article = _article()

    result = ArticleMapper.from_parsed_to_enriched(article)

    assert isinstance(result, EnrichedArticleModel)
    assert result.number == article.number
    assert result.title == article.title
    assert result.text == article.text
    assert result.paragraphs == article.paragraphs
    assert result.url == article.url
    assert result.scraped_at == article.scraped_at
    assert result.repealed == article.repealed


def test_from_parsed_to_enriched_sets_empty_contexts() -> None:
    article = _article()

    result = ArticleMapper.from_parsed_to_enriched(article)

    assert result.contexts == {}


def test_from_parsed_to_enriched_preserves_repealed_flag() -> None:
    article = _article(repealed=True)

    result = ArticleMapper.from_parsed_to_enriched(article)

    assert result.contexts == {}
    assert result.repealed is True


def test_from_embeddable_chunk_to_knowledge_chunk_copies_all_fields() -> None:
    model = _embeddable_chunk()

    result = ArticleMapper.from_embeddable_chunk_to_knowledge_chunk(model)

    assert isinstance(result, KnowledgeChunk)
    assert result.source == model.source
    assert result.article_number == model.article_number
    assert result.article_title == model.article_title
    assert result.comma_index == model.comma_index
    assert result.chunk_text == model.chunk_text
    assert result.context == model.context
    assert result.is_repealed == model.is_repealed
    assert result.source_url == model.source_url
    assert result.embedding == model.embedding


def test_from_embeddable_chunk_to_knowledge_chunk_preserves_none_embedding() -> None:
    model = _embeddable_chunk(embedding=None)

    result = ArticleMapper.from_embeddable_chunk_to_knowledge_chunk(model)

    assert result.embedding is None
