from commons.entities.knowledge import KnowledgeChunk
from guidami_ai_patente_ingestor.mappers import ArticleMapper
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


def _enriched(**kwargs) -> EnrichedArticleModel:
    defaults = dict(
        number="1",
        title="Titolo articolo 1",
        text="Testo articolo 1.",
        paragraphs=["Comma 1.", "Comma 2."],
        url="https://example.com/art-1",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
        contexts={},
    )
    return EnrichedArticleModel(**{**defaults, **kwargs})


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


# --- from_parsed_to_enriched ---


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


# --- from_enriched_to_embeddable_chunk ---


def test_from_enriched_to_embeddable_chunk_copies_article_fields() -> None:
    article = _enriched()

    result = ArticleMapper.from_enriched_to_embeddable_chunk(
        article, source="cds", comma_index=0, raw_text="Testo."
    )

    assert isinstance(result, EmbeddableChunkModel)
    assert result.source == "cds"
    assert result.article_number == article.number
    assert result.article_title == article.title
    assert result.source_url == article.url


def test_from_enriched_to_embeddable_chunk_uses_provided_raw_text_and_comma_index() -> None:
    article = _enriched()

    result = ArticleMapper.from_enriched_to_embeddable_chunk(
        article, source="cap", comma_index=2, raw_text="Testo del secondo comma."
    )

    assert result.comma_index == 2
    assert result.chunk_text == "Testo del secondo comma."
    assert result.source == "cap"


def test_from_enriched_to_embeddable_chunk_fetches_context_from_article_contexts() -> None:
    article = _enriched(contexts={1: "Contesto per il comma 1."})

    result = ArticleMapper.from_enriched_to_embeddable_chunk(
        article, source="cds", comma_index=1, raw_text="Testo."
    )

    assert result.context == "Contesto per il comma 1."


def test_from_enriched_to_embeddable_chunk_defaults_context_to_empty_string_when_missing() -> None:
    article = _enriched(contexts={})

    result = ArticleMapper.from_enriched_to_embeddable_chunk(
        article, source="cds", comma_index=3, raw_text="Testo."
    )

    assert result.context == ""


def test_from_enriched_to_embeddable_chunk_marks_repealed_when_article_is_repealed() -> None:
    article = _enriched(repealed=True)

    result = ArticleMapper.from_enriched_to_embeddable_chunk(
        article, source="cds", comma_index=0, raw_text="Testo qualsiasi."
    )

    assert result.is_repealed is True


def test_from_enriched_to_embeddable_chunk_marks_repealed_when_text_contains_abrogat() -> None:
    article = _enriched(repealed=False)

    result = ArticleMapper.from_enriched_to_embeddable_chunk(
        article, source="cds", comma_index=0, raw_text="Comma ABROGATO dal D.Lgs. 150/2021."
    )

    assert result.is_repealed is True


def test_from_enriched_to_embeddable_chunk_not_repealed_when_neither() -> None:
    article = _enriched(repealed=False)

    result = ArticleMapper.from_enriched_to_embeddable_chunk(
        article, source="cds", comma_index=0, raw_text="Testo valido."
    )

    assert result.is_repealed is False


# --- from_embeddable_chunk_to_knowledge_chunk ---


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
