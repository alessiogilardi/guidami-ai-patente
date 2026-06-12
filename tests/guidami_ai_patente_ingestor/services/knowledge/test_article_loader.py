from pathlib import Path

from guidami_ai_patente_ingestor.services.knowledge import ArticleLoader

FIXTURES_DIR = Path(__file__).parents[2] / "fixtures"


def test_load_maps_json_fields_into_articles() -> None:
    articles = ArticleLoader().load(FIXTURES_DIR / "cds_sample.json")

    assert [article.number for article in articles] == ["1", "2", "94-bis", "231"]

    article_1 = articles[0]
    assert article_1.title == "Principi generali"
    assert article_1.repealed is False
    assert article_1.text.startswith("((1. La sicurezza")
    assert len(article_1.paragraphs) == 4
    assert article_1.url.startswith("https://www.normattiva.it/")


def test_load_maps_repealed_article_with_empty_text() -> None:
    articles = ArticleLoader().load(FIXTURES_DIR / "cap_sample.json")

    article_118 = articles[0]
    assert article_118.number == "118"
    assert article_118.text == ""
    assert article_118.repealed is True
    assert len(article_118.paragraphs) == 4
