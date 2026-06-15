from pathlib import Path

from guidami_ai_patente_ingestor.repositories import ArticleRepository

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures"


def test_load_maps_json_fields_into_articles() -> None:
    articles = ArticleRepository().load(FIXTURES_DIR / "cds_sample.json")

    article_1 = next(article for article in articles if article.number == "1")
    assert article_1.title == "Principi generali"
    assert article_1.repealed is False
    assert article_1.text.startswith("((1. La sicurezza")
    assert len(article_1.paragraphs) == 4
    assert article_1.url.startswith("https://www.normattiva.it/")


def test_load_maps_repealed_article_with_empty_text() -> None:
    articles = ArticleRepository().load(FIXTURES_DIR / "cap_sample.json")

    article_118 = articles[0]
    assert article_118.number == "118"
    assert article_118.text == ""
    assert article_118.repealed is True
    assert len(article_118.paragraphs) == 4


def test_write_then_load_round_trips_articles(tmp_path: Path) -> None:
    repository = ArticleRepository()
    articles = repository.load(FIXTURES_DIR / "cds_sample.json")

    output_path = tmp_path / "cleaned" / "cds" / "codice_della_strada.json"
    repository.write(articles, output_path)

    assert output_path.exists()
    reloaded = repository.load(output_path)
    assert reloaded == articles
