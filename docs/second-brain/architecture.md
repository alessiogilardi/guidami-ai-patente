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
- `guidami_ai_patente/` — the FastAPI quiz-bot app. **Layout scaffolded,
  no domain endpoints yet**: a self-contained `api/` web layer (app
  factory, routers, schemas), pull-based `services/`/`repositories/`
  holding their first real (non-domain) classes, empty `models/`/
  `mappers/`, and `configs/` with a root `AppConfig`. Only concrete route
  so far is `GET /health`, which also doubles as the first live proof of
  `pywire`'s native FastAPI wiring (`pywire.fastapi.wire()`) — see the
  `guidami_ai_patente/` row below.

Two shared foundation packages support both apps (and are meant to keep
doing so once the FastAPI app starts):
- `commons/` — infrastructure: embedding clients, the Postgres client,
  LLM agent base class, `UseCase`/`ForEach` composition primitives,
  configs.
- `domain/` — entities/models persisted or shared across apps, grouped by
  bounded context: `entities/knowledge/` (`ArticleEntity`, `ArticleCommaEntity`),
  `entities/quiz/` (`QuizQuestionEntity`), `entities/observability/`
  (`LlmCallLogEntity`). The former `knowledge_chunk` was split into article +
  comma by spec 0001, and `retrieval_result` was deleted in the same change —
  a read-path model returns when the retrieval layer actually exists. `quiz_question`
  is flat: its former nested `quiz_metadata` was demoted to a transient
  ingestion model (`guidami_ai_patente_ingestor/models/quiz/quiz_metadata.py`)
  and flattened into columns (see `adr/0002-flatten-quiz-metadata-columns.md`).

`flowstep` is a domain-agnostic sequential-pipeline framework
(`Flow`/`Step`/`FlowBuilder`/`FlowContext`/`ApplyStep`) that the ingestor
is built on top of; it is an external git dependency (github.com/alessiogilardi/flowstep,
tracking `main` — see `[tool.uv.sources]` in `pyproject.toml`), not an
in-repo package. `parsers/` and `scrapers/` are one-shot data-acquisition
scripts, each registered as a `[project.scripts]` entry. `retrieval_evaluation/`
is a similarly standalone script package — an LLM-as-judge measurement tool
(`evaluate-retrieval-judge`), deliberately outside both apps and outside the
`ingest` CLI (ADR 0013).

## Main components

