"""Test per WriteCleanedStep (per-source)."""

from pathlib import Path
from unittest.mock import MagicMock

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import WriteCleanedStep
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


def test_required_keys() -> None:
    repo = MagicMock(spec=ArticleRepository)
    resolver = _make_layer_resolver()
    step = WriteCleanedStep("write", repo, resolver, output_layer="cleaned", source="cds")
    assert step.get_required_keys() == {context_keys.CLEANED_ARTICLES}


def test_produced_keys_is_empty_set() -> None:
    repo = MagicMock(spec=ArticleRepository)
    resolver = _make_layer_resolver()
    step = WriteCleanedStep("write", repo, resolver, output_layer="cleaned", source="cds")
    assert step.get_produced_keys() == set()


def test_execute_writes_cleaned_articles_to_resolved_path() -> None:
    articles = [_make_article("1"), _make_article("2")]
    repo = MagicMock(spec=ArticleRepository)
    resolver = _make_layer_resolver()
    context = FlowContext({context_keys.CLEANED_ARTICLES: articles})

    step = WriteCleanedStep("write", repo, resolver, output_layer="cleaned", source="cds")
    step.execute(context)

    resolver.path.assert_called_once_with("cleaned", "cds")
    repo.write.assert_called_once_with(articles, Path("/fake/cleaned/cds/articles.json"))
