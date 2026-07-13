# Project Layout

## Folder structure

```text
repo/
├── src/
│   ├── commons/                    # Shared infra: DI-friendly services, repositories,
│   │                                #   clients, configs, use_cases/ (UseCase, ForEach),
│   │                                #   agents/ (BaseAgent + PromptRenderer),
│   │                                #   ai/observability/ (LlmCallTracker port + impls;
│   │                                #   protocols/services/repositories/mappers/models)
│   ├── domain/                     # Shared domain entities/models (persisted + intermediate),
│   │                                #   no I/O or business logic
│   ├── guidami_ai_patente_ingestor/ # Batch ingestion app: prepares + indexes the
│   │                                #   normative corpus (CdS/CAP) and quiz bank
│   ├── guidami_ai_patente/         # FastAPI quiz-bot app — scaffold only, not started
│   ├── parsers/                    # Standalone script: quiz PDF -> data/parsed/
│   └── scrapers/                   # Standalone script: normattiva.it -> data/raw/ + data/parsed/
├── tests/                          # Mirrors src/ structure, no __init__.py per directory
│   ├── commons/
│   ├── domain/
│   └── guidami_ai_patente_ingestor/
├── configs/                        # Runtime YAML config (ingestor_config.yaml, agents/*.yaml)
├── db/                             # init.sql — Postgres/pgvector schema, applied on container init
├── docker/                         # docker-compose.yml + .env for the Postgres/pgvector service
├── data/                           # Pipeline data at rest: raw/ -> parsed/ -> cleaned/ -> docs/
├── docs/                           # This documentation (Second Brain) + docs/plans/ (design plans)
└── .claude/                        # Claude Code config: rules/, skills/, hooks/, agents/
```

`flowstep` (`Flow`, `Step`, `FlowBuilder`, `FlowContext`, `ApplyStep`) is
**not** part of this repo's tree: it's an external git dependency
(github.com/alessiogilardi/flowstep, tracked via `main` in `pyproject.toml`'s
`[tool.uv.sources]`) — see `docs/architecture.md`.

## Placement conventions

- **New batch-pipeline code** (ingestion, enrichment, indexing) goes under
  `src/guidami_ai_patente_ingestor/`, following the package-per-role layout
  documented in `~/.claude/rules/python/architecture.md`:
  `orchestrators/` (pipelines + builders) → `services/` (domain logic) →
  `repositories/` (data access) → `clients/` (external API adapters) →
  `models/` / `entities/` (data shapes) → `mappers/` (transformations) →
  `configs/` (Pydantic settings) → `agents/` (LLM agent wrappers).
- **Code shared across the ingestor and the future FastAPI app** (embedding
  clients, `UseCase`/`ForEach`, `BaseAgent`, Postgres client, generic
  configs) goes in `src/commons/`, not duplicated into
  `guidami_ai_patente_ingestor/`. This includes `src/commons/ai/observability/`
  — a commons-level package (unlike the ingestor's per-source
  `*StoreRepository`s) because the future FastAPI app will track its own LLM
  calls too. `src/commons/ai/` is a top-level grouping for AI-related
  capabilities (only `observability/` lives there today; `agents/` and
  `services/embeddings/` have not been moved under it). Its packages follow a
  five-subpackage-by-responsibility shape: `protocols/` (genuine
  cross-package ports only — e.g. `LlmCallTracker`, which `BaseAgent`
  depends on), `services/` (the concrete behavior classes; a narrow,
  private `protocols/` may nest *inside* `services/` for
  implementation-detail structural typing that never crosses a package
  boundary — see `docs/patterns.md`), `repositories/` (data access),
  `mappers/` (stateless object-to-object transformations), and `models/`
  (intermediate DTOs consumed only by that package's own mappers).
- **Persisted or cross-cutting domain shapes** (entities that map 1:1 to a
  DB table, models shared by more than one app) go in `src/domain/`.
  Models that only exist as an intermediate step inside one pipeline stay
  local to that package's `models/` (e.g.
  `guidami_ai_patente_ingestor/models/knowledge/parsed_article.py`).
- **Generic, domain-agnostic pipeline mechanics** (a new step type, a new
  flow-control primitive with no knowledge of ingestion/quiz content) is
  out of scope for this repo: it belongs in the external `flowstep`
  package (github.com/alessiogilardi/flowstep), not in
  `guidami_ai_patente_ingestor/` or anywhere else in this tree.
- **One-shot data-acquisition scripts** (a new scraper source, a new PDF
  parser) go in `src/scrapers/` or `src/parsers/` respectively, and are
  registered as a `[project.scripts]` entry in `pyproject.toml`.
- **FastAPI routes/services for the quiz bot** (not started yet) go under
  `src/guidami_ai_patente/`, following the same layered convention as the
  ingestor once that work begins.
- **New tests** mirror the `src/` path of the code under test inside
  `tests/`, with no `__init__.py` in any test directory (see
  `.claude/rules/code-conventions.md`).

*Last updated: 2026-07-13 — verified against commit `5398b2d`.*
