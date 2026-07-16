# guidami-ai-patente

Tool that makes Italian driving exam information freely accessible. Aggregates official questions, regulations, and reference material so users can study and query it without paywalls.

End goal: a **quiz bot** (FastAPI) that checks answers deterministically and explains them using RAG over the corpus normativo (CdS + CAP). Currently in the **data ingestion phase**.

## Setup

```bash
# Install dependencies
uv sync

# Copy and fill secrets
cp .env.example .env

# Start Postgres + pgvector
cd docker && docker compose up -d
```

## Commands

### Scraping

```bash
uv run scrape-codice          # Scrapes CdS → data/raw/cds/, data/parsed/cds/
uv run scrape-cap             # Scrapes CAP → data/raw/cap/, data/parsed/cap/
uv run parse-domande          # Parses quiz PDF → data/parsed/quiz-patente-ab/
```

### Ingestion

```bash
# Preparation (parsed → cleaned → enriched; skips if output exists)
uv run ingest prepare knowledge --source <cds|cap> [--force]
uv run ingest prepare quiz [--force]

# Indexing (enriched → DB; always full-reload)
uv run ingest index knowledge --source <cds|cap>
uv run ingest index quiz

# Reset (full wipe)
uv run ingest reset knowledge
uv run ingest reset quiz

# Status (config + per-command readiness; --online also checks Postgres)
uv run ingest status [--online]
```

See [`docs/`](./docs/README.md) for architecture, database schema, and design plans.

### Development

```bash
uv run pytest                 # Run tests (skips integration tests)
uv run ruff check src tests   # Lint
uv run ruff format src tests  # Format
uv run pyright                # Type check
```