| Component | Role | Main technology |
|---|---|---|
| `commons/ai/embedding/` | `clients/`: `EmbeddingClient` ABC (`embed_query`, `embed_passages`); `LiteLLMEmbeddingClient` (production) and `SentenceTransformerEmbeddingClient` (offline alternative, not hot-swappable — different dimension) — unchanged. `configs/`: `EmbeddingClientConfig` (renamed from `EmbeddingConfig` — it configures the *client*, not the module). `protocols/`: `TextComposer[T]` (`compose(model: T) -> str`, the 1:1 case — always a string, the port `ModelEmbeddingService[T]` depends on) and `OptionalTextComposer[T]` (`compose_or_none(model: T) -> str | None`, its counterpart for a representation that may legitimately be absent for a given model — `None` signals "nothing to embed", never a partial text; a distinct method name, not an overload of `compose`, since one class can implement both protocols at once). `models/`: `FieldSpec`/`EmbeddingSpec` (declarative composition recipe, dataclasses — `Callable` fields rule out `BaseModel`), `EmbeddingResult[T]` (`model`/`text`/`embedding` triple). `composition/`: `FieldSpecComposer[T]` (declarative, field-by-field; implements **both** `TextComposer[T]` (`compose`, always a string) and `OptionalTextComposer[T]` (`compose_or_none`, `None` when a field marked `skip_if_none=False` — "required" — is missing) — the caller picks whichever method its pipeline needs), `TemplateComposer[T]` (`string.Template` `$var` substitution against a `BaseModel`/dataclass/`Mapping`, dispatch ported from `agents/utils/prompt_renderer.py::PromptRenderer`, but strict `.substitute()` not `.safe_substitute()` — an unresolved placeholder must fail loud, not get embedded literally into the text sent for embedding; implements `TextComposer[T]`), `CallableComposer[T]` (wraps any `Callable[[T], str]`, e.g. a model's own computed property, avoiding a throwaway composer class per model type; implements `TextComposer[T]`). `services/`: `EmbeddingService` (batching, `Sequence[str] -> list[list[float]]`, unchanged public contract — internals now use `itertools.batched` and a new `commons.observability.progress_reporter.tracker` generator instead of manual chunking); `ModelEmbeddingService[T]` (composes+embeds a batch of models 1:1 via an injected `TextComposer[T]`, delegating all chunking/progress to the injected `EmbeddingService`). Per-variant dedup/omission/fan-out (N text representations of one model, each with its own omission rule and dedup key) is **not** generalized here: ADR 0014 proposed a `VariantSpec[T]`/`VariantModelEmbeddingService[T]` pair for it, and was rejected (`docs/second-brain/adr/0014-embedding-composition-layer.md`, status `Rejected`) — it stays domain logic local to `guidami_ai_patente_ingestor/services/quiz/` (see the quiz-indexing walkthrough below). Every `UseCase` in this module — and in the codebase generally — is invoked via `__call__`, never `.execute()` directly (`.claude/rules/use-case-invocation.md`) | litellm (→ OpenRouter), sentence-transformers |
| `commons/ai/agents/` | `BaseAgent[T_In, T_Out]` — wraps `pydantic_ai.Agent`, loads `AgentConfig` (in `configs/`) from YAML, renders prompts via `PromptRenderer`; requires an injected `pydantic_ai.providers.Provider[AsyncOpenAI]` (never reads env itself) — `OpenRouterProvider` selects `OpenRouterModel` (OpenRouter-specific cost tracking/settings), any other provider (e.g. `OllamaProvider`) selects the generic `OpenAIChatModel`, dispatched via the `_is_openrouter` property (`adr/0019-base-agent-generic-provider-ollama.md`); optionally tracks every call via an injected `LlmCallTracker` port | pydantic-ai-slim[openrouter] |
| `commons/configs/` | Shared, app-agnostic Pydantic settings: `PostgresConnectionConfig`, `OpenRouterConfig` (`BaseSettings`, `env_prefix="OPENROUTER_"`, holds `api_key: SecretStr`) | pydantic-settings |
| `commons/ai/observability/` | `LlmCallTracker` port (`protocols/`) + `PydanticAILlmCallCapture`/`QueuedLlmCallTracker` (`services/`) + `LlmCallLogRepository` (`repositories/`) + `LlmCallLogMapper`/`LlmCallCaptureModel` (`mappers/`, `models/`) — populates `llm_call_logs`; commons-level (not ingestor-only) because the future FastAPI app will track calls too | psycopg[binary] |
| `commons/observability/` | Thin re-exporting `__init__.py` over two self-contained sibling sub-packages: `progress_reporter/` (`ItemProgressReporter`/`ProgressReporter` port + `NullProgressReporter` + a `tracker(progress, label, items)` generator helper — iterates `items`, opening the track before the first, advancing after each is consumed, closing once exhausted or on exception; unrelated to the `LlmCallTracker`/`tracker` local variable in the LLM-observability narrative below, a pure naming coincidence — progress reporting for the ingest CLI's live dashboard, spec 0002) and `run_artifact_writer/` (`RunArtifactWriter` + a `models/` sub-package holding `RunManifest` (base) and `ScrapeManifest`; `RunArtifactWriterConfig` was removed, spec 0005 AD-5 — `RunArtifactWriter` is domain-agnostic mechanics only, no `protocols/`/`services/` split since AD-3 rejects a `Protocol` here with only one implementation; a context manager that owns one `logs/<prefix>_<timestamp>/` run directory, writing `run.log`/`manifest.json`/`report.md` from whatever `RunManifest` it holds and always finalizing them in `__exit__` even on an unhandled exception — shared between `ingest`'s `configure_logging` and the `scrapers/normattiva.py` scraper, spec 0005 AD-1/AD-4); a sibling of `commons/ai/observability/`, not nested under it, since it is not AI-specific. The `ingest`-only manifests (`PrepareManifest`/`IndexManifest`/`ResetManifest`) live in `guidami_ai_patente_ingestor/cli/models/run_artifacts/` instead, per the CLI self-containment rule (spec 0005 AD-6) | — |
| `commons/clients/postgres_client.py` | Generic, table-agnostic Postgres/pgvector client | psycopg[binary], pgvector |
| `commons/repositories/db/` | Read-only Postgres repositories, scoped **per entity** not per table (AD-7, spec 0007) — the project's first query code, every repository under `guidami_ai_patente_ingestor/repositories/db/` being write-only bulk insert. `CorpusReadRepository` (`articles` ⋈ `article_commas`) and `QuizReadRepository` (`quiz_questions` ⋈ `quiz_question_embeddings`), each taking an injected `PostgresClient`, mirroring `LlmCallLogRepository`'s shape. `CorpusReadRepository`'s shared `_BASE_SELECT` projection leads with `c.id` (spec 0011 FR-3), so every comma it returns — dense, random or text — can be joined back to its `article_commas` row without resolving a citation string. `QuizReadRepository.fetch_with_vectors(variant, model_column)` takes the model column explicitly (spec 0008 Phase 2, generalized from a single hardcoded `embedding_3_small`); `populated_model_columns()` introspects `information_schema.columns` for `embedding_*`-named columns holding ≥1 non-null vector, so the multi-arm evaluation harness's model axis needs no code change when a second model column is added (AD-6). Lives in `commons/` rather than the `ingest` CLI (which the self-containment rule would otherwise suggest) because a corpus reader is also what `src/guidami_ai_patente/` will eventually need — more than one consumer, same reasoning as `LlmCallLogRepository` | psycopg[binary], pgvector |
| `commons/use_cases/` | `UseCase`/`AsyncUseCase`, `ForEach`, `FlatMap` — generic composition primitives used across pipeline steps | — |
| `domain/entities/`, `domain/models/` | Persisted entities and shared cross-app models | pydantic |
| `flowstep` (external dependency) | Generic sequential-pipeline engine (`Flow`, `Step`, `FlowBuilder`, `FlowContext`, `ApplyStep`) | git dependency (github.com/alessiogilardi/flowstep) |
| `guidami_ai_patente_ingestor/` | Batch ingestion app — orchestrators, services, repositories, mappers, agents, models, configs (see flows below) | — |
| `guidami_ai_patente_ingestor/cli/` | Self-contained `ingest` CLI package (entry point, argument parsing, lazy DI wiring, per-subcommand dispatch, CLI-local `status` services/DTOs/renderer) — see `.claude/rules/cli-structure.md` and the `ingest status` flow below | argparse, rich |
| `guidami_ai_patente/` | FastAPI quiz bot — layout scaffolded (`api/` self-contained web layer, `configs/app_config.py::AppConfig`, empty pull-based `models/`/`mappers/`), only `GET /health` implemented so far; entry point `main.py::main`, registered as the `api` script. Dependency injection uses `pywire` (Spring-style `@service`/`@repository`/`@client`/`@component` decorators + `Autowired[T]` field injection), not the manual constructor injection the ingestor uses — see `adr/0015-pywire-di-for-fastapi-app.md` and `.claude/rules/pywire-di.md`. `pywire>=0.3.1` adds native FastAPI wiring: a single `wire(app)` call in `api/app.py::create_app` (never on an `APIRouter`) makes bare `Autowired[T]` route parameters resolve on every router mounted on the app; `services/health_check_service.py::HealthCheckService` (`Autowired[DependencyVersionRepository]`) is resolved this way on `GET /health` — no `Depends()` — proven live via `uv run api` + a real HTTP request, not just `TestClient`; see `adr/0016-pywire-native-fastapi-wiring.md` | FastAPI, uvicorn, pywire |
| `retrieval_evaluation/` | LLM-as-judge for retrieval quality (`evaluate-retrieval-judge` script) — deliberately separate from `ingest evaluate retrieval` (spec 0007 excludes an LLM judge as a Non-Goal, ADR 0013). `RetrievalJudgeAgent` + its DTOs (`agents/retrieval_judge/`, `BaseAgent` pattern — `agents/` is a generic per-role container, today holding the single `retrieval_judge/` agent subpackage) + `RetrievalJudgeEvaluationService` (`services/`) reuse `commons.repositories.db.{CorpusReadRepository,QuizReadRepository}` and `guidami_ai_patente_ingestor.configs.IngestorConfig` (Postgres/OpenRouter/table names/`agents_dir`) rather than owning new config or CLI infra | pydantic-ai-slim[openrouter] |
| `parsers/questions_pdf.py` | Quiz PDF → `data/parsed/quiz-patente-ab/quiz-patente-ab.json` (questions) + `data/quiz-images/` (extracted images, top-level, sibling of `parsed/` — ADR 0008) | pdfplumber, pymupdf |
| `scrapers/normattiva.py` | normattiva.it → `data/raw/` + `data/parsed/`, one `LawConfig` per law (`CDS`/`CAP`/`REG`/`AMB`) selected via a single `scrape --source <cds\|cap\|reg\|amb>` CLI entry point (`cli_main` — spec 0004 FR-1, replacing spec 0003's per-law `main_cds`/`main_cap`/`main_reg`; `AMB` — D.Lgs. 152/2006, Codice dell'Ambiente — added by spec 0009) | beautifulsoup4, lxml, httpx |
| `scrapers/range_filter.py` | Shared core (`filter_articles_by_range(source_path, dest_path, ranges)`) for narrowing a fully-scraped law down to inclusive numeric ranges over the article's leading number; extracted by spec 0009 once a second consumer (`amb_extract.py`) needed the identical algorithm `rca_extract.py` already had | stdlib only |
| `scrapers/rca_extract.py` | Filters the full CAP corpus (`data/parsed/cap/codice_assicurazioni_private.json`) down to `IngestorConfig.rca_ranges` → `data/parsed/cap/codice_rca.json`, via `range_filter.filter_articles_by_range`; not wired into `main_cap` or the `ingest` CLI — a standalone follow-up step | stdlib only |
| `scrapers/amb_extract.py` | Filters the full AMB corpus (`data/parsed/amb/codice_ambiente.json`) down to `IngestorConfig.amb_ranges` (Parte IV, Titolo III, artt. 227-237 — waste provisions covering used oil, batteries, tyres) → `data/parsed/amb/codice_ambiente_rifiuti.json`, same shape as `rca_extract.py`, registered as `extract-amb` (spec 0009) | stdlib only |
| `test_data_sampler/sampler.py` | Samples `--count` random elements per source from `data/parsed/{cds,cap,reg,quiz-patente-ab}` → `data/test-data/parsed/...`, copying only the quiz images the sampled questions reference from `data/quiz-images/` into `data/test-data/quiz-images/`; also copies the sampled quiz subset's already-enriched files from `data/enriched/quiz-patente-ab/` into `data/test-data/enriched/quiz-patente-ab/` (`sample_quiz_enriched`, keyed by `element_id("quiz", number)` — filesystem copy, no LLM call, no re-enrichment), so an integration test can exercise `ingest index quiz` end to end without either running enrichment or reading the full 7099-file bank; feeds `ingest --config configs/ingestor_config.test-data.yaml prepare\|index` (ADR 0006, ADR 0008) | stdlib only |

`parsers/questions_pdf.py` extracts each sub-question's image lazily: the
per-question default image (fallback for rows without their own nearby
image) is only extracted the first time a row actually needs it, not
eagerly when the question is created. Extracting it eagerly regardless of
use would silently orphan files under `data/quiz-images/` whenever every
row of a question resolves its own row-level image instead.

Images live in `data/quiz-images/`, a top-level directory sibling to
`raw/`/`parsed/`/`cleaned/`/`enriched/` rather than nested under `parsed/`
— unlike the JSON, image bytes never change after extraction, so they
aren't part of the parsed→cleaned→enriched transformation chain, and a
top-level location lets the future FastAPI quiz-bot app read them without
depending on the ingestion pipeline's internal staging (ADR 0008). At the
end of every `main_questions` run, `_referenced_images`/`_prune_orphans`
delete any file under `data/quiz-images/` no longer referenced by the
freshly-parsed output — cross-run drift (an image dropped by a PDF change
staying on disk forever) that the within-run MD5 dedup in `_save_image`
never addressed.

LLM agents in use today (all `BaseAgent` subclasses under
`guidami_ai_patente_ingestor/agents/`) — **knowledge-corpus enrichment has
been removed** (spec 0001 FR-16/AD-18, plan task T-13): `ContextEnricher`,
`ArticleContextualizerAgent` (+ its DTOs/mapper/yaml config), and
`build_knowledge_enrichment_flow` no longer exist. `ingest prepare
knowledge` now runs a cleaning-only flow (no LLM call); the two remaining
agents are quiz-only:
- `RoadSignDescriberAgent` — vision agent, quiz enrichment; deliberately
  answer-blind (see ADR below). Owns image-file reading via its
  `PromptRenderer`/`file_reader`; `ImageDescriptionEnricherService` only passes
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
module) — `ingest [--config PATH] prepare|index|reset knowledge|quiz` and
`ingest [--config PATH] status [--online]` (see command table in
`CLAUDE.md`). `--config` (anywhere in argv) is pre-parsed out by
`cli/main.py::_parse_config_override` — before `IngestorConfig` is built,
since the command parser itself is config-driven — then `main()` calls
`IngestorConfig.load(config_override)`, which inserts the override file as its
own `YamlConfigSettingsSource` (higher precedence than the base yaml, lower
than env/.env), deep-merged by pydantic-settings (ADR 0006, `patterns.md`).
`cli/main.py` loads `IngestorConfig`, builds the parser (`cli/parser.py:build_parser`) and
dispatches by subcommand to `cli/commands/{prepare,index,reset,status}.py`;
`cli/wiring.py` holds the lazy DI builders (`build_layer_resolver`,
`build_open_router_provider`, `build_postgres_client`, `build_tracker`,
`build_health_repositories`) so each command only builds the
clients/providers it actually needs. Both `dispatch_prepare` branches
(`knowledge` and, since spec 0006, `quiz`) run their flow(s) directly, with
no coarse per-source-file skip: idempotency lives entirely inside each
flow's `FilterAlreadyDoneStep`, which drops elements already present in the
per-element destination layer before the (possibly expensive) transform
runs. The former `run_preparation` helper (`orchestrators/preparation_runner.py`,
wrapping a whole flow with an `out_path.exists()` skip) is deleted — spec
0006/AD-5 removed its last consumer (quiz) once quiz's `cleaned`/`enriched`
layers became per-element too.

**`--dry-run`** (`prepare`/`index` only, every entity; `status` has
none — it never mutates anything): each `run_*` command function checks
`args.dry_run` as its first instruction, before any wiring call, and if set
calls a private `_render_*_dry_run` helper that describes the step chain via
`cli/rendering/dry_run_renderer.py:render_dry_run` (a `rich.Panel`; step text
is markup-escaped with `rich.markup.escape` since a literal `[...]` substring
is otherwise silently swallowed as an invalid style tag), then returns — no
`wiring.build_postgres_client`, no flow construction, no LLM/DB/filesystem
access.

**`reset`'s inverted gate** (`--apply`): `reset` is destructive (`TRUNCATE`),
so its default is flipped from every other command instead of reusing
`--dry-run`. `cli/commands/reset.py:run_reset` checks `not args.apply` first
and, unless `--apply` was passed, calls `_render_reset_preview` — the same
`render_dry_run` renderer as above — then returns with the identical
no-DB/no-filesystem guarantee (`wiring.build_postgres_client` is never even
called). `reset` does not define `--dry-run` at all; `--apply` is required to
run the real `TRUNCATE`. `cli/main.py:_is_dry_run(args)` centralizes this
direction flip for the two consumers below that need "is this a no-op
invocation": it returns `True` unconditionally for `status` (always
read-only, even `--online` only *reads* Postgres — spec 0005 AD-8, fixing a
prior bug where `status` fell through to the `getattr` default below and was
incorrectly treated as a real, writing run), `not args.apply` for `reset`,
and `getattr(args, "dry_run", False)` for every other command
(`prepare`/`index`).

