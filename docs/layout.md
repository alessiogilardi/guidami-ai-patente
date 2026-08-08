# Project Layout

## Folder structure

```text
repo/
├── src/
│   ├── commons/                    # Shared infra: DI-friendly services, repositories,
│   │                                #   repositories/db/: per-aggregate READ repositories
│   │                                #   (CorpusReadRepository, QuizReadRepository) — spec 0007 AD-7;
│   │                                #   clients, configs, use_cases/ (UseCase, ForEach),
│   │                                #   ai/ (agents/: BaseAgent + PromptRenderer;
│   │                                #   embedding/: clients/configs/protocols/models/
│   │                                #   composition/services;
│   │                                #   observability/: LlmCallTracker port + impls;
│   │                                #   utils/: domain-agnostic retrieval algorithms
│   │                                #   (reciprocal_rank_fusion) — spec 0008 Phase 2, AD-3;
│   │                                #   protocols/services/repositories/mappers/models);
│   │                                #   observability/: two self-contained sub-packages,
│   │                                #   progress_reporter/ (ItemProgressReporter/ProgressReporter
│   │                                #   port + NullProgressReporter) and run_artifact_writer/
│   │                                #   (RunArtifactWriter + models/: RunManifest base,
│   │                                #   ScrapeManifest; RunArtifactWriterConfig removed);
│   │                                #   sibling of ai/observability/, not AI-specific
│   ├── domain/                     # Shared domain entities/models (persisted + intermediate),
│   │                                #   models/retrieval/: read DTOs (RetrievedComma,
│   │                                #   QuizEvaluationRow) — carry `id`, unlike entities;
│   │                                #   no I/O or business logic
│   ├── guidami_ai_patente_ingestor/ # Batch ingestion app: prepares + indexes the
│   │                                #   normative corpus (CdS/CAP/Regolamento) and quiz bank
│   ├── guidami_ai_patente/         # FastAPI quiz-bot app — layout scaffolded, no domain
│   │                                #   endpoints yet. api/ (self-contained web
│   │                                #   layer: app.py factory, routers/, schemas/) →
│   │                                #   services/ / repositories/ / models/ / mappers/
│   │                                #   (empty, pull-based) → configs/ (AppConfig). Only
│   │                                #   concrete slice: GET /health. Entry point:
│   │                                #   `guidami_ai_patente.main:main`, registered as the
│   │                                #   `api` script
│   ├── html_viewers/               # Standalone, dependency-free HTML pages for manually
│   │                                #   inspecting pipeline output (e.g. quiz enrichment
│   │                                #   review); opened directly in a browser, no server
│   ├── parsers/                    # Standalone script: quiz PDF -> data/parsed/
│   ├── retrieval_evaluation/       # Standalone script: LLM-as-judge for retrieval quality —
│   │                                #   samples quiz questions, judges whether their top-k
│   │                                #   retrieved commas justify the answer (ADR 0013)
│   ├── scrapers/                   # Standalone script: normattiva.it -> data/raw/ + data/parsed/
│   └── test_data_sampler/          # Standalone script: data/parsed/ -> a random subset in
│                                    #   data/test-data/parsed/, plus the sampled quiz
│                                    #   subset's already-enriched files copied from
│                                    #   data/enriched/ into data/test-data/enriched/
│                                    #   (no LLM call — same C901-exempt tier as parsers/scrapers)
├── tests/                          # Mirrors src/ structure, no __init__.py per directory
│   ├── commons/
│   ├── domain/
│   └── guidami_ai_patente_ingestor/
├── configs/                        # Runtime YAML config (ingestor_config.yaml, agents/*.yaml,
│                                    #   ingestor_config.test-data.yaml — see below)
├── db/                             # init.sql — Postgres/pgvector target schema, applied on container init
│   └── migrations/                 #   idempotent, transactional ALTER scripts for existing DBs,
│                                    #   named NNNN_<slug>.sql after the spec introducing them;
│                                    #   must be kept equivalent to init.sql (see database.md)
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

- **Read (query) repositories** go in `src/commons/repositories/db/`, scoped **per
  entity/aggregate rather than per table** — a read returns what the caller needs whole,
  so `CorpusReadRepository` joins `articles`+`article_commas` and `QuizReadRepository`
  joins `quiz_questions`+`quiz_question_embeddings`. They live in `commons/` because the
  future FastAPI app needs the same corpus reader, not only the CLI. This is a deliberate
  asymmetry with the **write** repositories in
  `guidami_ai_patente_ingestor/repositories/db/`, which stay per table: an insert targets
  one table and needs its generated id back for the foreign key, so it cannot be an
  aggregate operation. See spec 0007, AD-7.
- **Read DTOs** (rows returned by those repositories, e.g. `RetrievedComma`,
  `QuizEvaluationRow`) go in `src/domain/models/retrieval/` — `domain/entities/` stays
  reserved for the insertable projection of a table row, which omits DB-generated columns;
  a read model does the opposite and carries `id`.
- **A generic retrieval algorithm with more than one plausible consumer** (not tied to the
  quiz/corpus domain types) goes in `src/commons/ai/utils/`, per the `utils/` convention in
  `rules/python/architecture.md` (genuinely generic, no domain-specific logic) —
  `reciprocal_rank_fusion(rankings, k)` operates on plain ranked id lists, added for the
  spec 0008 Phase 2 fusion arm but explicitly anticipated for reuse by a later hybrid
  (dense+FTS) search feature (AD-3). Kept out of `cli/services/evaluation/` (where its only
  caller, `MultiArmRetrievalEvaluator`, lives) for the same reason `CorpusReadRepository`/
  `QuizReadRepository` are in `commons/` rather than `cli/`: a named future consumer outside
  the CLI.

- **New batch-pipeline code** (ingestion, enrichment, indexing) goes under
  `src/guidami_ai_patente_ingestor/`, following the package-per-role layout
  documented in `~/.claude/rules/python/architecture.md`:
  `orchestrators/` (pipelines + builders) → `services/` (domain logic) →
  `providers/` (thin config/filesystem-path resolution, no business logic —
  e.g. `LayerResolverProvider`, resolving a `(layer, source)` pair to a
  `Path`; not part of the generic role table in
  `~/.claude/rules/python/architecture.md`, added for this app) →
  `repositories/` (data access) → `clients/` (external API adapters) →
  `models/` / `entities/` (data shapes) → `mappers/` (transformations) →
  `configs/` (Pydantic settings) → `agents/` (LLM agent wrappers) →
  `utils/` (generic, domain-agnostic helpers — e.g.
  `comma_repeal_detector.py::detect_comma_repeal`/`is_comma_repealed`,
  re-exported from `services/knowledge/` for call-site cohesion with
  `ArticleCleanerService`). The
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
  `configs/` for `EmbeddingClient`/`EmbeddingClientConfig` — renamed from
  `EmbeddingConfig`, since it configures the client, not the module —
  plus `protocols/`, `models/`, `composition/`, `services/` for the
  composition layer described below), and `observability/`.
  `observability/` (and, where it applies, `embedding/`) follows a
  five-subpackage-by-responsibility shape: `protocols/` (genuine
  cross-package ports only — e.g. `LlmCallTracker`, which `BaseAgent`
  depends on, or `TextComposer[T]`/`OptionalTextComposer[T]` in
  `embedding/`), `services/` (the
  concrete behavior classes; a narrow, private `protocols/` may nest
  *inside* `services/` for implementation-detail structural typing that
  never crosses a package boundary — see `docs/patterns.md`),
  `repositories/` (data access), `mappers/` (stateless object-to-object
  transformations), and `models/` (intermediate DTOs consumed only by
  that package's own mappers). `agents/` and `embedding/` only need the
  subset of that shape relevant to their own responsibility (`configs/`
  instead of a data-access/mapper shape, since neither owns persistence;
  `clients/` instead of `repositories/`, since embedding's external
  dependency is an API client, not a database). `embedding/` also adds a
  **sixth**, domain-specific subpackage beyond that shape —
  `composition/` (`FieldSpecComposer[T]`, implementing
  `OptionalTextComposer[T]`; `TemplateComposer[T]`/`CallableComposer[T]`,
  implementing `TextComposer[T]`) — for classes that compose a model into
  text but aren't services (no `UseCase`/
  injected-dependency-with-behavior shape) or classic static mappers
  (they hold config injected at construction, unlike this repo's
  stateless `*Mapper` convention — see `docs/patterns.md`); the
  five-subpackage template already anticipates a package using only the
  subset relevant to its own responsibility, so one extra, narrowly
  scoped subpackage for a responsibility the template doesn't name is an
  extension of that principle, not a violation of it.
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
  services (`EmbeddingService`, `ImageDescriptionEnricherService`,
  `NormReferenceEnricherService`) depend on. `run_artifact_writer/` (spec 0004
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
  `LayerResolverProvider`/`FileRepository`/an injected `id_of` keyer) stay in
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
  registered as a `[project.scripts]` entry in `pyproject.toml`. **A
  single-law narrowing script** (filters one already-scraped law down to
  configured article ranges — `scrapers/rca_extract.py`, `scrapers/amb_extract.py`)
  stays in `src/scrapers/` too, next to the scraper whose output it narrows,
  rather than becoming its own top-level package: it is tightly coupled to
  one law's parsed shape, not a cross-source operation. This is narrower
  than — and should not be confused with — the "reduces/samples an existing
  pipeline layer" rule below, which is for scripts that operate *across every
  source* (see `test_data_sampler/sampler.py`).
- **Manual review tooling for pipeline output** (a read-only HTML page to
  eyeball an enriched/cleaned JSON artifact) goes in `src/html_viewers/`:
  self-contained (no build step, no server, no external dependency), kept
  in sync with the Pydantic model it renders whenever that model's shape
  changes.
- **FastAPI routes/services for the quiz bot** go under
  `src/guidami_ai_patente/`, following the same package-per-role layered
  convention as the ingestor (`services/`, `repositories/`, `models/`,
  `mappers/`, `configs/`), with one addition: the HTTP-only concerns
  (FastAPI app factory, routers, request/response schemas) live in a
  self-contained `api/` sub-package (`api/app.py::create_app`,
  `api/routers/`, `api/schemas/`), the same self-containment convention
  `cli/`/`agents/` follow (`.claude/rules/cli-structure.md`) — a schema or
  router used only by the HTTP layer never leaks into the top-level
  `models/`/`services/`. `configs/app_config.py::AppConfig` is the root
  `BaseSettings`, built once in `main.py` and passed down into
  `api.app.create_app`, embedding `commons.configs.PostgresConnectionConfig`
  the same way `IngestorConfig` does. `services/`, `repositories/`,
  `models/`, and `mappers/` are scaffolded empty (docstring-only
  `__init__.py`) and filled in pull-based, as with `domain/entities/`
  elsewhere in this repo — no `orchestrators/` package yet, since that
  role is for batch-pipeline flows, not a synchronous request/response
  service. The only concrete vertical slice so far is `GET /health`,
  proving the wiring end-to-end; it carries no business logic. Entry
  point: `main.py::main` (loads `AppConfig`, builds the app via
  `create_app`, serves it with `uvicorn`), registered as the `api`
  script in `pyproject.toml`.
- **New tests** mirror the `src/` path of the code under test inside
  `tests/`, with no `__init__.py` in any test directory (see
  `.claude/rules/code-conventions.md`).
- **CLI-only components for the `ingest` CLI** (argument parsing, DI wiring,
  command dispatch, and any service/DTO/renderer that exists solely to serve
  a CLI command) go under `src/guidami_ai_patente_ingestor/cli/`, a
  self-contained package that replicates the layered structure locally
  instead of polluting the top-level `services/`/`models/` packages.
  Genuinely shared infrastructure (e.g. the `table_exists`/`row_count` read
  primitives on `UpsertStoreRepository`) stays in its own top-level layer
  instead. The internal `cli/` breakdown and the full self-containment
  boundary rule live in `.claude/rules/cli-structure.md` — not restated here.
  `cli/rendering/dashboard/` (`LiveDashboard`, `LogPanelHandler`) is the concrete,
  CLI-only `rich` implementation of the `commons/observability/` port — the port
  itself is shared, but nothing outside the CLI renders it, so the renderer stays
  local per the same rule.
- **A one-shot script that reduces/samples an existing pipeline layer
  across every source** (reads full JSON per source, writes a smaller
  derived JSON per source — unlike `scrapers/rca_extract.py`/
  `scrapers/amb_extract.py`, which each narrow one specific law, see above)
  goes as a flat module in its own top-level
  package, sibling to `parsers/`/`scrapers/`, not inside
  `guidami_ai_patente_ingestor/` even if it imports `IngestorConfig`/
  `SourceConfig` from it: `src/test_data_sampler/sampler.py` samples
  `data/parsed/` into `data/test-data/parsed/` (ADR 0006), copying the
  referenced subset of `data/quiz-images/` into `data/test-data/quiz-images/`
  alongside it (ADR 0008), and copying the sampled quiz subset's
  already-enriched files from `data/enriched/quiz-patente-ab/` into
  `data/test-data/enriched/quiz-patente-ab/` (`sample_quiz_enriched`, keyed
  by `element_id("quiz", number)` — a filesystem copy from the already-
  enriched full bank, never a re-enrichment LLM call), registered as
  `sample-test-data` and exempted from `C901` in `pyproject.toml` per the
  same "top-level orchestration is low-value to enforce" rationale as its
  siblings.
- **A standalone LLM-as-judge measurement tool** that needs the ingestor's
  Postgres/OpenRouter config but is neither a CLI feature nor a
  data-reduction script goes in its own top-level package, sibling to
  `parsers/`/`scrapers/`/`test_data_sampler/`, registered as its own
  `[project.scripts]` entry: `src/retrieval_evaluation/` (`agents/retrieval_judge/`
  — a generic `agents/` container, today holding the single named `retrieval_judge/`
  agent subpackage: the agent plus its `dto/` sibling — `services/`, `models/`,
  `wiring.py`, `main.py`) asks `RetrievalJudgeAgent`
  whether a question's `CorpusReadRepository.dense_top_k` commas justify its
  answer. It deliberately sits outside `ingest evaluate retrieval` (spec
  0007 lists an LLM judge as a Non-Goal) and outside `cli/` (no manifest, no
  dry-run chain, no `RunArtifactWriter` — ADR 0013), reusing
  `guidami_ai_patente_ingestor.configs.IngestorConfig` and the existing
  `commons/repositories/db/` read repositories rather than owning new
  config or new query code.

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

*Last updated: 2026-08-05 — verified against commit `6d96b7d`; `db/` gained a
`migrations/` sub-directory holding idempotent transactional ALTER scripts, a second
schema-management path alongside `init.sql` (spec 0008, ADR 0010).*

*Last updated: 2026-08-05 — verified against commit `91028b2`; recorded the new read layer
introduced while implementing spec 0007: `commons/repositories/db/` (per-aggregate read
repositories, deliberately asymmetric with the per-table write repositories) and
`domain/models/retrieval/` (read DTOs). The CLI-local `cli/services/evaluation/` and
`cli/models/evaluation/` packages are being added by the same work and follow the existing
`cli/services/status/` + `cli/models/status/` precedent, so they need no new rule.*

*Last updated: 2026-08-06 — verified against commit `91c4fe7`; added `src/retrieval_evaluation/`
(folder tree + new placement bullet), the LLM-as-judge module deliberately outside both
`ingest evaluate retrieval` and `cli/` (ADR 0013).*

*Last updated: 2026-08-06 — verified against commit `068c765`; the placement bullet's
`src/retrieval_evaluation/` breakdown now says `retrieval_judge/` (agent + its `dto/`
sibling, flat) instead of `agents/` — the module has only one agent, so the ingestor's
`agents/dto/<agent_name>/` nesting convention doesn't apply.*

*Last updated: 2026-08-06 — verified against commit `068c765`; the CLI self-containment
bullet now names `UpsertStoreRepository` (renamed from `BulkInsertStoreRepository`,
spec 0010 T-1).*

*Last updated: 2026-08-06 — verified against commit `f343270`; the placement bullet's
`src/retrieval_evaluation/` breakdown now says `agents/` again (agent + flat `dto/`
sibling) instead of `retrieval_judge/` — reverted on the user's explicit request.*

*Last updated: 2026-08-06 — verified against commit `f1839b9`; corrected: the agent and its
`dto/` sibling are nested under `agents/retrieval_judge/`, not flat directly under `agents/`
— `agents/` is a generic per-role container, not the agent's own folder.*

*Last updated: 2026-08-06 — verified against commit `598690c`; clarified that a
single-law narrowing script (`rca_extract.py`, and now `amb_extract.py`, spec 0009)
stays inside `scrapers/`, distinct from the cross-source pipeline-layer-sampling rule
below it (`test_data_sampler/`) — the two bullets previously used `rca_extract.py` as
an example of both, which was ambiguous.*

*Last updated: 2026-08-07 — verified against commit `bbbb291`; `test_data_sampler/`
tree comment and placement bullet now also cover `sample_quiz_enriched`, which copies the
sampled quiz subset's already-enriched files from `data/enriched/quiz-patente-ab/` into
`data/test-data/enriched/quiz-patente-ab/` — added while extracting spec 0008 Phase 2's
plan, since `data/test-data/enriched/` didn't exist yet and generating it for real would
mean re-running LLM enrichment.*

*Last updated: 2026-08-07 — verified against commit `bbbb291`; spec 0008 Phase 2 landed:
new `src/commons/ai/utils/` package (`reciprocal_rank_fusion`) plus a matching
placement bullet, `commons/` tree comment updated to list it. `cli/services/evaluation/`
and `cli/models/evaluation/` gained the multi-arm harness's new files
(`multi_arm_retrieval_evaluator.py`, `ranking_delta.py`, `arm_result.py`,
`multi_arm_evaluation_summary.py`) — no new rule needed, the 2026-08-05 entry above already
covers this pair generically.*

*Last updated: 2026-08-07 — verified against commit `bbec1a0` (working tree ahead of it,
uncommitted on `feat/ingestion`); `guidami_ai_patente_ingestor/` gained two new top-level
packages: `providers/` (`LayerResolverProvider`, moved out of `services/` and renamed —
new role bullet added to the package-per-role chain) and `utils/` (`comma_repeal_detector.py`,
moved out of `services/knowledge/`, unchanged behavior, still re-exported from
`services/knowledge/__init__.py`). Also: every `UseCase`/`AsyncUseCase` subclass under a
`services/` folder now also takes the `Service` suffix (`ArticleCleaner` →
`ArticleCleanerService`, `DeduplicateQuizItems` → `DeduplicateQuizItemsService`,
`EmbedQuizVariants` → `EmbedQuizVariantsService`, `ImageDescriptionEnricher` →
`ImageDescriptionEnricherService`, `NormReferenceEnricher` → `NormReferenceEnricherService`)
— rule updated in `.claude/rules/code-conventions.md`.*

*Last updated: 2026-08-08 — verified against commit `8d85a0bc` (working tree ahead of it,
uncommitted); `commons/ai/embedding/` gained `protocols/` (`TextComposer[T]` +
`OptionalTextComposer[T]`), `models/`, and a new sixth subpackage `composition/`
(`FieldSpecComposer[T]` implementing `OptionalTextComposer[T]`, `TemplateComposer[T]`/
`CallableComposer[T]` implementing `TextComposer[T]` — a role the five-subpackage template
doesn't name), alongside the existing `clients/`/`configs/`/`services/`.
`configs/embedding_config.py` renamed to `configs/embedding_client_config.py`
(`EmbeddingConfig` → `EmbeddingClientConfig`). `commons/observability/progress_reporter/`
gained a new `tracker.py` (a generator-function helper, not a class — see `docs/patterns.md`).
ADR 0014 (a proposed **seventh** subpackage member, `VariantModelEmbeddingService[T]`, to
generalize quiz's dedup/omission/fan-out mechanics) was rejected — see
`docs/adr/0014-embedding-composition-layer.md`, status `Rejected`; that logic stays local to
`guidami_ai_patente_ingestor/services/quiz/` (new file `quiz_variant_spec.py`).*

*Last updated: 2026-08-08 — verified against commit `507d2dfb` (working tree ahead of it,
uncommitted, on new branch `feat/backend`); `src/guidami_ai_patente/` layout scaffolded:
`api/` (self-contained web layer — `app.py::create_app`, `routers/health.py`,
`schemas/health.py`), `configs/app_config.py::AppConfig` (root `BaseSettings`, embeds
`commons.configs.PostgresConnectionConfig`), and empty pull-based `services/`,
`repositories/`, `models/`, `mappers/` packages. Entry point `main.py::main`, registered as
the `api` script in `pyproject.toml`. Added `fastapi`/`uvicorn[standard]` as project
dependencies. Only concrete endpoint so far: `GET /health`, verified booting end-to-end
via `uv run api`.*
