import json
from pathlib import Path

from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle
from guidami_ai_patente_ingestor.repositories import EnrichedArticleRepository


def _article(number: str, contexts: dict[int, str] | None = None) -> EnrichedArticle:
    return EnrichedArticle(
        number=number,
        title=f"Articolo {number}",
        text="Testo.",
        paragraphs=["Comma 1.", "Comma 2."],
        url=f"https://example.com/art-{number}",
        scraped_at="2025-01-01T00:00:00",
        repealed=False,
        contexts=contexts or {},
    )


def test_write_then_load_round_trips_articles(tmp_path: Path) -> None:
    path = tmp_path / "enriched" / "cds.json"
    articles = [_article("1", {0: "Contesto comma 0.", 1: "Contesto comma 1."})]

    repo = EnrichedArticleRepository()
    repo.write(articles, path)
    loaded = repo.load(path)

    assert len(loaded) == 1
    assert loaded[0].number == "1"
    assert loaded[0].contexts[0] == "Contesto comma 0."
    assert loaded[0].contexts[1] == "Contesto comma 1."


def test_write_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "nested" / "enriched.json"
    repo = EnrichedArticleRepository()
    repo.write([_article("1")], path)
    assert path.exists()


def test_load_returns_empty_list_for_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")
    repo = EnrichedArticleRepository()
    assert repo.load(path) == []


def test_write_preserves_utf8_characters(tmp_path: Path) -> None:
    path = tmp_path / "enriched.json"
    articles = [_article("1", {0: "È obbligatorio indossare le cinture."})]
    repo = EnrichedArticleRepository()
    repo.write(articles, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw[0]["contexts"]["0"] == "È obbligatorio indossare le cinture."
