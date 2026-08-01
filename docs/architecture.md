# Architecture

## Overview

`guidami-ai-patente` is a batch-pipeline project that builds a
retrieval-ready corpus for a future quiz bot over the Italian driving
exam: it scrapes/parses the normative corpus (Codice della Strada + CAP)
and a quiz question bank, cleans and LLM-enriches both, then embeds and
stores them in Postgres/pgvector.

Two apps live side by side under `src/`:
- `guidami_ai_patente_ingestor/` — the batch ingestion app. Fully
  implemented: preparation (clean + enrich) and indexing (embed + store)
  pipelines for both the knowledge corpus and the quiz bank.
- `guidami_ai_patente/` — the FastAPI quiz-bot app. **Not started**:
  only a package scaffold (`__init__.py`, `py.typed`) exists.

Two shared foundation packages support both apps (and are meant to keep
doing so once the FastAPI app starts):
- `commons/` — infrastructure: embedding clients, the Postgres client,
  LLM agent base class, `UseCase`/`ForEach` composition primitives,
  configs.
- `domain/` — entities/models persisted or shared across apps
  (`knowledge_chunk`, `quiz_question`, `retrieval_result`). `quiz_question`
  is flat: its former nested `quiz_metadata` was demoted to a transient
  ingestion model (`guidami_ai_patente_ingestor/models/quiz/quiz_metadata.py`)
  and flattened into columns (see `adr/0002-flatten-quiz-metadata-columns.md`).

`flowstep` is a domain-agnostic sequential-pipeline framework
(`Flow`/`Step`/`FlowBuilder`/`FlowContext`/`ApplyStep`) that the ingestor
is built on top of; it is an external git dependency (github.com/alessiogilardi/flowstep,
tracking `main` — see `[tool.uv.sources]` in `pyproject.toml`), not an
in-repo package. `parsers/` and `scrapers/` are one-shot data-acquisition
scripts, each registered as a `[project.scripts]` entry.

## Main components

