

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

**guidami-ai-patente** is a tool that makes Italian driving exam information freely accessible. It aggregates official questions, regulations, and reference material — currently scraped from the web and from PDFs — so users can study and query it without paywalls.

The end goal is a **quiz bot** (FastAPI) that checks answers deterministically and explains them using RAG over the corpus normativo (CdS + CAP). Postgres/pgvector infrastructure is running, corpus and quiz-bank ingestion pipelines are implemented, and the FastAPI app (`src/guidami_ai_patente/`, started with `uv run serve`) now serves the full quiz loop: browse topics, get a question, check an answer, fetch its image, ensure a comma labeling on demand, and get a RAG-backed explanation of the correct answer. Deterministic answer-checking is live; explaining an answer is now a two-step, on-demand flow (spec 0017) — `POST /{number}/label` ensures a labeling exists (computing it live only on a genuine cache miss), then `GET /{number}/explanation` renders from that existing labeling only.

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

No test ever touches this dev stack. They run against a fully isolated,
ephemeral Postgres (`docker/docker-compose.test.yml`: separate container, separate
port 5433, `tmpfs` data directory — never persisted, never the dev database) that
the `postgres_test_config` session fixture in `tests/conftest.py` starts
automatically the first time any collected test needs it — not only
`integration`-marked tests: several `guidami_ai_patente` API tests consume the
`app_config`/`api_client` fixtures, which depend on `postgres_test_config`
transitively. So a plain `uv run pytest` (no `-m integration`) also starts this
Docker stack, and hard-fails (not a skip) if Docker isn't running. No manual
`docker compose` step is needed for it either way; the stack tears down at the
end of the pytest session.

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
| `uv run ingest reset knowledge [--apply] [--force]` | `guidami_ai_patente_ingestor.cli:main` | Truncates `quiz_comma_labels`, `quiz_labelings`, `article_commas` and `articles` in one statement (full wipe); refuses when a human-validated labeling would be destroyed unless `--force` is also passed |
| `uv run ingest reset quiz [--apply]` | `guidami_ai_patente_ingestor.cli:main` | Truncates `quiz_questions` (full wipe) |
| `uv run ingest status [--online]` | `guidami_ai_patente_ingestor.cli:main` | Shows config (secrets masked) and per-command readiness; `--online` also checks Postgres reachability and per-table row counts |
| `uv run ingest evaluate retrieval [--seed N] [--baseline-repetitions N] [--dry-run] [--plain]` | `guidami_ai_patente_ingestor.cli:main` | Measures retrieval quality (corpus coverage, ranking vs. random baseline, lexical adherence, dense/FTS agreement, keyword-quality signals) over the quiz bank and knowledge corpus (spec 0007). `--seed`/`--baseline-repetitions` override `IngestorConfig.evaluation`; writes `data/eval/retrieval-summary.json` (committed) plus per-question detail and a judge-ready export under `logs/ingest_evaluate_<ts>/` |
| `uv run label-golden-set [--concurrency N] [--seed N] [--limit N] [--topic TOPIC]…` | `retrieval_evaluation.label_main:main` | Runs a golden-set labeling pass over the quiz bank via `CommaLabelerAgent`, persisting one `labeling_runs` row plus `quiz_labelings`/`quiz_comma_labels` (spec 0011). `--topic` (repeatable) restricts the run to the union of the named topics, applied before `--limit`; it selects which questions are labeled and is never recorded on the run (FR-18) |
| `uv run serve` | `guidami_ai_patente.main:main` | Starts the FastAPI service on `AppConfig.host:port` |
| `uv run telegram-bot` | `guidami_ai_patente_bot.main:main` | Starts the Telegram bot client, long-polling against a running `guidami_ai_patente` instance |

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

### API endpoints

Started via `uv run serve` (`docker compose up -d` first, so Postgres is reachable):

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check; reports the resolved `pywire` version |
| `GET /quiz-questions/topics` | Lists the distinct topics with their question counts (FR-16) |
| `GET /quiz-questions/random?seed=&index=&topic=` | Proposes the question at `index` of the seeded permutation `seed` induces, optionally restricted to `topic` (FR-1); response never includes `correct_answer` |
| `GET /quiz-questions/{number}` | Returns one question by its number, in the same shape as `/random` (FR-2) |
| `POST /quiz-questions/{number}/check` | Grades a submitted true/false answer and advertises the `explanation_status` (`cached`/`uncached`/`unavailable`) for that question (FR-3, FR-4) |
| `POST /quiz-questions/{number}/label` | Ensures a current comma labeling exists for the question, computing it live (retrieve → judge → write through) only on a genuine cache miss; no response body on success (spec 0017, FR-4). `404` for an unknown question; `503` on judge/write-through timeout or failure |
| `GET /quiz-questions/{number}/explanation?submitted=` | Renders the explanation from an already-existing comma labeling only — it never triggers the judge. `200` with `status: insufficient_knowledge` and a machine-readable `reason` when the corpus does not justify the question (FR-7); `409` (`LabelingNotReadyError`) when the question is embedded but has no current labeling yet — the caller must call `POST /{number}/label` first. Optional `submitted` tailors the wording to the answer the user gave (FR-11) |
| `GET /quiz-images/{filename}` | Serves a quiz image, authorized database-first: 404 unless some `quiz_questions` row actually references the filename (FR-12) |

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
- `OPENROUTER_API_KEY` — read by litellm from the environment; required for embedding and LLM
  steps in ingestion, **and required to start the API at all**: `main.py` loads
  `OpenRouterConfig`, whose `api_key` has no default, so `uv run serve` raises a
  `ValidationError` without it, even for `GET /health`.
