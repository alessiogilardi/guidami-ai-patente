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
| `uv run ingest prepare knowledge --source <cds\|cap> [--force] [--dry-run]` | `guidami_ai_patente_ingestor.cli:main` | Clean + enrich knowledge corpus for one source |
| `uv run ingest prepare quiz [--force] [--dry-run]` | `guidami_ai_patente_ingestor.cli:main` | Prepare quiz bank (enriched with image descriptions) |
| `uv run ingest index knowledge --source <cds\|cap> [--dry-run]` | `guidami_ai_patente_ingestor.cli:main` | Embed + store knowledge corpus for one source |
| `uv run ingest index quiz [--dry-run]` | `guidami_ai_patente_ingestor.cli:main` | Embed + store quiz bank |
| `uv run ingest reset knowledge [--dry-run]` | `guidami_ai_patente_ingestor.cli:main` | Truncates `knowledge_chunks` (full wipe) |
| `uv run ingest reset quiz [--dry-run]` | `guidami_ai_patente_ingestor.cli:main` | Truncates `quiz_questions` (full wipe) |
| `uv run ingest status [--online]` | `guidami_ai_patente_ingestor.cli:main` | Shows config (secrets masked) and per-command readiness; `--online` also checks Postgres reachability and per-table row counts |

`--dry-run` (on `prepare`/`index`/`reset`) prints the step chain that would run and exits — no filesystem writes, no LLM calls, no DB connection is ever opened.

Every real (non-`--dry-run`) invocation logs to console **and** to a per-run file at
`logs/ingest_<command>_<YYYYMMDDHHMM>/run.log` (a numeric suffix is appended on a
same-minute collision). `--dry-run` never writes to `logs/`, to keep its "no filesystem
writes" guarantee.

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

<!-- claude-planner:bootstrap:start (managed by the claude-planner plugin: do not hand-edit this block, edit skills/bootstrap/templates/claude-md-section.md in the plugin and re-run /bootstrap to refresh) -->
<!-- claude-planner:config specs-dir=specs plans-dir=plans -->
## Spec-Driven Development (claude-planner plugin)

This repository has the `claude-planner` plugin available for Spec-Driven Development (SDD).

**When it pays off**: multi-session or medium-and-larger features, work where
requirement-to-test traceability matters, or a design that is genuinely still
open. **When it doesn't**: small fixes and well-understood changes — make
those directly, no pipeline needed.

```
/brainstorm ──▶ discussion log ──▶ /write-spec ──▶ spec (contract) ──▶ /write-plan ──▶ plan ──▶ (implementation) ──▶ /close-plan
```

**Short path**: `/write-spec` can compile a spec directly from a conversation,
skipping `/brainstorm`, whenever the conversation already contains the
substance (decisions, alternatives, constraints).

**Permanence**: specs are the only permanent artifact. Discussion logs and
plans are ephemeral — deletable once the spec they fed reaches `implemented`
(`/close-plan` proposes the cleanup; nothing is deleted automatically).

| Skill | Invoke when | Reads | Writes |
|---|---|---|---|
| `/brainstorm` | Exploring or resuming a fuzzy feature/architecture idea before committing. | Conversation + codebase (+ existing log to resume) | `specs/discussions/<topic-slug>.md` |
| `/write-spec` | The discussion has converged, or the conversation already holds the substance; formalize it into a tracked contract. | Discussion log, or the conversation itself | `specs/NNNN-<slug>.md` |
| `/write-plan` | A spec is `ready`; extract an executable plan. | Spec | `plans/NNNN-<slug>-plan.md` |
| `/close-plan` | Implementation is done; verify the Definition of Done and close the loop. | Plan + spec + repo state | Changelog entry on the spec; proposes `status: implemented` |

Rules when touching these artifacts:
- The spec is the source of truth; plans are disposable, regenerated wholesale
  from the spec, never hand-patched.
- Only the user promotes a spec's status
  (`draft → ready → in-progress → implemented`, side exit `superseded`);
  skills only propose transitions.
- Specs are never deleted or renumbered. A replacing spec sets `status:
  superseded` on the old one and points to its successor; removed requirements
  are struck through (`~~FR-n: ...~~`).
- Every codebase claim in a spec or plan is backed by a verified `path:line`
  reference, not assumed.
<!-- claude-planner:bootstrap:end -->
