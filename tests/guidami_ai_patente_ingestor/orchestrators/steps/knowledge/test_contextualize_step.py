"""Test per ContextualizeStep."""

from unittest.mock import MagicMock

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import ContextualizeStep


def _make_article(number: str, repealed: bool = False) -> Article:
    return Article(
        number=number,
        title=f"Articolo {number}",
        text=f"Testo {number}.",
        paragraphs=[f"Comma 1 art {number}."],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=repealed,
    )


def test_required_keys() -> None:
    agent = MagicMock(spec=ArticleContextualizerAgent)
    step = ContextualizeStep("contextualize", agent)
    assert step.get_required_keys() == {context_keys.CLEANED_ARTICLES}


def test_produced_keys() -> None:
    agent = MagicMock(spec=ArticleContextualizerAgent)
    step = ContextualizeStep("contextualize", agent)
    assert step.get_produced_keys() == {context_keys.ENRICHED_ARTICLES}


def test_execute_delegates_to_agent_for_each_article() -> None:
    articles = [_make_article("1"), _make_article("2")]
    agent = MagicMock(spec=ArticleContextualizerAgent)
    agent.contextualize.return_value = {0: "Contesto."}
    context = FlowContext({context_keys.CLEANED_ARTICLES: articles})

    step = ContextualizeStep("contextualize", agent)
    step.execute(context)

    assert agent.contextualize.call_count == 2
    for call, article in zip(agent.contextualize.call_args_list, articles, strict=True):
        assert call.args[0] is article


def test_execute_produces_enriched_articles_with_contexts() -> None:
    articles = [_make_article("1"), _make_article("2")]
    agent = MagicMock(spec=ArticleContextualizerAgent)
    agent.contextualize.return_value = {0: "Contesto."}
    context = FlowContext({context_keys.CLEANED_ARTICLES: articles})

    step = ContextualizeStep("contextualize", agent)
    step.execute(context)

    result: list[EnrichedArticle] = context.get(context_keys.ENRICHED_ARTICLES)
    assert len(result) == 2
    assert all(isinstance(a, EnrichedArticle) for a in result)
    assert all(a.contexts == {0: "Contesto."} for a in result)


def test_execute_skips_repealed_articles_with_empty_contexts() -> None:
    articles = [_make_article("1", repealed=True)]
    agent = MagicMock(spec=ArticleContextualizerAgent)
    agent.contextualize.return_value = {}
    context = FlowContext({context_keys.CLEANED_ARTICLES: articles})

    step = ContextualizeStep("contextualize", agent)
    step.execute(context)

    result: list[EnrichedArticle] = context.get(context_keys.ENRICHED_ARTICLES)
    assert result[0].contexts == {}
    assert result[0].repealed is True