| Component | Role | Main technology |
|---|---|---|
| `commons/ai/embedding/` | `clients/`: `EmbeddingClient` ABC (`embed_query`, `embed_passages`); `LiteLLMEmbeddingClient` (production) and `SentenceTransformerEmbeddingClient` (offline alternative, not hot-swappable — different dimension). `services/`: `EmbeddingService` (batching) + `Embeddable`/`Embedded` protocols. `configs/`: `EmbeddingConfig` | litellm (→ OpenRouter), sentence-transformers |
| `commons/ai/agents/` | `BaseAgent[T_In, T_Out]` — wraps `pydantic_ai.Agent`, loads `AgentConfig` (in `configs/`) from YAML, renders prompts via `PromptRenderer`; requires an injected `OpenRouterProvider` (never reads env itself); optionally tracks every call via an injected `LlmCallTracker` port | pydantic-ai-slim[openrouter] |
| `commons/configs/` | Shared, app-agnostic Pydantic settings: `PostgresConnectionConfig`, `OpenRouterConfig` (`BaseSettings`, `env_prefix="OPENROUTER_"`, holds `api_key: SecretStr`) | pydantic-settings |
| `commons/ai/observability/` | `LlmCallTracker` port (`protocols/`) + `PydanticAILlmCallCapture`/`QueuedLlmCallTracker` (`services/`) + `LlmCallLogRepository` (`repositories/`) + `LlmCallLogMapper`/`LlmCallCaptureModel` (`mappers/`, `models/`) — populates `llm_call_logs`; commons-level (not ingestor-only) because the future FastAPI app will track calls too | psycopg[binary] |
| `commons/observability/` | `ItemProgressReporter`/`ProgressReporter` port (`protocols/`) + `NullProgressReporter` (`services/`) — progress reporting for the ingest CLI's live dashboard (spec 0002); a sibling of `commons/ai/observability/`, not nested under it, since it is not AI-specific | — |
| `commons/clients/postgres_client.py` | Generic, table-agnostic Postgres/pgvector client | psycopg[binary], pgvector |
| `commons/use_cases/` | `UseCase`/`AsyncUseCase`, `ForEach`, `FlatMap` — generic composition primitives used across pipeline steps | — |
| `domain/entities/`, `domain/models/` | Persisted entities and shared cross-app models | pydantic |
| `flowstep` (external dependency) | Generic sequential-pipeline engine (`Flow`, `Step`, `FlowBuilder`, `FlowContext`, `ApplyStep`) | git dependency (github.com/alessiogilardi/flowstep) |
| `guidami_ai_patente_ingestor/` | Batch ingestion app — orchestrators, services, repositories, mappers, agents, models, configs (see flows below) | — |
| `guidami_ai_patente_ingestor/cli/` | Self-contained `ingest` CLI package (entry point, argument parsing, lazy DI wiring, per-subcommand dispatch, CLI-local `status` services/DTOs/renderer) — see `.claude/rules/cli-structure.md` and the `ingest status` flow below | argparse, rich |
| `guidami_ai_patente/` | FastAPI quiz bot — **not started** | FastAPI (planned) |
| `parsers/questions_pdf.py` | Quiz PDF → `data/parsed/quiz-patente-ab/` | pdfplumber, pymupdf |
| `scrapers/normattiva.py` | normattiva.it → `data/raw/` + `data/parsed/` | beautifulsoup4, lxml, httpx |
| `scrapers/rca_extract.py` | Filters the full CAP corpus (`data/parsed/cap/codice_assicurazioni_private.json`) down to `IngestorConfig.rca_ranges` (inclusive numeric ranges over the article's leading number) → `data/parsed/cap/codice_rca.json`; not wired into `main_cap` or the `ingest` CLI — a standalone follow-up step | stdlib only |

`parsers/questions_pdf.py` extracts each sub-question's image lazily: the
per-question default image (fallback for rows without their own nearby
image) is only extracted the first time a row actually needs it, not
eagerly when the question is created. Extracting it eagerly regardless of
use silently orphans files under `data/parsed/quiz-patente-ab/images/`
whenever every row of a question resolves its own row-level image instead.

LLM agents in use today (all `BaseAgent` subclasses under
`guidami_ai_patente_ingestor/agents/`) — **knowledge-corpus enrichment has
been removed** (spec 0001 FR-16/AD-18, plan task T-13): `ContextEnricher`,
`ArticleContextualizerAgent` (+ its DTOs/mapper/yaml config), and
`build_knowledge_enrichment_flow` no longer exist. `ingest prepare
knowledge` now runs a cleaning-only flow (no LLM call); the two remaining
agents are quiz-only:
- `RoadSignDescriberAgent` — vision agent, quiz enrichment; deliberately
  answer-blind (see ADR below). Owns image-file reading via its
  `PromptRenderer`/`file_reader`; `ImageDescriptionEnricher` only passes
  image paths and holds no reader of its own. Called **once per distinct
  image** (not per quiz), concurrently across images, bounded by
  `IngestorConfig.road_sign_describer_concurrency` (default `8`) — see
  `adr/0003-group-road-sign-description-by-image.md` and `patterns.md`.
- `NormReferenceDescriberAgent` — quiz enrichment, norm-reference metadata
  for future RAG retrieval. Answer-aware (the counterpart to the
  answer-blind road-sign describer): its request carries `correct_answer`,
  and its prompt instructs that when the statement is **false** the metadata
  must describe the *correct* norm, not the false claim — so retrieval lands
  on the right CdS/CAP article either way.

Storage: Postgres 16 + pgvector — see `database.md`. Embedding: production
model is `text-embedding-3-small` (OpenAI), 1536-dim, via litellm routed
through OpenRouter, authenticated with `OPENROUTER_API_KEY` (litellm reads
the env var itself). LLM agents (`BaseAgent`) authenticate differently:
`cli/wiring.py:build_open_router_provider` builds one `OpenRouterProvider`
from `IngestorConfig.open_router_config.api_key` (populated from the same
`OPENROUTER_API_KEY` via `commons.configs.OpenRouterConfig`), built lazily
by `cli/main.py` only for the `prepare` command (never for `index`/`reset`/
`status`), and threads it explicitly through every
`build_*_enrichment_flow(...)` → `Agent.from_yaml(..., provider=...)` call —
no agent constructor reads the environment directly (see `patterns.md`).

## Main flows

Entry point: `guidami_ai_patente_ingestor/cli/` (package, not a single
module) — `ingest prepare|index|reset knowledge|quiz` and `ingest status
[--online]` (see command table in `CLAUDE.md`). `cli/main.py` loads
`IngestorConfig`, builds the parser (`cli/parser.py:build_parser`) and
dispatches by subcommand to `cli/commands/{prepare,index,reset,status}.py`;
`cli/wiring.py` holds the lazy DI builders (`build_layer_resolver`,
`build_open_router_provider`, `build_postgres_client`, `build_tracker`,
`build_health_repositories`) so each command only builds the
clients/providers it actually needs. `run_preparation` wraps every
preparation flow with idempotency (skips a stage if its output file already
exists, unless `--force`).

**`--dry-run`** (`prepare`/`index`/`reset` only, every entity; `status` has
none — it never mutates anything): each `run_*` command function checks
`args.dry_run` as its first instruction, before any wiring call, and if set
calls a private `_render_*_dry_run` helper that describes the step chain via
`cli/rendering/dry_run_renderer.py:render_dry_run` (a `rich.Panel`; step text
is markup-escaped with `rich.markup.escape` since a literal `[...]` substring
is otherwise silently swallowed as an invalid style tag), then returns — no
`wiring.build_postgres_client`, no flow construction, no LLM/DB/filesystem
access.

**Per-run file logging**: `cli/main.py:main` parses args first (the log
folder name needs `args.command`), then calls
`cli/logging_setup.py:configure_logging(config.project_root, args.command,
dry_run=..., use_console_handler=...)`, which attaches a `FileHandler` to the
root logger unless `dry_run`, plus a console `StreamHandler` only when
`use_console_handler` is True — `main` passes `use_console_handler=dashboard
is None`, since a live dashboard owns the console itself (see below) and would
otherwise corrupt its `Live` region by racing a plain `StreamHandler` writing
to the same stream. Every `logging.getLogger(...)` call anywhere in the
codebase is still captured either way: by the `FileHandler` always, and by
whichever console sink (`StreamHandler` or the dashboard's `LogPanelHandler`)
is active. Log files land in `logs/ingest_<command>_<YYYYMMDDHHMM>/run.log`; a
same-minute collision appends a numeric suffix (`_2`, `_3`, ...) via the
private `_build_run_dir`. `--dry-run` runs never get a log directory — that
would contradict the "no filesystem writes" guarantee `render_dry_run` prints.

**Live dashboard** (`prepare`/`index` only, interactive TTY, non-dry-run,
non-`--plain` — spec 0002): `cli/main.py:_build_dashboard(args)` returns a
`cli/rendering/dashboard/live_dashboard.py:LiveDashboard` when
`args.command` is `prepare`/`index`, `args.dry_run` and `args.plain` are both
falsy (via `getattr(args, ..., False)`, since `reset`/`status` define
neither flag), and `rich.console.Console().is_terminal` is True; otherwise
`None`. `main()` always passes a concrete `ProgressReporter` down — the
dashboard itself when built, else `commons.observability.NullProgressReporter`
— so no command or flow factory ever branches on whether a dashboard exists.
When a dashboard is built, `main()` enters it through a `contextlib.ExitStack`
around the command dispatch, so it is torn down (its `Live` stopped, its
`LogPanelHandler` detached from the root logger) *before* any exception from
the flow propagates to the terminal (FR-5).

Progress rides two independent channels, both driven by the same
`ProgressReporter`, composed with no branching thanks to the null-object
default:
- **Step/flow position** rides `flowstep`'s own `FlowObserver` protocol.
  `orchestrators/progress_flow_observer.py:ProgressFlowObserver` adapts it
  onto `ProgressReporter.begin_step`/`end_step`; every `build_*_flow` factory
  registers one via `FlowBuilder.add_observer(ProgressFlowObserver(reporter))`
  — composed with, not replacing, the framework's default
  `LoggingFlowObserver`. The flow-level bar (`begin_run`/`begin_flow`/
  `end_flow`) is driven one level up, by `dispatch_prepare`/`run_index`
  themselves: a `Flow` only knows its own steps, never how many flows
  `begin_run` covers — `index` always runs one flow; `prepare` runs one for
  knowledge (cleaning only, since T-13 removed enrichment) and two for quiz
  (cleaning + enrichment), so `dispatch_prepare` passes a per-entity
  `begin_run` count rather than a shared constant.
- **Item-level position** (inside one long-running step) rides the
  `commons/observability/` `ProgressReporter` port directly, injected as the
  last constructor argument into the three instrumented services:
  `EmbeddingService` (one tick per batch), and, inside the single
  `enrich_quiz` step, `ImageDescriptionEnricher` then `NormReferenceEnricher`
  in sequence (one tick per distinct image, then one tick per post-dedup
  unique question) — two successive item bars for that one step.
  (`ContextEnricher` was a fourth such service before spec 0001/T-13 removed
  knowledge-corpus enrichment entirely.)

`cli/rendering/dashboard/log_panel_handler.py:LogPanelHandler` is a bounded
(`deque(maxlen=15)`) `logging.Handler` that also filters out third-party
loggers (`httpx`, `httpcore`, `litellm`, `openai`, `urllib3`, case-insensitive
prefix match) from the panel only — the run log file, via the separate
`FileHandler`, still receives every record unfiltered and unbounded. Its
lifetime is scoped to the dashboard, not to `configure_logging`: attached to
the root logger in `LiveDashboard.__enter__`, detached and closed in
`__exit__`. `--plain` (leaf-subparser flag, `prepare`/`index` only, mirroring
`--dry-run`) and a non-interactive stdout both degrade to the pre-dashboard
plain-logging behavior, satisfying FR-4 with no separate code path.

**LLM call observability** (`prepare` path only, no agent calls on `index`/`reset`):
`cli/commands/prepare.py:run_prepare` opens a `PostgresClient` (via
`wiring.build_postgres_client`) and, inside `with postgres_client,
wiring.build_tracker(postgres_client) as tracker:`, dispatches to
`dispatch_prepare(..., tracker)`, which forwards `tracker` into
`build_quiz_enrichment_flow` → the agents' `from_yaml(..., tracker=tracker)`
(the knowledge side has no enrichment flow/agent left to forward it to,
since T-13 removed context enrichment — `tracker` is simply unused on that
branch). Inside `BaseAgent.run`/`run_sync`, a tracked call is
wrapped in `PydanticAILlmCallCapture` (records prompt/response/tokens/latency/status
synchronously, including `cost_usd` — summed from OpenRouter's own reported cost on every
`ModelResponse` in the run, see `adr/0004-openrouter-native-cost-tracking.md`) and
`tracker.track(capture.log)` enqueues the already-final log for the background worker,
which just inserts it via `LlmCallLogRepository` — off the hot path, so a slow/failing
DB write never blocks the LLM call. If
`PostgresClient` construction fails (`psycopg.Error`), `run_prepare` logs a warning and
dispatches with `tracker=None`: `BaseAgent.__init__` substitutes a `NullLlmCallTracker`
(Null Object, see `docs/patterns.md`), so the capture is still built on every call but
`track()` is a no-op — the LLM output is unaffected, only the DB write is skipped.

**`ingest status [--online]`** (`cli/commands/status.py:run_status`, never
raises, always exits 0): `cli/services/status/status_inspector.py:
StatusInspector.evaluate_readiness()` computes a per-(command, entity)
readiness matrix (`RUNNABLE`/`SKIP`/`BLOCKED`) purely from
`Path.exists()` checks via `LayerResolver` — no DB, no network, by default.
For **quiz** (still monolithic single-file layers): `prepare` is `SKIP` when
its enriched output already exists, `BLOCKED` when its parsed input is
missing, else `RUNNABLE`; `index` has no filesystem signal for its output (a
DB table), so it is only `RUNNABLE`/`BLOCKED` depending on whether its
enriched input exists. For **knowledge** (per-element `cleaned`/`enriched`
directories — see the flow description above): `prepare` is **never** `SKIP`
(a directory can be partially populated, so there is no honest binary
"already done" signal), only `BLOCKED` when its `parsed` input file is
missing (that layer is still a single file) or `RUNNABLE`; `index`'s input is
now a directory too, so it drops the `BLOCKED` signal as well and is always
`RUNNABLE`. `StatusInspector` takes this `per_element` flag from the caller
rather than inferring it from the entity name, so the readiness logic itself
stays free of hardcoded domain strings. `reset` is always `RUNNABLE` offline
for both entities (a single synthetic entry per entity, no source
dimension). With `--online`, `run_status` best-effort opens a
`PostgresClient` (catching `psycopg.Error` → `db_reachable=False,
tables=None`, still exits 0) and, if reachable, runs
`cli/services/status/table_health_checker.py:TableHealthChecker` over the
repositories from `wiring.build_health_repositories` to report per-table
existence and row count (`table_exists()`/`row_count()`, added to the
shared `BulkInsertStoreRepository` base — the one explicit exception to the
CLI's self-containment, see `.claude/rules/cli-structure.md`).
`cli/rendering/status_renderer.py:render` presents the report via `rich`,
masking `postgres.password`/`open_router_config.api_key` to `****`/
`missing` — never printed in clear.

**Knowledge corpus** (per source, `cds`/`cap` — `orchestrators/knowledge_flows.py`). `cleaned`
is a **per-element** layer (one JSON file per article, named by a deterministic
`commons.utils.element_id(source, number)`; `parsed` stays a single monolithic file
per source — see `docs/plans/2026-07-17--per-element-knowledge-layers.md`). The
`enriched` layer name still exists in `LayerResolver` config, but only the quiz
pipeline writes to it now (AD-19) — the knowledge corpus has no `enriched` stage:
1. *Cleaning*: `LoadJsonStep` (parsed, single file) → `ApplyStep(ForEach(ArticleCleaner), ForEach(partial(ArticleMapper.from_parsed_to_cleaned, source=source)))` → `FilterAlreadyDoneStep` (drops articles already present in `cleaned/`) → `WriteJsonDirStep` (one file per article). `ArticleCleaner` operates on `ParsedArticleModel.commas: list[ParsedComma]` (structured per-comma, spec 0001 T-5/T-6), not a flat `paragraphs`/`text` pair — it only normalizes the title and strips residual inline markup from each comma's text, never dropping a comma.
2. *Enrichment* — **removed** (spec 0001 FR-16/AD-18, plan task T-13):
   `ingest prepare knowledge` runs the cleaning flow only; there is no LLM call
   anywhere in the knowledge-preparation path.
3. *Indexing* (spec 0001 T-14 — **working end-to-end**, validated by a live-Postgres integration test): `LoadJsonDirStep` (`cleaned`, per-element, `CleanedArticleModel`) → `ApplyStep("map_to_article_entities", ForEach(ArticleMapper.from_cleaned_to_article_entity))` → `ApplyStep("expand_to_embeddable_commas", FlatMap(ArticleMapper.from_cleaned_to_embeddable_commas))` → `EmbedCommasStep` → `StoreArticlesAndCommasStep` (writes both `articles` and `article_commas` in one step, per PD-7, keeping a source's full reload — delete-by-source then insert — atomic at the step boundary). The two `ApplyStep`s are an intentional fan-out (PD-12): both read the *same* loaded `CLEANED_ARTICLES` list independently (article rows and comma rows derived in parallel), rather than one being reconstructed from the other. No LLM call anywhere in this chain; the embedding input is article title + raw comma text only (AD-18).

Spec 0001 "Article-level storage with first-class commas" is now fully implemented
(plan tasks T-1 through T-16 complete). The superseded chunk-based chain
(`ArticleChunker`, `EmbedChunksStep`, `StoreChunksStep`, `KnowledgeChunkStoreRepository`,
`KnowledgeChunk`, `EmbeddableChunkModel`, `EnrichedArticleModel`, `RetrievalResult`)
has been deleted (T-15) — `knowledge_chunks` is gone from both the schema and the
codebase; the corpus normativo is stored exclusively as `articles`/`article_commas`.

Resumability from the per-element layout is **cross-run only**: a re-run of
`ingest prepare knowledge` without `--force` re-processes only the articles
missing their destination file (`FilterAlreadyDoneStep`); a crash *during* a
run still loses that run's unwritten work, since writing stays a terminal
`WriteJsonDirStep` (write-through is deferred to a future plan). `--force`
bypasses the filter entirely (every article is kept, no filesystem check).
`CleanedArticleModel` (`models/knowledge/cleaned_article.py`) carries its own
`source: Literal["cds", "cap"]`, stamped on at the parsed→cleaned boundary by
`ArticleMapper.from_parsed_to_cleaned`, making the element's id (and its
filename) computable from the element alone, independent of flow context.

**Quiz bank** (`orchestrators/quiz_flows.py`):
1. *Cleaning*: `LoadJsonStep` → `ApplyStep(FlatMap(QuizMapper.from_parsed_to_cleaned_all), DeduplicateQuizItems())` → `WriteJsonStep` (parsed → cleaned; dedup on normalized-text + correct_answer + image identity).
2. *Enrichment*: `LoadJsonStep` → `ApplyStep(ForEach(QuizMapper.from_cleaned_to_enriched))` → `AsyncApplyStep(ImageDescriptionEnricher(road_sign_describer_concurrency, RoadSignDescriberAgent), NormReferenceEnricher(NormReferenceDescriberAgent))` → `WriteJsonStep` (cleaned → enriched). The mapping runs in a synchronous `ApplyStep`; both enrichers run in a separate `AsyncApplyStep` (concurrent LLM calls). `ImageDescriptionEnricher` groups quizzes by image filename and issues one concurrent vision call per image (see `patterns.md`), writing both the flat `image_description` (downstream/embedding field) and the structured `image_analysis` (full LLM output, debug-only) onto every quiz sharing that image.
3. *Indexing*: `LoadJsonStep` → `ApplyStep(DeduplicateQuizItems(), ForEach(QuizMapper.from_enriched_to_embedded))` → `ApplyStep(EmbedQuizMetadata)` → `ApplyStep(ForEach(QuizMapper.from_embedded_to_quiz_question))` → `DbStoreStep` (full truncate + bulk insert). `EmbedQuizMetadata` extracts `quiz_metadata` (itself `Embeddable`) from each item and calls `EmbeddingService` on that list directly — not on the `EmbeddedQuizModel` items themselves, which no longer implement `Embeddable`/`Embedded`. Items without `quiz_metadata` end up with `embedding=None`. `QuizMetadata` stays a cohesive nested object through the ingestion models (`EnrichedQuizModel`/`EmbeddedQuizModel`) and is flattened onto the `QuizQuestion` entity columns **only** at the boundary, inside `from_embedded_to_quiz_question`.

## Relevant architectural decisions

See `adr/` for the full history. Currently accepted:

- **Road sign describer is answer-blind** — `RoadSignDescriberAgent`
  never receives `correct_answer` in its request DTO, by design, to avoid
  the description leaking the answer. Still true in code today.
- **Quiz metadata flattened into columns** — the retrieval-relevant
  `QuizMetadata` fields are first-class `quiz_questions` columns and
  `QuizMetadata` is a transient ingestion model, not a persisted entity
  (`adr/0002-flatten-quiz-metadata-columns.md`).
- **Road sign description is grouped by image, not by quiz** —
  `ImageDescriptionEnricher` keys on the image filename only; all quizzes
  sharing an image get one vision call and one `image_description`/
  `image_analysis` instead of one call per `(image, topic, text)` triple
  (`adr/0003-group-road-sign-description-by-image.md`).
- **LLM call tracking is a port injected into `BaseAgent`, not an external
  wrapper** — token usage (`result.usage()`) only exists inside
  `run`/`run_sync`; an external decorator would force `BaseAgent.run` to
  return a rich result object, breaking every enricher. `LlmCallTracker`
  persistence failures degrade gracefully (log a warning, never abort the
  pipeline) — a deliberate, documented exception to "never swallow
  exceptions" (`.claude/rules/python/standards.md`; see also `patterns.md`).
- **`cost_usd` comes from OpenRouter's own reported cost, not a litellm
  pricing-table lookup** — `BaseAgent` uses `pydantic_ai`'s `OpenRouterModel`
  with `openrouter_usage={"include": True}`, and `PydanticAILlmCallCapture`
  sums `ModelResponse.provider_details["cost"]` synchronously; no fallback
  estimate when OpenRouter omits cost (`adr/0004-openrouter-native-cost-tracking.md`).
- **Per-element knowledge layers, cross-run resumability, write-through
  deferred** — `cleaned`/`enriched` for the knowledge corpus moved from one
  monolithic JSON per source to one JSON file per article, so a `--force`-less
  re-run only pays for the articles still missing (see the flow description
  above and `docs/plans/2026-07-17--per-element-knowledge-layers.md`). Full
  write-through (durable progress *during* a run, not just across runs) is
  explicitly out of scope for this change and left to a follow-up plan.
- **`ingest` CLI is a self-contained package with lazy DI wiring** — the
  former 278-line `cli.py` monolith (which built a `PostgresClient` and an
  `OpenRouterProvider` eagerly in `main()` for every command) was split into
  `cli/{main,parser,wiring}.py` + `cli/commands/*.py`; clients/providers are
  now built per command in `wiring.py`, so `reset`/`status` run without
  `OPENROUTER_API_KEY`, and `status` never touches the network unless
  `--online` is passed. `status`'s readiness/health services and DTOs
  (`cli/services/status/`, `cli/models/status/`) are CLI-local rather than
  top-level `services/`/`models/`, since nothing outside the CLI consumes
  them (`.claude/rules/cli-structure.md`).

*Last updated: 2026-08-01 — verified against commit `c457354`; added
`scrapers/rca_extract.py` (T-4); spec 0001 "Article-level storage with first-class
commas" is now fully implemented (T-1 through T-16 complete) — knowledge-corpus
enrichment removed (T-13), `build_knowledge_indexing_flow` rewired to
`articles`/`article_commas` and working end-to-end (T-14), and the superseded
chunk-based chain (`ArticleChunker`, `EmbedChunksStep`, `StoreChunksStep`,
`KnowledgeChunkStoreRepository`, `KnowledgeChunk`, `EmbeddableChunkModel`,
`EnrichedArticleModel`, `RetrievalResult`) deleted entirely (T-15).*
