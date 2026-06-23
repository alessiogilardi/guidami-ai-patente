"""Test per CleanArticlesStep."""

from unittest.mock import MagicMock

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.knowledge import CleanArticlesStep
from guidami_ai_patente_ingestor.services.knowledge import ArticleCleaner


def _make_article(number: str) -> Article:
    return Article(
        number=number,
        title=f"(Articolo {number})",
        text=f"Testo {number}.",
        paragraphs=[f"1. Comma 1 art {number}."],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
    )


def test_required_keys() -> None:
    step = CleanArticlesStep("clean", ArticleCleaner())
    assert step.get_required_keys() == {context_keys.PARSED_ARTICLES}


def test_produced_keys() -> None:
    step = CleanArticlesStep("clean", ArticleCleaner())
    assert step.get_produced_keys() == {context_keys.CLEANED_ARTICLES}


def test_execute_delegates_to_cleaner_for_each_article() -> None:
    articles = [_make_article("1"), _make_article("2")]
    mock_cleaner = MagicMock(spec=ArticleCleaner)
    mock_cleaner.clean.side_effect = lambda article: article
    context = FlowContext({context_keys.PARSED_ARTICLES: articles})

    step = CleanArticlesStep("clean", mock_cleaner)
    step.execute(context)

    assert mock_cleaner.clean.call_count == 2
    for call, article in zip(mock_cleaner.clean.call_args_list, articles, strict=True):
        assert call.args[0] is article


def test_execute_produces_cleaned_articles_list_in_context() -> None:
    articles = [_make_article("1"), _make_article("2")]
    context = FlowContext({context_keys.PARSED_ARTICLES: articles})

    step = CleanArticlesStep("clean", ArticleCleaner())
    step.execute(context)

    result: list[Article] = context.get(context_keys.CLEANED_ARTICLES)
    assert len(result) == 2
    assert all(not article.title.startswith("(") for article in result)


def test_execute_preserves_order() -> None:
    articles = [_make_article("1"), _make_article("2"), _make_article("3")]
    context = FlowContext({context_keys.PARSED_ARTICLES: articles})

    step = CleanArticlesStep("clean", ArticleCleaner())
    step.execute(context)

    result: list[Article] = context.get(context_keys.CLEANED_ARTICLES)
    assert [a.number for a in result] == ["1", "2", "3"]