- `AGENTS_DIR` — directory holding the agent YAML files. Has **no default** on any of
  **three** config roots (`IngestorConfig.agents_dir`, `LabelingConfig.agents_dir` and
  `AppConfig.agents_dir`, spec 0012, AD-22/AD-27): a missing value is a loud
  `ValidationError` at startup, never a silent fallback, because the batch labeler and the
  live judge must load the identical prompt file for their configuration-epoch hash
  (`prompt_version`) to mean the same thing on both sides. `AppConfig.agents_dir` is
  declared separately from `LabelingConfig.agents_dir` because it resolves a different kind
  of prompt: the API's own agents whose prompts enter no configuration epoch (today,
  `explanation_writer.yaml`), versus the epoch-controlled judge prompt (D4, ADR 0020).
- `TELEGRAM_BOT_TOKEN` — the bot's Telegram Bot API token. `BotConfig.telegram_bot_token`
  has no default, so a missing value is a loud `ValidationError` at startup: `uv run
  telegram-bot` refuses to start rather than polling with no credentials.

The labeling/judge configuration epoch (`judge_model`, `prompt_version`, `candidate_variant`,
`dense_k`, `text_k`, `lexeme_fields`) is read from a single file, `configs/labeling.yaml`, via
`LabelingConfig` — embedded in `IngestorConfig` on the batch side; the API side loads and
registers its own independent `LabelingConfig` instance from the same file/env at `main.py`
(spec 0013, FR-1) rather than nesting it inside `AppConfig`, so the two roots read the same
source without either one owning the other (see `docs/second-brain/patterns.md` and ADR 0020).

## Architecture

Before starting any implementation task, read the reference documents:

- **Design specs** (feature contracts, "what to build"): `docs/superpowers/specs/` — written by the `superpowers:brainstorming` skill's architectural path
- **Implementation plans** (not-yet-implemented work, "how it gets built task-by-task"): `docs/superpowers/plans/` — written by the `superpowers:writing-plans` skill; gitignored, pruned once implemented
- **Implemented architecture, patterns, database, layout, testing, glossary**: the Second Brain under `docs/second-brain/` — governed by the Second Brain plugin; see the "Skill: Second Brain" block below for how to read and update it. The former `doc-reader`/`doc-architect` agents are decommissioned; the Second Brain plugin's agent/skills replace them.

### Complex tasks — brainstorming, then grilling

When a task's horizon is complex (architectural, multi-step, or ambiguous scope), run
`superpowers:brainstorming` first. Only once that preliminary discussion has produced a
first-pass shared understanding, hand off to `mattpocock-skills:grilling` to stress-test
it before writing a spec or plan — grilling sharpens a plan, it does not replace the
discussion that produces one.

For this project, override grilling's default batching: ask one question at a time, not
the whole frontier as a list. Each question is multiple-choice, with the recommended
option marked, and you wait for the user's answer before asking the next.

Put every question to the user — brainstorming's and grilling's alike — through the
`AskUserQuestion` tool rather than as plain chat text, so each renders as an actual
multiple-choice prompt with the recommended option first.

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
**Full Policy:** the `second-brain:update` skill (decisions: `second-brain:adr`).

@docs/second-brain/README.md

### Triggers (IMMEDIATE ACTION REQUIRED)
**Before** any analysis, code review, planning or implementation, run
`skill: "second-brain:read"` — it queries `docs/second-brain/` through the
read-only reader subagent. Never read `docs/second-brain/*.md` yourself.

**After** schema changes, structural refactors, new recurring patterns or
conventions, testing-strategy changes — or a
`[SECOND BRAIN SYSTEM] COMMIT REJECTED` error — run
`skill: "second-brain:update"`.

Run `skill: "second-brain:adr"` when the fact is a **decision** with real
alternatives and trade-offs — it owns `docs/second-brain/adr/` (numbering,
proposal mode, superseding).

**Exception:** IF `docs/second-brain/*.md` contains `> Placeholder —`, run
`second-brain:onboard` instead.

### Strict Commit Rule
Commits touching code **MUST** stage an update to `docs/second-brain/` **or
this file**. (If the project sets `SB_GATE=push` in `.second-brain.conf`, the
requirement applies to the branch rather than to each commit — the pre-push
hook checks the whole branch diff.) If rejected: 1. Run skill -> 2. Stage docs
-> 3. Retry. Never use dummy updates.
**Never hand-edit `docs/second-brain/*.md` to satisfy the pre-commit check.**
The check is syntactic only — it can't tell whether the change is real.
Always go through `skill: "second-brain:update"` instead.
<!-- END SECOND BRAIN SYSTEM -->
