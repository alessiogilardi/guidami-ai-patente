# Project Layout

## Folder structure

```text
repo/
├── src/
│   ├── commons/                    # Shared infra: DI-friendly services, repositories,
│   │                                #   clients, configs, use_cases/ (UseCase, ForEach),
│   │                                #   ai/ (agents/: BaseAgent + PromptRenderer;
│   │                                #   embedding/: clients/configs/services;
│   │                                #   observability/: LlmCallTracker port + impls;
│   │                                #   protocols/services/repositories/mappers/models)
│   ├── domain/                     # Shared domain entities/models (persisted + intermediate),
│   │                                #   no I/O or business logic
│   ├── guidami_ai_patente_ingestor/ # Batch ingestion app: prepares + indexes the
│   │                                #   normative corpus (CdS/CAP) and quiz bank
│   ├── guidami_ai_patente/         # FastAPI quiz-bot app — scaffold only, not started
│   ├── html_viewers/               # Standalone, dependency-free HTML pages for manually
│   │                                #   inspecting pipeline output (e.g. quiz enrichment
│   │                                #   review); opened directly in a browser, no server
│   ├── parsers/                    # Standalone script: quiz PDF -> data/parsed/
│   └── scrapers/                   # Standalone script: normattiva.it -> data/raw/ + data/parsed/
├── tests/                          # Mirrors src/ structure, no __init__.py per directory
│   ├── commons/
│   ├── domain/
│   └── guidami_ai_patente_ingestor/
├── configs/                        # Runtime YAML config (ingestor_config.yaml, agents/*.yaml)
├── db/                             # init.sql — Postgres/pgvector schema, applied on container init
├── docker/                         # docker-compose.yml + .env for the Postgres/pgvector service
├── data/                           # Pipeline data at rest: raw/ -> parsed/ -> cleaned/ -> enriched/
│                                    #   knowledge's cleaned/enriched are per-element (one JSON
│                                    #   file per article, named by commons.utils.element_id);
│                                    #   parsed and the whole quiz pipeline stay monolithic
│                                    #   (data/docs/ is not a pipeline stage: it holds the source quiz PDF)
├── docs/                           # This documentation (Second Brain) + docs/plans/ (design plans)
└── .claude/                        # Claude Code config: rules/, skills/, hooks/, agents/
```

`flowstep` (`Flow`, `Step`, `FlowBuilder`, `FlowContext`, `ApplyStep`) is
**not** part of this repo's tree: it's an external git dependency
(github.com/alessiogilardi/flowstep, tracked via `main` in `pyproject.toml`'s
`[tool.uv.sources]`) — see `docs/architecture.md`.

`specs/` (claude-planner plugin, not shown in the tree above — it's SDD
pipeline state, not app code) holds two kinds of file with different
lifetimes: `specs/NNNN-*.md` are the permanent spec contracts, tracked
normally; `specs/discussions/*.md` are ephemeral brainstorm logs and are
gitignored — never committed, safe to delete once the spec they fed is
`implemented`.

## Placement conventions

- **New batch-pipeline code** (ingestion, enrichment, indexing) goes under
  `src/guidami_ai_patente_ingestor/`, following the package-per-role layout
  documented in `~/.claude/rules/python/architecture.md`:
  `orchestrators/` (pipelines + builders) → `services/` (domain logic) →
  `repositories/` (data access) → `clients/` (external API adapters) →
  `models/` / `entities/` (data shapes) → `mappers/` (transformations) →
  `configs/` (Pydantic settings) → `agents/` (LLM agent wrappers). The
  top-level `mappers/` package (`ArticleMapper`, `QuizMapper`) holds only
  pipeline-stage domain mappers; a mapper that exists solely to translate
  a domain model to/from one agent's request/response DTOs lives in
  `agents/mappers/` instead (`ArticleContextualizerMapper`,
  `NormReferenceDescriberMapper`, `RoadSignDescriberMapper`) — `agents/`
  is a self-contained package for its own DTOs (`agents/dto/`) and their
  mappers, the same self-containment convention `cli/` follows (see
  `.claude/rules/cli-structure.md`).
