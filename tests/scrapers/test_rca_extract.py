import json
from pathlib import Path

import pytest
from scrapers.rca_extract import extract_rca


def _article(number: str) -> dict[str, object]:
    return {
        "number": number,
        "title": f"Titolo {number}",
        "commas": [{"number": "1", "text": f"Testo {number}"}],
        "url": f"http://example/{number}",
        "scraped_at": "2026-07-31T00:00:00+00:00",
        "repealed": False,
    }


def test_extract_rca_filters_by_leading_numeric_part(tmp_path: Path) -> None:
    numbers = ["117", "118", "119-bis", "165", "166", "277", "278", "300", "301"]
    articles = [_article(number) for number in numbers]
    source_path = tmp_path / "codice_assicurazioni_private.json"
    dest_path = tmp_path / "codice_rca.json"
    source_path.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")

    extract_rca(source_path, dest_path, ["118-165", "278-300"])

    written = json.loads(dest_path.read_text(encoding="utf-8"))
    assert [article["number"] for article in written] == ["118", "119-bis", "165", "278", "300"]
    expected_by_number = {article["number"]: article for article in articles}
    for article in written:
        assert article == expected_by_number[article["number"]]


def test_extract_rca_raises_on_empty_range_match(tmp_path: Path) -> None:
    articles = [_article(str(number)) for number in range(1, 11)]
    source_path = tmp_path / "codice_assicurazioni_private.json"
    dest_path = tmp_path / "codice_rca.json"
    source_path.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="500-600"):
        extract_rca(source_path, dest_path, ["500-600"])

    assert not dest_path.exists()
