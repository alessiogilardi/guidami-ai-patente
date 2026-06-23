"""Test per LoadCleanedArticlesStep (per-source)."""

from pathlib import Path
from unittest.mock import MagicMock

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import LoadCleanedArticlesStep
from guidami_ai_patente_ingestor.repositories import ArticleRepository
from guidami_ai_patente_ingestor.services import LayerResolver


def _make_article(number: str) -> Article:
    return Article(
        number=number,
        title=f"Articolo {number}",
        text=f"Testo {number}.",
        paragraphs=[f"Comma 1 art {number}."],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
    )


def _make_layer_resolver() -> LayerResolver:
    resolver = MagicMock(spec=LayerResolver)
    resolver.path.side_effect = lambda layer, src: Path(f"/fake/{layer}/{src}/articles.json")
    return resolver


def test_required_keys_is_empty_set() -> None:
    repo = MagicMock(spec=ArticleRepository)
    resolver = _make_layer_resolver()
    step = LoadCleanedArticlesStep("load", repo, resolver, input_layer="cleaned", source="cds")
    assert step.get_required_keys() == set()


def test_produced_keys_contains_cleaned_articles() -> None:
    repo = MagicMock(spec=ArticleRepository)
    resolver = _make_layer_resolver()
    step = LoadCleanedArticlesStep("load", repo, resolver, input_layer="cleaned", source="cds")
    assert step.get_produced_keys() == {context_keys.CLEANED_ARTICLES}


def test_execute_loads_source_and_puts_flat_list_in_context() -> None:
    articles = [_make_article("1"), _make_article("2")]
    repo = MagicMock(spec=ArticleRepository)
    repo.load.return_value = articles
    resolver = _make_layer_resolver()

    step = LoadCleanedArticlesStep("load", repo, resolver, input_layer="cleaned", source="cds")
    context = FlowContext()
    step.execute(context)

    result: list[Article] = context.get(context_keys.CLEANED_ARTICLES)
    assert result is articles


def test_execute_resolves_path_for_the_configured_source() -> None:
    repo = MagicMock(spec=ArticleRepository)
    repo.load.return_value = []
    resolver = _make_layer_resolver()

    step = LoadCleanedArticlesStep("load", repo, resolver, input_layer="cleaned", source="cap")
    step.execute(FlowContext())

    resolver.path.assert_called_once_with("cleaned", "cap")
