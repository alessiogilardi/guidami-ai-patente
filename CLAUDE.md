

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
# Start Postgres + pgvector (required for ingestion; NOT required for integration
# tests — see below)
cd docker && docker compose up -d

# Recreate DB from scratch (required after schema changes in db/init.sql)
# Data persists to the docker/.volumes/postgres_data bind mount (gitignored) — down -v
# has nothing left to remove, so wipe the directory instead
docker compose -f docker/docker-compose.yml down
rm -rf docker/.volumes/postgres_data
docker compose -f docker/docker-compose.yml up -d
```

Integration tests never touch this dev stack. They run against a fully isolated,
ephemeral Postgres (`docker/docker-compose.test.yml`: separate container, separate
port 5433, `tmpfs` data directory — never persisted, never the dev database) that
the `postgres_test_config` session fixture in `tests/conftest.py` starts
automatically the first time an integration test needs it, and tears down at the
end of the pytest session. No manual `docker compose` step is needed for it —
just `uv run pytest -m integration` (Docker must be running).

### Available scripts

| Command | Entry point | Description |
|---|---|---|
| `uv run scrape --source <cds\|cap\|reg> [--dry-run]` | `scrapers.normattiva:cli_main` | Scrapes the selected law (CdS, CAP, or the Regolamento di attuazione DPR 495/1992) → `data/raw/<source>/`, `data/parsed/<source>/` |
| `uv run extract-rca` | `scrapers.rca_extract:main` | Filters `codice_assicurazioni_private.json` down to `IngestorConfig.rca_ranges` → `data/parsed/cap/codice_rca.json` |
| `uv run parse-domande` | `parsers.questions_pdf:main_questions` | Parses quiz PDF → `data/parsed/quiz-patente-ab/` |
| `uv run sample-test-data [--count N] [--seed N]` | `test_data_sampler.sampler:main` | Samples `--count` (default 20) random elements per source from `data/parsed/` → `data/test-data/parsed/` (cds/cap/reg/quiz + only the referenced quiz images) |
| `uv run ingest prepare knowledge --source <cds\|cap> [--force] [--dry-run]` | `guidami_ai_patente_ingestor.cli:main` | Clean + enrich knowledge corpus for one source |
| `uv run ingest prepare quiz [--force] [--dry-run]` | `guidami_ai_patente_ingestor.cli:main` | Prepare quiz bank (enriched with image descriptions) |
| `uv run ingest index knowledge --source <cds\|cap> [--dry-run]` | `guidami_ai_patente_ingestor.cli:main` | Embed + store knowledge corpus for one source |
| `uv run ingest index quiz [--dry-run]` | `guidami_ai_patente_ingestor.cli:main` | Embed + store quiz bank |
| `uv run ingest reset knowledge [--apply]` | `guidami_ai_patente_ingestor.cli:main` | Truncates `articles` and `article_commas` (full wipe) |
| `uv run ingest reset quiz [--apply]` | `guidami_ai_patente_ingestor.cli:main` | Truncates `quiz_questions` (full wipe) |
| `uv run ingest status [--online]` | `guidami_ai_patente_ingestor.cli:main` | Shows config (secrets masked) and per-command readiness; `--online` also checks Postgres reachability and per-table row counts |
| `uv run ingest evaluate retrieval [--seed N] [--baseline-repetitions N] [--dry-run] [--plain]` | `guidami_ai_patente_ingestor.cli:main` | Measures retrieval quality (corpus coverage, ranking vs. random baseline, lexical adherence, dense/FTS agreement, keyword-quality signals) over the quiz bank and knowledge corpus (spec 0007). `--seed`/`--baseline-repetitions` override `IngestorConfig.evaluation`; writes `data/eval/retrieval-summary.json` (committed) plus per-question detail and a judge-ready export under `logs/ingest_evaluate_<ts>/` |

`--dry-run` (on `prepare`/`index`/`evaluate`) prints the step chain that would run and
exits — no filesystem writes, no LLM calls, no DB connection is ever opened.

`reset` is destructive, so its gate is inverted: it always previews (same no-filesystem/
no-DB guarantee as `--dry-run`) unless `--apply` is passed, which is required to actually
run the `TRUNCATE`. It does not have a `--dry-run` flag of its own.

Every real (non-preview) invocation logs to console **and** to a per-run file at
`logs/ingest_<command>_<YYYYMMDDHHMM>/run.log` (a numeric suffix is appended on a
same-minute collision). Previews (`--dry-run` on `prepare`/`index`, or `reset` without
`--apply`) never write to `logs/`, to keep the "no filesystem writes" guarantee.

Register new CLI commands under `[project.scripts]` in `pyproject.toml`.

### Running against a test-data subset

Every `ingest` command accepts a global `--config PATH` flag (anywhere in argv,
before or after the subcommand) pointing at an alternate `ingestor_config.yaml`.
`configs/ingestor_config.test-data.yaml` retargets the `parsed`/`cleaned`/`enriched`
layers and `quiz_images_dir` at `data/test-data/` instead of `data/` — same Postgres
tables, same source catalog, just a smaller corpus:

```bash
# One-off: (re)generate the subset from the full corpus in data/parsed/
uv run sample-test-data --count 20 --seed 42

