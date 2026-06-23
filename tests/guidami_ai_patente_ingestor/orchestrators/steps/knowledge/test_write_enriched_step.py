"""Test per WriteEnrichedStep (per-source)."""

from pathlib import Path
from unittest.mock import MagicMock

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import WriteEnrichedStep
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
        contexts={0: "Contesto."},
    )


def _make_layer_resolver() -> LayerResolver:
    resolver = MagicMock(spec=LayerResolver)
    resolver.path.side_effect = lambda layer, src: Path(f"/fake/{layer}/{src}/articles.json")
    return resolver


def test_required_keys() -> None:
    repo = MagicMock(spec=EnrichedArticleRepository)
    resolver = _make_layer_resolver()
    step = WriteEnrichedStep("write", repo, resolver, output_layer="enriched", source="cds")
    assert step.get_required_keys() == {context_keys.ENRICHED_ARTICLES}


def test_produced_keys_is_empty_set() -> None:
    repo = MagicMock(spec=EnrichedArticleRepository)
    resolver = _make_layer_resolver()
    step = WriteEnrichedStep("write", repo, resolver, output_layer="enriched", source="cds")
    assert step.get_produced_keys() == set()


def test_execute_writes_enriched_articles_to_resolved_path() -> None:
    articles = [_make_article("1"), _make_article("2")]
    repo = MagicMock(spec=EnrichedArticleRepository)
    resolver = _make_layer_resolver()
    context = FlowContext({context_keys.ENRICHED_ARTICLES: articles})

    step = WriteEnrichedStep("write", repo, resolver, output_layer="enriched", source="cds")
    step.execute(context)

    resolver.path.assert_called_once_with("enriched", "cds")
    repo.write.assert_called_once_with(articles, Path("/fake/enriched/cds/articles.json"))
