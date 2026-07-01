# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

**guidami-ai-patente** is a tool that makes Italian driving exam information freely accessible. It aggregates official questions, regulations, and reference material — currently scraped from the web and from PDFs — so users can study and query it without paywalls.

The end goal is a **quiz bot** (FastAPI) that checks answers deterministically and explains them using RAG over the corpus normativo (CdS + CAP). The project is currently in the **data ingestion phase**: infrastruttura Postgres/pgvector operativa, pipeline di ingestion corpus + quiz bank implementate. L'app FastAPI non è ancora avviata.

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

# Lint / format / type check
uv run ruff check src tests
uv run ruff format src tests
uv run pyright
```

### Infrastructure

```bash
# Start Postgres + pgvector (required for integration tests and ingestion)
cd docker && docker compose up -d

# Recreate DB from scratch (required after schema changes in db/init.sql)
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d
```

### Available scripts

| Command | Entry point | Description |
|---|---|---|
| `uv run scrape-codice` | `scrapers.normattiva:main_cds` | Scrapes CdS → `data/raw/cds/`, `data/parsed/cds/codice_della_strada.json` |
| `uv run scrape-cap` | `scrapers.normattiva:main_cap` | Scrapes CAP → `data/raw/cap/`, `data/parsed/cap/codice_rca.json` |
| `uv run parse-domande` | `parsers.questions_pdf:main_questions` | Parses quiz PDF → `data/parsed/quiz-patente-ab/` |
| `uv run ingest prepare knowledge --source <cds\|cap> [--force]` | `guidami_ai_patente_ingestor.cli:main` | Clean + enrich knowledge corpus for one source |
| `uv run ingest prepare quiz [--force]` | `guidami_ai_patente_ingestor.cli:main` | Prepare quiz bank (enriched with image descriptions) |
| `uv run ingest index knowledge --source <cds\|cap>` | `guidami_ai_patente_ingestor.cli:main` | Embed + store knowledge corpus for one source |
| `uv run ingest index quiz` | `guidami_ai_patente_ingestor.cli:main` | Embed + store quiz bank |
| `uv run ingest reset knowledge` | `guidami_ai_patente_ingestor.cli:main` | Truncates `knowledge_chunks` (full wipe) |
| `uv run ingest reset quiz` | `guidami_ai_patente_ingestor.cli:main` | Truncates `quiz_questions` (full wipe) |

Register new CLI commands under `[project.scripts]` in `pyproject.toml`.

### Secrets required

Copy `.env.example` to `.env` and fill in:
- `POSTGRES__USER` / `POSTGRES__PASSWORD` — DB credentials (double underscore = nested delimiter for `IngestorConfig.postgres`)
- `OPENROUTER_API_KEY` — required for embedding and LLM steps; read by litellm from the environment

## Architecture

Prima di iniziare qualsiasi task implementativo, leggere i documenti di riferimento:

- **Piani di progettazione** (inclusi quelli non ancora implementati): `plans/` — indice in `plans/_index.md`
- **Decisioni implementate**: `.claude/architectures/` — indice in `.claude/architectures/index.md`
- **Package layout, pipeline, layer dati, pattern di config**: `.claude/architectures/ingestor/index.md`
- **Schema DB e infrastruttura**: `.claude/architectures/infrastructure.md`

### Scrivere un piano

Un piano è obbligatorio prima di qualsiasi nuova funzionalità, modulo o cambio architetturale non banale. Regole complete in `.claude/rules/plan-writing.md`.

## Code Conventions

Vedi `.claude/rules/code-conventions.md`.

## Data Notes

- `data/docs/domande AB italiano 23 04 2025.pdf` — official question bank for categories A/B, Italian language, dated April 2025.
- `data/parsed/cap/codice_rca.json` — 96 articles relevant to RCA/patente (subset of full CAP).
- When scraping, prefer storing raw HTML/PDF alongside parsed output so re-parsing is possible without re-fetching.
- Source URLs and scrape timestamps must be recorded with every document.
