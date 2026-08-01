import pytest

from guidami_ai_patente_ingestor.models.knowledge import CleanedArticleModel, ParsedComma


def _article(**kwargs) -> CleanedArticleModel:
    defaults = dict(
        number="1",
        title="Finalità",
        commas=[
            ParsedComma(number="1", text="Primo comma."),
            ParsedComma(number="2", text="Secondo comma."),
        ],
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


def test_cleaned_article_model_has_commas_field() -> None:
    data = {
        "number": "142",
        "title": "Titolo articolo",
        "url": "https://example.com/art-142",
        "scraped_at": "2025-01-01T00:00:00",
        "repealed": False,
        "source": "cds",
        "commas": [{"number": "1", "text": "Testo del comma."}],
    }

    result = CleanedArticleModel.model_validate(data)

    assert result.commas == [ParsedComma(number="1", text="Testo del comma.")]
