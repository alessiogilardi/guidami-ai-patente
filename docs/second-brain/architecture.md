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
- `guidami_ai_patente/` — the FastAPI quiz-bot app. A self-contained
  `api/` web layer (app factory, routers, schemas), `services/`/
  `repositories/` holding both infra classes and quiz domain logic,
  empty `models/`/`mappers/`, and `configs/` with a root `AppConfig`.
  Live routes now include `GET /health` — which also doubles as the
  first live proof of `pywire`'s native FastAPI wiring
  (`pywire.fastapi.pywire_lifespan`, ADR 0028) — plus five quiz domain
  endpoints; see the `guidami_ai_patente/` row below.

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
| `commons/clients/postgres_client.py` | Generic, table-agnostic Postgres/pgvector client backed by a `psycopg_pool.ConnectionPool` (AD-26): holds min/max pool size from `PostgresConnectionConfig.pool_min_size`/`pool_max_size` (defaults 1/8), opens eagerly with `wait=True` to fail fast on an unreachable database (D3), registers the pgvector adapter on every connection via a `configure=_configure` hook, and asserts no session state survives a borrow via a `reset=_reset` hook (D4). Public method surface unchanged (`truncate`, `execute`, `execute_many`, `execute_many_returning`, `fetch`, `close`, `__enter__`, `__exit__`): every call site borrows a connection from the pool. It wraps sync `psycopg`/`psycopg_pool`, not their async counterparts (`AsyncConnection`/`AsyncConnectionPool`) — shared as-is with the fully synchronous `guidami_ai_patente_ingestor` batch pipeline, which never runs inside an event loop. `guidami_ai_patente/`'s route handlers compensate per request via `asyncio.to_thread` (AD-25) rather than the client itself being non-blocking; swapping `PostgresClient` to psycopg's async API instead of that per-request thread hop is a possible future enhancement — not yet planned, decided, or tracked by an ADR. | psycopg[binary,pool], pgvector |
| `commons/repositories/db/` | Read-only Postgres repositories, scoped **per entity** not per table (AD-7, spec 0007) — the project's first query code, every repository under `guidami_ai_patente_ingestor/repositories/db/` being write-only bulk insert. `CorpusReadRepository` (`articles` ⋈ `article_commas`) and `QuizReadRepository` (`quiz_questions` ⋈ `quiz_question_embeddings`), each taking an injected `PostgresClient`, mirroring `LlmCallLogRepository`'s shape. `CorpusReadRepository`'s shared `_BASE_SELECT` projection leads with `c.id` (spec 0011 FR-3), so every comma it returns — dense, random or text — can be joined back to its `article_commas` row without resolving a citation string. `QuizReadRepository.fetch_with_vectors(variant, model_column)` takes the model column explicitly (spec 0008 Phase 2, generalized from a single hardcoded `embedding_3_small`); `populated_model_columns()` introspects `information_schema.columns` for `embedding_*`-named columns holding ≥1 non-null vector, so the multi-arm evaluation harness's model axis needs no code change when a second model column is added (AD-6). Lives in `commons/` rather than the `ingest` CLI (which the self-containment rule would otherwise suggest) because a corpus reader is also what `src/guidami_ai_patente/` will eventually need — more than one consumer, same reasoning as `LlmCallLogRepository` | psycopg[binary], pgvector |
| `commons/use_cases/` | `UseCase`/`AsyncUseCase`, `ForEach`, `FlatMap` — generic composition primitives used across pipeline steps | — |
| `domain/entities/`, `domain/models/` | Persisted entities and shared cross-app models | pydantic |
| `flowstep` (external dependency) | Generic sequential-pipeline engine (`Flow`, `Step`, `FlowBuilder`, `FlowContext`, `ApplyStep`) | git dependency (github.com/alessiogilardi/flowstep) |
| `guidami_ai_patente_ingestor/` | Batch ingestion app — orchestrators, services, repositories, mappers, agents, models, configs (see flows below) | — |
| `guidami_ai_patente_ingestor/cli/` | Self-contained `ingest` CLI package (entry point, argument parsing, lazy DI wiring, per-subcommand dispatch, CLI-local `status` services/DTOs/renderer) — see `.claude/rules/cli-structure.md` and the `ingest status` flow below | argparse, rich |
| `guidami_ai_patente/` | FastAPI quiz bot — `api/` self-contained web layer, `configs/app_config.py::AppConfig`, empty pull-based `models/`/`mappers/`; eleven live endpoints (`GET /health` plus ten other routes across `me`/`quiz_questions`/`quiz_images`/`quiz_answers`/`explanation_translations`, detailed below); entry point `main.py::main`, registered as the `serve` script. `AppConfig` (`BaseSettings`) loads once at startup and is registered on the `pywire` container as a singleton: it holds `postgres` (connection pool config, `pool_min_size`/`pool_max_size`); `quiz_images_dir` (root directory for quiz image access, default `Path("data/quiz-images")` — FR-12); and table-name fields (`articles_table`, `article_commas_table`, `quiz_questions_table`, `quiz_question_embeddings_table`, `labeling_runs_table`, `quiz_labelings_table`, `quiz_comma_labels_table`, all defaults matching the schema) parameterizing the API's repositories. Since spec 0013 FR-1, `AppConfig` declares **no** `labeling` field — `main.py` loads and registers an independent `LabelingConfig` instance (the same `BaseSettings` root `IngestorConfig.labeling` embeds on the batch side, single-sourced from `configs/labeling.yaml`/`AGENTS_DIR`) via a generalized `_register_instance[T]` helper, and every consumer that used to read `self.config.labeling.X` now declares its own `labeling_config: Autowired[LabelingConfig]`. `LabelingConfig.yaml_file` is `configs/labeling.yaml`, resolved relative to the process's **working directory**, not the repo root — a pre-existing, undismissed limitation (`labeling/configs/labeling_config.py`'s own class docstring/`model_config` comment) that now also applies to the API: a process started from the wrong `CWD` silently falls back to this class's Python defaults for every epoch field except `agents_dir` (env-var-sourced, defaultless), and is **not** caught by FR-14's coherence check, which compares `prompt_version` — sourced from `AGENTS_DIR`, not from `yaml_file` — so a divergence here is invisible to that diagnostic. Deliberately not fixed in spec 0012 phase 3 (D11). Dependency injection uses `pywire` (Spring-style `@service`/`@repository`/`@client`/`@component` decorators + `Autowired[T]` field injection), not the manual constructor injection the ingestor uses — see `adr/0015-pywire-di-for-fastapi-app.md` and `.claude/rules/pywire-di.md`. `pywire>=0.3.1` adds native FastAPI wiring: bare `Autowired[T]` route parameters resolve on every router mounted on the app once the container is bound to it — originally via a single `wire(app)` call in `api/app.py::create_app` (never on an `APIRouter`); since `pywire>=0.7.0`, via `pywire_lifespan` instead (see the Task 13 note below — `wire()` still works but never tears the container down). `services/health_check_service.py::HealthCheckService` (`Autowired[DependencyVersionRepository]`) is resolved this way on `GET /health` — no `Depends()` — proven live via `uv run api` + a real HTTP request, not just `TestClient`; see `adr/0016-pywire-native-fastapi-wiring.md`. As of quiz-flow-api-phase2 Task 3, `clients/` held the app's first two `@client` providers (spec 0012, AD-16). Since spec 0013 FR-2 (AD-16 revised — the test is now direction-of-dependency, not constructor arity; full definition in `.claude/rules/pywire-di.md`'s `@provider` section), `clients/` holds only `PostgresClientProvider` (`config: Autowired[AppConfig]`, builds `self.client: PostgresClient` in its own `__init__` via `labeling.wiring.build_postgres_client(config.postgres)` — one pooled client for the whole process, sizing from `AppConfig.postgres`, never from `LabelingConfig`, AD-26; also gained a `@pre_destroy` method calling `self.client.close()`, spec 0013 FR-6, run by `Container.close()` — since `pywire>=0.7.0` called by `pywire_lifespan` itself, nested inside `api/app.py::_lifespan` rather than invoked by `_lifespan` directly — after `yield`). A new sibling package, `providers/`, holds `LabelingStackProvider` (decorated `@provider`, `labeling_config: Autowired[LabelingConfig]`/`agent_configs: Autowired[AgentConfigRepository]`, loads `comma_labeler.yaml` once via `AgentConfigRepository.load("comma_labeler")` and derives `self.epoch: LabelingEpoch` via `LabelingEpochMapper.from_config_to_epoch` — the same six-field epoch the FR-8 precedence query and the FR-14 startup check both compare against; deliberately does not call `labeling.wiring.build_comma_labeler_config`, which would be a second, uncoordinated read of the same file). `repositories/` gained `AgentConfigRepository` (`@repository`, `labeling_config: Autowired[LabelingConfig]` — since spec 0013 FR-1, not `AppConfig`), the API's single door to resolving `LabelingConfig.agents_dir` and reading agent prompt YAML (AD-22): its `__init__` anchors a `commons.repositories.YamlRepository[AgentConfig]` to a `commons.clients.file_system.LocalFileSystemClient(self.labeling_config.agents_dir)`, and `load(name) -> AgentConfig` reads `<name>.yaml`, raising `FileNotFoundError` for a missing file and `PermissionError` for a name that resolves outside `agents_dir` (the file-system client's own containment check, not caller-side sanitisation). As of quiz-flow-api-phase2 Task 6, `repositories/` also holds `QuizQuestionRepository` (`@repository`, `config`/`postgres: Autowired[AppConfig, PostgresClientProvider]`) — every read the quiz endpoints make: `find_by_permutation`/`find_by_number`/`find_correct_answer`/`list_topics`/`image_is_referenced`/`has_embedding`, all synchronous, all returning `None`/`False`/`[]` on absence rather than raising (see `patterns.md` for the seeded-permutation and FR-12 database-first-authorization details, and the note there — since spec 0013 FR-2/FR-3 removed the `clients`<->`repositories` cycle at the root, this repository now imports `PostgresClientProvider` from the `clients` package re-export like any other consumer, no direct-submodule exception needed anymore). Both providers and the repositories are zero-argument constructible, building their real work inside `__init__` after pywire sets their `Autowired` fields (ADR 0017); `api/app.py` imports `LabelingStackProvider`/`PostgresClientProvider` for their pywire-registration side effect, same as every other decorated class. As of quiz-flow-api-phase2 Task 7, `repositories/` also holds `GoldenSetReadRepository` (AD-16b, app-local rather than beside `GoldenSetWriteRepository` in `src/labeling/`): `find_current_labeling(number, epoch)` (FR-8's precedence query, SQL-expressed) and `distinct_prompt_versions` (FR-14's coherence probe). Since spec 0013 FR-3 (ADR 0027, superseding ADR 0024), `find_current_labeling` takes `epoch: LabelingEpoch` as an explicit parameter instead of autowiring `LabelingStackProvider` — it is now a pure function of its two parameters, with no `clients`/`providers` dependency at all beyond `PostgresClientProvider`, now imported from the `clients` package re-export (the fix-wave following the final review simplified this off its former direct-submodule import once the cycle was confirmed gone). ADR 0024's bare-import-plus-quoted-`Autowired["clients.LabelingStackProvider"]` mechanism, which had routed around a *true* mutual `clients`<->`repositories` package-init cycle, is gone from this file entirely — the cycle is removed at the root, verified in both import orders. As of quiz-flow-api-phase2 Task 8, `services/` gained `ExplanationStatusService` (`@service`, `labeling_stack`/`golden_set`/`questions: Autowired[LabelingStackProvider \| GoldenSetReadRepository \| QuizQuestionRepository]`, all plain package-level imports — `services/` sits above both `clients/` and `repositories/` in the dependency direction, so it triggers neither of the two `clients`<->`repositories` cycles Tasks 6/7 had to work around): (since spec 0013 FR-4, `ExplanationStatusService(UseCase[str, ExplanationStatus])`, method renamed `resolve`→`execute`, invoked via `__call__`) — its `execute(request: str) -> ExplanationStatus` applies FR-4's three cases in order, reading `epoch = self.labeling_stack.epoch` once and passing it explicitly into `find_current_labeling` (spec 0013 FR-3) — a current labeling with supporting commas is `CACHED` regardless of whether an embedding exists (the cached path never retrieves, so it never needs a query vector); a current labeling without supporting commas is `UNAVAILABLE` (the judge already answered "no", re-probing the embedding wouldn't change that); only when there is **no** current labeling does it fall back to `QuizQuestionRepository.has_embedding(number, variant)` (`variant` from `LabelingStackProvider.epoch.candidate_variant`) — present is `UNCACHED`, absent is `UNAVAILABLE` (FR-7's `not_indexed`). The order is load-bearing: checking the embedding before the labeling would let a missing vector wrongly downgrade a valid cache hit. As of quiz-flow-api-phase2 Task 12, `services/` also holds `JudgeCoherenceChecker` (`@service`, `labeling_stack`/`golden_set: Autowired[LabelingStackProvider \| GoldenSetReadRepository]`) — a startup diagnostic (FR-14) that warns when this deployment's judge prompt diverges from what the batch labeling used (wired into the lifespan in Task 13). Compares `LabelingStackProvider.epoch.prompt_version` against `GoldenSetReadRepository.distinct_prompt_versions()`: logs a warning if they mismatch, or if the check itself fails (database not yet ready); never raises, so a deployment can start even if the check is blocked or the judge diverges. An empty golden set is not a divergence (first deployment or post-reset state). As of quiz-flow-api-phase2 Task 13, `api/app.py::create_app` wires `_lifespan` (an `@asynccontextmanager`, passed as `FastAPI(..., lifespan=_lifespan)`) which — since `pywire>=0.7.0` — nests `pywire_lifespan(app)` (binding the container to the app and closing it on shutdown, superseding the deprecated `wire()`) and, inside that, awaits `_run_judge_coherence_check()`: a standalone top-level function, kept separate from `_lifespan` precisely so a test can exercise its "container `resolve()` can also raise" guard directly, without entering `pywire_lifespan` and thereby binding/closing the real process-wide default container. `_run_judge_coherence_check` resolves `JudgeCoherenceChecker` from the container and runs its `check()` via `asyncio.to_thread` before `yield` — every request-serving route only starts accepting traffic after the FR-14 diagnostic has had its one shot, though (per the paragraph above) a failing check never blocks that startup. The app now registers two new routers, `api/routers/quiz_questions.py` (`router = APIRouter(prefix="/quiz-questions", ...)`) and `api/routers/quiz_images.py` (`prefix="/quiz-images"`), giving the API its first five real domain endpoints: `GET /quiz-questions/topics` (`QuizProposalService.topics`, FR-16), `GET /quiz-questions/random?seed=&index=&topic=` (`QuizProposalService.propose`, FR-1), `GET /quiz-questions/{number}` (`QuizProposalService.fetch`, FR-2), `POST /quiz-questions/{number}/check` (`QuizAnswerChecker`, FR-3/FR-4 — since spec 0013 FR-4, `UseCase[QuizAnswerCheckRequest, tuple[bool, ExplanationStatus]]`, invoked via `__call__` with the new `QuizAnswerCheckRequest` DTO assembled from the path param + wire-format body; request/response wire DTOs `QuizCheckRequest`/`QuizCheckResponse` in `api/schemas/quiz_check.py` are unchanged), and `GET /quiz-images/{filename}` (`QuizImageService`, FR-12 — since spec 0013 FR-4, `UseCase[str, QuizImage]`, method renamed `load`→`execute`, invoked via `__call__`, returns a raw `fastapi.Response` with the image's bytes/media type, not a `response_model`). `/topics` and `/random` are declared **before** `/{number}` in `quiz_questions.py` — FastAPI matches routes in declaration order, so a parameterised route declared first would swallow the literal paths and return a nonexistent-question 404 instead of the topics menu or a validation error. Every handler in both routers is `async def` and reaches its synchronous service/mapper call through `asyncio.to_thread` (AD-25, same rule as the lifespan check above); none contains a `try`/`except` or HTTP status logic — every domain exception (`QuestionNotFoundError`, `QuizImageNotFoundError`) is raised by the service/repository layer and rendered by the global handlers registered in `register_exception_handlers` (Task 4), never caught in a router. Since quiz-flow-api-phase3, `providers/` holds **three** providers over the shared labeling stack, not two — AD-16 called for two total, and this is a deliberate deviation recorded as a spec errata (plan decision D3): `LabelingStackProvider` stays the judge's *identity* only (the loaded prompt and the epoch it implies, read on every `POST /check`), while a new `LiveLabelingStackProvider` (`Autowired[AppConfig, LabelingConfig, LabelingStackProvider, PostgresClientProvider, OpenRouterProviderComponent, LlmCallTrackerProvider]`) builds the *machinery* — the corpus/quiz/golden-set repositories, the candidate-set service, the built `CommaLabelerAgent` (from `LabelingStackProvider.agent_config`, never reloaded) and the shared `QuestionLabelingService` (`labeling.wiring.build_question_labeling_service`) — exposed as plain attributes (`corpus`, `quiz`, `golden_set`, `candidate_set`, `question_labeling`). Splitting them keeps FR-14's deliberately-swallowing startup diagnostic from masking a malformed prompt file or a bad credential (resolving the epoch would otherwise also construct the whole LLM graph) and keeps the hot `POST /check` path — which only reads the epoch — from ever building an LLM graph it never calls. Two more providers complete the stack: `OpenRouterProviderComponent` (`Autowired[OpenRouterConfig]`, builds the one `pydantic_ai.providers.openrouter.OpenRouterProvider` every agent in the process shares, via `labeling.wiring.build_open_router_provider` — third-party class, not ours to decorate, AD-16 rule 2) and `LlmCallTrackerProvider` (`Autowired[ObservabilityConfig, PostgresClientProvider]`, D5) which enters `build_llm_call_tracker`'s context manager once through an `ExitStack` at construction and exposes `self.tracker: LlmCallTracker`, closed by a `@pre_destroy` hook that `Container.close()` runs — built *after* `PostgresClientProvider` since it depends on it, so reverse build order drains the tracker's queue before closing the pool it writes through; with `ObservabilityConfig.enabled` false it holds a `NullLlmCallTracker` instead, so disabling tracking is a config change, never a code path. This closes a standing gap: `labeling.wiring.build_comma_labeler_agent`'s `tracker` parameter used to be documented as unusable from the API (no request-scoped owner for a `QueuedLlmCallTracker`'s background worker) — pywire 0.6.0's `@pre_destroy` removed that obstacle, and the docstring is corrected accordingly (spec 0013 FR-6, phase 3 Task 14). `services/` gained `CommaSelectorService` (`AsyncUseCase[str, CommaSelection]`, `Autowired[LabelingConfig, LabelingStackProvider, LiveLabelingStackProvider, CurrentLabelingReadService]`) — on a hit it reads FR-8's current labeling and issues no retrieval and no judge call; on a miss it reads the precomputed query vector via `QuizReadRepository.find_with_vector(number, variant, EMBEDDING_MODEL_COLUMN)` (the single-row counterpart of `fetch_with_vectors`, same three-table join, `None` covering both "no such question" and "no vector for this variant/model" so the caller renders either as `not_indexed`) and delegates to the shared `LiveLabelingStackProvider.question_labeling`, resolving the live run id lazily — only right before the write, via `GoldenSetWriteRepository.find_or_create_live_run`, called from inside `QuestionLabelingService`'s own `asyncio.to_thread` hop — so a failed judge leaves no `labeling_runs` row behind either (spec 0012 AD-20/FR-6 errata, D8). Since spec 0017 (on-demand-explanation), its read path no longer queries `GoldenSetReadRepository` directly: it delegates to the new `CurrentLabelingReadService` (injected as `reader`, see below) and reacts to `reader` raising `LabelingNotReadyError` by running the same live retrieval-plus-judge path described above, then re-reading via `reader` so the return shape is always `reader`'s. `services/` also gained `ExplanationService` (`AsyncUseCase[ExplanationRequest, Explanation]`; since spec 0017, `Autowired[AppConfig, QuizQuestionRepository, CurrentLabelingReadService, ExplanationWriterAgent]` — the field is named `reader`, not `selector`, and depends on `CurrentLabelingReadService` directly rather than on `CommaSelectorService`, so `ExplanationService` structurally can never trigger the judge; a `LabelingNotReadyError` raised by `reader` propagates uncaught and is mapped by `register_exception_handlers` to `409`, telling the caller to call the new `/label` endpoint below first), which wraps the read-plus-write in one `asyncio.timeout(config.explanation_deadline_s)` (`AppConfig.explanation_deadline_s`, narrowed by spec 0017 to 10.0s, writer-stage only — the labeling-stage budget moved to the new `AppConfig.labeling_deadline_s`, 25.0s, used by `LabelingService` below): a request-wide budget for the writer call, not a per-stage sum and not a lower `comma_labeler.yaml` timeout, since the batch shares that file and its content hash is `prompt_version`. The writer (`ExplanationWriterAgent`, a container singleton) is never called without supporting commas (FR-7) and is retried up to 3 times if it cites an ordinal outside the supplied commas (FR-10). `api/routers/quiz_questions.py` gained the route `GET /quiz-questions/{number}/explanation?submitted=` (`ExplanationService`, FR-5/FR-6/FR-7/FR-11/FR-13), declared genuinely `async def` with no `to_thread` wrapper — unlike its synchronous siblings, the service itself is async at the LLM boundary (AD-25) — returning `200` with `status: insufficient_knowledge` plus a machine-readable `reason` when the corpus does not justify the answer, `409` (spec 0017, above) when the question is embedded but not yet labeled, and mapped by `register_exception_handlers` to `503` on `ExplanationUnavailableError` (judge/writer failure or an exceeded deadline). Since spec 0017, this route never triggers retrieval or the judge itself — it renders from an already-existing labeling only; that responsibility moved to a new sibling route. `services/` gained two more classes for this split: `CurrentLabelingReadService` (a plain read-only service, `Autowired[LabelingStackProvider, GoldenSetReadRepository, QuizQuestionRepository]`) is the shared lookup both `CommaSelectorService` and `ExplanationService` now depend on — it looks up a question's current comma labeling without ever triggering retrieval or the judge, returning `CommaSelection(labeling=None)` for a genuine pipeline gap (no embedding at all, per `QuizQuestionRepository.has_embedding`) and raising the new `LabelingNotReadyError` (`exceptions/`, mapped by `register_exception_handlers` to `409`) when `has_embedding` is true but the question is not yet labeled; `LabelingService` (`Autowired[AppConfig, QuizQuestionRepository, CommaSelectorService]`) wraps `CommaSelectorService` in its own `asyncio.timeout(config.labeling_deadline_s)` plus a 404 existence check. `api/routers/quiz_questions.py` gained a new route, `POST /quiz-questions/{number}/label` (`LabelingService`) — `204` on success, `404` unknown question, `503` on timeout or judge failure — which ensures a labeling exists for a question, running the live retrieval-plus-judge path only on a genuine miss (no existing labeling). The net shift: what used to be one combined check-then-explain flow is now three single-responsibility endpoints — `/check` (unchanged), `/label` (ensure a labeling exists, computing live only on a miss), `/explanation` (render from an already-existing labeling only, never triggering the judge) — with `CurrentLabelingReadService` as the shared read-only dependency both `/label`'s `CommaSelectorService` and `/explanation`'s `ExplanationService` delegate to (see `patterns.md` for this as a reusable convention). Since spec 0016, every route above (bar none) is gated behind a Telegram-identity auth check: `api/dependencies/user_identity.py::resolve_identity` (plain `Depends()`, not a pywire component — see `patterns.md`) reads the `X-Telegram-User-Id` header and calls `UserRepository.provision` (new `repositories/user_repository.py`, `@repository`), which idempotently inserts-then-selects the caller's `users` row (`INSERT ... ON CONFLICT DO NOTHING` + follow-up `SELECT`, atomic at the DB level, AD-6-style — no application locking); `require_registered_user` (built on top of `resolve_identity`, never duplicating its provisioning) raises the new `UnregisteredUserError`, mapped by `register_exception_handlers` to `403` (FR-3), if `registered` is still `false`. `GET /me` (`api/routers/me.py`) is the one route using `resolve_identity` alone — it reports status without gating, so an unapproved caller can still learn they're pending. `domain/entities/users/user.py::UserEntity` (`telegram_user_id`, `registered`) is the entity both the repository and the auth dependency return. `services/`/`repositories/` also gained `QuizAnswerRepository` (`repositories/quiz_answer_repository.py`, `@repository`) — `record_answer` inserts one `quiz_answers` row via a single `INSERT ... SELECT` resolving both `user_id`/`quiz_id` server-side from the caller's natural keys (`telegram_user_id`, `number`), and `session_summary` returns a `SessionSummary` (answered/correct counts, correctness always joined against `quiz_questions.correct_answer` live, never cached — same AD-3 rule as every other correctness check in this spec). `POST /{number}/check` now calls `QuizAnswerRepository.record_answer` as a side effect of grading (via the existing `QuizAnswerChecker`, which gained the two new `QuizAnswerCheckRequest` fields `session_id`/`telegram_user_id`), and a new `GET /quiz-answers/summary` route (`api/routers/quiz_answers.py`) exposes `SessionSummaryService` (`AsyncUseCase`-shaped) over the same repository, returning the totals plus a per-topic breakdown (`by_topic`) and the wrongly answered questions (`wrong_questions`), mapped by `SessionSummaryMapper`. Since spec 0018, a new router, `api/routers/explanation_translations.py` (`prefix="/explanations"`), serves `POST /explanations/translate?lang=ru` (body `{text}`, 1-6000 chars; response `{translated_text}`, schemas in `api/schemas/explanation_translation.py`): it takes no question `{number}` — the client passes the Italian text it already holds from `GET /quiz-questions/{number}/explanation` (AD-1), so the endpoint is decoupled from the RAG/labeling pipeline entirely (no `CurrentLabelingReadService`, no judge, no retrieval). It is gated by `require_registered_user` like every other business route, plus a second plain `Depends()`, `api/dependencies/language.py::require_supported_language`, which accepts only `lang="ru"` and otherwise raises the new `UnsupportedLanguageError` (`exceptions/`), rendered by `register_exception_handlers`' new `_bad_request` handler as `400` (FR-2) — the query parameter stays open so a later language needs no new route. The handler calls `ExplanationTranslationService` (`services/`, `AsyncUseCase[str, str]` — a plain `str` in and out, no wrapper DTO, per `.claude/rules/use-case-invocation.md`; `Autowired[AppConfig, ExplanationTranslatorAgent]`), which wraps one `ExplanationTranslatorAgent.run` call in `asyncio.timeout(AppConfig.translation_deadline_s)` (default 20.0s, `gt=0`, AD-5) and raises the **existing** `ExplanationUnavailableError` (already mapped to `503`) for both a timeout and any agent failure rather than a new exception class (AD-4, see `patterns.md`). `ExplanationTranslatorAgent` (`agents/explanation_translator/`, `@agent`, `BaseAgent` subclass with the same three `Autowired` providers as `ExplanationWriterAgent` — `AgentConfigRepository`, `OpenRouterProviderComponent`, `LlmCallTrackerProvider`, so its calls are tracked per ADR 0031) loads `configs/agents/explanation_translator.yaml` (model `openrouter/google/gemini-2.5-flash`, `temperature` 0.2, `max_tokens` 2400 — a non-epoch prompt, resolved through the same `AGENTS_DIR` anchor as `explanation_writer.yaml`); its prompt instructs it to leave article/comma references and the codes' proper names untranslated, and its response DTO's LLM-facing text is Italian per the `code-conventions.md` exception. Since spec 0020, `GET /quiz-questions/{number}/explanation` no longer renders one LLM call — `ExplanationService._explain` splits into `_legal_outcome` (the unchanged spec-0017 path above) and a new `_vocabulary_outcome`, run concurrently via `asyncio.TaskGroup` (final-review fix wave: not `asyncio.gather`, which does not cancel a sibling task merely because another one raised) under the same `explanation_deadline_s` timeout (writer-stage only; both stages must finish inside it, cancellation on timeout affects both, and a legal-stage failure now also cancels a still-running vocabulary task instead of leaving it orphaned). `_vocabulary_outcome` additionally bounds itself with its own inner `asyncio.timeout` (`explanation_deadline_s` minus a fixed margin), so a slow vocabulary call degrades on its own budget rather than tripping the shared outer deadline. `_vocabulary_outcome` is answer-blind by construction (AD-4): it reads `QuizQuestionRepository.find_question_vocabulary_context` (a projection with structurally no `correct_answer` field), retrieves candidates via the new `GlossaryReadRepository.candidates_for` (hybrid dense+full-text, RRF-fused entirely in one SQL query — see `patterns.md`), shuffles them once (`random.shuffle`, no fixed seed — live per-request serving, not the batch labeler's audited `shuffle_seed`) before building `QuestionExplainerRequest`, and reuses that exact shuffled list to resolve the new `QuestionExplainerAgent`'s `cited_term_numbers` ordinals back into `CitedGlossaryTerm`s afterward — the same list object for both steps, or the ordinals would resolve to the wrong terms. The whole stage is wrapped in one blanket `try/except Exception`, spanning the DB call, the retrieval call and the agent call, degrading to `(None, ())` and logging a `warning` on any failure — a bug here must never take down the already-shipped legal-explanation path it runs alongside (FR-5). `QuestionExplainerAgent` (`agents/question_explainer/`, mirrors `ExplanationWriterAgent`'s `output_validator` shape, see `patterns.md`) is unsuffixed (Italian output, base language, `agent-config-naming.md`). `Explanation` gained `term_explanation: str | None`/`translation_hints: tuple[CitedGlossaryTerm, ...]`, populated independently of `result` (AD-1) — a refused legal explanation can still carry a vocabulary explanation. The wire response (`CitedGlossaryTermResponse`) and the bot rendering (a third message section, `_glossary_block`) both thread through unchanged from there; the bot's `POST /explanations/translate` forwarding (spec 0018) now also carries `hints` built from `translation_hints`, never `definition` | FastAPI, uvicorn, pywire |
| `labeling/` | Shared labeling/judge stack (spec 0012, AD-12), split out of `retrieval_evaluation/` so both the batch harness and the future FastAPI app can depend on it without pulling in a standalone script's entry point. Manual constructor injection only, no `pywire` (ADR 0015); every component stays synchronous (AD-25); `tests/labeling/test_module_boundary.py` guards that it imports nothing from `retrieval_evaluation/`, `pywire`, or `guidami_ai_patente/`, and that `domain/` never imports it back. As of spec 0012 Task 5 it holds the full judge stack: `agents/comma_labeler/` (`CommaLabelerAgent`), `models/` (`CandidateComma`, `LabelingEpoch`, `QuestionLabelingRequest`), `services/` (`CandidateSetService`, `GoldenSetLabelingService`, `QuestionLabelingService`, `QuestionLexemeService`), `repositories/` (`GoldenSetWriteRepository`), `exceptions/` (`CandidateNumberOutOfRangeError`), `utils/` (`corpus_commit`, `prompt_version`), `configs/` (`LabelingConfig`), `constants.py` (`EMBEDDING_MODEL_COLUMN = "embedding_3_small"`, re-exported from the package `__init__.py` — deliberately a constant, not configuration, because it names which `quiz_question_embeddings` column both the batch pass and the live path read for the dense arm, and making it configurable would oblige it to enter the epoch key. A true symmetric parameterisation — per-model columns on `article_commas` too, a parameterised `dense_top_k`, the column inside the epoch key, an ingestion write path targeting it — is deliberately out of scope here and needs its own spec, spec 0012 phase 3 D7), and `mappers/` (`LabelingEpochMapper`, `LabelingRunMapper`). `QuestionLabelingService` (spec 0012 phase 3 Task 5, AD-12) is the extraction that makes this package's sharing real rather than aspirational: it is the **one** implementation of "judge this question and record the verdict" — candidate retrieval, per-question shuffle, judge call with transport retry, ordinal resolution and the write — called by both `GoldenSetLabelingService` (the batch fan-out) and `guidami_ai_patente/services/comma_selector_service.py::CommaSelectorService` (the live cache fill), so a batch labeling and a live labeling under the same epoch key are the same code path, not two lookalikes (see "Relevant architectural decisions" and the pattern entry in `patterns.md`). Since Task 6 it also holds `wiring.py`: manual DI builders for this stack's collaborators (`build_open_router_provider`, `build_postgres_client`, `build_tracker`, `build_corpus_repository`, `build_quiz_repository`, `build_golden_set_repository`, `build_comma_labeler_config`, `build_comma_labeler_agent` — its `tracker` parameter is optional so a caller with no sink can omit it, but both real callers pass one: the batch through `build_llm_call_tracker`, the API through `guidami_ai_patente/providers/llm_call_tracker_provider.py::LlmCallTrackerProvider`, whose `@pre_destroy` hook gives the background worker a container-scoped owner (pywire 0.6.0, spec 0013 FR-6) — `build_question_lexeme_service`, `build_candidate_set_service`, and, since Task 5, `build_question_labeling_service`), each parameterised on `LabelingConfig`/plain values rather than `IngestorConfig`/`AppConfig` (`tests/labeling/test_wiring.py::test_no_builder_takes_an_ingestor_config` asserts this by signature inspection). `retrieval_evaluation/main.py` and `label_main.py` both consume it instead of duplicating their own `_build_*` helpers | pydantic-ai-slim[openrouter] |
| `retrieval_evaluation/` | LLM-as-judge for retrieval quality (`evaluate-retrieval-judge` script) — deliberately separate from `ingest evaluate retrieval` (spec 0007 excludes an LLM judge as a Non-Goal, ADR 0013) — plus `label-golden-set`, persisting a labeled golden set built from `labeling/`'s collaborators (spec 0011 phase 2). Since spec 0012 Task 5 this package holds only `agents/retrieval_judge/`, `models/retrieval_judge_item_result.py`, `services/retrieval_judge_evaluation_service.py`, `main.py`, `label_main.py`, and a `wiring.py` trimmed to one builder, `build_retrieval_judge_agent(agents_dir, provider, tracker)`. Since Task 6, `main.py` and `label_main.py` import every other DI builder they need from `labeling.wiring` (`build_open_router_provider`, `build_postgres_client`, `build_tracker`, `build_corpus_repository`, `build_quiz_repository`, and — `label_main.py` only — `build_golden_set_repository`, `build_comma_labeler_config`, `build_comma_labeler_agent`, `build_question_lexeme_service`, `build_candidate_set_service`) rather than each carrying its own duplicated `_build_*` set; both widen their pooled `PostgresClient`'s `pool_max_size` to `max(config.postgres.pool_max_size, concurrency)` before building it (D7/D14), since each fans `concurrency` tasks out over one shared connection pool. `RetrievalJudgeAgent` + its DTOs (`agents/retrieval_judge/`, `BaseAgent` pattern — `agents/` is a generic per-role container, today holding the single `retrieval_judge/` agent subpackage) + `RetrievalJudgeEvaluationService` (`services/`) reuse `commons.repositories.db.{CorpusReadRepository,QuizReadRepository}` and `guidami_ai_patente_ingestor.configs.IngestorConfig` (Postgres/OpenRouter/table names) plus `IngestorConfig.labeling.agents_dir` (`src/labeling/configs/`, spec 0012 Task 3) rather than owning new config or CLI infra | pydantic-ai-slim[openrouter] |
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
(Postgres connection, table names, OpenRouter provider) from
`guidami_ai_patente_ingestor.configs` rather than owning its own settings class —
the one deliberate cross-package dependency this module has. Its agent YAML
(`retrieval_judge.yaml`) loads from `config.labeling.agents_dir`, not a bare
`agents_dir` on `IngestorConfig` — since spec 0012 Task 3, this directory feeds the
labeling judge's configuration-epoch hash (AD-22), which `IngestorConfig.agents_dir`
itself does not (see `patterns.md`). Since spec 0012 Task 5, `retrieval_evaluation/
wiring.py` is trimmed to a single builder, `build_retrieval_judge_agent(agents_dir,
provider, tracker)` (reparameterised off a bare `agents_dir: Path` rather than
`IngestorConfig`, so `main()` passes `config.labeling.agents_dir` in explicitly). Since
Task 6, every other builder this script needs (`build_open_router_provider`,
`build_postgres_client`, `build_tracker`, `build_corpus_repository`,
`build_quiz_repository`) is imported from `labeling.wiring` instead of a private,
duplicated `_build_*` helper — `main.py` no longer carries its own copies. `main()`
also widens the client it builds: `config.postgres.model_copy(update={"pool_max_size":
max(config.postgres.pool_max_size, args.concurrency)})`, so `--concurrency` judge calls
fanning out over one pooled connection don't starve each other under Task 1's bounded
`timeout` (D7/D14) — the same widening `label_main.py` below applies.

**Golden-set labeler** (`label-golden-set` script, entry point `src/retrieval_evaluation/
label_main.py`, its collaborators in `src/labeling/` since spec 0012 Task 5): a
second entry point over the same corpus, persisting a labeled retrieval golden set
to Postgres instead of printing a spot-check verdict (spec 0011 phase 2). Where the
judge above looks at one arm (`dense_top_k`) and writes nothing, the labeler builds
a **two-arm candidate union** and writes every labeling to three new tables
(`labeling_runs`, `quiz_labelings`, `quiz_comma_labels` — see `database.md`).

`QuestionLexemeService.build` (`labeling/services/question_lexeme_service.py`) concatenates
a question's configured `LabelingConfig.lexeme_fields` (`topic`/`text`/
`image_description`, skipping blanks) and hands the text to a new
`CorpusReadRepository.extract_lexemes` method, which asks Postgres itself —
`SELECT lexeme FROM unnest(to_tsvector('italian', %s))` — for the exact stemmed,
stop-word-filtered lexemes the corpus's own GIN indexes are built from (AD-9: same
dictionary on both sides, so extraction and search cannot silently diverge). The
returned lexemes are then single-quoted with internal quotes doubled before being
handed to `text_match_top_k`, since `to_tsquery` treats an unquoted lexeme
containing punctuation (e.g. `e-mail`) as a syntax error, not a literal.
`CandidateSetService.build` (`labeling/services/candidate_set_service.py`) then unions
`CorpusReadRepository.dense_top_k` with `text_match_top_k(lexemes, text_k)`, keyed
by comma id, recording each arm's one-based rank on a `CandidateComma` — the union
is **not** truncated, sorted or fused (AD-3): its length is the full union, and a
comma found by both arms carries both ranks.

Since spec 0012 phase 3 Task 5, the pass is split across two collaborators instead of
one. `GoldenSetLabelingService.execute` (`labeling/services/golden_set_labeling_service.py`,
`AsyncUseCase[int, int]`, `request` is the already-created `run_id`) does **selection and
concurrency only**: for every question with a query vector for the configured
`candidate_variant`, first optionally restricted to the union of `--topic` (repeatable)
topics when given (FR-18) — a pure selection filter, applied *before* the limit so
`--limit N --topic t` means "N questions of topic t", and never recorded on
`labeling_runs` or folded into the judge's configuration epoch, since it changes *which*
questions are judged, not *how* — then optionally restricted to `--limit` questions via a
seeded shuffle independent of the presentation shuffle (PD-18), it fans the selected rows
out under a per-run `asyncio.Semaphore` built inside `execute` (bound to the event loop of
its first use, so it cannot live on `self`), bounded by `max_concurrency`, and awaits
`QuestionLabelingService(QuestionLabelingRequest(row=row, resolve_run_id=lambda: run_id))`
for each one via `asyncio.gather` with no `return_exceptions=True` (PD-9 — a partially-
labeled run cannot look complete; any failure aborts the whole run).

The judging itself — candidate retrieval, presentation shuffle, the judge call, ordinal
resolution and the write — lives in `QuestionLabelingService.execute`
(`labeling/services/question_labeling_service.py`, `AsyncUseCase[QuestionLabelingRequest,
int | None]`), extracted out of what used to be `GoldenSetLabelingService.label_all`
specifically so the batch pass and the API's live cache fill (`CommaSelectorService`,
below) run **one** implementation — the epoch key cannot tell two judging implementations
apart (AD-12). It calls the injected `CandidateSetService` and shuffles the presentation
order with `random.Random(f"{shuffle_seed}:{question_id}")` (deterministic per question,
independent of processing order — PD-8), then asks a second, distinct agent,
`CommaLabelerAgent` (`labeling/agents/comma_labeler/`, its own `dto/` — `CommaLabelerRequest`/
`CommaLabelerResponse`, own `configs/agents/comma_labeler.yaml` prompt — FR-12
requires this rather than widening `RetrievalJudgeResponse`, since `BaseAgent`
binds one `output_type` per class), which candidate ordinals (at most three, most-
justifying first) justify the correct answer. Each returned ordinal resolves to its
presented candidate by list index, never by matching text (AD-12); an ordinal
outside the presented range raises `CandidateNumberOutOfRangeError` and propagates —
nothing is written and no run id is resolved (FR-13). Only transport-level
failures are retried (`httpx.TransportError`, or `ModelHTTPError` with a 429/5xx
status), up to `labeling.transport_retries` times with exponential backoff; every
other exception, including a permanent 4xx or a validation error, propagates
immediately (PD-17). Every synchronous collaborator here (`CandidateSetService`, the
insert) is crossed with `asyncio.to_thread` (AD-25) — not only for the API, whose event
loop must not block, but for the batch too: its candidate-set and insert work now fans
out under the semaphore instead of serialising on the event-loop thread, which is what
`label_main`'s pool sizing (below) is for.

**The run id is resolved lazily, inside the write, after the judge has answered**
(`QuestionLabelingService._write`, calling `request.resolve_run_id()`) — not before the
judge call. For the batch this closure is trivial (`lambda: run_id`, the id
`label_main.py` already created before the pass); for the live API path
(`CommaSelectorService._live_run_id`) it does real work,
`GoldenSetWriteRepository.find_or_create_live_run`, and only runs once the judge has
produced a verdict. This is what makes "on judge failure, no row is written to *any*
golden-set table" literally true for a live request: an eagerly-created `labeling_runs`
row would otherwise survive a failed judge call as an orphan (spec 0012 AD-20/FR-6
errata, quiz-flow-api-phase3 plan decision D8).

`GoldenSetWriteRepository` (`labeling/repositories/golden_set_write_repository.py`) is
insert-only (AD-10, mirroring `LlmCallLogRepository`'s precedent): `insert_run`
writes one `labeling_runs` row; `insert_labeling` writes a `quiz_labelings` row and
its `quiz_comma_labels` children in a **single data-modifying CTE**, atomic despite
`PostgresClient`'s `autocommit=True` (PD-15) — two separate statements would let a
failing child insert leave a childless parent indistinguishable from a genuine "no
justifying comma" outcome (AD-6: the outcome is *derived* by counting children,
never stored as a column). `outcome_counts` is the one read method on the class (a
`SELECT`, not a write), used by `label_main.py` to print the with-commas/without-
commas breakdown after the run. `label_main.py` inserts the `labeling_runs` row
*before* the pass, built via `LabelingEpochMapper.from_config_to_epoch(labeling,
agent_config)` (the epoch: `judge_model`, a `prompt_version` hashed from the loaded
prompt text via `labeling/utils/run_provenance.py::prompt_version` — no human-maintained
version field, AD-11 — `candidate_variant`, `dense_k`, `text_k`, sorted `lexeme_fields`)
followed by `LabelingRunMapper.from_epoch_to_entity(epoch, LabelingRunOrigin.BATCH,
shuffle_seed=..., corpus_comma_count=..., corpus_commit=..., question_limit=...)` — the
sanctioned constructor as of Task 6, replacing the inline `LabelingRunEntity(...)`
stopgap the earlier tasks used before the mappers existed. `corpus_comma_count` comes
from a new unfiltered `CorpusReadRepository.comma_count`, `corpus_commit` from `git
rev-parse HEAD`. `label_main.py` also validates `candidate_variant` against
`QuizReadRepository.available_variants()` first (same guard as the judge script), widens
its pooled `PostgresClient`'s `pool_max_size` to `max(config.postgres.pool_max_size,
concurrency + 1)` before building it — since spec 0012 phase 3 Task 5, the `+ 1` (not
just `concurrency`) is deliberate: `QuestionLabelingService` now crosses
`asyncio.to_thread` for its candidate-set and insert work too, so up to `concurrency`
workers can each hold a connection for that hop, on top of the connection the request
that triggered the fan-out itself may still be holding — and — like
the judge script — reuses only `RunArtifactWriter.build_run_dir` for its
`logs/label_golden_set_<timestamp>/` directory, with no manifest, no dry-run chain, no
`report.md` (AD-10; the module's placement rationale in ADR 0013 extends unchanged to
this second script, though the ADR's premise that the module writes no persistent
artifact no longer holds — see the ADR itself). Since Task 6, both `main.py` and
`label_main.py` build every shared collaborator (Postgres client, OpenRouter provider,
tracker, quiz/corpus read repositories, golden-set repository, comma-labeler
config/agent, question-lexeme service, candidate-set service) via `labeling.wiring`
instead of a private, duplicated `_build_*` helper set.

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

*Last updated: 2026-08-25 — verified against commit `f1a2b74e`.*

*Last updated: 2026-08-26 — verified against commit `d21223b7` (working tree ahead:
quiz-flow-api-phase2 branch, pre-implementation grilling/check session). ADR 0017's
zero-arg-`@component` `AppConfig` workaround (Decision item 1) and its
constructor-parameter testability exception (Decision item 3) are superseded by
`adr/0023-appconfig-registered-instance-supersedes-0017.md`: `AppConfig` is loaded once
at `main.py` and registered via `container.register_instance(app_config, as_type=
AppConfig)`; a class needing a test double stays field-only `Autowired[T]` and the test
registers a mock plus calls `clear_instances()` instead. ADR 0017's Decision item 2
(`PostgresClientProvider` building `PostgresClient` in its own `__init__`) is unaffected.
`.claude/rules/pywire-di.md` updated accordingly. No source code changed — the
quiz-flow-api-phase2 plan's Tasks 1-2 are the first code built against ADR 0023.*

*Last updated: 2026-08-25 — verified against commit `440bad56` (working tree ahead: spec
0012, quiz-flow-api-phase1 plan Task 3); the golden-set labeler section and the
`retrieval_evaluation/` component-table row now say the retrieval judge and comma-labeler
agent YAML load from `IngestorConfig.labeling.agents_dir` (`src/labeling/configs/`), not a
bare `agents_dir` field on `IngestorConfig` — `IngestorConfig.agents_dir` still exists,
but only the quiz-enrichment agents (`quiz_flows.py`) read it now, since their prompts
enter no configuration epoch. See `patterns.md` for the full single-sourcing rationale.*

*Last updated: 2026-08-25 — verified against commit `7005ad3f` (working tree ahead: spec
0012, quiz-flow-api-phase1 plan Task 5). Pure `git mv` sweep completed: the "Golden-set
labeler" section's file-path references and the component table now point at
`labeling/agents/comma_labeler/`, `labeling/services/`, `labeling/repositories/`, and
`labeling/utils/run_provenance.py` instead of `retrieval_evaluation/`'s equivalents;
added a `labeling/` component-table row. `retrieval_evaluation/wiring.py` is trimmed to
one builder, `build_retrieval_judge_agent(agents_dir, provider, tracker)` (renamed from
`build_agent`, reparameterised off a bare `agents_dir: Path` instead of `IngestorConfig`).
The other builders that module used to hold (Postgres client, OpenRouter provider,
tracker, quiz/corpus read repositories, golden-set repository, comma-labeler config/agent)
are not yet in a shared `labeling/wiring.py` — that module doesn't exist yet, Task 6
(builders reparameterisation) hasn't run — so `main.py` and `label_main.py` each carry a
temporary, verbatim-duplicated set of private `_build_*` helpers instead, flagged with a
comment pointing at Task 6 as the resolution. Added
`tests/labeling/test_module_boundary.py` (asserts `labeling/` imports nothing from
`retrieval_evaluation/`, `pywire`, or `guidami_ai_patente/`, and that `domain/` imports
nothing from `labeling/`).*

*Last updated: 2026-08-25 — verified against commit `2a639831` (working tree ahead: spec
0012, quiz-flow-api-phase1 plan Task 6). `labeling/` gained `wiring.py` (manual DI
builders, all reparameterised off `LabelingConfig`/plain values, never `IngestorConfig`/
`AppConfig`); `retrieval_evaluation/main.py` and `label_main.py` now import from it
instead of each carrying its own duplicated `_build_*` helper set, resolving the Task 5
duplication. `label_main.py`'s `labeling_runs` insert is now built via
`LabelingEpochMapper.from_config_to_epoch` + `LabelingRunMapper.from_epoch_to_entity`,
replacing the inline `LabelingRunEntity(...)` stopgap. Both scripts widen their pooled
`PostgresClient`'s `pool_max_size` to `max(config.postgres.pool_max_size, concurrency)`
before building it (D7/D14), so their `--concurrency` fan-out can't starve the pool under
Task 1's bounded `timeout`. `tests/retrieval_evaluation/test_wiring.py` was renamed to
`test_entry_points.py` to free the `test_wiring` basename for the new
`tests/labeling/test_wiring.py` (pytest's default import mode needs a unique module
basename per test file across the whole `tests/` tree, since no directory carries an
`__init__.py`).*

*Last updated: 2026-08-25 — verified against commit `5582529a` (working tree ahead:
spec 0012, quiz-flow-api-phase1 plan Task 10, FR-18). `GoldenSetLabelingService.__init__`
gained `topics: Sequence[str] | None`, positioned after `question_limit` and before the
injected collaborators. `label_all` filters `rows` to the union of `self._topics` (when
set) *before* applying `self._question_limit`, so `--limit N --topic t` selects "N
questions of topic t". `label_main.py` gained a repeatable `--topic` flag
(`action="append"`) passed straight through as `topics=args.topic`; the value is a pure
selection filter and never reaches `labeling_runs` or the judge's configuration epoch.*

*Last updated: 2026-08-26 — verified against commit `0526fe74` (quiz-flow-api-phase2 Task 1). `AppConfig` now embeds the shared `LabelingConfig` as a `labeling` field (single-sourced from the same YAML and env, spec 0012 AD-27), gains `quiz_images_dir` for image access (FR-12, default `Path("data/quiz-images")`), and adds table-name fields for repository parameterization.*

*Last updated: 2026-08-26 — verified against commit `546985b5` (working tree ahead: spec
0012, quiz-flow-api-phase2 plan Task 3). `guidami_ai_patente/clients/` added: the app's
first two `@client` providers, `PostgresClientProvider` and `LabelingStackProvider`
(AD-16). `guidami_ai_patente/repositories/` gained `AgentConfigRepository`, the API's only
door to `agents_dir` and the agent prompt files (AD-22), re-exported from
`repositories/__init__.py`.*

*Last updated: 2026-08-26 — verified against commit `2eab1e35` (working tree ahead: spec
0012, quiz-flow-api-phase2 plan Task 6). `guidami_ai_patente/repositories/` gained
`QuizQuestionRepository`, the API's only reads against `quiz_questions`/
`quiz_question_embeddings` (FR-1/2/3/4/12/16), re-exported from `repositories/__init__.py`
alongside `DependencyVersionRepository` (which was implemented earlier but not yet
re-exported there). See `patterns.md` for the seeded-permutation, absence-handling, and
FR-12 authorization-pattern details.*

*Last updated: 2026-08-26 — verified against commit `ec2cb784` (working tree ahead: spec
0012, quiz-flow-api-phase2 plan Task 7). `guidami_ai_patente/repositories/` gained
`GoldenSetReadRepository` (AD-16b): `find_current_labeling(number) -> CurrentLabeling |
None` implements FR-8's precedence rule entirely in SQL (human-validated always qualifies;
otherwise only a labeling whose run matches the active `LabelingStackProvider.epoch`;
`(validated_at IS NOT NULL) DESC, created_at DESC` picks the winner), and
`distinct_prompt_versions() -> list[str]` feeds the FR-14 startup coherence check.
App-local rather than beside `GoldenSetWriteRepository` in `src/labeling/`, re-exported
from `repositories/__init__.py`. Its dependency on `LabelingStackProvider` is a true
`clients`<->`repositories` package-init cycle that Task 6's direct-submodule-import trick
cannot resolve (the requested class is not a leaf — it is the exact module whose own import
pulls `repositories/__init__.py` in, in the `clients`-first order); resolved instead with a
bare `import guidami_ai_patente.clients as clients` plus a quoted
`Autowired["clients.LabelingStackProvider"]` forward reference, which `pywire` evaluates
lazily against this module's globals only when the container resolves the class — see
ADR 0024 and `patterns.md` for the full mechanism.*

*Last updated: 2026-08-26 — verified against commit `c8da3a25` (quiz-flow-api-phase2 plan Task 12). `guidami_ai_patente/services/` also gained `JudgeCoherenceChecker` (FR-14 startup diagnostic): warns at app startup if this deployment's judge prompt diverges from what the batch labeling recorded, never raises to block startup. See the `guidami_ai_patente/` row above for full details.*

*Last updated: 2026-08-26 — verified against commit `1ca436ca` (quiz-flow-api-phase2 plan Task 13). `api/app.py::create_app` now wires the FR-14 startup check via a `_lifespan` context manager, and registers the app's first two domain routers — `api/routers/quiz_questions.py` (4 routes) and `api/routers/quiz_images.py` (1 route) — exposing the five endpoints described in the `guidami_ai_patente/` row above. New `api/schemas/quiz_check.py` holds `QuizCheckRequest`/`QuizCheckResponse`. This is the first task to expose real, externally-callable REST endpoints beyond `GET /health`.*

*Last updated: 2026-08-26 — verified against commit `dc3a932d` (whole-branch review fix). Corrected a stale claim carried over from the scaffolding stage: the Overview and the `guidami_ai_patente/` component row both still opened with "only `GET /health` implemented so far" / "no domain endpoints yet", even though the same row already went on to describe five live quiz endpoints (Tasks 6-13). No behavior changed — text only.*

*Last updated: 2026-09-01 — verified against commit `51dcba1a`; spec 0013 (labeling/API
dependency-injection cleanup) landed on `feat/quiz-flow-api-phase1`. Rewrote the
`guidami_ai_patente/` component row in five places: (1) `AppConfig` no longer declares a
`labeling` field (FR-1) — `main.py` loads/registers an independent `LabelingConfig`
instance instead; (2) `clients/` holds only `PostgresClientProvider` now, which also
gained a `@pre_destroy` teardown hook (FR-6); `LabelingStackProvider` moved to a new
`providers/` package, decorated `@provider` (FR-2, AD-16 revised — direction-of-dependency
test, not constructor arity); (3) `AgentConfigRepository` autowires `LabelingConfig`
directly, not `AppConfig.labeling` (FR-1); (4) `GoldenSetReadRepository
.find_current_labeling` takes an explicit `epoch` parameter instead of autowiring
`LabelingStackProvider` — ADR 0024's bare-import-plus-quoted-`Autowired` mechanism is gone
from this file, the `clients`<->`repositories` cycle is removed at the root (ADR 0027,
superseding ADR 0024); (5) `ExplanationStatusService`, `QuizAnswerChecker`,
`QuizImageService` are now `UseCase` subclasses invoked via `__call__` (FR-4;
`QuizAnswerChecker` takes the new `QuizAnswerCheckRequest` DTO). No endpoint, response
shape, or persisted behavior changed anywhere in this pass — a pure structural cleanup.*

*Last updated: 2026-09-02 — verified against commit `6f729600` (working tree ahead:
uncommitted, on `feat/quiz-flow-api-phase1`); bumped `pywire` 0.6.0 -> 0.7.0
(`pyproject.toml`'s `[tool.uv.sources]` tag `v0.6.0` -> `v0.7.0`). `api/app.py::create_app`
no longer calls `pywire.fastapi.wire()` (deprecated in 0.7.0 — it binds the container but
never tears it down); `_lifespan` now nests `pywire_lifespan(app)`, which binds
`app.state.pywire_container` at startup and runs `Container.close()` at shutdown (spec
0013 FR-6, same `@pre_destroy` teardown as before). The FR-14 judge-coherence startup
diagnostic, previously inlined in `_lifespan`, is now `_run_judge_coherence_check()`, a
standalone top-level `async def` — `tests/guidami_ai_patente/api/test_app.py` now calls
it directly instead of entering `_lifespan`/`pywire_lifespan`, so the test no longer
binds/closes the real process-wide default container as a side effect. `.claude/rules/
pywire-di.md`'s "FastAPI wiring" section rewritten around `pywire_lifespan`.*

*Last updated: 2026-09-02 — verified against commit `9ae6dbd1`. No code changed; annotated
a known gap surfaced in conversation on the `commons/clients/postgres_client.py` row —
`PostgresClient` has no async variant, so `guidami_ai_patente/` relies on `asyncio.to_thread`
per request (AD-25) instead. A future async `PostgresClient` is a possible enhancement, not
a decision — no ADR was opened for it.*

*Last updated: 2026-09-02 — verified against commit `8d8443e5` (working tree ahead:
uncommitted, on `feat/quiz-flow-api-phase1`); bumped `pywire` 0.7.0 -> 0.8.0
(`[tool.uv.sources]` tag `v0.7.0` -> `v0.8.0`). The release's **sole breaking change** is
the removal of `pywire.fastapi.wire()`, deprecated one release earlier — `pywire.fastapi`
now exports only `pywire_lifespan`, and `from pywire.fastapi import wire` raises
`ImportError`. `Container`'s API is unchanged (`register`, `register_factory`,
`register_instance`, `resolve`, `get`, `clear_instances`, `close`, `as_type=`,
`@pre_destroy`), so no DI mechanism this repo relies on moved. No source change was needed
beyond the pin: `api/app.py::_lifespan` had already migrated to `pywire_lifespan` in the
previous entry, and no `wire()` call existed in `src/` or `tests/` — only a docstring in
`api/app.py::_lifespan` still called `wire()` "deprecated" rather than removed, now
corrected. Verified on 0.8.0: 810 tests passed, `uv run pytest -m integration` green,
`ruff check`/`ruff format --check` clean, `pyright` 0 errors. `adr/0016` is now
`Superseded by ADR 0028` on its Decision item 3 only (items 1, 2, 4 stand); see
`adr/0028-pywire-lifespan-sole-fastapi-wiring-entry-point.md`, which also records the
one real cost of the migration — a `TestClient(app)` used without `with` never runs the
lifespan, so `Autowired[T]` routes fall back to the default container **silently**
(`tests/conftest.py::api_client` is the reference fixture).*

*Last updated: 2026-09-03 — verified against commit `e592b110` (quiz-flow-api-phase3
plan Task 14, close-out). `providers/` now holds three providers over the shared
labeling stack, not two: `LabelingStackProvider` (judge identity only) and a new
`LiveLabelingStackProvider` (the machinery — corpus/quiz/golden-set repositories,
candidate-set service, the built `CommaLabelerAgent`, `QuestionLabelingService`),
plus `OpenRouterProviderComponent` and `LlmCallTrackerProvider` — a deliberate
deviation from AD-16, recorded as a spec errata (D3, `adr/0029`). `labeling/services/`
gained `QuestionLabelingService`, the one shared per-question labeling unit called by
both the batch (`GoldenSetLabelingService`) and the live path (`CommaSelectorService`),
crossing `asyncio.to_thread` internally and resolving the live run id lazily, right
before the write (D8, `adr/0030`). `services/` gained `CommaSelectorService` and
`ExplanationService`; `api/routers/quiz_questions.py` gained
`GET /quiz-questions/{number}/explanation?submitted=` (FR-5/FR-6/FR-7/FR-11/FR-13),
bounded by a new `AppConfig.explanation_deadline_s` (default 25.0s, D10). API-side LLM
call tracking now exists via `LlmCallTrackerProvider`'s `@pre_destroy` hook (D5,
`adr/0031`), closing the gap `labeling.wiring.build_comma_labeler_agent`'s docstring
used to document. Two recorded-but-not-fixed debt items added: `LabelingConfig.yaml_file`
is CWD-relative (D11) and `EMBEDDING_MODEL_COLUMN` is a shared constant pending a
symmetric parameterisation spec (D7) — `ingest reset quiz`'s FK breakage was already
documented in `database.md` before this task.*

*Last updated: 2026-09-16 — verified against commit `68f98012` (working tree ahead:
uncommitted, on `feat/backend`); bumped `pywire` 0.8.0 -> 0.9.0 (`[tool.uv.sources]` tag
`v0.8.0` -> `v0.9.0`). The release adds async-component support: `@async_component`
registers a class that is itself an async context manager (`__aenter__`/`__aexit__`),
entered/exited by the new `Container.astart()`/`aclose()`, composable as `async with
container.lifespan(): ...` for a non-FastAPI async entrypoint — the capability
`adr/0032` (Telegram bot design, spec 0015) documented as absent in v0.8.0.
`Container`'s existing sync API (`register`, `register_instance`, `resolve`, `close`,
`@pre_destroy`) is unchanged, so no source change was needed in `guidami_ai_patente/`,
which uses none of the new async-component API today. Verified on 0.9.0: 78 tests
passed (`tests/guidami_ai_patente`), `ruff check`/`ruff format --check` clean, `pyright`
0 errors. No `guidami_ai_patente_bot/` package exists yet — spec 0015 is still at the
implementation-plan stage (`docs/superpowers/plans/`, gitignored) — so this entry
records only the dependency bump. Once that package lands, `QuizApiClient` is planned
to adopt `@async_component` instead of the manual-`aclose()` workaround `adr/0032`
describes, and that ADR will need marking `Superseded by` the ADR recording the switch.*

*Last updated: 2026-09-16 — verified against commit `1f6c7739` (telegram-bot-client-mvp
plan, Tasks 1-4 committed; Task 5 in progress, uncommitted). `src/guidami_ai_patente_bot/`
now exists and is coupled to `guidami_ai_patente` only over HTTP (AD-1) — no import of
its services/enums/DTOs. Component graph so far: `QuizApiClient` (an async-context-manager
bean, the previous entry's "planned" `@async_component` adoption is now real — see the
2026-09-16/`f53ad73f` entry below for a correction to how it's registered — its
`httpx.AsyncClient` opens in `__aenter__`/closes in `__aexit__`, entered/exited by
`Container.astart()`/`aclose()`) wraps one HTTP method per endpoint shape
(`propose_question`, `download_image`, `check_answer`, `get_explanation`), wrapping
every failure into `QuizApiError`. `QuizFlowService` (a pywire `@service`, `api:
Autowired[QuizApiClient]`) is the only place with orchestration logic: it derives the
chat's `QuizSession` (seed/index/current question — a fresh session gets a new
`uuid4().hex` seed at index 0, an existing one reuses its seed and advances index by
one) and enforces the FR-3 stale-button guard (`StaleQuestionError` before any API call
if the tapped question isn't the chat's current one). `docs/second-brain/database.md`
needs no change: this app has no database of its own, only the FastAPI app's HTTP API.
`adr/0032` still needs marking `Superseded by` a new ADR recording the `@async_component`
switch — not yet done, tracked in the plan's own "After this plan" section, to be run via
`second-brain:adr` once the whole plan lands.*

*Last updated: 2026-09-16 — verified against commit `f53ad73f` (telegram-bot-client-mvp
plan complete: all six tasks plus a final whole-branch-review fix wave). Component graph
finished: `handlers/` (`quiz_handlers.py`, `error_handler.py`) are thin PTB controllers —
parse the update, resolve `QuizFlowService` via
`pywire.get_default_container().resolve(...)` (plain PTB callables aren't FastAPI routes,
so `Autowired`-as-parameter doesn't apply — this confirms spec 0015's AD-8 open question),
call it, render the response, no business logic. `main.py::_run` is the composition root:
loads `BotConfig` once and `register_instance`s it, then calls
`get_default_container().register_async_component(QuizApiClient)` **explicitly**, then
runs `python-telegram-bot`'s manual async lifecycle (`async with application`,
`application.start()`/`updater.start_polling()`, a `try/finally`-guarded
`stop_event.wait()` so `updater.stop()`/`application.stop()` always run before the
`async with` unwinds) inside `container.lifespan()`, all inside one `asyncio.run()`.

The explicit-registration call (rather than decorating `QuizApiClient` with
`@async_component` at class-definition time, which the plan originally specified) was a
**Critical** finding from the final whole-branch review, not visible to any single-task
review: `guidami_ai_patente`'s FastAPI app (`api/app.py`) runs
`FastAPI(lifespan=pywire_lifespan)` against the same process-wide *default* pywire
container `@async_component`/`@service`/etc. all write into. A decorator-time
registration meant merely *importing* `guidami_ai_patente_bot.clients` — which happens
the instant both test trees are collected in the same `uv run pytest` invocation —
registered `QuizApiClient` on that shared container, and the API's own `astart()` then
tried to enter it too, failing to resolve `BotConfig` (which only the bot's own
composition root provides). Fixed by moving registration into `main.py::_run`, so
merely importing the bot package has no side effect on any container it doesn't own.
See `adr/0033-explicit-async-component-registration-for-shared-container.md`, which
supersedes `adr/0032`.

`QuizFlowService.handle_answer` also gained a narrow fallback (a second final-review
finding): if `check_answer` succeeds but the subsequent `get_explanation` call raises
`QuizApiError` — a `503` from that endpoint is a first-class, documented outcome (API
FR-13/AD-20), not a rare failure — the already-computed grade no longer gets discarded.
The method catches `QuizApiError` around the `get_explanation` call only (a
`check_answer` failure still propagates normally, since no grade exists yet) and falls
back to `QuizExplanation(status=ExplanationOutcome.INSUFFICIENT_KNOWLEDGE,
explanation=None)`, reusing the handler's already-correct "no explanation available"
rendering rather than adding a new enum member or changing the method's return shape.

Also fixed: `httpx`'s own INFO-level request logging was printing
`https://api.telegram.org/bot<TOKEN>/...` (the bot token, unmasked) to stdout on every
long-poll request, since `main.py` sets the root logger to INFO —
`logging.getLogger("httpx").setLevel(logging.WARNING)` closes it.

Two items intentionally left open by this plan, tracked for the user rather than fixed
unilaterally (both are spec/process drift, not code defects): spec 0015's AD-5 (closed
package list) and AD-8 (the pre-v0.9.0 async-component workaround) are now stale against
the implemented code — the spec is user-owned, so this needs a human edit, not an
agent one. Separately, most of this plan's commits went through a plain `git commit -m`
rather than this repo's mandated `commit-moji` skill, and several also carry a
`Co-Authored-By` trailer `.claude/rules/commits.md`'s Hard Rules explicitly forbid —
judged not worth a mid-plan history rewrite (would need `git rebase -i`), flagged for the
user's own call instead.*

*Last updated: 2026-09-18 — verified against commit `68575993` (spec 0016, bot user
authorization & answer history — db-schema, backend, and telegram-bot plans, implemented
in sequence on `worktree-bot-auth`). Rewrote the `guidami_ai_patente/` component row: every
route is now gated behind `resolve_identity`/`require_registered_user`
(`api/dependencies/user_identity.py`, plain `Depends()` functions rather than pywire
components — see `patterns.md`), backed by the new `UserRepository`/`UserEntity`
(idempotent provision-then-select against `users`) and `UnregisteredUserError` → `403`;
`GET /me` uses `resolve_identity` alone (reports status, never gates). New
`QuizAnswerRepository` records an answer as a side effect of `POST /{number}/check` and
backs the new `GET /quiz-answers/summary` route (`SessionSummaryService`, the first
`AsyncUseCase` in this package with no synchronous-caller precedent to match, per its own
docstring). On the bot side (`src/guidami_ai_patente_bot/`, no component-table row of its
own — see `layout.md`'s tree comment for the full file list): every `QuizApiClient` call
now attaches an `X-Telegram-User-Id` header and recognizes a `403` as
`exceptions/unauthorized_error.py::UnauthorizedError`; `container.py::resolve` centralizes
resolving pywire components through `Application.bot_data` (mirroring the API's own
`app.state` fallback, see `patterns.md`) instead of each handler calling
`pywire.get_default_container().resolve(...)` directly; `/start` and `/quiz` are now
separate handlers (`/start` only reports registration status, FR-7/FR-8); a new `/stop`
handler ends the session and shows its `SessionSummary` via the new
`QuizApiClient.get_session_summary`; and the global error boundary
(`handlers/error_handler.py`) now shows a friendly message on `UnauthorizedError` instead
of the generic failure text. User-facing bot strings were centralized into a new
`messages.py` module ahead of this work (a small refactor commit, not spec 0016 itself).
Both plans' work landed with **zero deviations from an API contract, auth semantics, or
persisted schema beyond what their plans specified** — the only code-level surprises were
a pywire route-signature ordering constraint and a pre-existing FK-truncate test-fixture
gap the new `quiz_answers` FK exposed, both recorded in `patterns.md`/`testing.md`. Two
items still open, not addressed by this pass: a live end-to-end Telegram verification
(spec 0016's Definition of Done item 4 — requires a human with a running dev stack) and a
possible new ADR (or an addendum to `adr/0033`) for the `Application.bot_data`
container-resolution pattern, which the telegram-bot plan's own text suggested but left
to a later `second-brain:adr` pass.*

*Last updated: 2026-09-18 — verified against commit `9d3397a7` (spec 0017, on-demand
explanation — `docs/superpowers/plans/2026-09-18-on-demand-explanation.md`, Tasks 1-10,
implemented on `worktree-on-demand-explanation`). See the `guidami_ai_patente/` component
row above for the API-side split (`LabelingNotReadyError`/409, `CurrentLabelingReadService`,
`LabelingService`, the new `POST /quiz-questions/{number}/label` route, and the narrowed
`ExplanationService`/`CommaSelectorService` dependency on `reader`). On the bot side
(`src/guidami_ai_patente_bot/`), the answer flow is now two steps instead of one:
`QuizFlowService.handle_answer` no longer fetches an explanation at all — it now returns
only `tuple[bool, ExplanationStatus]` from grading (`QuizApiClient.check_answer`'s own
return type changed from `bool` to that same tuple, mirroring the API's wire vocabulary via
a new `ExplanationStatus` enum in `enums/`: `CACHED`/`UNCACHED`/`UNAVAILABLE`). A separate
new method, `QuizFlowService.handle_explanation_request(number, telegram_user_id,
submitted) -> QuizExplanation`, calls the new `QuizApiClient.label_question` (its own
timeout override, `BotConfig.label_request_timeout_seconds`, 30.0s) then
`get_explanation` in strict sequence, falling back to the existing "insufficient
knowledge" rendering if either call raises `QuizApiError` — the same fallback shape
`handle_answer` used before this split, just relocated. `handlers/` gained
`EXPLAIN_CALLBACK_PREFIX`/`handle_explain_callback` (registered in `main.py`): a "Spiega"
button now appears alongside "Prossima domanda" after a graded answer (omitted when
`ExplanationStatus.UNAVAILABLE`), and tapping it does an optimistic edit — a loading line,
with "Spiega" removed from the keyboard to prevent a double-tap — before the real
explanation replaces the message. Full regression: 957 tests passed (0 failures, 190
integration tests deselected), `ruff check`/`ruff format --check` clean, `pyright` 0
errors. See `patterns.md` for the new "single-responsibility endpoints and the services
they call" convention this split establishes for future endpoint design.*

*Last updated: 2026-09-20 — verified against commit `57f40f5d` (spec 0018 bot UX,
explanation-translator-bot-ux plan, Tasks 1-3 complete on `feat/backend`). On the bot side
(`src/guidami_ai_patente_bot/`), the on-demand explanation flow (spec 0017) gained a
translate-to-Russian step. `QuizApiClient` gained `translate_explanation(telegram_user_id,
text) -> str`, calling `POST /explanations/translate?lang=ru` (the `"ru"` query param is
hardcoded — no language picker exists yet) with its own timeout override
(`BotConfig.translation_request_timeout_seconds`), the same shape `label_question` already
established for an endpoint slower than the client's generic default. `QuizFlowService`
gained `handle_translation_request(text, telegram_user_id) -> str`, a thin passthrough
that — unlike `handle_explanation_request`'s "insufficient knowledge" fallback —
deliberately lets `QuizApiError` propagate: the caller (the new "Traduci" tap handler)
needs to distinguish success from failure to decide between showing the translation and
reverting its optimistic edit. `QuizSession` gained `last_explanation: str | None = None`
— the Italian text last shown by "Spiega", stashed by `handle_explain_callback` only when
the explanation is `EXPLAINED` with non-empty text, and read by the new "Traduci" tap
(a `None` value is treated as its own staleness signal, exactly like a
`current_question_number` mismatch). `handlers/quiz_handlers.py` gained
`TRANSLATE_CALLBACK_PREFIX`/`handle_translate_callback` (registered in `main.py`): a
"🇷🇺 Traduci" button appears alongside "Prossima domanda" whenever `handle_explain_callback`
renders a non-empty explanation. `handle_translate_callback` answers the callback query
*before* the (possibly slow) translation call — see `patterns.md`'s new "one `answer()`
per callback query" row for the full rationale and the failure-revert shape this forces —
then shows a loading line, and on success either extends the message text or, for a photo
message (Telegram's 1024-char caption limit), reverts the caption and sends the
translation as a separate chat message instead. Full regression: 966 tests passed,
`ruff check`/`ruff format --check` clean, `pyright` 0 errors.*

*Last updated: 2026-09-20 — verified against commit `ed51081c` (spec 0018 backend,
explanation-translator plan, Tasks 1-5 on `feat/backend`). API-side counterpart of the
2026-09-20 bot entry above: `POST /explanations/translate?lang=ru` now exists. See the
`guidami_ai_patente/` component row for the mechanism — `ExplanationTranslatorAgent`,
`ExplanationTranslationService`, `require_supported_language` +
`UnsupportedLanguageError` -> `400`, `AppConfig.translation_deadline_s` (20.0s). Its two
failure modes (timeout, agent failure) both reuse `ExplanationUnavailableError` -> `503`
instead of minting a `TranslationUnavailableError`; `patterns.md` records this as a rule.
The endpoint is deliberately stateless with respect to the quiz: it never reads
`quiz_questions`, `quiz_labelings` or any other table, so `database.md` is unchanged.
`uv run ruff check`/`ruff format --check`/`pyright` clean; default `uv run pytest`: 944
passed, 34 errors — every error is the ephemeral test-Postgres fixture failing to start
(Docker not running), not a test failure; the `integration`-marked suite, including the six
router tests in `tests/guidami_ai_patente/api/routers/test_explanation_translations.py`, was
not run in this pass.*

*Last updated: 2026-09-21 — verified against commit `61c290f1` (bot UX pass on
`feat/backend`, after the first live Telegram run). `GET /quiz-answers/summary` now returns
`by_topic` (per-topic answered/correct, ordered by topic) and `wrong_questions` (each wrongly
answered question once, in first-miss order) next to `answered`/`correct` — additive fields,
no schema change; the bot mirrors them (`models/topic_summary.py`, `wrong_question.py`) and
renders `/stop` through `messages.summary_message` as plain text (no `parse_mode`, since the
embedded question texts are free-form). Official topic names run to 330 chars, so the bot
keeps only the first `;` clause, cut at 40; at most five wrong questions are listed. Bot
flow changes: the answer edit now appends the outcome to the question instead of replacing
it; `/quiz` sends an intro message only when no session exists yet (a resumed session goes
straight to its pending question); `/start` lists the commands. Bot and API must be deployed
together — a bot parsing the new summary against an old API fails validation on the missing
fields. The first live end-to-end Telegram run (spec 0016's Definition of Done item 4, still
open above) surfaced that the dev DB predated spec 0016's `users`/`quiz_answers` DDL:
`db/init.sql` only runs on a fresh volume, so an existing dev volume needs those tables
applied by hand.*

*Last updated: 2026-09-23 — verified against commit `ac86ab52` (spec 0018 amendment,
FR-8/AD-9, explanation-translator-hints plan, Tasks 1-5 plus one final-review fix wave, via
`superpowers:subagent-driven-development` in an isolated worktree). `POST
/explanations/translate?lang=ru` gains an optional `hints: list[{term, term_ru}]` field (max
10 entries, each field max 80 chars) letting a caller anchor a specific Italian term to an
already-reviewed Russian rendering instead of leaving `ExplanationTranslatorAgent` to infer it
fresh every call. Two new domain models in `guidami_ai_patente/models/`: `TranslationHint`
(frozen, `term`/`term_ru`, blank/whitespace-only and control-character values rejected, valid
values stripped) and `TranslationRequest` (the translation `UseCase`'s new input —
`ExplanationTranslationService.execute` now takes it instead of a bare `str` — `text` plus
`hints`, rejecting two hints that share the same `term` case-insensitively). The wire schema
(`api/schemas/explanation_translation.py`'s `TranslationHintRequest`/
`ExplanationTranslationRequest`) duplicates both the blank/control-char and duplicate-term
validators rather than delegating to `TranslationRequest`'s own: `TranslationRequest` itself
has no length/duplicate guard, so without the wire-layer duplication a bad request would only
fail deep inside the router's `TranslationRequest(...)` construction as an unhandled `500`,
not a clean `422` (`patterns.md` records the general rule). A request with no `hints` is
byte-identical to before this amendment on the ENTIRE rendered prompt, not just the user
template: `ExplanationTranslatorRequest.hints_block` (a `@computed_field`) is `""` when empty
and, when non-empty, carries the *entire* hint-honoring instruction itself (term list,
grammatical-inflection guidance, first-occurrence «TERMINE» (resa) formatting) — the static
`system:` block in `configs/agents/explanation_translator.yaml` was deliberately kept free of
any hint-conditional text so it never changes per-request, hints or not. Full regression:
default suite 1025 passed, integration suite 205 passed/2 skipped (pre-existing
Docker-dependent skips), `ruff check`/`ruff format --check`/`pyright` all clean.*

*Last updated: 2026-09-23 — verified against the final whole-branch review's fix wave
(spec 0020, question vocabulary explanation, 11 tasks plus a fix round, one
full-suite/smoke-test pass, and a final review fix wave, via
`superpowers:subagent-driven-development` in an isolated worktree). `GET
/quiz-questions/{number}/explanation` now runs two independent LLM stages concurrently
via `asyncio.TaskGroup` (not `asyncio.gather` — the fix wave replaced it specifically so
a legal-stage failure actually cancels the still-running vocabulary task, which `gather`
does not do on its own) instead of one: the unchanged spec-0017 legal-explanation path,
and a new answer-blind vocabulary stage (`QuestionExplainerAgent` +
`GlossaryReadRepository`, new `glossary_entries` table) that degrades to `(None, ())` on
any failure — including its own inner-timeout expiry — without ever affecting the legal
stage. See the `guidami_ai_patente/` component row above for the full detail and
`patterns.md` for the RRF-in-SQL retrieval and the second/third `output_validator`
occupants. Full regression, re-run after the fix wave: default suite (`uv run pytest`,
excludes `integration`-marked tests per `pyproject.toml`'s `addopts = "-m 'not
integration'"`) 1063 passed; integration suite (`uv run pytest -m integration`, separate
Docker-backed Postgres stack) 217 passed, 0 failed, 2 skipped (pre-existing
Docker-dependent skips) — the two counts are reported separately here because an earlier
version of this entry incorrectly described the default-suite count alone as "including"
the integration suite. `ruff`/`pyright` both clean. The Task 11 real-model smoke test
(prior to the fix wave, still valid) confirmed both a matching-glossary-term case and a
clean no-match case (legal stage refused, vocabulary stage still returned a real
sentence) work end to end.*
