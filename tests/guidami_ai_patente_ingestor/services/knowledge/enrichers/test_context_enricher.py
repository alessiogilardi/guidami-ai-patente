"""Tests for ContextEnricher (async, symmetric to the quiz enrichers)."""

from unittest.mock import MagicMock

from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
    ArticleContextualizerRequest,
    ArticleContextualizerResponse,
)
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel
from guidami_ai_patente_ingestor.services.knowledge.enrichers import ContextEnricher


def _article(
    number: str, repealed: bool = False, paragraphs: list[str] | None = None
) -> EnrichedArticleModel:
    return EnrichedArticleModel(
        number=number,
        title=f"Articolo {number}",
        text=f"Testo {number}.",
        paragraphs=paragraphs if paragraphs is not None else [f"Comma 1 art {number}."],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=repealed,
        source="cds",
        contexts={},
    )


def _make_agent(contexts: dict[int, str] | None = None) -> MagicMock:
    """Fake agent exposing an async `run` (auto-detected as AsyncMock via `spec`)."""
    agent = MagicMock(spec=ArticleContextualizerAgent)
    agent.run.return_value = ArticleContextualizerResponse(contexts=contexts or {0: "Contesto."})
    return agent


async def test_enrich_sets_contexts_from_agent() -> None:
    agent = _make_agent(contexts={0: "Contesto comma 1."})
    enricher = ContextEnricher(8, agent)
    articles = [_article("1")]

    result = await enricher(articles)

    assert result[0].contexts == {0: "Contesto comma 1."}


async def test_enrich_calls_agent_run_once_per_article() -> None:
    agent = _make_agent()
    enricher = ContextEnricher(8, agent)
    articles = [_article("1"), _article("2")]

    await enricher(articles)

    assert agent.run.call_count == 2


async def test_enrich_passes_correct_request_to_agent() -> None:
    agent = _make_agent()
    enricher = ContextEnricher(8, agent)
    article = _article("1")

    await enricher([article])

    request = agent.run.call_args.args[0]
    assert isinstance(request, ArticleContextualizerRequest)
    assert request.title == article.title
    assert request.text == article.text


async def test_enrich_empty_list_returns_empty_list() -> None:
    agent = _make_agent()
    enricher = ContextEnricher(8, agent)

    result = await enricher([])

    assert result == []
    agent.run.assert_not_called()


async def test_enrich_does_not_mutate_input_models() -> None:
    agent = _make_agent()
    enricher = ContextEnricher(8, agent)
    original = _article("1")

    await enricher([original])

    assert original.contexts == {}


async def test_enrich_skips_repealed_article_without_calling_agent() -> None:
    agent = _make_agent()
    enricher = ContextEnricher(8, agent)
    article = _article("1", repealed=True)

    result = await enricher([article])

    assert result[0].contexts == {}
    agent.run.assert_not_called()


async def test_enrich_skips_article_with_no_paragraphs_without_calling_agent() -> None:
    agent = _make_agent()
    enricher = ContextEnricher(8, agent)
    article = _article("1", paragraphs=[])

    result = await enricher([article])

    assert result[0].contexts == {}
    agent.run.assert_not_called()


async def test_enrich_agent_failure_on_one_item_returns_article_unchanged_and_warns(
    caplog,
) -> None:
    agent = _make_agent()

    async def side_effect(
        request: ArticleContextualizerRequest,
    ) -> ArticleContextualizerResponse:
        if "2" in request.title:
            raise RuntimeError("LLM call failed")
        return ArticleContextualizerResponse(contexts={0: "Contesto ok."})

    agent.run.side_effect = side_effect
    enricher = ContextEnricher(8, agent)
    articles = [_article("1"), _article("2"), _article("3")]

    with caplog.at_level("WARNING"):
        result = await enricher(articles)

    by_number = {article.number: article for article in result}
    assert by_number["1"].contexts == {0: "Contesto ok."}
    assert by_number["2"].contexts == {}
    assert by_number["3"].contexts == {0: "Contesto ok."}
    assert any("2" in record.message for record in caplog.records)
