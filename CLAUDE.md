# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

**guidami-ai-patente** is a tool that makes Italian driving exam information freely accessible. It aggregates official questions, regulations, and reference material — currently scraped from the web and from PDFs — so users can study and query it without paywalls.

The end goal is a **quiz bot** (FastAPI) that checks answers deterministically and explains them using RAG over the corpus normativo (CdS + CAP). The project is currently in the **data ingestion phase**: Postgres/pgvector infrastructure is running, corpus and quiz-bank ingestion pipelines are implemented. The FastAPI app has not been started yet.

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

Before starting any implementation task, read the reference documents:

- **Design plans** (including not-yet-implemented ones): `docs/plans/` — index at `docs/plans/_index.md`
- **Implemented decisions**: `docs/architecture/` — index at `docs/architecture/_index.md`
- **Package layout, pipelines, data layer, config patterns**: `docs/architecture/modules/ingestor/_index.md`
- **DB schema and infrastructure**: `docs/architecture/database/_index.md`

For any architecture question, start from `docs/architecture/_index.md`: it links all specific documents. Each subfolder has its own `_index.md` — read it before the detail files.

### Reading architecture documentation — `doc-reader`

**MUST** invoke the `doc-reader` agent (never Read `docs/architecture/` files directly) in every one of these situations:

- Before writing or reviewing any implementation plan
- Before starting any non-trivial implementation task (orientation phase)
- When answering any question about the project architecture, existing modules, or design decisions
- Before making any edit to `docs/architecture/` for any reason

`doc-reader` navigates `docs/architecture/` and returns structured content with source references.

### Updating architectural documentation — `doc-architect`

**MUST** invoke the `doc-architect` agent after every one of these events:

- Completing any implementation task (new feature, refactor, bugfix) that changes code in `src/`
- Making any architectural decision during a conversation (new pattern, naming convention, structural choice)
- Adding or removing a module, package, or significant component

Do not edit `docs/architecture/` directly — `doc-architect` reads existing content via `doc-reader` before writing, to prevent duplication. Pass it a concise summary of what changed and which decisions were made.

### Writing a plan

A plan is mandatory before any new feature, module, or non-trivial architectural change. Full rules in `.claude/rules/plan-writing.md`.

## Code Conventions

See `.claude/rules/code-conventions.md`.

### Updating rules during a conversation

Whenever a decision about how to write or organize code is established during a conversation
(style conventions, architectural patterns, naming constraints, testing rules, etc.),
immediately update the appropriate file in `.claude/rules/`:

- If the decision concerns conventions already covered by an existing file → add it there.
- If the decision opens a new topic → create a new file in `.claude/rules/` with a descriptive name.
  - Good: `error-handling.md`, `async-patterns.md`, `repository-conventions.md`
  - Avoid: `rules.md`, `misc.md`, `decisions.md`, `new-stuff.md`

Do not wait until the end of the task: update `.claude/rules/` **before** closing the conversation.

## Data Notes

See `docs/architecture/data-sources.md`.
