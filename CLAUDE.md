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
- **Implemented architecture, patterns, database, layout, testing, glossary**: the Second Brain under `docs/` — start at `docs/README.md`, which routes to `architecture.md`, `database.md`, `patterns.md`, `glossary.md`, `layout.md`, `testing.md`, and `adr/`.

Reading and updating these files is governed by the `update-second-brain` skill (see the "Skill: Second Brain" block below) — read the relevant `docs/*.md` file directly rather than invoking an agent, and run the skill after any change described in its triggers. The former `doc-reader`/`doc-architect` agents are decommissioned; the Second Brain plugin's skills replace them.

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

Domain terms for the scraped/parsed sources (CdS, CAP, corpus normativo) are in `docs/glossary.md`; the pipeline stages that produce/consume them are in `docs/architecture.md`.


<!-- BEGIN SECOND BRAIN SYSTEM (managed by the second-brain plugin: do not edit this block by hand, edit bootstrap/payload/claude-md-block.md and re-run the bootstrap with --refresh-system) -->
## Skill: Second Brain
**Source of Truth:** `docs/` (architecture, ADRs, state).
**Full Policy:** the `second-brain:update` skill.

@docs/README.md

### Triggers (IMMEDIATE ACTION REQUIRED)
Run `skill: "second-brain:update"` after:
* Schema changes or structural refactors.
* New architectural decisions or recurring patterns.
* Testing-strategy changes.
* `[SECOND BRAIN SYSTEM] COMMIT REJECTED` pre-commit error.

**Exception:** IF `docs/*.md` contains `> Placeholder —`, run `second-brain:onboard` instead.

### Strict Commit Rule
Commits touching code **MUST** stage an update to `docs/` **or this file**.
If rejected: 1. Run skill -> 2. Stage docs -> 3. Retry. Never use dummy updates.
<!-- END SECOND BRAIN SYSTEM -->

