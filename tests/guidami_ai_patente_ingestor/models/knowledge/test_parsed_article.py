import pytest
from pydantic import ValidationError

from guidami_ai_patente_ingestor.models.knowledge import ParsedArticleModel, ParsedComma


def _article_data(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "number": "142",
        "title": "Titolo articolo",
        "url": "https://example.com/art-142",
        "scraped_at": "2025-01-01T00:00:00",
        "repealed": False,
        "commas": [{"number": "1", "text": "Testo del comma."}],
    }
    return {**defaults, **overrides}


def test_parsed_article_model_has_commas_field() -> None:
    result = ParsedArticleModel.model_validate(_article_data())

    assert result.commas == [ParsedComma(number="1", text="Testo del comma.")]

    legacy_data = _article_data()
    del legacy_data["commas"]
    legacy_data["paragraphs"] = ["Testo del comma."]

    with pytest.raises(ValidationError):
        ParsedArticleModel.model_validate(legacy_data)
