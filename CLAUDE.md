# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

**guidami-ai-patente** is a tool that makes Italian driving exam information freely accessible. It aggregates official questions, regulations, and reference material — currently scraped from the web and from PDFs — so users can study and query it without paywalls.

The project is in the **data collection phase**: sourcing documents, scraping regulatory sites, and parsing PDFs. No user-facing product exists yet.

## Environment & Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run a single test
uv run pytest tests/path/to/test_file.py::test_name

# Add a dependency
uv add <package>
```

### Available scripts

| Command | Entry point | Output |
|---|---|---|
| `uv run scrape-codice` | `scrapers.normattiva:main_cds` | `data/raw/cds/`, `data/processed/cds/codice_della_strada.json` |
| `uv run scrape-cap` | `scrapers.normattiva:main_cap` | `data/raw/cap/`, `data/processed/cap/codice_assicurazioni_private.json` |
| `uv run parse-domande` | `parsers.domande_pdf:main_domande` | `data/processed/quiz-patente-ab/quiz-patente-ab.json`, `data/processed/quiz-patente-ab/images/` |

Register new CLI commands under `[project.scripts]` in `pyproject.toml`.

## Data Notes

- `data/docs/domande AB italiano 23 04 2025.pdf` — official question bank for categories A/B, Italian language, dated April 2025.
- When scraping, prefer storing raw HTML/PDF alongside parsed output so re-parsing is possible without re-fetching.
- Source URLs and scrape timestamps must be recorded with every document.
