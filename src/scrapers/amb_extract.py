"""Extract the waste-management (Titolo III) article ranges from D.Lgs. 152/2006.

Filters `codice_ambiente.json` (the full AMB corpus, scraped by
`scrapers.normattiva:main` with the `AMB` `LawConfig`) down to the article ranges
configured on `IngestorConfig.amb_ranges`, producing `codice_ambiente_rifiuti.json`.
"""

from __future__ import annotations

from pathlib import Path

from guidami_ai_patente_ingestor.configs import IngestorConfig

from .range_filter import filter_articles_by_range

_SOURCE_PATH = Path("data/parsed/amb/codice_ambiente.json")
_DEST_PATH = Path("data/parsed/amb/codice_ambiente_rifiuti.json")


def extract_amb(source_path: Path, dest_path: Path, ranges: list[str]) -> None:
    """Filter `source_path` down to `ranges`, writing `dest_path`.

    Thin, AMB-named wrapper over `range_filter.filter_articles_by_range`, kept as a
    stable entry point for `main()` and tests, symmetric with `rca_extract.extract_rca`.
    """
    filter_articles_by_range(source_path, dest_path, ranges)


def main() -> None:
    """Filter the full AMB corpus down to the configured waste-provision article ranges."""
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]
    extract_amb(_SOURCE_PATH, _DEST_PATH, config.amb_ranges)


if __name__ == "__main__":
    main()