**Per-run file logging and artifacts**: `cli/main.py:main` parses args first
(the log folder name needs `args.command`), then calls
`cli/logging_setup.py:configure_logging(config.project_root, args,
dry_run=_is_dry_run(args), use_console_handler=...)`. Unless `dry_run`, this
now builds and returns a full `RunArtifactWriter` (spec 0005 AD-4 — no longer
just a bare `run.log` `Path`): internally, `_build_manifest(args)` dispatches
on `args.command` to construct the command-appropriate manifest
(`PrepareManifest`/`IndexManifest`/`ResetManifest`, `guidami_ai_patente_ingestor
.cli.models.run_artifacts`, never called for `status` — AD-8 makes it always
dry-run), and `RunArtifactWriter(logs_root, run_id_prefix=f"ingest_{args
.command}", manifest=...)` reserves the run directory. `main` then enters the
writer through its existing `contextlib.ExitStack` (the same one conditionally
entering the live dashboard) — `stack.enter_context(writer)` attaches the
`run.log` `FileHandler`, and the `ExitStack`'s exception safety guarantees
`manifest.json`/`report.md` are written by `RunArtifactWriter.__exit__` even
if the dispatched command raises. `configure_logging` itself still installs a
console `StreamHandler` only when `use_console_handler` is True — `main`
passes `use_console_handler=dashboard is None`, since a live dashboard owns
the console itself (see below) and would otherwise corrupt its `Live` region
by racing a plain `StreamHandler` writing to the same stream. Every
`logging.getLogger(...)` call anywhere in the codebase is still captured
either way: by the `FileHandler` always, and by whichever console sink
(`StreamHandler` or the dashboard's `LogPanelHandler`) is active. Log files
land in `logs/ingest_<command>_<YYYYMMDDHHMM>/run.log`, alongside
`manifest.json`/`report.md` (spec 0005 FR-1) — a same-minute collision appends
a numeric suffix (`_2`, `_3`, ...) via
`commons.observability.RunArtifactWriter.build_run_dir(logs_root,
f"ingest_{command}")` (spec 0004 FR-3/AD-3 — `configure_logging` delegates its
run-dir creation and log format, `commons.observability.LOG_FORMAT`, to the
shared `RunArtifactWriter` component instead of a private
`_build_run_dir`/`_LOG_FORMAT`, so `ingest` and `scrape` runs share one
collision-suffix convention and one log format). No-op invocations (`--dry-run`
on `prepare`/`index`, `reset` without `--apply`, or any `status` invocation —
anywhere `_is_dry_run(args)` is True) never get a log directory or any
artifact file — that would contradict the "no filesystem writes" guarantee
`render_dry_run` prints (and, for `status`, its own documented no-write
behavior — spec 0005 FR-2/AD-8, fixing a prior bug where `status` created a
`run.log` unconditionally). `run_artifact_writer.py` also sets
`logging.Formatter.converter = time.gmtime` as a module-level side effect
right after the `LOG_FORMAT` constant, forcing every `%(asctime)s` in every
`Formatter` created anywhere in the process — including `basicConfig`'s
internal one in both `configure_logging` and `scrapers/normattiva.py` — onto
UTC, matching the `datetime.now(UTC)` timestamps used everywhere else
(`manifest.json`, `TIMESTAMPTZ` columns); see
`docs/second-brain/adr/0007-utc-timestamp-convention.md`.

`configure_logging` sets `os.environ.setdefault("LITELLM_LOG", "WARNING")`
before returning — quiets litellm's own `StreamHandler`, attached to a
`"LiteLLM"` logger the first time litellm is imported (lazily, inside
`LiteLLMEmbeddingClient._embed`), independent of the root logger configured
above and defaulting to `DEBUG` when `LITELLM_LOG` is unset; `setdefault` keeps
an operator-provided `LITELLM_LOG` (e.g. set to `DEBUG` for troubleshooting) in
control. That handler writes straight to the stream, bypassing `LOG_FORMAT`,
but litellm never calls `.setLevel()` on the `"LiteLLM"` logger itself, only on
that handler — its *effective* level is otherwise inherited from the root
logger (`INFO`), so records from it (and from `httpx`/`httpcore`/`openai`/
`urllib3`, all noisy at `INFO`) still propagate to and would print through our
own handlers. `cli/logging_setup.py:MutedThirdPartyFilter`, a `logging.Filter`
matching `httpx`/`httpcore`/`litellm`/`openai`/`urllib3` by case-insensitive
name prefix, is attached to the console `StreamHandler` `configure_logging`
builds (and to `LogPanelHandler`, below) to drop those records at the
sink — never at the logger's level, so the run log file's `FileHandler`,
which never gets this filter, always keeps every record unfiltered and
unbounded regardless of which console sink is active. (An earlier version
instead called `logging.getLogger("LiteLLM").setLevel(...)` to quiet the
console; that approach suppressed the records at the logger itself, silently
dropping them from the file too — the shared, handler-level filter fixes
that gap.)

`litellm`'s own module-level `_suppress_loggers()` (runs once, on that same
first import) separately force-sets the `"httpx"` logger's *level* to
`WARNING`, silently overriding whatever level the host process configured —
independent of, and not fixed by, `MutedThirdPartyFilter` above (a handler
filter never changes a logger's level). `LiteLLMEmbeddingClient._embed`
resets `logging.getLogger("httpx")` back to `NOTSET` immediately after the
import that causes it (the only import site of litellm in the codebase),
restoring inheritance from the root logger.

**Live dashboard** (`prepare`/`index` only, interactive TTY, non-dry-run,
non-`--plain` — spec 0002): `cli/main.py:_build_dashboard(args)` returns a
`cli/rendering/dashboard/live_dashboard.py:LiveDashboard` when
`args.command` is `prepare`/`index`, `_is_dry_run(args)` is False and
`args.plain` is falsy (via `getattr(args, "plain", False)`, since `reset`/
`status` define no `--plain`), and `rich.console.Console().is_terminal` is
True; otherwise `None`. `reset`/`status` short-circuit to `None` on the
first check (`args.command not in _MONITORED_COMMANDS`) regardless of
`_is_dry_run`. `main()` always passes a concrete `ProgressReporter` down — the
dashboard itself when built, else `commons.observability.NullProgressReporter`
— so no command or flow factory ever branches on whether a dashboard exists.
When a dashboard is built, `main()` enters it through a `contextlib.ExitStack`
around the command dispatch, so it is torn down (its `Live` stopped, its
`LogPanelHandler` detached from the root logger) *before* any exception from
the flow propagates to the terminal (FR-5).

`LiveDashboard` renders its `Live` with `screen=True` (alternate screen
buffer): the fixed 20-row frame (`_PROGRESS_REGION_SIZE` + `_LOGS_REGION_SIZE`)
is taller than many terminal windows, and without `screen=True` a
mid-run scroll desyncs `Live`'s cursor-up redraw math, printing a duplicate
frame instead of overwriting the old one. Trade-off: on exit the terminal
restores the pre-run screen, so the dashboard's final frame does not remain
in scrollback (unlike a plain, non-screen `Live`).

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
  `enrich_quiz` step, `ImageDescriptionEnricherService` then `NormReferenceEnricherService`
  in sequence (one tick per distinct image, then one tick per post-dedup
  unique question) — two successive item bars for that one step.
  (`ContextEnricher` was a fourth such service before spec 0001/T-13 removed
  knowledge-corpus enrichment entirely.)

`cli/rendering/dashboard/log_panel_handler.py:LogPanelHandler` is a bounded
(`deque(maxlen=15)`) `logging.Handler` that also filters out third-party
loggers from the panel only, via the same `MutedThirdPartyFilter` the console
`StreamHandler` uses (above) — the run log file, via the separate
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
(Null Object, see `docs/second-brain/patterns.md`), so the capture is still built on every call but
`track()` is a no-op — the LLM output is unaffected, only the DB write is skipped.

**`ingest status [--online]`** (`cli/commands/status.py:run_status`, never
raises, always exits 0): `cli/services/status/status_inspector.py:
StatusInspector.evaluate_readiness()` computes a per-(command, entity)
readiness matrix (`RUNNABLE`/`SKIP`/`BLOCKED`) purely from
`Path.exists()` checks via `LayerResolverProvider` — no DB, no network, by default.
Both **knowledge** and, since spec 0006, **quiz** have per-element
`cleaned`/`enriched` directories (see the flow descriptions above): `prepare`
is **never** `SKIP` for either (a directory can be partially populated, so
there is no honest binary "already done" signal), only `BLOCKED` when the
`parsed` input file is missing (that layer is still a single file for both
entities) or `RUNNABLE`; `index`'s input is a directory for both too, so it
drops the `BLOCKED` signal as well and is always `RUNNABLE`. `StatusInspector`
takes this `per_element` flag from the caller (`True` for both `knowledge` and
`quiz` in `evaluate_readiness()`) rather than inferring it from the entity
name, so the readiness logic itself stays free of hardcoded domain strings.
`reset` is always `RUNNABLE` offline for both entities (a single synthetic
entry per entity, no source
dimension). With `--online`, `run_status` best-effort opens a
`PostgresClient` (catching `psycopg.Error` → `db_reachable=False,
tables=None`, still exits 0) and, if reachable, runs
`cli/services/status/table_health_checker.py:TableHealthChecker` over the
repositories from `wiring.build_health_repositories` to report per-table
existence and row count (`table_exists()`/`row_count()`, added to the
shared `UpsertStoreRepository` base — the one explicit exception to the
CLI's self-containment, see `.claude/rules/cli-structure.md`).
`cli/rendering/status_renderer.py:render` presents the report via `rich`,
masking `postgres.password`/`open_router_config.api_key` to `****`/
`missing` — never printed in clear.

**Knowledge corpus** (per source, `cds`/`cap`/`reg`/`amb` — `orchestrators/knowledge_flows.py`;
`reg` added by spec 0003 FR-4/FR-5, `amb` (D.Lgs. 152/2006, narrowed to Parte IV Titolo III
artt. 227-237 by `scrapers/amb_extract.py`) added by spec 0009 — no source-specific branch
anywhere in `prepare`/`index`). `cleaned`
is a **per-element** layer (one JSON file per article, named by a deterministic
`commons.utils.element_id(source, number)`; `parsed` stays a single monolithic file
per source — pattern originally introduced for knowledge, then applied identically to
quiz by `docs/superpowers/specs/2026-08-05-quiz-per-element-layers-design.md`). The
`enriched` layer name still exists in `LayerResolverProvider` config, but only the quiz
pipeline writes to it now (AD-19) — the knowledge corpus has no `enriched` stage:
1. *Cleaning*: `LoadJsonStep` (parsed, single file) → `ApplyStep(ForEach(ArticleCleanerService), ForEach(partial(ArticleMapper.from_parsed_to_cleaned, source=source)))` → `FilterAlreadyDoneStep` (drops articles already present in `cleaned/`) → `WriteJsonDirStep` (one file per article). `ArticleCleanerService` operates on `ParsedArticleModel.commas: list[ParsedComma]` (structured per-comma, spec 0001 T-5/T-6), not a flat `paragraphs`/`text` pair — it only normalizes the title and strips residual inline markup from each comma's text, never dropping a comma.
2. *Enrichment* — **removed** (spec 0001 FR-16/AD-18, plan task T-13):
   `ingest prepare knowledge` runs the cleaning flow only; there is no LLM call
   anywhere in the knowledge-preparation path.
3. *Indexing* (spec 0001 T-14 — **working end-to-end**, validated by a live-Postgres integration test): `LoadJsonDirStep` (`cleaned`, per-element, `CleanedArticleModel`) → `ApplyStep("map_to_article_entities", ForEach(ArticleMapper.from_cleaned_to_article_entity))` → `ApplyStep("expand_to_embeddable_commas", FlatMap(ArticleMapper.from_cleaned_to_embeddable_commas))` → `EmbedCommasStep` (constructed with a `ModelEmbeddingService[EmbeddableArticleComma]` — composer `FieldSpecComposer[EmbeddableArticleComma](EmbeddingSpec(...))`, built inline at the call site, declaring the title+text join via `FieldSpec`; `FieldSpecComposer.compose()` implements `TextComposer[T]` directly, so no adapter is needed — replaces the deleted `EmbeddableArticleComma.embedded_text` computed property, see `docs/second-brain/patterns.md`; delegates chunking to `EmbeddingService`, no behavior change) → `StoreArticlesAndCommasStep` (writes both `articles` and `article_commas` in one step, per PD-7, keeping a source's full reload — delete-by-source then insert — atomic at the step boundary). The two `ApplyStep`s are an intentional fan-out (PD-12): both read the *same* loaded `CLEANED_ARTICLES` list independently (article rows and comma rows derived in parallel), rather than one being reconstructed from the other. No LLM call anywhere in this chain; the embedding input is article title + raw comma text only (AD-18).

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
`source: Literal["cds", "cap", "reg", "amb"]`, stamped on at the parsed→cleaned boundary by
`ArticleMapper.from_parsed_to_cleaned`, making the element's id (and its
filename) computable from the element alone, independent of flow context.

D.Lgs. 152/2006 (`amb`) surfaced a second `article-num-akn` prefix variant: about 50 of
its 440 articles render the number as the full word `"Articolo N"` instead of the
abbreviated `"Art. N"` every other law (and most of `amb` itself) uses.
`_extract_numero_and_titolo` strips both (`re.sub(r"^Art(?:\.|icolo)\s*", "", numero_raw)`,
spec 0009) — discovered because `amb_extract.py`'s range filter needs every article's
leading numeric part to be parseable, and 'Articolo 177' isn't.

The Regolamento (`reg`, DPR 495/1992) has a markup shape the other two sources don't:
every article's whole body sits in one `art-just-text-akn` block (no `article-heading-akn`,
no `art-comma-div-akn`), so `_parse_article` (`scrapers/normattiva.py`) normalizes it to the
same `commas: list[ParsedComma]` shape via rules added for spec 0003 (FR-2/FR-3): the
leading `(Title)` parenthesised segment is split off as the article title
(`_split_leading_title` — loops over *consecutive* leading segments, keeping the *last* as
the title, since some articles carry a cross-reference note before the real title, e.g.
`(Art. 70 Cod. Str.) (Servizio di piazza...)`; since spec 0004 T-7/FR-5, also strips a leading
`((` amendment-bracket marker first — e.g. Regolamento art. 6's `(( (Modalità e procedura...)`
— so a whole-title-wrapped-in-`((...))` article no longer falls through to the "no title"
warning path; the equivalent fix for `heading_tag`-shaped articles, `_extract_heading_title`,
also handles a glued leading cross-reference note with no separating space, e.g.
`(Art. 10 Cod. Str.)Provvedimento di autorizzazione`), then the remaining body is segmented
into one comma per inline `N.` marker (`_split_into_comma_segments`/`_is_marker_start`). A
position is a genuine marker start when it opens the body, sits right after `((` (an amendment
bracket — real articles insert whole later commas this way, anywhere in the body, not just at
the start), is preceded by `)` or `;` (always a boundary), is preceded by `.` whose preceding
word isn't an abbreviation (`art`/`n`/`fig`/…, which also end in digit+period but aren't a new
comma), or — since spec 0004 T-8/FR-6 — is preceded by no `.`/`)`/`;` at all but the token
immediately before it itself ends in a digit (e.g. `"...modello II.6/q2 11. Il modello
II.7..."`). This last case is **deliberately narrow**, not "any bare token is a boundary": the
broader formulation (any non-whitespace, non-glued token) was tried first and found, via a
full offline re-parse of the 409-article Regolamento corpus, to introduce 51 new
false-positive splits on ordinary numeric cross-references in prose (`"...commi 4, 5 e 6. La
decorrenza..."`, `"...all'articolo 266. ((46))..."`, bare years like `"...finanziario 1994.
3. Per il..."`) — the digit-ending-token narrowing fixes exactly the two verified real cases
(Regolamento art. 83 comma 11, art. 194 comma 2) with zero regressions elsewhere in the
corpus (confirmed by re-parsing and diffing all 409 articles against the committed JSON); a
safer, more general rule is deferred to a future enhancement, not attempted by this spec.
`((N.))` — no space before the closing bracket — is also recognised, and the leftover `))`
stripped from the following text. `_validate_contiguous_numbering` fails loudly (`ValueError`)
unless the extracted *base* numbers run `1, 2, 3, …` with no gap/duplicate, while tolerating a
`-bis`/`-ter`-suffixed comma immediately after its base number (AD-3's relaxed rule — the same
convention the CdS uses, confirmed needed by real articles, e.g. art. 9's `1, 2, 3, 3-bis`) —
the guard against a mis-split going undetected, given the CdS/CAP defects spec 0001 found had
gone unnoticed for months. A later amendment can also re-emit an earlier comma's number to
mark it repealed/replaced (e.g. a trailing `6. ((COMMA SOPPRESSO ...))`); `_parse_article`
keeps only the last occurrence (with a `warning`), matching Normattiva's "vigente" convention —
the DB's `UNIQUE (article_id, comma_number)` couldn't store both anyway. When `_parse_article`
still raises for an article `main()` can't otherwise reconcile, `_process_article`
(`scrapers/normattiva.py`, spec 0004 T-4 — extracted from `main()`'s former inline loop body,
replacing its `continue`-based skips with early `return None`s per `.claude/rules/code-conventions.md`)
catches the `ValueError`, calls `manifest.record_skip("parse_error", label, str(exc))` (spec 0005
AD-7 — `_process_article` takes the `ScrapeManifest` directly, not the `RunArtifactWriter`, since
`record_skip` is the only thing it ever needed) and logs a
`warning`, then returns `None` — `main()`'s loop only appends non-`None` records, so the run
proceeds to the next article rather than aborting the whole 409-article run. Skipped articles
(across all three categories: `fetch_failed`, `session_invalid`, `parse_error`) are grouped in
the run's `report.md` (see the `commons/observability/` row above), not printed inline. A live
run against the real corpus (2026-08-01) needed all of the above and still skipped 2 of 409
articles as `parse_error` (a table-formatted comma with no sentence punctuation before a
marker — art. 83's `"...modello II.6/q2 11."` boundary — and a semicolon-terminated sub-list
item — art. 194's `"...pulizia dei supporti; 2."` boundary) — under spec 0003's own
5%-of-articles guardrail for treating the fallback rate as a design failure. Spec 0004 FR-6
(T-8, the digit-ending-token and `;`-boundary cases added to `_is_marker_start` above) targets
exactly these two symptoms and has been confirmed to recover both offline: re-parsing all 409
`data/raw/reg/*.html` files against the fixed code yields zero `parse_error`s (up from 2), and
diffing every re-parsed record against the currently-committed
`data/parsed/reg/regolamento_attuazione.json` shows no unintended comma-boundary change
elsewhere in the corpus (only the two newly-recovered articles plus the 26 title-only changes
already attributed to T-7/FR-5 above). A live re-scrape against normattiva.it is still needed
once, to regenerate the committed JSON file itself with this corrected content — the offline
check only confirms the *code* behaves correctly against already-fetched HTML.

**Quiz bank** (`orchestrators/quiz_flows.py`). Since spec 0006, `cleaned` and
`enriched` are **per-element** layers for quiz too (one JSON file per cleaned/
enriched sub-question, named by `commons.utils.element_id("quiz", item.number)`,
`_quiz_id` in `quiz_flows.py`; `parsed` stays a single monolithic file, same as
knowledge):
1. *Cleaning*: `LoadJsonStep` (parsed, single file) → `ApplyStep(FlatMap(QuizMapper.from_parsed_to_cleaned_all), DeduplicateQuizItemsService())` (unnest + corpus-wide dedup on normalized-text + correct_answer + image identity — the id depends on `number`, which only exists after this flatten, so the filter can't run any earlier) → `FilterAlreadyDoneStep` (drops items already present in `cleaned/`) → `WriteJsonDirStep` (one file per surviving item).
2. *Enrichment*: `LoadJsonDirStep` (cleaned, per-element) → `FilterAlreadyDoneStep` (drops items already present in `enriched/`, **before** the mapping/LLM transform — the filter runs pre-transform here since enrichment, unlike cleaning, *is* the expensive step) → `ApplyStep(ForEach(QuizMapper.from_cleaned_to_enriched))` → `AsyncApplyStep(ImageDescriptionEnricherService(road_sign_describer_concurrency, RoadSignDescriberAgent), NormReferenceEnricherService(NormReferenceDescriberAgent))` → `WriteJsonDirStep` (one file per enriched item). The mapping runs in a synchronous `ApplyStep`; both enrichers run in a separate `AsyncApplyStep` (concurrent LLM calls) over whatever subset the filter left — `ImageDescriptionEnricherService` groups the *not-yet-done* quizzes by image filename and issues one concurrent vision call per image (see `patterns.md`), writing both the flat `image_description` (downstream/embedding field) and the structured `image_analysis` (full LLM output, debug-only) onto every quiz sharing that image. Corpus-wide dedup already happened at cleaning, so no duplicate-image concern arises across runs.
3. *Indexing*: `LoadJsonDirStep` (enriched, per-element) → `ApplyStep(DeduplicateQuizItemsService(), ForEach(QuizMapper.from_enriched_to_embedded))` → `ApplyStep(EmbedQuizVariantsService)` → `ApplyStep(ForEach(QuizMapper.from_embedded_to_quiz_question))` → `ApplyStep(FlatMap(QuizMapper.from_embedded_to_quiz_images))` → `StoreQuizStep` (`orchestrators/steps/quiz/store_quiz_step.py`, spec 0008 — mirrors `StoreArticlesAndCommasStep`: upserts `quiz_questions` on `number` (via `upsert_returning_ids`, resolving each question's DB-generated `id`) then reconciles the whole table via `QuizQuestionStoreRepository.delete_missing`, quiz having a single source unlike the knowledge side's per-source scope; upserts `quiz_images` on `filename` and `quiz_question_embeddings` on `(quiz_question_id, variant)`, neither reconciled — both explicitly deferred open questions). This replaced the former `DbStoreStep` full-reload (truncate + bulk insert) terminal step; `DbStoreStep` and the generic `StoreRepository` protocol it depended on are deleted (AD-10), having zero remaining callers.

   `EmbedQuizVariantsService` (`services/quiz/embed_quiz_variants.py`, spec 0008 Phase 2, replacing `EmbedQuizMetadata`) computes and embeds every configured quiz query representation itself: the dedup/omission/fan-out mechanics considered for generalization into `commons.ai.embedding` (ADR 0014, `VariantSpec[T]`/`VariantModelEmbeddingService[T]`) were kept local to the ingestor instead — ADR 0014 was rejected, see `docs/second-brain/adr/0014-embedding-composition-layer.md`, status `Rejected` — since the quiz registry is the only caller and a fourth `commons/ai/embedding` subpackage for one consumer wasn't judged worth it. It resolves every variant named in `IngestorConfig.quiz_embedding_variants` against a registry (`services/quiz/quiz_variant_registry.py`, AD-7) into `QuizVariantSpec` instances (`services/quiz/quiz_variant_spec.py` — a local frozen dataclass, not a `NamedTuple`, since it carries a `Callable` field, `dedup_key`), then, for each spec: builds every item's text via its `text_composer: commons.ai.embedding.OptionalTextComposer[EmbeddedQuizModel]` (`compose_or_none(item) -> str | None`; `None` is counted as an omission, e.g. when the item lacks `quiz_metadata`), groups items sharing a `dedup_key` result, embeds one text per group via the injected `EmbeddingService` (invoked via `__call__`, not `.execute()`), and fans the vector back out to every item in the group. Every variant in `quiz_variant_registry.py` is defined purely declaratively via `commons.ai.embedding`'s `EmbeddingSpec`/`FieldSpec`/`FieldSpecComposer` — no hand-written text-joining functions: fields that are simply optional use `FieldSpec`'s default `skip_if_none=True` (silently dropped when absent, e.g. `image_description` in `topic_text`); fields whose absence should invalidate the *entire* variant (e.g. `quiz_metadata.vector_search_queries` for `search_queries`/`combined`/`combined_description`) are marked `skip_if_none=False` — `FieldSpecComposer.compose_or_none()` treats any such "required" field as reason to return `None` outright instead of a partial text (unconditionally, no separate spec-level flag needed), while `.compose()` (the plain `TextComposer[T]` method, used for the knowledge side's 1:1 case) ignores that distinction entirely and always returns a string. `dedup_key` has a domain-sensible default (`item.number`, since `QuizVariantSpec` is concrete to `EmbeddedQuizModel`, unlike a hypothetical generic `VariantSpec[T]`) — overridden only for `image_description` (`item.image_filename or item.number`, so several questions sharing one image issue exactly one embedding call, AD-8). The six registered variants (unchanged): `text` (question text alone), `topic_text` (topic + text + image description when present), `search_queries` (`quiz_metadata.vector_search_queries` joined), `combined` (topic + text + search queries), `combined_description` (`combined` + image description when present), `image_description` (the description alone, image questions only). Output is wrapped in an `EmbedQuizVariantsResult` alongside a per-variant omission-count `dict`, exactly as before this refactor — `StoreQuizStep` resolves each row's `question_number` to the just-upserted `quiz_question_id` before writing `QuizQuestionEmbeddingEntity` rows via `QuizQuestionEmbeddingStoreRepository`; `cli/commands/index.py` reads the same result back off the `FlowContext` `flow.run()` returns and records the omission counts on `IndexManifest` (FR-2) — neither is affected by this refactor. `QuizMetadata` stays a cohesive nested object through the ingestion models (`EnrichedQuizModel`/`EmbeddedQuizModel`) and is flattened onto the `QuizQuestionEntity` entity columns **only** at the boundary, inside `from_embedded_to_quiz_question`.

`dispatch_prepare`'s `quiz` branch (`cli/commands/prepare.py`) runs both the
cleaning and enrichment flows directly on every invocation — no coarse
whole-file skip — mirroring the `knowledge` branch; `--force` threads into
both flow factories and bypasses their respective `FilterAlreadyDoneStep`s.
The stale monolithic `data/cleaned/quiz-patente-ab/quiz-patente-ab.json` and
`data/enriched/quiz-patente-ab/quiz-patente-ab.json` (pre-spec-0006 layout)
were deleted as a one-time manual prerequisite — an un-deleted monolith sitting
inside what is now a per-element container directory would make `load_dir`
raise a loud `ValueError`, not silently corrupt data.

**Retrieval evaluation harness** (`ingest evaluate retrieval`, spec 0007 + spec
0008 Phase 2's FR-3 multi-arm rearchitecture — an `ingest` CLI feature, not
`src/guidami_ai_patente/`, per AD-1's documented deviation from `layout.md`): a
data-quality instrument, not application runtime, that measures whether dense
retrieval over the corpus can actually answer a quiz question — no retrieval code
existed anywhere before spec 0007. `MultiArmRetrievalEvaluator`
(`cli/services/evaluation/multi_arm_retrieval_evaluator.py`) enumerates every
**arm** — a `(variant, model_column)` pair — from the database rather than a
hardcoded list: `QuizReadRepository.available_variants()` (distinct `variant`
values present) crossed with `populated_model_columns()` (columns matching AD-6's
`embedding_*` naming convention in `information_schema.columns` that hold at least
one non-null vector, introspected so a second model column needs no harness
change). A single populated model column collapses each arm's label to the
variant name alone; more than one appends `::model_column`. For each arm,
`RetrievalEvaluator` (now a **pure per-arm calculator**: `evaluate(rows)` takes
already-loaded `QuizEvaluationRow`s and no longer owns row-loading or the
`quiz_repository` dependency it used to) runs the same eight-ish named steps as
before (`STEP_NAMES`, shared verbatim with `--dry-run`'s renderer) and aggregates
FR-2 corpus coverage, FR-3's random baseline, FR-4 hit@k, FR-5 lexical adherence,
FR-6 dense/FTS agreement, and FR-10's keyword-signal check — see spec 0007's own
FR list for each metric's definition, unchanged by the rearchitecture. A **fusion**
arm is added on top: for every question with both a `topic_text` and a `text`
variant row (required; `image_description` joins in only when that question also
has one, spec 0008 AD-3/PD-1), `MultiArmRetrievalEvaluator._fuse_dense` retrieves
each constituent vector's own `dense_top_k` ranking independently and fuses them
by citation identity via `commons.ai.utils.reciprocal_rank_fusion` (a small,
domain-agnostic RRF function, `EvaluationConfig.rrf_k`, default 60, uncalibrated) —
no fused vector is ever queried or stored. The `search_queries` variant is the
baseline arm (`EvaluationConfig.quiz_embedding_variant`, repurposed from "the only
variant loaded" to "which arm's numbers become the baseline"); every other arm
carries a `RankingDelta` (`hit_full` at each `k`, in percentage points) against it.
Per-arm `excluded_count` is `total_questions - question_count` (a question missing
that arm's input). Results assemble into `MultiArmEvaluationSummary` (`arms: dict[str,
ArmResult]`, keyed by label, each holding its own `EvaluationSummary`) — the
committed `data/eval/retrieval-summary.json` and the console renderer both iterate
per arm; the per-question detail file and judge-ready export (FR-9) still cover
only the baseline arm's outcomes, not every arm (spec 0008 Phase 2 PD-13 — FR-3
requires the *summary* per arm, not per-question artifacts multiplied by arm). All
run parameters (seed, baseline repetitions, `k` values, DF cutoffs, text coverage
thresholds, `rrf_k`) live in `IngestorConfig.evaluation: EvaluationConfig`, with
`--seed`/`--baseline-repetitions` CLI overrides layered on top in
`cli/commands/evaluate.py`. No LLM call anywhere in the harness (FR-8): it reads
only what ingestion already persisted.

**Retrieval judge** (`evaluate-retrieval-judge` script, `src/retrieval_evaluation/`):
a second, deliberately separate measurement over the same corpus, answering a
question the harness above does not — do the retrieved commas actually justify
the answer? — via an LLM judge rather than a deterministic signal.
`RetrievalJudgeAgent` (`agents/retrieval_judge/retrieval_judge_agent.py`,
`BaseAgent[RetrievalJudgeRequest, RetrievalJudgeResponse]`, its two DTOs in the sibling
`agents/retrieval_judge/dto/` — `agents/` is a generic per-role container (parallel to
`services/`/`models/`), holding one named agent subpackage per agent; today just
`retrieval_judge/` — same pattern as
`RoadSignDescriberAgent`/`NormReferenceDescriberAgent`) is asked,
per sampled quiz question, whether its top-`k` `CorpusReadRepository.dense_top_k`
commas clearly and unambiguously justify the correct answer;
`RetrievalJudgeEvaluationService` either samples `n` random rows via
`QuizReadRepository.fetch_with_vectors` (`evaluate`, the default) or judges every
row it returns (`evaluate_all`, the script's `--all` flag) — both share a private
`_load_rows` helper and differ only in whether the result is sampled. Both are
`async` and fan the sample out through `_judge_all`/`_judge_one`: every judge call
runs via `BaseAgent.run` (not `run_sync`) under `asyncio.gather`, bounded by an
`asyncio.Semaphore(max_concurrency)` built fresh per call (same per-run-loop
pattern as `NormReferenceEnricherService`/`ImageDescriptionEnricherService`, not
stored across calls) — `main()` passes `--concurrency` (default 8) through and
wraps the whole `evaluate`/`evaluate_all` call in a single `asyncio.run`, with the
synchronous `dense_top_k` comma lookup still called inline inside each coroutine
(a single blocking DB round-trip per question, not itself parallelized).
`fetch_with_vectors`'s `FROM` clause `LEFT JOIN`s `quiz_images` on `image_filename`
(shared `QuizReadRepository`, so every consumer — this script and the deterministic
`ingest evaluate retrieval` harness — gets `QuizEvaluationRow.image_description`
alongside `image_filename`, `None` for image-less questions or when the image was
never enriched); `RetrievalJudgeItemResult` carries both through, and both the
console report and `results.json` show them when present.
`RetrievalJudgeRequest.image_description` (falling back to a fixed "no image" Italian
literal when the row has none, same fallback convention as
`norm_reference_describer_mapper.py`) also reaches the judge's own prompt
(`configs/agents/retrieval_judge.yaml`): a `$image_description` line in the `<quiz>`
block plus a system-prompt rule telling the judge the image description is valid
context for whether the answer gets an adequate explanation — road-sign questions
often have commas that state the rule abstractly without describing the specific sign,
which the image description does. Which
variant is fetched defaults to `config.evaluation.quiz_embedding_variant` but can
be overridden per run with `--variant`, checked in `main()` against
`QuizReadRepository.available_variants()` (`argparse.error` on a name with no
stored rows) before the Postgres connection is used for anything else. It is
**not** a mode of
`ingest evaluate retrieval`: spec 0007 lists "LLM-as-judge relevance scoring" as
an explicit Non-Goal (deterministic signals cost nothing and run in CI; a judge
should be targeted, not run over everything) — text the spec still carries
unchanged, by deliberate choice (ADR 0013). This module is the judge that
Non-Goal deferred, built as its own top-level package rather than as a spec-0007
extension, so it carries none of the harness's manifest/`manifest.json`/`report.md`/
dry-run-chain machinery: `main.py` is a plain `argparse` script printing
per-question verdicts and a share-clear percentage to stdout, meant to be
re-run manually (a few times to gauge judge stability, then once with `--all`
or a larger `--n` for a final estimate) rather than averaged automatically
across runs. It does reuse one piece of the harness's plumbing —
`RunArtifactWriter.build_run_dir` (just the static, collision-safe
`logs/<prefix>_<timestamp>/` directory helper, not the writer instance or its
manifest/report machinery) — to reserve `logs/evaluate_judge_<timestamp>/` per
run, attach a plain `run.log` `FileHandler` (`LOG_FORMAT`, both also imported
from `commons.observability`) to the root logger, and write `results.json`: the
full judged records (`RetrievalJudgeItemResult`, now carrying `topic`/`text`/
`correct_answer`/`retrieved_commas` alongside the verdict, not just the verdict)
for offline inspection, since the stdout report alone doesn't retain the
retrieved commas or the quiz context. It reuses `IngestorConfig`
(Postgres connection, table names, `agents_dir`, OpenRouter provider) from
`guidami_ai_patente_ingestor.configs` rather than owning its own settings class —
the one deliberate cross-package dependency this module has.

**Golden-set labeler** (`label-golden-set` script, `src/retrieval_evaluation/`): a
second entry point in the same package, persisting a labeled retrieval golden set
to Postgres instead of printing a spot-check verdict (spec 0011 phase 2). Where the
judge above looks at one arm (`dense_top_k`) and writes nothing, the labeler builds
a **two-arm candidate union** and writes every labeling to three new tables
(`labeling_runs`, `quiz_labelings`, `quiz_comma_labels` — see `database.md`).

`QuestionLexemeService.build` (`services/question_lexeme_service.py`) concatenates
a question's configured `LabelingConfig.lexeme_fields` (`topic`/`text`/
`image_description`, skipping blanks) and hands the text to a new
`CorpusReadRepository.extract_lexemes` method, which asks Postgres itself —
`SELECT lexeme FROM unnest(to_tsvector('italian', %s))` — for the exact stemmed,
stop-word-filtered lexemes the corpus's own GIN indexes are built from (AD-9: same
dictionary on both sides, so extraction and search cannot silently diverge). The
returned lexemes are then single-quoted with internal quotes doubled before being
handed to `text_match_top_k`, since `to_tsquery` treats an unquoted lexeme
containing punctuation (e.g. `e-mail`) as a syntax error, not a literal.
`CandidateSetService.build` (`services/candidate_set_service.py`) then unions
`CorpusReadRepository.dense_top_k` with `text_match_top_k(lexemes, text_k)`, keyed
by comma id, recording each arm's one-based rank on a `CandidateComma` — the union
is **not** truncated, sorted or fused (AD-3): its length is the full union, and a
comma found by both arms carries both ranks.

`GoldenSetLabelingService.label_all` (`services/golden_set_labeling_service.py`)
drives the pass: for every question with a query vector for the configured
`candidate_variant` (optionally restricted to `--limit` questions via a seeded
shuffle independent of the presentation shuffle, PD-18), it builds the candidate
set *inside* a per-run `asyncio.Semaphore` (PD-16 — keeps at most
`max_concurrency` candidate sets alive at once, rather than building all ~7k
eagerly before the first judge call), shuffles the presentation order with
`random.Random(f"{shuffle_seed}:{question_id}")` (deterministic per question,
independent of processing order — PD-8), and asks a second, distinct agent,
`CommaLabelerAgent` (`agents/comma_labeler/`, its own `dto/` — `CommaLabelerRequest`/
`CommaLabelerResponse`, own `configs/agents/comma_labeler.yaml` prompt — FR-12
requires this rather than widening `RetrievalJudgeResponse`, since `BaseAgent`
binds one `output_type` per class), which candidate ordinals (at most three, most-
justifying first) justify the correct answer. Each returned ordinal resolves to its
presented candidate by list index, never by matching text (AD-12); an ordinal
outside the presented range raises `CandidateNumberOutOfRangeError` and aborts the
whole run rather than recording a label (PD-9 — no `return_exceptions=True` on the
`gather`, so a partially-labeled run cannot look complete). Only transport-level
failures are retried (`httpx.TransportError`, or `ModelHTTPError` with a 429/5xx
status), up to `labeling.transport_retries` times with exponential backoff; every
other exception, including a permanent 4xx or a validation error, propagates
immediately (PD-17).

`GoldenSetWriteRepository` (`repositories/golden_set_write_repository.py`) is
insert-only (AD-10, mirroring `LlmCallLogRepository`'s precedent): `insert_run`
writes one `labeling_runs` row; `insert_labeling` writes a `quiz_labelings` row and
its `quiz_comma_labels` children in a **single data-modifying CTE**, atomic despite
`PostgresClient`'s `autocommit=True` (PD-15) — two separate statements would let a
failing child insert leave a childless parent indistinguishable from a genuine "no
justifying comma" outcome (AD-6: the outcome is *derived* by counting children,
never stored as a column). `outcome_counts` is the one read method on the class (a
`SELECT`, not a write), used by `label_main.py` to print the with-commas/without-
commas breakdown after the run. `label_main.py` inserts the `labeling_runs` row
*before* the pass (recording `judge_model`, a `prompt_version` hashed from the
loaded prompt text via `run_provenance.prompt_version` — no human-maintained
version field, AD-11 — `corpus_commit` from `git rev-parse HEAD`, and
`corpus_comma_count` from a new unfiltered `CorpusReadRepository.comma_count`),
validates `candidate_variant` against `QuizReadRepository.available_variants()`
first (same guard as the judge script), and — like the judge script — reuses only
`RunArtifactWriter.build_run_dir` for its `logs/label_golden_set_<timestamp>/`
directory, with no manifest, no dry-run chain, no `report.md` (AD-10; the module's
placement rationale in ADR 0013 extends unchanged to this second script, though the
ADR's premise that the module writes no persistent artifact no longer holds — see
the ADR itself).

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
  `ImageDescriptionEnricherService` keys on the image filename only; all quizzes
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
- **`BaseAgent` takes a generic `Provider[AsyncOpenAI]`, not an
  `OpenRouterProvider`** — `_create_model`/`_create_model_settings`/
  `_log_call_completed` all dispatch on `isinstance(provider, OpenRouterProvider)`
  (the `_is_openrouter` property): OpenRouter gets `OpenRouterModel` +
  `openrouter_usage` + the "no cost" warning; any other OpenAI-compatible
  provider (e.g. `OllamaProvider`) gets the generic `OpenAIChatModel`, no
  OpenRouter-only settings, and no cost warning (a local model never
  reports a cost, so the warning would otherwise fire on every call —
  `.claude/rules/logging.md`). No agent is wired to Ollama yet — this
  only widens `BaseAgent` itself (`adr/0019-base-agent-generic-provider-ollama.md`).
- **Per-element knowledge (then quiz) layers, cross-run resumability,
  write-through deferred** — `cleaned`/`enriched` for the knowledge corpus
  moved from one monolithic JSON per source to one JSON file per article, so a
  `--force`-less re-run only pays for the articles still missing (see the flow
  description above). `docs/superpowers/specs/2026-08-05-quiz-per-element-layers-design.md` brought quiz's `cleaned`/`enriched` layers to the same per-element
  model, reusing the generic `FilterAlreadyDoneStep`/`LoadJsonDirStep`/
  `WriteJsonDirStep` steps as-is (no quiz-specific step classes), keyed by
  `element_id("quiz", item.number)` instead of `element_id(source, number)` —
  quiz has a single fixed source, so no `source` field needed adding to
  `CleanedQuizModel`/`EnrichedQuizModel` the way knowledge needed one on
  `CleanedArticleModel`. Full write-through (durable progress *during* a run,
  not just across runs) is explicitly out of scope for both and left to a
  follow-up plan.
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
- **Retrieval-quality LLM judge lives in its own top-level package, not
  inside `ingest evaluate retrieval`** — deliberately outside the harness's
  manifest/dry-run/`RunArtifactWriter` machinery, reusing `IngestorConfig`
  and the existing read repositories rather than introducing new config or
  CLI infrastructure (`adr/0013-retrieval-judge-separate-module.md`).

*Last updated: 2026-08-04 — verified against commit `165fa9e`; noted
`LiteLLMEmbeddingClient._embed` resetting the `"httpx"` logger's level back to
`NOTSET` right after litellm's import, undoing litellm's own `_suppress_loggers()`
side effect that force-sets it to `WARNING` regardless of host configuration.*

*Last updated: 2026-08-04 — verified against commit `86542bc`; the `configure_logging`
paragraph now describes the shared `MutedThirdPartyFilter` (`cli/logging_setup.py`)
applied to both the console `StreamHandler` and `LogPanelHandler`, replacing the old
`logging.getLogger("LiteLLM").setLevel(...)` approach, which silently dropped muted
records from the run log file too.*

*Last updated: 2026-08-04 — verified against commit `51cabb3`; `parsers/questions_pdf.py`
row and its lazy-image-extraction paragraph now reflect `data/quiz-images/`, a top-level
directory sibling to `raw/`/`parsed/`/`cleaned/`/`enriched/` (moved out of
`data/parsed/quiz-patente-ab/images/`), plus the new cross-run `_referenced_images`/
`_prune_orphans` pair in `main_questions` that deletes stale image files no longer
referenced by the freshly-parsed output (ADR 0008). The `test_data_sampler/sampler.py`
row now points at the same new source/destination paths.*

*Last updated: 2026-08-04 — verified against commit `2248dcc`; `commons/observability/`
row now also covers the new `run_artifact_writer/` sibling sub-package (spec 0004 T-2/T-3),
the per-run file logging section reflects `configure_logging`'s delegation to
`RunArtifactWriter.build_run_dir`/`LOG_FORMAT` plus the module-level
`logging.Formatter.converter = time.gmtime` UTC forcing (ADR 0007), and the Regolamento
parse-error-skip paragraph reflects `_process_article`'s extraction and
`RunArtifactWriter.record_skip` (spec 0004 T-4, replacing the former inline
`continue`/print-summary shape). The `scrapers/normattiva.py` row now reflects the single
`scrape --source <cds|cap|reg>` CLI entry point (`cli_main`), replacing the per-law
`main_cds`/`main_cap`/`main_reg` entry points (spec 0004 T-5). The Regolamento parsing
paragraph now documents `_split_leading_title`/`_extract_heading_title`'s
amendment-bracket and glued cross-reference handling (spec 0004 T-7/FR-5) and
`_is_marker_start`'s widened `;`-boundary and digit-ending-token-boundary rules (spec
0004 T-8/FR-6 — narrowed from an initial broader "any bare token" rule after it was found
to cause 51 new false-positive splits on an offline corpus re-parse; the broader rule is
deferred to a future enhancement), and records that an offline re-parse of all 409
Regolamento articles confirms both previously-skipped articles now recover with zero
regressions elsewhere. Also merged in the `feat/ingestion` verification against commit
`96feb45`: the `ingest --config` entry-point note reflects `IngestorConfig.load()`
(ADR 0006).*

*Last updated: 2026-08-04 — verified against commit `78433b5`.*

*Last updated: 2026-08-04 — verified against commit `e503c94`; `reset` now
inverts the dry-run gate instead of reusing `--dry-run`: it previews by
default (no `--dry-run` flag of its own) and requires `--apply` to actually
run the `TRUNCATE`. `cli/main.py:_is_dry_run(args)` centralizes the flip for
`_build_dashboard`/`configure_logging`, both updated to call it instead of
reading `args.dry_run` directly.*

*Last updated: 2026-08-05 — verified against commit `52cc03e`; `RunArtifactWriter` and
`configure_logging` reflect spec 0005 (ADR 0009): `RunArtifactWriterConfig` is removed,
`RunArtifactWriter` is generalized onto a `RunManifest`-typed `manifest` constructor arg,
`configure_logging` now takes `args` (not `args.command`) and returns
`RunArtifactWriter | None`, entered by `cli/main.py:main` via its `ExitStack` so `ingest
prepare`/`index`/`reset` get `manifest.json`/`report.md` alongside `run.log` (previously
scraper-only). `_is_dry_run` gained a `status` branch (always `True`, AD-8), fixing a prior
bug where `ingest status` unconditionally created a `run.log`. `_process_article` takes
`ScrapeManifest` directly, not `RunArtifactWriter` (AD-7).*

*Last updated: 2026-08-05 — verified against commit `b5ce3ea`; the quiz per-element
layout note now says `load_dir` (renamed from `load_all`) for the loud `ValueError` an
un-deleted monolith triggers inside a per-element container directory.*

*Last updated: 2026-08-05 — verified against commit `6d96b7d`; corrected the `domain/`
entry, which still listed `knowledge_chunk` and `retrieval_result`: the former was split
into `ArticleEntity`/`ArticleCommaEntity` and the latter deleted, both by spec 0001.*

*Last updated: 2026-08-05 — spec 0007 implemented: `commons/repositories/db/` (the
project's first query code, `CorpusReadRepository`/`QuizReadRepository`, AD-7) and the
`ingest evaluate retrieval` command (`cli/commands/evaluate.py`,
`cli/services/evaluation/`, `cli/models/evaluation/`) added. See the "Retrieval
evaluation harness" paragraph above and the `commons/repositories/db/` row in the
components table.*

*Last updated: 2026-08-06 — verified against commit `91c4fe7`; the two dead
`docs/plans/2026-07-17--per-element-knowledge-layers.md` citations (removed by commit
`0a18903`) in the knowledge-corpus flow description and the "Notable implementation
details" list replaced with pointers to `docs/superpowers/specs/2026-08-05-quiz-per-element-layers-design.md`.*

*Last updated: 2026-08-06 — verified against commit `91c4fe7`; added `src/retrieval_evaluation/`
(new components-table row, Overview mention, "Retrieval judge" paragraph, and an ADR bullet):
an LLM-as-judge for retrieval quality, deliberately separate from `ingest evaluate retrieval`
(spec 0007's Non-Goal is left unchanged, ADR 0013).*

*Last updated: 2026-08-06 — verified against commit `7bca08d`; the "Retrieval judge" paragraph
now covers `RetrievalJudgeEvaluationService.evaluate_all()` and the script's `--all` flag,
which judge every quiz question with a query vector instead of only a random `n`-sized sample.*

*Last updated: 2026-08-06 — verified against commit `068c765`; `RetrievalJudgeAgent` and its
DTOs moved from `agents/`/`agents/dto/retrieval_judge/` to a flat `retrieval_judge/` +
`retrieval_judge/dto/` (no `agents/` package, no `<agent_name>` repeated as a nesting level)
— the components-table row and the "Retrieval judge" paragraph now reflect the new paths.*

*Last updated: 2026-08-06 — verified against commit `068c765`; the `table_exists`/`row_count`
row now names `UpsertStoreRepository` (renamed from `BulkInsertStoreRepository`, spec 0010 T-1).*

*Last updated: 2026-08-06 — verified against commit `f343270`; the components-table row and
the "Retrieval judge" paragraph now say `agents/` again instead of `retrieval_judge/` —
reverted on the user's explicit request.*

*Last updated: 2026-08-06 — verified against commit `f1839b9`; corrected: the agent and its
DTOs live nested under `agents/retrieval_judge/` (`agents/` is a generic per-role container,
not the agent's own folder) — the previous entry described them as flat directly under
`agents/`, which was wrong.*

*Last updated: 2026-08-06 — verified against commit `598690c`; spec 0009 adds `AMB`
(D.Lgs. 152/2006) as a fourth knowledge source, narrowed to Parte IV Titolo III
(artt. 227-237) by the new `scrapers/amb_extract.py`, which shares its filtering core
(`scrapers/range_filter.py`) with `rca_extract.py` — both rows updated, plus the
`Literal["cds", "cap", "reg"]` reference.*

*Last updated: 2026-08-06 — verified against commit `f6df198`; new paragraph on the
`"Articolo N"` full-word prefix `_extract_numero_and_titolo` now strips, found via the
live `amb` scrape.*

*Last updated: 2026-08-06 — verified against commit `598690c`; the quiz indexing step chain's
terminal step is now `StoreQuizStep` (new `orchestrators/steps/quiz/` package, mirroring
`orchestrators/steps/knowledge/`), replacing `DbStoreStep`'s truncate + bulk-insert full
reload — `DbStoreStep` and the generic `StoreRepository` protocol are deleted, zero remaining
callers (spec 0008 Phase 1, AD-10). A new `ApplyStep(FlatMap(QuizMapper.from_embedded_to_quiz_images))`
step precedes it, mapping each embedded question to zero-or-one `QuizImageEntity`.*

*Last updated: 2026-08-07 — verified against commit `bbbb291`; `test_data_sampler/sampler.py`
row now also covers `sample_quiz_enriched`, added while extracting spec 0008 Phase 2's plan —
`data/test-data/enriched/` was previously missing entirely (only `parsed/`/`cleaned/` existed),
blocking an FR-4 integration test from exercising `ingest index quiz` against a small corpus.
The fix copies from the already-enriched full bank rather than re-running enrichment. Also:
`commons/ai/embedding/` row updated for spec 0008 Phase 2, AD-9 — `EmbeddingService`
now takes `Sequence[str]` directly and the `Embeddable`/`Embedded` protocols are deleted (one
object can no longer express "the one text to embed" once a question yields several variant
texts).*

*Last updated: 2026-08-07 — verified against commit `bbbb291`; spec 0008 Phase 2 landed in
full. Quiz indexing's step 3 rewritten: `EmbedQuizVariantsService`/the `quiz_variant_registry.py`
registry (AD-7) replace `EmbedQuizMetadata`, computing all six configured variants and
persisting them via the new `quiz_question_embeddings` write path (`QuizQuestionEmbeddingStoreRepository`,
`StoreQuizStep` now resolving `quiz_question_id` via `upsert_returning_ids` before writing
variant rows); per-variant omission counts reach `IndexManifest` via the `FlowContext`
`flow.run()` returns. The retrieval evaluation harness is rearchitected from single-arm to
multi-arm (FR-3): `MultiArmRetrievalEvaluator`, `commons/repositories/db/quiz_read_repository.py`'s
new `populated_model_columns()`, the fusion arm via the new `commons/ai/utils/reciprocal_rank_fusion.py`,
and three new report models (`RankingDelta`, `ArmResult`, `MultiArmEvaluationSummary`).
`RetrievalEvaluator` itself is now a pure per-arm calculator, decoupled from `QuizReadRepository`.
`src/retrieval_evaluation/services/retrieval_judge_evaluation_service.py` (outside spec 0008's
scope but coupled to the changed `fetch_with_vectors` signature) was updated to pass
`"embedding_3_small"` explicitly, the only model column that exists today.*

*Last updated: 2026-08-07 — verified against commit `bbec1a0` (working tree ahead of it,
uncommitted on `feat/ingestion`); renamed every `UseCase`/`AsyncUseCase` subclass under
`services/` that also takes the new `Service` suffix (`ArticleCleaner` → `ArticleCleanerService`,
`DeduplicateQuizItems` → `DeduplicateQuizItemsService`, `EmbedQuizVariants` →
`EmbedQuizVariantsService`, `ImageDescriptionEnricher` → `ImageDescriptionEnricherService`,
`NormReferenceEnricher` → `NormReferenceEnricherService`) and `LayerResolver` →
`LayerResolverProvider` (moved from `services/` to the new `providers/` package — see
`docs/second-brain/layout.md`).*

*Last updated: 2026-08-08 — verified against commit `8d85a0bc` (working tree ahead of it,
uncommitted). ADR 0014 (generalizing `EmbedQuizVariantsService`'s dedup/omission/fan-out into
`commons.ai.embedding` as `VariantSpec[T]`/`VariantModelEmbeddingService[T]`) was rejected —
see `docs/second-brain/adr/0014-embedding-composition-layer.md`, status `Rejected`. `commons/ai/embedding/`
instead gained a smaller, declarative extension: `protocols/optional_text_composer.py::
OptionalTextComposer[T]` (`compose_or_none(model: T) -> str | None`, counterpart of
`TextComposer[T]` for representations that may be absent — a distinct method name, not an
overload of `compose`, so one class can implement both protocols) and `FieldSpec.from_attr`
gained a `skip_if_none` parameter. `FieldSpecComposer` implements **both** protocols:
`compose(model) -> str` (unchanged, always a string — satisfies `TextComposer[T]`) and the new
`compose_or_none(model) -> str | None` (returns `None` when a field marked `skip_if_none=False`
is missing, unconditionally — no separate spec-level flag needed). `EmbeddingConfig` renamed
`EmbeddingClientConfig`. `EmbeddingService`'s internals now use `itertools.batched` and a new
`commons.observability.progress_reporter.tracker` generator (public contract unchanged).
`EmbedCommasStep` migrated onto `ModelEmbeddingService[EmbeddableArticleComma]` wired with a
`FieldSpecComposer[EmbeddableArticleComma]` built inline (no adapter needed, since `.compose()`
already satisfies `TextComposer[T]`) — replacing the deleted `EmbeddableArticleComma.embedded_text`
computed property. `EmbedQuizVariantsService` keeps its own dedup/omission/fan-out mechanics
(not generalized); `quiz_variant_registry.py` defines every variant declaratively via
`EmbeddingSpec`/`FieldSpec`/`FieldSpecComposer`, calling `.compose_or_none()`; the old
`QuizVariantSpec` `NamedTuple` is replaced by a local frozen dataclass of the same name
(`services/quiz/quiz_variant_spec.py`) typed with
`text_composer: OptionalTextComposer[EmbeddedQuizModel]` — not by a generic commons type. Every
`UseCase` in the codebase is now invoked via `__call__`, never `.execute()` (rule,
`.claude/rules/use-case-invocation.md`).*

*Last updated: 2026-08-07 — verified against commit `8d85a0b` (working tree ahead of it,
uncommitted on `feat/ingestion`); `evaluate-retrieval-judge` gained a `--variant` CLI flag
(default `config.evaluation.quiz_embedding_variant`), validated in `main()` against
`QuizReadRepository.available_variants()` before any Postgres/LLM work happens.*

*Last updated: 2026-08-08 — verified against commit `8d85a0b` (working tree ahead of it,
uncommitted on `feat/ingestion`); `evaluate-retrieval-judge` now writes
`logs/evaluate_judge_<timestamp>/run.log` and `results.json` per run (reusing
`RunArtifactWriter.build_run_dir` for the directory only, none of the writer's
manifest/report machinery); `RetrievalJudgeItemResult` extended with `topic`/`text`/
`correct_answer`/`retrieved_commas` so the JSON export carries the full judged record,
not just the verdict.*

*Last updated: 2026-08-08 — verified against commit `8d85a0b` (working tree ahead of it,
uncommitted on `feat/ingestion`); `QuizReadRepository` (`src/commons/repositories/db/`,
shared by both the deterministic harness and the retrieval judge) now takes a
`quiz_images_table` and `LEFT JOIN`s it into `fetch_with_vectors`; `QuizEvaluationRow`
and `RetrievalJudgeItemResult` gained `image_description` alongside `image_filename`,
surfaced in the judge's console report and `results.json`.*

*Last updated: 2026-08-08 — verified against commit `8d85a0b` (working tree ahead of it,
uncommitted on `feat/ingestion`); `RetrievalJudgeRequest` gained `image_description`
(fallback literal when absent, `norm_reference_describer_mapper.py`'s convention), now
rendered into the judge's own prompt (`configs/agents/retrieval_judge.yaml`) with a rule
telling it the image description is valid context for judging whether the answer gets
an adequate explanation.*

*Last updated: 2026-08-08 — verified against commit `f072a30` (working tree ahead of it,
uncommitted on `feat/ingestion`); `RetrievalJudgeEvaluationService.evaluate`/`evaluate_all`
are now `async`, calling `BaseAgent.run` instead of `run_sync` for every sampled question
concurrently under `asyncio.gather`, bounded by an `asyncio.Semaphore(max_concurrency)`
built per call (same per-run-loop pattern as the enrichers); `main()` gained `--concurrency`
(default 8) and wraps the evaluation call in `asyncio.run`.*

*Last updated: 2026-08-08 — verified against commit `507d2dfb` (working tree ahead of it,
uncommitted, on new branch `feat/backend`); `guidami_ai_patente/` moved from a bare package
scaffold to a laid-out FastAPI app: `api/` self-contained web layer (`app.py::create_app`,
`routers/health.py`, `schemas/health.py`), `configs/app_config.py::AppConfig` (root
`BaseSettings`, embeds `commons.configs.PostgresConnectionConfig`), and empty pull-based
`services/`/`repositories/`/`models/`/`mappers/`. `main.py::main` is the entry point,
registered as the `api` script. Added `fastapi`/`uvicorn[standard]` dependencies. Booted
and smoke-tested `GET /health` end-to-end via `uv run api`.*

*Last updated: 2026-08-12 — verified against commit `5a215141` (working tree ahead of it,
uncommitted, on `feat/backend`); added `pywire` as a git dependency
(`pyproject.toml`/`uv.lock`), adopted for dependency injection in `guidami_ai_patente/`
only — Spring-style `@service`/`@repository`/`@client`/`@component` decorators +
`Autowired[T]` field injection, replacing constructor injection for that package. The
`guidami_ai_patente/` component row now notes this and points at
`adr/0015-pywire-di-for-fastapi-app.md` and `.claude/rules/pywire-di.md`.*

*Last updated: 2026-08-17 — verified against commit `b3ca8b30` (working tree ahead of it,
uncommitted, on `feat/backend`); bumped `pywire` 0.2.1 -> 0.3.1 (`pyproject.toml` now pins
`[tool.uv.sources]` to `tag = "v0.3.1"` instead of floating on the default branch;
`pywire[fastapi]` extra added), adopting its new native FastAPI integration.
`services/` and `repositories/` under `guidami_ai_patente/` gained their first real
classes — `repositories/dependency_version_repository.py::DependencyVersionRepository`
and `services/health_check_service.py::HealthCheckService` (the latter
`Autowired[DependencyVersionRepository]`) — wired into `GET /health` via a bare
`Autowired[HealthCheckService]` route parameter (`api/routers/health.py`). `wire(app)` is
called exactly once, in `api/app.py::create_app`, on the `FastAPI` app itself: `pywire`
0.3.0 required wiring each `APIRouter` individually (wiring the app did not propagate
through `include_router()`), but 0.3.1 redesigned `wire()` to only accept the app and
patch route resolution process-wide, removing the per-router call and its
decoration-order footgun — `api/app.py` imports `pywire.fastapi` before its router
modules so that patch installs first. Verified end-to-end against a live `uv run api`
process with a real HTTP request, not only `TestClient`. `.claude/rules/pywire-di.md`
gained a "FastAPI wiring" section documenting the convention; see
`adr/0016-pywire-native-fastapi-wiring.md`.*

*Last updated: 2026-08-19 — verified against commit `2dd56724` (working tree ahead:
spec 0011 phase 1, T-1); `CorpusReadRepository`'s shared projection now leads with `c.id`,
noted on the `commons/repositories/db/` component row.*

*Last updated: 2026-08-21 — verified against commit `e4977a94` (working tree ahead:
spec 0011 phase 2, T-4 through T-11); added the "Golden-set labeler" section —
`label-golden-set`, a second `retrieval_evaluation/` entry point that persists a labeled
golden set (two-arm candidate union, `CommaLabelerAgent`, `GoldenSetWriteRepository`'s
single-CTE atomic write) to the three tables described in `database.md`. `CorpusReadRepository`
gained `extract_lexemes` (Postgres-side lexeme extraction, AD-9) and `comma_count`.*

*Last updated: 2026-08-24 — verified against commit `677737fb` (working tree ahead: bumped
`pywire` 0.3.1 -> 0.5.0, `[tool.uv.sources]` tag `v0.3.1` -> `v0.5.0`); the intervening
release added `Container.register_instance(obj)`/`register_factory(Type, callable)` (publish
an externally-built instance / a lazy provider, keyed by runtime type or `as_type=`), which
did not exist when `adr/0017-appconfig-component-and-testable-autowiring.md` was written —
that ADR's Context section asserts no such mechanism exists and works around its absence by
making `AppConfig` a fake zero-arg `@component`. `guidami_ai_patente/`'s only current pywire
usage (`GET /health`'s `HealthCheckService`/`DependencyVersionRepository` field injection,
`pywire.fastapi.wire()`) still passes end-to-end against 0.5.0 — full suite (709 tests),
`ruff`, `pyright`, and a live `uv run api` + `GET /health` request all verified — despite an
intervening breaking change in pywire itself ("Move wiring from class instrumentation into
resolve()", pywire 0.4.0). The quiz-check-endpoint code ADR 0017 was written for
(`PostgresClientProvider`, `QuizAnswerChecker`) has not been implemented yet, so no source
in this repo depends on the workaround today; ADR 0017's Status/Decision are left untouched
pending a user call on whether to revise them before that endpoint is built.*

*Last updated: 2026-08-25 — verified against commit `2826f9d5` (working tree ahead: `feat/agent-ollama`
branch); `BaseAgent` now takes a generic `pydantic_ai.providers.Provider[AsyncOpenAI]`
instead of `OpenRouterProvider`, dispatching `_create_model`/`_create_model_settings`/the
"no cost" warning on provider type (`_is_openrouter` property) so it can also be built
with `OllamaProvider` — see `adr/0019-base-agent-generic-provider-ollama.md` (Proposed).*
