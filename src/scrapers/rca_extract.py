"""Extract the RCA (assicurazione responsabilita civile auto) article ranges.

Filters `codice_assicurazioni_private.json` (the full CAP corpus, scraped by
`scrapers.normattiva:main_cap`) down to the article ranges configured on
`IngestorConfig.rca_ranges`, producing `codice_rca.json`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from guidami_ai_patente_ingestor.configs import IngestorConfig

_LEADING_NUMBER_PATTERN = re.compile(r"^\d+")

_SOURCE_PATH = Path("data/parsed/cap/codice_assicurazioni_private.json")
_DEST_PATH = Path("data/parsed/cap/codice_rca.json")


def _parse_range(range_str: str) -> tuple[int, int]:
    start, end = range_str.split("-")
    return int(start), int(end)


def _leading_number(article_number: str) -> int:
    match = _LEADING_NUMBER_PATTERN.match(article_number)
    if match is None:
        raise ValueError(f"Article number {article_number!r} has no leading numeric part")
    return int(match.group())


def extract_rca(source_path: Path, dest_path: Path, ranges: list[str]) -> None:
    """Filter the articles at `source_path` down to `ranges`, writing `dest_path`.

    Args:
        source_path: path to the full CAP corpus JSON array (`ArticleRecord`-shaped
            dicts, i.e. the output of `main_cap`).
        dest_path: path the filtered JSON array is written to.
        ranges: inclusive `"{start}-{end}"` ranges over the article's leading numeric
            part (e.g. `"119-bis"` matches `119`).

    Raises:
        ValueError: if any configured range matches zero articles. No output file is
            written in that case.
    """
    articles: list[dict[str, object]] = json.loads(source_path.read_text(encoding="utf-8"))
    parsed_ranges = [_parse_range(range_str) for range_str in ranges]

    filtered: list[dict[str, object]] = []
    match_counts = [0] * len(parsed_ranges)
    for article in articles:
        leading_number = _leading_number(str(article["number"]))
        matched_any = False
        for range_index, (start, end) in enumerate(parsed_ranges):
            if start <= leading_number <= end:
                match_counts[range_index] += 1
                matched_any = True
        if matched_any:
            filtered.append(article)

    for range_str, match_count in zip(ranges, match_counts, strict=True):
        if match_count == 0:
            raise ValueError(f"RCA range {range_str!r} matched no articles")

    dest_path.write_text(
        json.dumps(filtered, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    """Filter the full CAP corpus down to the configured RCA article ranges."""
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]
    extract_rca(_SOURCE_PATH, _DEST_PATH, config.rca_ranges)


if __name__ == "__main__":
    main()
