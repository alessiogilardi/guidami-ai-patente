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
│   │                                #   protocols/services/repositories/mappers/models);
│   │                                #   observability/: two self-contained sub-packages,
│   │                                #   progress_reporter/ (ItemProgressReporter/ProgressReporter
│   │                                #   port + NullProgressReporter) and run_artifact_writer/
│   │                                #   (RunArtifactWriter + models/: RunManifest base,
│   │                                #   ScrapeManifest; RunArtifactWriterConfig removed);
│   │                                #   sibling of ai/observability/, not AI-specific
│   ├── domain/                     # Shared domain entities/models (persisted + intermediate),
│   │                                #   no I/O or business logic
│   ├── guidami_ai_patente_ingestor/ # Batch ingestion app: prepares + indexes the
│   │                                #   normative corpus (CdS/CAP/Regolamento) and quiz bank
│   ├── guidami_ai_patente/         # FastAPI quiz-bot app — scaffold only, not started
│   ├── html_viewers/               # Standalone, dependency-free HTML pages for manually
│   │                                #   inspecting pipeline output (e.g. quiz enrichment
│   │                                #   review); opened directly in a browser, no server
│   ├── parsers/                    # Standalone script: quiz PDF -> data/parsed/
│   ├── scrapers/                   # Standalone script: normattiva.it -> data/raw/ + data/parsed/
│   └── test_data_sampler/          # Standalone script: data/parsed/ -> a random subset in
│                                    #   data/test-data/parsed/ (same C901-exempt tier as
│                                    #   parsers/scrapers)
├── tests/                          # Mirrors src/ structure, no __init__.py per directory
│   ├── commons/
│   ├── domain/
│   └── guidami_ai_patente_ingestor/
├── configs/                        # Runtime YAML config (ingestor_config.yaml, agents/*.yaml,
│                                    #   ingestor_config.test-data.yaml — see below)
├── db/                             # init.sql — Postgres/pgvector schema, applied on container init
├── docker/                         # docker-compose.yml + .env for the Postgres/pgvector service
├── data/                           # Pipeline data at rest: raw/ -> parsed/ -> cleaned/ -> enriched/
│                                    #   knowledge's cleaned/enriched are per-element (one JSON
│                                    #   file per article, named by commons.utils.element_id);
│                                    #   parsed and the whole quiz pipeline stay monolithic
│                                    #   (data/docs/ is not a pipeline stage: it holds the source quiz PDF)
│                                    #   quiz-images/ is a stable top-level sibling of raw/parsed/
│                                    #   cleaned/enriched, NOT nested under parsed/: extracted image
│                                    #   bytes never change, so they sit outside the JSON's
│                                    #   parsed->cleaned->enriched transformation chain, committed
│                                    #   like parsed/cleaned (deterministic), for enrichment today
│                                    #   and the future FastAPI app to share (ADR 0008)
│                                    #   test-data/ mirrors parsed/cleaned/enriched + quiz-images/ on
│                                    #   a random subset (see ADR 0006, ADR 0008), for fast local
│                                    #   prepare/index runs
├── docs/                           # This documentation (Second Brain) + docs/plans/ (design plans)
└── .claude/                        # Claude Code config: rules/, skills/, hooks/, agents/
```

`docker/.volumes/` (gitignored, not shown in the tree above) holds the
Postgres data directory bind-mounted by `docker/docker-compose.yml` — see
`docs/database.md`.

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
  `agents/mappers/` instead (`NormReferenceDescriberMapper`,
  `RoadSignDescriberMapper`) — `agents/`
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
  `src/commons/observability/` (top-level, a **sibling** of `commons/ai/`,
  not nested under it) is itself just a thin re-exporting `__init__.py` over
  two self-contained sibling sub-packages (same self-containment convention
  as `cli/`/`agents/` above — a component whose whole reason to exist is one
  responsibility gets its own local shape instead of being scattered across
  the parent package's top-level dirs): `observability/progress_reporter/`
  and `observability/run_artifact_writer/`. `progress_reporter/protocols/`
  holds `ItemProgressReporter`/`ProgressReporter`, `progress_reporter/services/`
  holds `NullProgressReporter` — the progress-reporting port the ingest
  CLI's live dashboard (spec 0002) drives and the three instrumented
  services (`EmbeddingService`, `ImageDescriptionEnricher`,
  `NormReferenceEnricher`) depend on. `run_artifact_writer/` (spec 0004
  FR-3/AD-3, generalized in spec 0005) holds `RunArtifactWriter` directly —
  no internal `protocols/`/`services/` split, since there is no port (AD-3
  rejects a `Protocol` here: only one implementation exists) — plus a
  `models/` sub-package with `RunManifest` (shared base: `started_at`/
  `ended_at`, abstract `to_report_lines()`) and `ScrapeManifest` (the
  scraper's own fields, unchanged behavior). `RunArtifactWriterConfig` was
  removed (spec 0005 AD-5) — its fields moved onto `ScrapeManifest` directly.
  This is the shared per-run `run.log`/`manifest.json`/`report.md` writer
  both `ingest` and `scrape` (`scrapers/normattiva.py`) delegate to; the
  `ingest`-only manifests (`PrepareManifest`/`IndexManifest`/`ResetManifest`)
  live under `guidami_ai_patente_ingestor/cli/models/run_artifacts/` instead,
  per the CLI self-containment rule (spec 0005 AD-6) — see ADR 0009. Neither
  `commons/observability/` sub-package is
  under `commons/ai/` because neither is AI-specific (`EmbeddingService` is
  the only one of the three progress-reporting consumers that happens to
  also be AI-related); see `docs/patterns.md` for both shapes.
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
  `cli/rendering/dashboard/` (`LiveDashboard`, `LogPanelHandler`) is the concrete,
  CLI-only `rich` implementation of the `commons/observability/` port — the port
  itself is shared, but nothing outside the CLI renders it, so the renderer stays
  local per the same rule.
- **A one-shot script that reduces/samples an existing pipeline layer**
  (reads full JSON, writes a smaller derived JSON — same shape as
  `scrapers/rca_extract.py`) goes as a flat module in its own top-level
  package, sibling to `parsers/`/`scrapers/`, not inside
  `guidami_ai_patente_ingestor/` even if it imports `IngestorConfig`/
  `SourceConfig` from it: `src/test_data_sampler/sampler.py` samples
  `data/parsed/` into `data/test-data/parsed/` (ADR 0006), copying the
  referenced subset of `data/quiz-images/` into `data/test-data/quiz-images/`
  alongside it (ADR 0008), registered as `sample-test-data` and exempted
  from `C901` in `pyproject.toml` per the same "top-level orchestration is
  low-value to enforce" rationale as its siblings.

*Last updated: 2026-08-04 — verified against commit `51cabb3`; `data/` tree entry and the
`test_data_sampler/sampler.py` placement bullet now describe `data/quiz-images/`, a new
top-level directory (sibling of `raw/`/`parsed/`/`cleaned/`/`enriched/`) holding quiz
images previously nested under `data/parsed/quiz-patente-ab/images/` (ADR 0008), plus its
`data/test-data/quiz-images/` mirror.*

*Last updated: 2026-08-04 — verified against commit `2248dcc`; noted the gitignored
`docker/.volumes/` bind-mount directory (Postgres data, was a named Docker volume before).*

*Last updated: 2026-08-03 — verified against commit `600b4be`; `commons/observability/`
gained a second self-contained sibling sub-package, `run_artifact_writer/` (spec 0004
T-2/T-3), alongside the pre-existing `progress_reporter/`. Also merged in the
`feat/ingestion` verification against commit `d4c92ca`: added `src/test_data_sampler/`
and the `data/test-data/` mirror (ADR 0006).*

*Last updated: 2026-08-05 — verified against commit `52cc03e`; `run_artifact_writer/`
gained a `models/` sub-package (`RunManifest`, `ScrapeManifest`), `RunArtifactWriterConfig`
was removed, and `guidami_ai_patente_ingestor/cli/models/` gained a `run_artifacts/`
sub-package (`PrepareManifest`/`IndexManifest`/`ResetManifest`) — spec 0005, ADR 0009.*
