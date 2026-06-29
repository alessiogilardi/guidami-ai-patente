"""Test per ChunkArticlesStep (per-source)."""

from unittest.mock import MagicMock

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.models.knowledge import EmbeddableChunkModel, EnrichedArticleModel
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import ChunkArticlesStep
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker


def _make_article(number: str, repealed: bool = False) -> EnrichedArticleModel:
    return EnrichedArticleModel(
        number=number,
        title=f"Articolo {number}",
        text=f"Testo {number}.",
        paragraphs=[f"Comma 1 art {number}."],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=repealed,
        contexts={},
    )


def test_required_keys() -> None:
    step = ChunkArticlesStep("chunk", ArticleChunker(), source="cds")
    assert step.get_required_keys() == {context_keys.ENRICHED_ARTICLES}


def test_produced_keys() -> None:
    step = ChunkArticlesStep("chunk", ArticleChunker(), source="cds")
    assert step.get_produced_keys() == {context_keys.EMBEDDABLE_CHUNKS}


def test_execute_produces_chunks_tagged_with_the_injected_source() -> None:
    articles = [_make_article("1"), _make_article("2")]
    context = FlowContext({context_keys.ENRICHED_ARTICLES: articles})

    step = ChunkArticlesStep("chunk", ArticleChunker(), source="cap")
    step.execute(context)

    chunks: list[EmbeddableChunkModel] = context.get(context_keys.EMBEDDABLE_CHUNKS)
    assert len(chunks) > 0
    assert {c.source for c in chunks} == {"cap"}


def test_execute_includes_repealed_chunks_without_filter() -> None:
    """ChunkArticlesStep non filtra i repealed — li include tutti."""
    articles = [_make_article("1", repealed=False), _make_article("2", repealed=True)]
    context = FlowContext({context_keys.ENRICHED_ARTICLES: articles})

    step = ChunkArticlesStep("chunk", ArticleChunker(), source="cds")
    step.execute(context)

    chunks: list[EmbeddableChunkModel] = context.get(context_keys.EMBEDDABLE_CHUNKS)
    assert len([c for c in chunks if c.is_repealed]) > 0
    assert len([c for c in chunks if not c.is_repealed]) > 0


def test_execute_flattens_chunks_from_multiple_articles() -> None:
    """Più articoli → flatten corretto."""
    articles = [_make_article("1"), _make_article("2"), _make_article("3")]
    context = FlowContext({context_keys.ENRICHED_ARTICLES: articles})

    step = ChunkArticlesStep("chunk", ArticleChunker(), source="cds")
    step.execute(context)

    chunks: list[EmbeddableChunkModel] = context.get(context_keys.EMBEDDABLE_CHUNKS)
    # ogni articolo ha text + 1 paragraph → 2 chunk; 3 articoli → 6 chunk
    assert len(chunks) == 6


def test_execute_passes_injected_source_to_chunker_for_each_article() -> None:
    """Lo step delega al chunker, invocandolo per ogni articolo con la source iniettata."""
    articles = [_make_article("1"), _make_article("2")]
    mock_chunker = MagicMock(spec=ArticleChunker)
    mock_chunker.chunk.return_value = []
    context = FlowContext({context_keys.ENRICHED_ARTICLES: articles})

    step = ChunkArticlesStep("chunk", mock_chunker, source="cds")
    step.execute(context)

    assert mock_chunker.chunk.call_count == 2
    for call in mock_chunker.chunk.call_args_list:
        assert call.args[1] == "cds"