# Run prepare/index against it instead of the full corpus
uv run ingest --config configs/ingestor_config.test-data.yaml prepare knowledge --source cds
uv run ingest --config configs/ingestor_config.test-data.yaml index quiz
```

`data/test-data/parsed/` and `data/test-data/cleaned/` are committed as a pinned
fixture, same as their main-tree counterparts. `data/test-data/enriched/` is committed
on the same terms once it exists (it does not yet) — as is `data/enriched/`, which
holds the 7099 enriched quiz files (ADR 0012, superseding ADR 0005).

### Secrets required

Copy `.env.example` to `.env` and fill in:
- `POSTGRES__USER` / `POSTGRES__PASSWORD` — DB credentials (double underscore = nested delimiter for `IngestorConfig.postgres`)
- `OPENROUTER_API_KEY` — required for embedding and LLM steps; read by litellm from the environment

## Architecture

Before starting any implementation task, read the reference documents:

- **Design specs** (feature contracts, "what to build"): `docs/superpowers/specs/` — written by the `superpowers:brainstorming` skill's architectural path
- **Implementation plans** (not-yet-implemented work, "how it gets built task-by-task"): `docs/superpowers/plans/` — written by the `superpowers:writing-plans` skill; gitignored, pruned once implemented
- **Implemented architecture, patterns, database, layout, testing, glossary**: the Second Brain under `docs/second-brain/` — start at `docs/second-brain/README.md`, which routes to `architecture.md`, `database.md`, `patterns.md`, `glossary.md`, `layout.md`, `testing.md`, and `adr/`.

Reading and updating these files is governed by the `update-second-brain` skill (see the "Skill: Second Brain" block below) — read the relevant `docs/second-brain/*.md` file directly rather than invoking an agent, and run the skill after any change described in its triggers. The former `doc-reader`/`doc-architect` agents are decommissioned; the Second Brain plugin's skills replace them.

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

Domain terms for the scraped/parsed sources (CdS, CAP, corpus normativo) are in `docs/second-brain/glossary.md`; the pipeline stages that produce/consume them are in `docs/second-brain/architecture.md`.


<!-- BEGIN SECOND BRAIN SYSTEM (managed by the second-brain plugin: do not edit this block by hand, edit bootstrap/payload/claude-md-block.md and re-run the bootstrap with --refresh-system) -->
## Skill: Second Brain
**Source of Truth:** `docs/second-brain/` (architecture, ADRs, state).
**Full Policy:** the `second-brain:update` skill.

@docs/second-brain/README.md

### Before Non-Trivial Work (MANDATORY)
Before any analysis, code review, planning, or implementation, delegate to
the `second-brain:second-brain-reader` subagent to check `docs/second-brain/`
for existing patterns, prior decisions, domain terms, and testing
conventions. Do not read the `docs/second-brain/*.md` files yourself to
answer these questions — that defeats the subagent's purpose. Skipping this
step means acting on stale assumptions about architecture that's already
been decided.

### Triggers (IMMEDIATE ACTION REQUIRED)
Run `skill: "second-brain:update"` after:
* Schema changes or structural refactors.
* New architectural decisions or recurring patterns.
* Testing-strategy changes.
* `[SECOND BRAIN SYSTEM] COMMIT REJECTED` pre-commit error.

**Exception:** IF `docs/second-brain/*.md` contains `> Placeholder —`, run
`second-brain:onboard` instead.

### Strict Commit Rule
Commits touching code **MUST** stage an update to `docs/second-brain/` **or
this file**. (If the project sets `SB_GATE=push` in `.second-brain.conf`, the
requirement applies to the branch rather than to each commit — the pre-push
hook checks the whole branch diff.) If rejected: 1. Run skill -> 2. Stage docs
-> 3. Retry. Never use dummy updates.
**Never hand-edit `docs/second-brain/*.md` to satisfy the pre-commit check.**
The check is syntactic only — it just confirms *some* file under
`docs/second-brain/` changed, it cannot tell whether the change is real.
Always go through `skill: "second-brain:update"`, which routes the fact to
the right file, proposes an ADR when warranted, and refreshes the freshness
footer. A hand-edit that skips these steps passes the check but leaves the
docs wrong or stale, defeating the whole point of the system.
<!-- END SECOND BRAIN SYSTEM -->
