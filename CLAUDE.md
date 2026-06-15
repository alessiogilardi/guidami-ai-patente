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

## Architettura

- Progettazione (anche non ancora implementata): `plans/`. Prima di iniziare un
  task implementativo, leggere sempre i piani partendo da
  [plans/architecture-index.md](plans/architecture-index.md) e seguendo i
  documenti collegati.
- Decisioni architetturali **effettivamente implementate**:
  [.claude/architectures/index.md](.claude/architectures/index.md). Al termine
  di un task implementativo, invocare l'agente `architecture-doc-keeper`
  (definito in [.claude/agents/architecture-doc-keeper.md](.claude/agents/architecture-doc-keeper.md))
  per aggiornare questa cartella con le decisioni prese e il design
  effettivamente realizzato — non modificare direttamente i file in
  `.claude/architectures/`.

## Code Conventions

- Pydantic config classes (anything under `configs/`) must set
  `model_config = ConfigDict(frozen=True)` — configurations are immutable
  once loaded.
- Root configuration classes loaded at the entry point (`main.py`) that need
  values from outside the codebase must use `pydantic_settings.BaseSettings`
  with the two-level pattern: a committed, non-secret YAML file under
  `configs/<service>_config.yaml` (via `SettingsConfigDict(yaml_file=...)`
  and a `YamlConfigSettingsSource`), plus env vars / `.env` for secrets only
  (`env_nested_delimiter="__"`, `env_file=".env"`). Override
  `settings_customise_sources` so env/`.env` (secrets) take precedence over
  the YAML (non-secrets). `model_config` must still set `frozen=True`. See
  `IngestorConfig` (`src/guidami_ai_patente_ingestor/configs/ingestor_config.py`)
  and `.claude/architectures/ingestor.md` for the reference implementation.

## Data Notes

- `data/docs/domande AB italiano 23 04 2025.pdf` — official question bank for categories A/B, Italian language, dated April 2025.
- When scraping, prefer storing raw HTML/PDF alongside parsed output so re-parsing is possible without re-fetching.
- Source URLs and scrape timestamps must be recorded with every document.
