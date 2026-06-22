"""Test per LoadEnrichedArticlesStep (per-source)."""

from pathlib import Path
from unittest.mock import MagicMock

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import (
    LoadEnrichedArticlesStep,
)
from guidami_ai_patente_ingestor.repositories import EnrichedArticleRepository
from guidami_ai_patente_ingestor.services import LayerResolver


def _make_article(number: str) -> EnrichedArticle:
    return EnrichedArticle(
        number=number,
        title=f"Articolo {number}",
        text=f"Testo {number}.",
        paragraphs=[f"Comma 1 art {number}."],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
        contexts={},
    )


def _make_layer_resolver() -> LayerResolver:
    resolver = MagicMock(spec=LayerResolver)
    resolver.path.side_effect = lambda layer, src: Path(f"/fake/{layer}/{src}/articles.json")
    return resolver


def test_required_keys_is_empty_set() -> None:
    repo = MagicMock(spec=EnrichedArticleRepository)
    resolver = _make_layer_resolver()
    step = LoadEnrichedArticlesStep("load", repo, resolver, input_layer="enriched", source="cds")
    assert step.get_required_keys() == set()


def test_produced_keys_contains_enriched_articles() -> None:
    repo = MagicMock(spec=EnrichedArticleRepository)
    resolver = _make_layer_resolver()
    step = LoadEnrichedArticlesStep("load", repo, resolver, input_layer="enriched", source="cds")
    assert step.get_produced_keys() == {context_keys.ENRICHED_ARTICLES}


def test_execute_loads_source_and_puts_flat_list_in_context() -> None:
    articles = [_make_article("1"), _make_article("2")]
    repo = MagicMock(spec=EnrichedArticleRepository)
    repo.load.return_value = articles
    resolver = _make_layer_resolver()

    step = LoadEnrichedArticlesStep("load", repo, resolver, input_layer="enriched", source="cds")
    context = FlowContext()
    step.execute(context)

    result: list[EnrichedArticle] = context.get(context_keys.ENRICHED_ARTICLES)
    assert result is articles


def test_execute_resolves_path_for_the_configured_source() -> None:
    repo = MagicMock(spec=EnrichedArticleRepository)
    repo.load.return_value = []
    resolver = _make_layer_resolver()

    step = LoadEnrichedArticlesStep("load", repo, resolver, input_layer="enriched", source="cap")
    step.execute(FlowContext())

    resolver.path.assert_called_once_with("enriched", "cap")
