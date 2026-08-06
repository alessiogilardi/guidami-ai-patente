"""Shared article-range filtering core, reused by `rca_extract.py` and `amb_extract.py`.

Both scripts narrow a fully-scraped law down to the article ranges relevant to this
project, differing only in source/dest paths and which `IngestorConfig` field carries
the ranges; the filtering algorithm itself is identical, so it lives here once.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_LEADING_NUMBER_PATTERN = re.compile(r"^\d+")


def _parse_range(range_str: str) -> tuple[int, int]:
    start, end = range_str.split("-")
    return int(start), int(end)


def _leading_number(article_number: str) -> int:
    match = _LEADING_NUMBER_PATTERN.match(article_number)
    if match is None:
        raise ValueError(f"Article number {article_number!r} has no leading numeric part")
    return int(match.group())


def filter_articles_by_range(source_path: Path, dest_path: Path, ranges: list[str]) -> None:
    """Filter the articles at `source_path` down to `ranges`, writing `dest_path`.

    Args:
        source_path: path to a full law's parsed JSON array (`ArticleRecord`-shaped
            dicts, i.e. the output of `scrapers.normattiva:main`).
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
            raise ValueError(f"Range {range_str!r} matched no articles")

    dest_path.write_text(
        json.dumps(filtered, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
