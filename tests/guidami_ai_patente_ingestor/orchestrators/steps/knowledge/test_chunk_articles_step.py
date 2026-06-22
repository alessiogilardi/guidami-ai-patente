"""Test per ChunkArticlesStep."""

from unittest.mock import MagicMock

from commons.entities.knowledge import KnowledgeChunk
from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import ChunkArticlesStep
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker


def _make_article(number: str, repealed: bool = False) -> EnrichedArticle:
    return EnrichedArticle(
        number=number,
        title=f"Articolo {number}",
        text=f"Testo {number}.",
        paragraphs=[f"Comma 1 art {number}."],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=repealed,
        contexts={},
    )


def _make_chunk(source: str, number: str, repealed: bool = False) -> KnowledgeChunk:  # type: ignore[return]
    return KnowledgeChunk(
        source=source,  # type: ignore[arg-type]
        article_number=number,
        article_title=f"Articolo {number}",
        comma_index=0,
        chunk_text=f"Testo {number}.",
        is_repealed=repealed,
        source_url=f"https://example.com/art-{number}",
    )


def test_required_keys() -> None:
    step = ChunkArticlesStep("chunk", ArticleChunker())
    assert step.get_required_keys() == {context_keys.ARTICLES_BY_SOURCE}


def test_produced_keys() -> None:
    step = ChunkArticlesStep("chunk", ArticleChunker())
    assert step.get_produced_keys() == {context_keys.CHUNKS}


def test_execute_produces_chunks_for_all_sources() -> None:
    cds_article = _make_article("1")
    cap_article = _make_article("2")

    articles_by_source: dict[str, list[EnrichedArticle]] = {
        "cds": [cds_article],
        "cap": [cap_article],
    }
    context = FlowContext({context_keys.ARTICLES_BY_SOURCE: articles_by_source})

    step = ChunkArticlesStep("chunk", ArticleChunker())
    step.execute(context)

    chunks: list[KnowledgeChunk] = context.get(context_keys.CHUNKS)
    assert len(chunks) > 0

    sources_in_chunks = {c.source for c in chunks}
    assert sources_in_chunks == {"cds", "cap"}


def test_execute_includes_repealed_chunks_without_filter() -> None:
    """ChunkArticlesStep non filtra i repealed — li include tutti."""
    normal_article = _make_article("1", repealed=False)
    repealed_article = _make_article("2", repealed=True)

    articles_by_source: dict[str, list[EnrichedArticle]] = {
        "cds": [normal_article, repealed_article],
    }
    context = FlowContext({context_keys.ARTICLES_BY_SOURCE: articles_by_source})

    step = ChunkArticlesStep("chunk", ArticleChunker())
    step.execute(context)

    chunks: list[KnowledgeChunk] = context.get(context_keys.CHUNKS)
    repealed = [c for c in chunks if c.is_repealed]
    non_repealed = [c for c in chunks if not c.is_repealed]
    assert len(repealed) > 0, "i chunk repealed devono essere presenti"
    assert len(non_repealed) > 0, "i chunk non-repealed devono essere presenti"


def test_execute_flattens_chunks_from_multiple_articles() -> None:
    """Più articoli per source → flatten corretto."""
    articles = [_make_article("1"), _make_article("2"), _make_article("3")]
    articles_by_source: dict[str, list[EnrichedArticle]] = {"cds": articles}
    context = FlowContext({context_keys.ARTICLES_BY_SOURCE: articles_by_source})

    chunker = ArticleChunker()
    step = ChunkArticlesStep("chunk", chunker)
    step.execute(context)

    chunks: list[KnowledgeChunk] = context.get(context_keys.CHUNKS)
    # ogni articolo ha text + 1 paragraph → 2 chunk; 3 articoli → 6 chunk
    assert len(chunks) == 6


def test_execute_uses_chunker_for_each_article() -> None:
    """Lo step delega al chunker e lo invoca per ogni articolo."""
    cds_articles = [_make_article("1"), _make_article("2")]

    mock_chunker = MagicMock(spec=ArticleChunker)
    mock_chunker.chunk.return_value = []

    articles_by_source: dict[str, list[EnrichedArticle]] = {"cds": cds_articles}
    context = FlowContext({context_keys.ARTICLES_BY_SOURCE: articles_by_source})

    step = ChunkArticlesStep("chunk", mock_chunker)
    step.execute(context)

    assert mock_chunker.chunk.call_count == 2
    # verifica che la source "cds" sia passata a tutti i chunk calls
    for call in mock_chunker.chunk.call_args_list:
        assert call.args[1] == "cds"
