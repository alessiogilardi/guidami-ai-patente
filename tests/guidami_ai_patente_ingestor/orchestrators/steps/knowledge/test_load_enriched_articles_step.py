"""Test per LoadEnrichedArticlesStep."""

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


def _make_repo(articles_by_source: dict[str, list[EnrichedArticle]]) -> EnrichedArticleRepository:
    repo = MagicMock(spec=EnrichedArticleRepository)
    repo.load.side_effect = lambda path: articles_by_source.get(path.parent.name, [])
    return repo


def test_required_keys_is_empty_set() -> None:
    repo = MagicMock(spec=EnrichedArticleRepository)
    resolver = _make_layer_resolver()
    step = LoadEnrichedArticlesStep(
        "load", repo, resolver, input_layer="enriched", sources=["cds", "cap"]
    )
    assert step.get_required_keys() == set()


def test_produced_keys_contains_articles_by_source() -> None:
    repo = MagicMock(spec=EnrichedArticleRepository)
    resolver = _make_layer_resolver()
    step = LoadEnrichedArticlesStep(
        "load", repo, resolver, input_layer="enriched", sources=["cds", "cap"]
    )
    assert step.get_produced_keys() == {context_keys.ARTICLES_BY_SOURCE}


def test_execute_loads_each_source_and_puts_dict_in_context() -> None:
    cds_articles = [_make_article("1"), _make_article("2")]
    cap_articles = [_make_article("3")]

    repo = MagicMock(spec=EnrichedArticleRepository)
    resolver = _make_layer_resolver()
    repo.load.side_effect = lambda path: (
        cds_articles if "cds" in str(path) else cap_articles if "cap" in str(path) else []
    )

    step = LoadEnrichedArticlesStep(
        "load", repo, resolver, input_layer="enriched", sources=["cds", "cap"]
    )
    context = FlowContext()
    step.execute(context)

    result: dict[str, list[EnrichedArticle]] = context.get(context_keys.ARTICLES_BY_SOURCE)
    assert set(result.keys()) == {"cds", "cap"}
    assert result["cds"] is cds_articles
    assert result["cap"] is cap_articles


def test_execute_calls_resolver_for_each_source() -> None:
    repo = MagicMock(spec=EnrichedArticleRepository)
    repo.load.return_value = []
    resolver = _make_layer_resolver()

    step = LoadEnrichedArticlesStep(
        "load", repo, resolver, input_layer="enriched", sources=["cds", "cap"]
    )
    context = FlowContext()
    step.execute(context)

    assert resolver.path.call_count == 2
    called_sources = {call.args[1] for call in resolver.path.call_args_list}
    assert called_sources == {"cds", "cap"}


def test_execute_with_single_source() -> None:
    quiz_articles = [_make_article("Q1")]
    repo = MagicMock(spec=EnrichedArticleRepository)
    repo.load.return_value = quiz_articles
    resolver = _make_layer_resolver()

    step = LoadEnrichedArticlesStep(
        "load", repo, resolver, input_layer="enriched", sources=["quiz"]
    )
    context = FlowContext()
    step.execute(context)

    result: dict[str, list[EnrichedArticle]] = context.get(context_keys.ARTICLES_BY_SOURCE)
    assert list(result.keys()) == ["quiz"]
    assert result["quiz"] is quiz_articles
