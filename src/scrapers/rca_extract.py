"""Extract the RCA (assicurazione responsabilita civile auto) article ranges.

Filters `codice_assicurazioni_private.json` (the full CAP corpus, scraped by
`scrapers.normattiva:main_cap`) down to the article ranges configured on
`IngestorConfig.rca_ranges`, producing `codice_rca.json`.
"""

from __future__ import annotations

from pathlib import Path

from guidami_ai_patente_ingestor.configs import IngestorConfig

from .range_filter import filter_articles_by_range

_SOURCE_PATH = Path("data/parsed/cap/codice_assicurazioni_private.json")
_DEST_PATH = Path("data/parsed/cap/codice_rca.json")


def extract_rca(source_path: Path, dest_path: Path, ranges: list[str]) -> None:
    """Filter `source_path` down to `ranges`, writing `dest_path`.

    Thin, RCA-named wrapper over `range_filter.filter_articles_by_range`, kept as a
    stable entry point for `main()` and existing callers/tests.
    """
    filter_articles_by_range(source_path, dest_path, ranges)


def main() -> None:
    """Filter the full CAP corpus down to the configured RCA article ranges."""
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]
    extract_rca(_SOURCE_PATH, _DEST_PATH, config.rca_ranges)


if __name__ == "__main__":
    main()