- **Code shared across the ingestor and the future FastAPI app** (embedding
  clients, `UseCase`/`ForEach`, `BaseAgent`, Postgres client, generic
  configs) goes in `src/commons/`, not duplicated into
  `guidami_ai_patente_ingestor/`. `src/commons/ai/` is the top-level
  grouping for AI-related capabilities — a commons-level package (unlike
  the ingestor's per-source `*StoreRepository`s) because the future
  FastAPI app will reuse agents/embedding/observability too. It has three
  subpackages today: `agents/` (`BaseAgent` + `PromptRenderer`, with its
  own `configs/` subfolder for `AgentConfig`), `embedding/` (`clients/`,
  `configs/`, `services/` for `EmbeddingClient`/`EmbeddingConfig`/
  `EmbeddingService`), and `observability/`. `observability/` (and, where
  it applies, `embedding/`) follows a five-subpackage-by-responsibility
  shape: `protocols/` (genuine cross-package ports only — e.g.
  `LlmCallTracker`, which `BaseAgent` depends on), `services/` (the
  concrete behavior classes; a narrow, private `protocols/` may nest
  *inside* `services/` for implementation-detail structural typing that
  never crosses a package boundary — see `docs/patterns.md`),
  `repositories/` (data access), `mappers/` (stateless object-to-object
  transformations), and `models/` (intermediate DTOs consumed only by
  that package's own mappers). `agents/` and `embedding/` only need the
  subset of that shape relevant to their own responsibility (`configs/`
  instead of a data-access/mapper shape, since neither owns persistence).
- **Persisted or cross-cutting domain shapes** (entities that map 1:1 to a
  DB table, models shared by more than one app) go in `src/domain/`.
  Models that only exist as an intermediate step inside one pipeline stay
  local to that package's `models/` (e.g.
  `guidami_ai_patente_ingestor/models/knowledge/parsed_article.py`).
- **Generic, domain-agnostic pipeline mechanics** (a new step type, a new
  flow-control primitive with no knowledge of ingestion/quiz content) is
  out of scope for this repo: it belongs in the external `flowstep`
  package (github.com/alessiogilardi/flowstep), not in
  `guidami_ai_patente_ingestor/` or anywhere else in this tree. Exception:
  steps that are domain-agnostic but specific to *this repo's* layer/source
  model (e.g. `orchestrators/steps/generic/{load_json_dir_step,
  filter_already_done_step,write_json_dir_step}.py`, parametrized by
  `LayerResolver`/`FileRepository`/an injected `id_of` keyer) stay in
  `guidami_ai_patente_ingestor/orchestrators/steps/generic/`, next to
  `LoadJsonStep`/`WriteJsonStep` — they know nothing of articles or quizzes,
  but they do know this repo's layer/source vocabulary, which `flowstep`
  itself does not.
- **A new, genuinely generic helper with no domain logic** (e.g. a
  deterministic id function usable by any future keyer) goes flat in
  `src/commons/utils/`, next to `deduplicate.py`/`hash_utils.py` — e.g.
  `commons/utils/element_id.py::element_id(*parts) -> str`. Domain binding
  (which parts identify an element) stays at the call site, not inside the
  helper.
- **One-shot data-acquisition scripts** (a new scraper source, a new PDF
  parser) go in `src/scrapers/` or `src/parsers/` respectively, and are
  registered as a `[project.scripts]` entry in `pyproject.toml`.
- **Manual review tooling for pipeline output** (a read-only HTML page to
  eyeball an enriched/cleaned JSON artifact) goes in `src/html_viewers/`:
  self-contained (no build step, no server, no external dependency), kept
  in sync with the Pydantic model it renders whenever that model's shape
  changes.
- **FastAPI routes/services for the quiz bot** (not started yet) go under
  `src/guidami_ai_patente/`, following the same layered convention as the
  ingestor once that work begins.
- **New tests** mirror the `src/` path of the code under test inside
  `tests/`, with no `__init__.py` in any test directory (see
  `.claude/rules/code-conventions.md`).
- **CLI-only components for the `ingest` CLI** (argument parsing, DI wiring,
  command dispatch, and any service/DTO/renderer that exists solely to serve
  a CLI command) go under `src/guidami_ai_patente_ingestor/cli/`, a
  self-contained package that replicates the layered structure locally
  instead of polluting the top-level `services/`/`models/` packages.
  Genuinely shared infrastructure (e.g. the `table_exists`/`row_count` read
  primitives on `BulkInsertStoreRepository`) stays in its own top-level layer
  instead. The internal `cli/` breakdown and the full self-containment
  boundary rule live in `.claude/rules/cli-structure.md` — not restated here.

*Last updated: 2026-07-31 — verified against commit `794d1b5`.*
