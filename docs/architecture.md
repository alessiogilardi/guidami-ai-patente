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
| `commons/observability/` | Thin re-exporting `__init__.py` over two self-contained sibling sub-packages: `progress_reporter/` (`ItemProgressReporter`/`ProgressReporter` port + `NullProgressReporter` — progress reporting for the ingest CLI's live dashboard, spec 0002) and `run_artifact_writer/` (`RunArtifactWriter` + a `models/` sub-package holding `RunManifest` (base) and `ScrapeManifest`; `RunArtifactWriterConfig` was removed, spec 0005 AD-5 — `RunArtifactWriter` is domain-agnostic mechanics only, no `protocols/`/`services/` split since AD-3 rejects a `Protocol` here with only one implementation; a context manager that owns one `logs/<prefix>_<timestamp>/` run directory, writing `run.log`/`manifest.json`/`report.md` from whatever `RunManifest` it holds and always finalizing them in `__exit__` even on an unhandled exception — shared between `ingest`'s `configure_logging` and the `scrapers/normattiva.py` scraper, spec 0005 AD-1/AD-4); a sibling of `commons/ai/observability/`, not nested under it, since it is not AI-specific. The `ingest`-only manifests (`PrepareManifest`/`IndexManifest`/`ResetManifest`) live in `guidami_ai_patente_ingestor/cli/models/run_artifacts/` instead, per the CLI self-containment rule (spec 0005 AD-6) | — |
| `commons/clients/postgres_client.py` | Generic, table-agnostic Postgres/pgvector client | psycopg[binary], pgvector |
| `commons/use_cases/` | `UseCase`/`AsyncUseCase`, `ForEach`, `FlatMap` — generic composition primitives used across pipeline steps | — |
| `domain/entities/`, `domain/models/` | Persisted entities and shared cross-app models | pydantic |
| `flowstep` (external dependency) | Generic sequential-pipeline engine (`Flow`, `Step`, `FlowBuilder`, `FlowContext`, `ApplyStep`) | git dependency (github.com/alessiogilardi/flowstep) |
| `guidami_ai_patente_ingestor/` | Batch ingestion app — orchestrators, services, repositories, mappers, agents, models, configs (see flows below) | — |
| `guidami_ai_patente_ingestor/cli/` | Self-contained `ingest` CLI package (entry point, argument parsing, lazy DI wiring, per-subcommand dispatch, CLI-local `status` services/DTOs/renderer) — see `.claude/rules/cli-structure.md` and the `ingest status` flow below | argparse, rich |
| `guidami_ai_patente/` | FastAPI quiz bot — **not started** | FastAPI (planned) |
| `parsers/questions_pdf.py` | Quiz PDF → `data/parsed/quiz-patente-ab/quiz-patente-ab.json` (questions) + `data/quiz-images/` (extracted images, top-level, sibling of `parsed/` — ADR 0008) | pdfplumber, pymupdf |
| `scrapers/normattiva.py` | normattiva.it → `data/raw/` + `data/parsed/`, one `LawConfig` per law (`CDS`/`CAP`/`REG`) selected via a single `scrape --source <cds\|cap\|reg>` CLI entry point (`cli_main` — spec 0004 FR-1, replacing spec 0003's per-law `main_cds`/`main_cap`/`main_reg`) | beautifulsoup4, lxml, httpx |
| `scrapers/rca_extract.py` | Filters the full CAP corpus (`data/parsed/cap/codice_assicurazioni_private.json`) down to `IngestorConfig.rca_ranges` (inclusive numeric ranges over the article's leading number) → `data/parsed/cap/codice_rca.json`; not wired into `main_cap` or the `ingest` CLI — a standalone follow-up step | stdlib only |
| `test_data_sampler/sampler.py` | Samples `--count` random elements per source from `data/parsed/{cds,cap,reg,quiz-patente-ab}` → `data/test-data/parsed/...`, copying only the quiz images the sampled questions reference from `data/quiz-images/` into `data/test-data/quiz-images/`; feeds `ingest --config configs/ingestor_config.test-data.yaml prepare\|index` (ADR 0006, ADR 0008) | stdlib only |

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
(`knowledge` and, since spec 0005, `quiz`) run their flow(s) directly, with
no coarse per-source-file skip: idempotency lives entirely inside each
flow's `FilterAlreadyDoneStep`, which drops elements already present in the
per-element destination layer before the (possibly expensive) transform
runs. The former `run_preparation` helper (`orchestrators/preparation_runner.py`,
wrapping a whole flow with an `out_path.exists()` skip) is deleted — spec
0005/AD-5 removed its last consumer (quiz) once quiz's `cleaned`/`enriched`
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
`docs/adr/0007-utc-timestamp-convention.md`.

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
(Null Object, see `docs/patterns.md`), so the capture is still built on every call but
`track()` is a no-op — the LLM output is unaffected, only the DB write is skipped.

**`ingest status [--online]`** (`cli/commands/status.py:run_status`, never
raises, always exits 0): `cli/services/status/status_inspector.py:
StatusInspector.evaluate_readiness()` computes a per-(command, entity)
readiness matrix (`RUNNABLE`/`SKIP`/`BLOCKED`) purely from
`Path.exists()` checks via `LayerResolver` — no DB, no network, by default.
Both **knowledge** and, since spec 0005, **quiz** have per-element
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
shared `BulkInsertStoreRepository` base — the one explicit exception to the
CLI's self-containment, see `.claude/rules/cli-structure.md`).
`cli/rendering/status_renderer.py:render` presents the report via `rich`,
masking `postgres.password`/`open_router_config.api_key` to `****`/
`missing` — never printed in clear.

**Knowledge corpus** (per source, `cds`/`cap`/`reg` — `orchestrators/knowledge_flows.py`; `reg`
added by spec 0003 FR-4/FR-5, no source-specific branch anywhere in `prepare`/`index`). `cleaned`
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
`source: Literal["cds", "cap", "reg"]`, stamped on at the parsed→cleaned boundary by
`ArticleMapper.from_parsed_to_cleaned`, making the element's id (and its
filename) computable from the element alone, independent of flow context.

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

**Quiz bank** (`orchestrators/quiz_flows.py`). Since spec 0005, `cleaned` and
`enriched` are **per-element** layers for quiz too (one JSON file per cleaned/
enriched sub-question, named by `commons.utils.element_id("quiz", item.number)`,
`_quiz_id` in `quiz_flows.py`; `parsed` stays a single monolithic file, same as
knowledge):
1. *Cleaning*: `LoadJsonStep` (parsed, single file) → `ApplyStep(FlatMap(QuizMapper.from_parsed_to_cleaned_all), DeduplicateQuizItems())` (unnest + corpus-wide dedup on normalized-text + correct_answer + image identity — the id depends on `number`, which only exists after this flatten, so the filter can't run any earlier) → `FilterAlreadyDoneStep` (drops items already present in `cleaned/`) → `WriteJsonDirStep` (one file per surviving item).
2. *Enrichment*: `LoadJsonDirStep` (cleaned, per-element) → `FilterAlreadyDoneStep` (drops items already present in `enriched/`, **before** the mapping/LLM transform — the filter runs pre-transform here since enrichment, unlike cleaning, *is* the expensive step) → `ApplyStep(ForEach(QuizMapper.from_cleaned_to_enriched))` → `AsyncApplyStep(ImageDescriptionEnricher(road_sign_describer_concurrency, RoadSignDescriberAgent), NormReferenceEnricher(NormReferenceDescriberAgent))` → `WriteJsonDirStep` (one file per enriched item). The mapping runs in a synchronous `ApplyStep`; both enrichers run in a separate `AsyncApplyStep` (concurrent LLM calls) over whatever subset the filter left — `ImageDescriptionEnricher` groups the *not-yet-done* quizzes by image filename and issues one concurrent vision call per image (see `patterns.md`), writing both the flat `image_description` (downstream/embedding field) and the structured `image_analysis` (full LLM output, debug-only) onto every quiz sharing that image. Corpus-wide dedup already happened at cleaning, so no duplicate-image concern arises across runs.
3. *Indexing*: `LoadJsonDirStep` (enriched, per-element) → `ApplyStep(DeduplicateQuizItems(), ForEach(QuizMapper.from_enriched_to_embedded))` → `ApplyStep(EmbedQuizMetadata)` → `ApplyStep(ForEach(QuizMapper.from_embedded_to_quiz_question))` → `DbStoreStep` (full truncate + bulk insert, unaffected by the per-element load). `EmbedQuizMetadata` extracts `quiz_metadata` (itself `Embeddable`) from each item and calls `EmbeddingService` on that list directly — not on the `EmbeddedQuizModel` items themselves, which no longer implement `Embeddable`/`Embedded`. Items without `quiz_metadata` end up with `embedding=None`. `QuizMetadata` stays a cohesive nested object through the ingestion models (`EnrichedQuizModel`/`EmbeddedQuizModel`) and is flattened onto the `QuizQuestionEntity` entity columns **only** at the boundary, inside `from_embedded_to_quiz_question`.

`dispatch_prepare`'s `quiz` branch (`cli/commands/prepare.py`) runs both the
cleaning and enrichment flows directly on every invocation — no coarse
whole-file skip — mirroring the `knowledge` branch; `--force` threads into
both flow factories and bypasses their respective `FilterAlreadyDoneStep`s.

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
- **Per-element knowledge (then quiz) layers, cross-run resumability,
  write-through deferred** — `cleaned`/`enriched` for the knowledge corpus
  moved from one monolithic JSON per source to one JSON file per article, so a
  `--force`-less re-run only pays for the articles still missing (see the flow
  description above and `docs/plans/2026-07-17--per-element-knowledge-layers.md`).
  Spec 0005 brought quiz's `cleaned`/`enriched` layers to the same per-element
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
