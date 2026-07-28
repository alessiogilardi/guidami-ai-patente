import pytest

from guidami_ai_patente_ingestor.models.knowledge import CleanedArticleModel


def _article(**kwargs) -> CleanedArticleModel:
    defaults = dict(
        number="1",
        title="Finalità",
        text="Testo articolo 1.",
        paragraphs=["Primo comma.", "Secondo comma."],
        url="https://example.com/art-1",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
        source="cds",
    )
    return CleanedArticleModel(**{**defaults, **kwargs})


def test_cleaned_article_requires_source() -> None:
    article = _article(source="cap")
    assert article.source == "cap"


def test_cleaned_article_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="source"):
        _article(source="unknown")


def test_cleaned_article_round_trips_through_json() -> None:
    original = _article(source="cds")
    restored = CleanedArticleModel.model_validate(original.model_dump())
    assert restored == original
