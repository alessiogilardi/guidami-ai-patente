"""Test per ContextEnricher."""

from unittest.mock import MagicMock

from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle
from guidami_ai_patente_ingestor.services.knowledge.enrichers import ContextEnricher


def _article(number: str, repealed: bool = False) -> EnrichedArticle:
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


def _make_agent() -> MagicMock:
    return MagicMock(spec=ArticleContextualizerAgent)


def test_enrich_sets_contexts_from_agent() -> None:
    agent = _make_agent()
    agent.contextualize.return_value = {0: "Contesto comma 1."}
    enricher = ContextEnricher(agent)
    articles = [_article("1")]

    result = enricher.enrich(articles)

    assert result[0].contexts == {0: "Contesto comma 1."}


def test_enrich_calls_agent_once_per_article() -> None:
    agent = _make_agent()
    agent.contextualize.return_value = {0: "Contesto."}
    enricher = ContextEnricher(agent)
    articles = [_article("1"), _article("2")]

    enricher.enrich(articles)

    assert agent.contextualize.call_count == 2
    for call, article in zip(agent.contextualize.call_args_list, articles, strict=True):
        assert call.args[0] is article


def test_enrich_empty_list_returns_empty_list() -> None:
    agent = _make_agent()
    enricher = ContextEnricher(agent)

    result = enricher.enrich([])

    assert result == []
    agent.contextualize.assert_not_called()


def test_enrich_does_not_mutate_input_models() -> None:
    agent = _make_agent()
    agent.contextualize.return_value = {0: "Contesto."}
    enricher = ContextEnricher(agent)
    original = _article("1")
    articles = [original]

    enricher.enrich(articles)

    assert original.contexts == {}


def test_enrich_agent_failure_on_one_item_skips_with_empty_contexts_and_warns(caplog) -> None:
    agent = _make_agent()

    def side_effect(article: EnrichedArticle) -> dict[int, str]:
        if article.number == "2":
            raise RuntimeError("LLM call failed")
        return {0: "Contesto ok."}

    agent.contextualize.side_effect = side_effect
    enricher = ContextEnricher(agent)
    articles = [_article("1"), _article("2"), _article("3")]

    with caplog.at_level("WARNING"):
        result = enricher.enrich(articles)

    by_number = {article.number: article for article in result}
    assert by_number["1"].contexts == {0: "Contesto ok."}
    assert by_number["2"].contexts == {}
    assert by_number["3"].contexts == {0: "Contesto ok."}
    assert any("2" in record.message for record in caplog.records)
