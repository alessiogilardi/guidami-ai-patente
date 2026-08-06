import json
from pathlib import Path

import pytest
from scrapers.amb_extract import extract_amb


def _article(number: str) -> dict[str, object]:
    return {
        "number": number,
        "title": f"Titolo {number}",
        "commas": [{"number": "1", "text": f"Testo {number}"}],
        "url": f"http://example/{number}",
        "scraped_at": "2026-08-06T00:00:00+00:00",
        "repealed": False,
    }


def test_extract_amb_filters_by_leading_numeric_part(tmp_path: Path) -> None:
    numbers = ["226", "227", "228", "236", "237", "238", "232-bis"]
    articles = [_article(number) for number in numbers]
    source_path = tmp_path / "codice_ambiente.json"
    dest_path = tmp_path / "codice_ambiente_rifiuti.json"
    source_path.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")

    extract_amb(source_path, dest_path, ["227-237"])

    written = json.loads(dest_path.read_text(encoding="utf-8"))
    assert [article["number"] for article in written] == [
        "227",
        "228",
        "236",
        "237",
        "232-bis",
    ]


def test_extract_amb_raises_on_empty_range_match(tmp_path: Path) -> None:
    articles = [_article(str(number)) for number in range(1, 11)]
    source_path = tmp_path / "codice_ambiente.json"
    dest_path = tmp_path / "codice_ambiente_rifiuti.json"
    source_path.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="500-600"):
        extract_amb(source_path, dest_path, ["500-600"])

    assert not dest_path.exists()
