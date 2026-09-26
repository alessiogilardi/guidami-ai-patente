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
│   │                                #   observability/: LlmCallTracker port (context mgr) +
│   │                                #   utils/: domain-agnostic retrieval algorithms
│   │                                #   (reciprocal_rank_fusion) — spec 0008 Phase 2, AD-3;
│   │                                #   adapters/entities/enums/configs/services/repositories/models);
│   │                                #   observability/: two self-contained sub-packages,
│   │                                #   progress_reporter/ (ItemProgressReporter/ProgressReporter
│   │                                #   port + NullProgressReporter) and run_artifact_writer/
│   │                                #   (RunArtifactWriter + models/: RunManifest base,
│   │                                #   ScrapeManifest; RunArtifactWriterConfig removed);
│   │                                #   sibling of ai/observability/, not AI-specific
│   ├── domain/                     # Shared domain entities/models/enums/validators (persisted +
│   │                                #   intermediate), models/retrieval/: read DTOs (RetrievedComma,
│   │                                #   QuizEvaluationRow) — carry `id`, unlike entities;
│   │                                #   entities/: knowledge/, quiz/, evaluation/
│   │                                #   (LabelingRunEntity, QuizLabelingEntity,
│   │                                #   QuizCommaLabelEntity — spec 0011 phase 2), users/
│   │                                #   (UserEntity — spec 0016);
│   │                                #   entities/observability/ removed — LlmCallLogEntity
│   │                                #   moved into commons/ai/observability/entities/;
│   │                                #   enums/: closed vocabularies, e.g. LexemeField,
│   │                                #   LabelingRunOrigin (spec 0012, AD-8);
│   │                                #   validators/: shared invariant-check functions reused
│   │                                #   across entities (require_canonical_lexeme_fields — spec
│   │                                #   0012, D8/D13; new package, first occupant); domain/ never
│   │                                #   imports labeling/, so shared logic that labeling/ also
│   │                                #   needs lives here, not there (guarded by
│   │                                #   tests/labeling/test_module_boundary.py, spec 0012, Task 5);
│   │                                #   no I/O or business logic
│   ├── guidami_ai_patente_ingestor/ # Batch ingestion app: prepares + indexes the
│   │                                #   normative corpus (CdS/CAP/Regolamento) and quiz bank
│   ├── guidami_ai_patente/         # FastAPI quiz-bot app — serves the full quiz loop
│   │                                #   (topics, propose/fetch a question, check an
│   │                                #   answer, fetch its image, explain the correct
│   │                                #   answer — spec 0012 phase 3). api/ (self-contained web
│   │                                #   layer: app.py factory, routers/, schemas/) →
│   │                                #   services/ / repositories/ / models/ / mappers/
│   │                                #   (empty, pull-based) → configs/ (AppConfig); enums/ (closed
│   │                                #   vocabularies: ExplanationStatus, InsufficientKnowledgeReason
│   │                                #   — spec 0012, Task 5). As of
│   │                                #   quiz-flow-api-phase2 Task 3, clients/ held the app's
│   │                                #   first two `@client` providers; since spec 0013 FR-2,
│   │                                #   clients/ holds only PostgresClientProvider (wraps
│   │                                #   commons/ PostgresClient via
│   │                                #   labeling.wiring.build_postgres_client — its placement
│   │                                #   here is temporary, pending commons/ adopting pywire).
│   │                                #   New sibling package providers/ holds three
│   │                                #   providers (spec 0012 phase 3, D3): LabelingStackProvider
│   │                                #   (judge identity only — loads comma_labeler.yaml through
│   │                                #   AgentConfigRepository, derives the LabelingEpoch via
│   │                                #   LabelingEpochMapper), LiveLabelingStackProvider (the
│   │                                #   live judge machinery — see adr/0029), and
│   │                                #   OpenRouterProviderComponent + LlmCallTrackerProvider
│   │                                #   (D5, adr/0031); all decorated @provider — the revised
│   │                                #   AD-16 test is direction-of-dependency, not constructor
│   │                                #   arity, see .claude/rules/pywire-di.md; repositories/ gains
│   │                                #   AgentConfigRepository, the
│   │                                #   API's only door to `agents_dir` and the agent prompt
│   │                                #   files (AD-22), now re-exported from
│   │                                #   repositories/__init__.py. Since spec 0016, also
│   │                                #   UserRepository (users whitelist, provision-then-select)
│   │                                #   and QuizAnswerRepository (quiz_answers write + session
│   │                                #   summary read). New api/dependencies/ package
│   │                                #   (user_identity.py: resolve_identity/
│   │                                #   require_registered_user, plain Depends() functions, not
│   │                                #   pywire components — see patterns.md) gates every
│   │                                #   business route; exceptions/ gained
│   │                                #   unregistered_user_error.py -> 403. Eleven live endpoints:
│   │                                #   GET /health, GET /me, seven quiz-domain routes (topics,
│   │                                #   propose/fetch a question, check an answer, ensure a
│   │                                #   labeling, fetch its image, explain the correct answer —
│   │                                #   see architecture.md for the full list),
│   │                                #   GET /quiz-answers/summary, and (spec 0018)
│   │                                #   POST /explanations/translate — one route in
│   │                                #   api/routers/explanation_translations.py, backed by
│   │                                #   agents/explanation_translator/,
│   │                                #   services/explanation_translation_service.py,
│   │                                #   api/dependencies/language.py and
│   │                                #   exceptions/unsupported_language_error.py -> 400.
│   │                                #   Since spec 0021, first utils/ package in this app
│   │                                #   (merge_glossary_candidates.py — pure, standalone
│   │                                #   merge function, no injected dependency, mirroring
│   │                                #   the ingestor's utils/ precedent); enums/ gained
│   │                                #   GlossaryTermOrigin; agents/ gained
│   │                                #   glossary_enricher/ (GlossaryEnricherAgent + dto/),
│   │                                #   an answer-blind live agent grounded on
│   │                                #   LiveLabelingStackProvider's retrieval stack.
│   │                                #   Entry point:
│   │                                #   `guidami_ai_patente.main:main`, registered as the
│   │                                #   `serve` script
│   ├── guidami_ai_patente_bot/     # Telegram bot client (spec 0015) — drives propose →
│   │                                #   answer → explanation against the already-live
│   │                                #   guidami_ai_patente FastAPI app, coupled to it only
│   │                                #   over HTTP (AD-1), never a Python import of its
│   │                                #   services/enums/DTOs. Package-per-role, same pywire
│   │                                #   posture as guidami_ai_patente/ (ADR 0032 extended
│   │                                #   pywire's scope to this app): configs/ (BotConfig,
│   │                                #   root BaseSettings, loaded once in main.py),
│   │                                #   enums/ (ExplanationOutcome, mirroring the API's wire
│   │                                #   vocabulary), models/ (QuizQuestion, QuizExplanation —
│   │                                #   both independent DTOs, not imports of the API's own
│   │                                #   schemas; QuizSession, the per-chat state kept in
│   │                                #   context.user_data for the process lifetime, AD-2),
│   │                                #   exceptions/ (QuizApiError, StaleQuestionError,
│   │                                #   UnauthorizedError — spec 0016, raised by QuizApiClient
│   │                                #   on a 403), messages.py (centralized user-facing
│   │                                #   strings, spec 0016), container.py (resolve(context,
│   │                                #   service_type): resolves a pywire component through
│   │                                #   Application.bot_data, mirroring the API's own
│   │                                #   app.state fallback — see patterns.md; replaces every
│   │                                #   handler's own pywire.get_default_container().resolve(...) call),
│   │                                #   clients/ (QuizApiClient, an async-context-manager bean —
│   │                                #   pywire>=0.9.0's register_async_component() — wrapping
│   │                                #   one httpx.AsyncClient, entered/exited by
│   │                                #   Container.astart()/aclose() via container.lifespan().
│   │                                #   Registered explicitly from main.py::_run, NOT via the
│   │                                #   @async_component class decorator: guidami_ai_patente's
│   │                                #   FastAPI app shares the same process-wide default pywire
│   │                                #   container, and a decorator-time registration would make
│   │                                #   its own astart() try to enter QuizApiClient too, failing
│   │                                #   to resolve BotConfig — superseding ADR 0032's original
│   │                                #   v0.8.0-era hand-called-aclose() workaround, see ADR 0033),
│   │                                #   services/ (QuizFlowService, the only place with
│   │                                #   orchestration logic — derives QuizSession, enforces the
│   │                                #   FR-3 stale-button guard, and falls back to an
│   │                                #   "insufficient knowledge"-shaped QuizExplanation if the
│   │                                #   explanation fetch itself fails after a successful grade,
│   │                                #   so a transient API error never strands an already-graded
│   │                                #   answer), handlers/ (python-telegram-bot controllers —
│   │                                #   parse the update, call QuizFlowService, render the
│   │                                #   response; resolve components via container.resolve(...)
│   │                                #   rather than Autowired-as-parameter, since plain-callable
│   │                                #   PTB handlers are not FastAPI routes. Since spec 0016,
│   │                                #   /start (start_command, reports registration status
│   │                                #   only) and /quiz (quiz_command) are separate handlers —
│   │                                #   previously one combined start_or_quiz; a new
│   │                                #   stop_command backs /stop, ending the session and
│   │                                #   showing its SessionSummary (totals, per-topic rows, wrong
│   │                                #   questions; rendered as plain text by
│   │                                #   messages.summary_message; models/ mirrors it with
│   │                                #   TopicSummary/WrongQuestion), never clearing the session
│   │                                #   on a failed summary call, D-16). Entry point:
│   │                                #   `guidami_ai_patente_bot.main:main`, registered as the
│   │                                #   `telegram-bot` script; long polling only, no webhook
│   │                                #   (AD-3); no ConversationHandler, plain handlers +
│   │                                #   context.user_data (AD-4); no persistence across
│   │                                #   restarts (AD-2, Non-Goals)
│   ├── glossary/                   # Standalone package (spec 0019): Italian legal-definitions
│   │                                #   glossary. Imports only commons/domain (AD-1); pywire
│   │                                #   field injection throughout (AD-1a), a narrow exception
│   │                                #   to this repo's batch-package constructor-DI default —
│   │                                #   see .claude/rules/pywire-di.md. configs/ (GlossaryConfig,
│   │                                #   GlossaryBlockConfig) → repositories/ (block/entry/term
│   │                                #   read+write, GlossaryAgentConfigRepository shared by both
│   │                                #   agents) → services/ (GlossaryExtractionService,
│   │                                #   GlossaryBuildService, GlossaryTermTranslationService,
│   │                                #   GlossaryTermTranslationRunService) → utils/ (chunking.py's
│   │                                #   split_into_chunks + entry_markers.py's shared marker
│   │                                #   regexes and count_expected_entries/is_abrogated/
│   │                                #   is_cross_reference + normalization.py's normalize_term/
│   │                                #   capitalize_definition, all stateless, domain-specific
│   │                                #   pure-function modules — same placement rationale as
│   │                                #   guidami_ai_patente_ingestor/utils/comma_repeal_detector.py)
│   │                                #   → agents/
│   │                                #   (GlossaryExtractorAgent, GlossaryTermTranslatorAgent) →
│   │                                #   mappers/ (GlossaryEntryMapper, static) → models/ →
│   │                                #   exceptions/ → wiring.py (builder functions for the
│   │                                #   commons primitives pywire has no recipe for) → main.py /
│   │                                #   translate_main.py, the two `[project.scripts]` entry
│   │                                #   points (build-glossary, translate-glossary-terms). See
│   │                                #   docs/second-brain/architecture.md's `glossary/` row for
│   │                                #   the full component breakdown
│   ├── html_viewers/               # Standalone, dependency-free HTML pages for manually
│   │                                #   inspecting pipeline output (e.g. quiz enrichment
│   │                                #   review); opened directly in a browser, no server
│   ├── labeling/                   # Shared labeling/judge stack (spec 0012, AD-12), split
│   │                                #   out of retrieval_evaluation/ so both the batch harness
│   │                                #   and the future FastAPI app can depend on it without the
│   │                                #   app pulling in a standalone script's entry point. Manual
│   │                                #   constructor injection only, no pywire (ADR 0015), and
│   │                                #   every component stays synchronous (AD-25); guarded by
│   │                                #   tests/labeling/test_module_boundary.py (no import of
│   │                                #   retrieval_evaluation/, pywire, or guidami_ai_patente/).
│   │                                #   As of Task 5 of the quiz-flow-api-phase1 plan it holds
│   │                                #   the full judge stack, all moved from retrieval_evaluation/
│   │                                #   by `git mv`: agents/comma_labeler/ (CommaLabelerAgent +
│   │                                #   its dto/), models/ (CandidateComma, LabelingEpoch),
│   │                                #   services/ (CandidateSetService, GoldenSetLabelingService,
│   │                                #   QuestionLabelingService — the shared per-question unit,
│   │                                #   spec 0012 phase 3, adr/0030 — QuestionLexemeService),
│   │                                #   constants.py (EMBEDDING_MODEL_COLUMN), repositories/
│   │                                #   (GoldenSetWriteRepository, insert-only), exceptions/
│   │                                #   (CandidateNumberOutOfRangeError), utils/ (corpus_commit,
│   │                                #   prompt_version — run provenance), configs/ (LabelingConfig,
│   │                                #   a BaseSettings reading configs/labeling.yaml), and mappers/
│   │                                #   (LabelingEpochMapper.from_config_to_epoch — the one place
│   │                                #   lexeme_fields is sorted — and LabelingRunMapper.
│   │                                #   from_epoch_to_entity). As of Task 6 it also holds wiring.py:
│   │                                #   manual DI builders for this stack's collaborators
│   │                                #   (build_open_router_provider, build_postgres_client,
│   │                                #   build_tracker, build_corpus_repository,
│   │                                #   build_quiz_repository, build_golden_set_repository,
│   │                                #   build_comma_labeler_config, build_comma_labeler_agent —
│   │                                #   its tracker param is optional, no request-scoped owner
│   │                                #   for a QueuedLlmCallTracker's background lifecycle —
│   │                                #   build_question_lexeme_service, build_candidate_set_service),
│   │                                #   every parameter LabelingConfig/plain values, never
│   │                                #   IngestorConfig/AppConfig; retrieval_evaluation/main.py and
│   │                                #   label_main.py import from it instead of duplicating their
│   │                                #   own _build_* helpers (resolving the Task 5 duplication)
│   ├── parsers/                    # Standalone script: quiz PDF -> data/parsed/
│   ├── retrieval_evaluation/       # Standalone scripts over the same corpus, two entry points:
│   │                                #   evaluate-retrieval-judge — LLM-as-judge spot-check,
│   │                                #   samples quiz questions, judges whether their top-k
│   │                                #   retrieved commas justify the answer, writes nothing (ADR 0013);
│   │                                #   label-golden-set — persists a labeled golden set to Postgres
│   │                                #   (labeling_runs/quiz_labelings/quiz_comma_labels). Since
│   │                                #   Task 5 this package holds only agents/retrieval_judge/,
│   │                                #   models/retrieval_judge_item_result.py,
│   │                                #   services/retrieval_judge_evaluation_service.py, main.py,
│   │                                #   label_main.py, and a wiring.py trimmed to one builder,
│   │                                #   build_retrieval_judge_agent(agents_dir, provider, tracker)
│   │                                #   (renamed from build_agent, reparameterised off a bare
│   │                                #   agents_dir: Path). Everything comma-labeler/golden-set
│   │                                #   related (agents/comma_labeler/, repositories/, exceptions/,
│   │                                #   utils/) moved out to labeling/ — see above. Since Task 6,
│   │                                #   main.py and label_main.py import every other builder they
│   │                                #   need from labeling/wiring.py instead of each duplicating a
│   │                                #   private _build_* set; both widen their pooled
│   │                                #   PostgresClient's pool_max_size to
│   │                                #   max(config.postgres.pool_max_size, concurrency) before
│   │                                #   building it (D7/D14)
│   ├── scrapers/                   # Standalone script: normattiva.it -> data/raw/ + data/parsed/
│   └── test_data_sampler/          # Standalone script: data/parsed/ -> a random subset in
│                                    #   data/test-data/parsed/, plus the sampled quiz
│                                    #   subset's already-enriched files copied from
│                                    #   data/enriched/ into data/test-data/enriched/
│                                    #   (no LLM call — same C901-exempt tier as parsers/scrapers)
├── tests/                          # Mirrors src/ structure, no __init__.py per directory
│   ├── commons/
│   ├── domain/
│   ├── glossary/
│   ├── guidami_ai_patente_ingestor/
│   └── labeling/
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
├── docs/                           # This documentation (Second Brain) + docs/superpowers/ (SDD state)
└── .claude/                        # Claude Code config: rules/, skills/, hooks/, agents/
```

Every top-level `src/` package that is a `[project.scripts]` entry point or an
app (`guidami_ai_patente_ingestor/`, `guidami_ai_patente/`, `parsers/`,
`retrieval_evaluation/`, `scrapers/`, `test_data_sampler/`) carries an empty
`py.typed` marker file (PEP 561), so `pyright` treats the package as typed
when resolved via its installed distribution rather than by path.
`commons/`, `domain/`, and `html_viewers/` don't need one: they're never
imported as a standalone installed package outside this repo's own checkout.

`docker/.volumes/` (gitignored, not shown in the tree above) holds the
Postgres data directory bind-mounted by `docker/docker-compose.yml` — see
`docs/second-brain/database.md`.

`flowstep` (`Flow`, `Step`, `FlowBuilder`, `FlowContext`, `ApplyStep`) is
**not** part of this repo's tree: it's an external git dependency
(github.com/alessiogilardi/flowstep, tracked via `main` in `pyproject.toml`'s
`[tool.uv.sources]`) — see `docs/second-brain/architecture.md`.

`docs/superpowers/` (superpowers plugin, not shown in the tree above — it's SDD
pipeline state, not app code; superseded the removed claude-planner plugin's
`specs/`/`plans/`) holds three kinds of file with different lifetimes:
`docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` are the permanent spec
contracts (written by the `brainstorming` skill's architectural path), tracked
normally; `docs/superpowers/specs/discussions/*.md` are ephemeral brainstorm logs,
gitignored — never committed, safe to delete once the spec they fed is `implemented`;
`docs/superpowers/plans/YYYY-MM-DD-<feature>[-phaseN]-plan.md` are implementation
plans (written by the `writing-plans` skill), also gitignored — pruned once
implemented.

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
  a read model does the opposite and carries `id`. `RetrievedComma` was the standing
  exception to that rule until spec 0011 FR-3; it now carries the `article_commas.id` of
  the row it was read from, as a required field with no default, so a consumer can
  reference that row without a second lookup keyed on the `citation` string.
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
  `embedding/` follows the original five-subpackage-by-responsibility
  shape: `protocols/` (genuine cross-package ports only — e.g.
  `TextComposer[T]`/`OptionalTextComposer[T]`), `services/`,
  `repositories/`, `mappers/` (stateless object-to-object transformations),
  and `models/` (intermediate DTOs consumed only by that package's own
  mappers) — using only the subset relevant to its own responsibility
  (`configs/` instead of a data-access/mapper shape, since it owns no
  persistence; `clients/` instead of `repositories/`, since embedding's
  external dependency is an API client, not a database), plus a
  **sixth**, domain-specific subpackage beyond that shape — `composition/`
  (`FieldSpecComposer[T]`, implementing `OptionalTextComposer[T]`;
  `TemplateComposer[T]`/`CallableComposer[T]`, implementing
  `TextComposer[T]`) — for classes that compose a model into text but
  aren't services (no `UseCase`/injected-dependency-with-behavior shape)
  or classic static mappers (they hold config injected at construction,
  unlike this repo's stateless `*Mapper` convention — see
  `docs/second-brain/patterns.md`); the five-subpackage template already
  anticipates a package using only the subset relevant to its own
  responsibility, so one extra, narrowly scoped subpackage for a
  responsibility the template doesn't name is an extension of that
  principle, not a violation of it.

  `observability/` no longer follows that template: the simplification
  that removed `mappers/`, `models/llm_call_capture_model.py`, and the
  private `services/protocols/` sink port (see `docs/second-brain/patterns.md`
  and `adr/0025-context-manager-tracker-port.md`) replaced it with a shape
  built around a **stateful adapter** rather than a stateless mapper.
  Today: `protocols/` (two genuine cross-package ports, both public now —
  `LlmCallTracker`, a context manager `BaseAgent` depends on, and
  `LlmCallLogRepository`, the sink port `QueuedLlmCallTracker` depends on;
  the narrow private `protocols/` that used to nest *inside* `services/`
  for the sink port is gone along with the port it typed), `adapters/`
  (`PydanticAILlmCallRecorder` — a **stateful** translation from
  pydantic_ai's own result/message types to `LlmCallLogEntity`, built
  fresh per call; see `.claude/rules/code-conventions.md`'s `adapters/`
  package-naming convention for why it lives here rather than in
  `services/` — chiefly, to avoid a `protocols/` ↔ `services/` import
  cycle, since `protocols/` needs the recorder's type and `services/`
  needs the ports), `services/` (`NullLlmCallTracker`,
  `QueuedLlmCallTracker` — the concrete `LlmCallTracker` implementations),
  `repositories/` (`PostgresLlmCallLogRepository`, table name now a
  constructor argument), `entities/` (`LlmCallLogEntity`, moved in from
  `domain/entities/observability/` — the module's own persisted row shape
  now lives with the rest of the module, so it stays removable in one
  piece), `enums/` (`TrackerBackend`), `configs/` (`ObservabilityConfig`,
  a self-loading `commons.configs.BaseConfig` subclass — see the
  `commons/configs/` bullet in `docs/second-brain/architecture.md`),
  `models/` (`TrackedCaller`, the per-agent-lifetime identity
  `BaseAgent.__init__` builds once and passes by reference on every call
  — no longer an intermediate DTO consumed only by a mapper, since there
  is no mapper left), and a package-root `tracker_factory.py`
  (`build_llm_call_tracker`, a `@contextmanager` composition-root
  factory, replacing the duplicated `build_tracker` helper that used to
  live separately in `cli/wiring.py` and `retrieval_evaluation/wiring.py`).
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
  also be AI-related); see `docs/second-brain/patterns.md` for both shapes.
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
  the same way `IngestorConfig` does. `models/` is filled in pull-based as
  with `domain/entities/` elsewhere in this repo. `mappers/` (spec 0012
  quiz-flow-api-phase2 plan Task 10) holds its first occupant,
  `QuizQuestionMapper` (`mappers/quiz_question_mapper.py`), a static mapper
  in the same style as the ingestor's `mappers/` package, alongside the
  module-level `QUIZ_IMAGE_URL_PREFIX` constant it declares — re-exported
  from `mappers/__init__.py`; the FR-12 images router (a later task)
  imports the constant from there instead of duplicating the literal.
  `api/schemas/` gained its first non-`health` DTOs in the same task:
  `quiz_question.py::QuizQuestionResponse` and
  `quiz_topics.py::{QuizTopicResponse, QuizTopicsResponse}`, neither
  re-exported from `api/schemas/__init__.py` — routers import them
  directly from their module, matching `api_error.py`/`health.py`.
  `services/` and `repositories/` gained their first real, non-domain
  classes —
  `repositories/dependency_version_repository.py::DependencyVersionRepository`
  and `services/health_check_service.py::HealthCheckService` — wired into
  `GET /health` (see `docs/architecture.md` and
  `adr/0016-pywire-native-fastapi-wiring.md`) — no `orchestrators/` package
  yet, since that role is for batch-pipeline flows, not a synchronous
  request/response service. The only concrete vertical slice so far is
  `GET /health`, proving the wiring end-to-end; it carries no business
  logic. Entry point: `main.py::main` (loads `AppConfig`, builds the app via
  `create_app`, serves it with `uvicorn`), registered as the `serve`
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
  config or new query code. A second entry point,
  `label-golden-set` (`label_main.py`), was added alongside it in the same
  package (spec 0011 phase 2) rather than as a new top-level module or as a
  mode of the judge script: FR-12 requires a distinct `CommaLabelerAgent`
  (own DTOs, own prompt file) but the same lightweight, no-manifest shape.
  It originally introduced `retrieval_evaluation/repositories/` for
  `GoldenSetWriteRepository` — insert-only, `INSERT` statements only, no
  `UPDATE`/`DELETE`/DDL (AD-10). Since spec 0012 Task 5, `GoldenSetWriteRepository`
  and the rest of the golden-set/comma-labeler stack live in `src/labeling/` instead
  (see the next bullet); `retrieval_evaluation/` keeps only what stays specific to
  the two standalone scripts (`agents/retrieval_judge/`, `main.py`, `label_main.py`,
  `services/retrieval_judge_evaluation_service.py`, and a `wiring.py` trimmed to the
  retrieval-judge builder). Since Task 6 of the same plan, both scripts import their
  Postgres/OpenRouter/repository/service builders from the new `labeling/wiring.py`
  instead of each duplicating its own private `_build_*` helpers, and both widen the
  `PostgresClient` they build from `config.postgres.model_copy(update={"pool_max_size":
  max(config.postgres.pool_max_size, concurrency)})` before opening it — D7/D14, so
  the `--concurrency` tasks each script fans out over one pooled connection can't
  starve each other under Task 1's bounded `timeout`.
- **Code shared by the batch labeling harness and the future FastAPI app's live
  judge** (spec 0012, AD-12) goes in `src/labeling/`, a new top-level package sibling
  to `retrieval_evaluation/`: manual constructor injection only, no `pywire` import
  anywhere in it (ADR 0015), and every component stays synchronous, since the API
  calls it via `asyncio.to_thread` rather than an async duplicate (AD-25).
  `labeling/configs/labeling_config.py::LabelingConfig` (moved out of
  `guidami_ai_patente_ingestor/configs/`, Task 3 of the quiz-flow-api-phase1 plan) was
  its first occupant; as of Task 5 (same plan) it holds the full judge stack, moved
  from `retrieval_evaluation/` by `git mv`: `CommaLabelerAgent`, `CandidateSetService`,
  `QuestionLexemeService`, `GoldenSetWriteRepository`, `CandidateComma`,
  `CandidateNumberOutOfRangeError`, and `corpus_commit`/`prompt_version`, alongside
  `LabelingEpoch` and its mappers (Task 4). `evaluate-retrieval-judge`
  and `label-golden-set` (`retrieval_evaluation/`) keep depending on `labeling/` rather
  than the reverse — the standalone scripts are consumers of the shared stack, not its
  owner; `tests/labeling/test_module_boundary.py` enforces this both ways (`labeling/`
  imports nothing from `retrieval_evaluation/`, `pywire`, or `guidami_ai_patente/`;
  `domain/` imports nothing from `labeling/`). As of Task 6, `labeling/` also holds
  `wiring.py`: manual DI builders for every collaborator this stack needs (Postgres
  client, OpenRouter provider, tracker, corpus/quiz read repositories, golden-set write
  repository, comma-labeler config/agent, question-lexeme service, candidate-set
  service), each parameterised on `LabelingConfig` and/or plain values — never on
  `IngestorConfig`/`AppConfig` — so both the batch scripts and the future FastAPI app
  can drive them without either package importing the other's root config
  (`tests/labeling/test_wiring.py::test_no_builder_takes_an_ingestor_config` asserts
  this by inspecting every builder's signature). `retrieval_evaluation/main.py` and
  `label_main.py` both import from it now, resolving the temporary `_build_*`
  duplication Task 5 introduced.
- **A field two config roots must never resolve differently** (e.g. `agents_dir`,
  which both `IngestorConfig` and `LabelingConfig` need because
  `guidami_ai_patente_ingestor/orchestrators/quiz_flows.py`'s quiz-enrichment agents
  and `labeling/`'s judge agent load from the same kind of directory but for
  unrelated reasons — the judge's prompt hash **is** its configuration epoch,
  spec 0012 AD-22, while the enrichment agents' prompts enter no epoch at all) is
  declared **on both roots**, each field defaultless and aliased to the *same* single
  environment variable (`Field(validation_alias=AliasChoices("AGENTS_DIR",
  "agents_dir"))` on both `IngestorConfig.agents_dir` and
  `LabelingConfig.agents_dir`). The single-source guarantee comes from the one
  defaultless env var every root reads, not from collapsing the two fields into one
  shared field or a shared default — collapsing them would force one of the two
  unrelated readers to import the other's config package just to find a directory
  path. `ingest status` cross-checks the two resolved values and reports a `BLOCKED`
  readiness row (`command="config", entity="agents_dir"`) if they ever disagree — see
  `StatusInspector._agents_dir_agreement_readiness` in
  `guidami_ai_patente_ingestor/cli/services/status/status_inspector.py`.
- **Telegram-bot-only components** (new handlers, session-flow logic, HTTP
  adapters to `guidami_ai_patente`) go under `src/guidami_ai_patente_bot/`,
  following AD-5's fixed package set: `configs/`, `enums/`, `models/`,
  `exceptions/`, `clients/`, `services/`, `handlers/` — no other top-level
  subpackage. `enums/` is not in AD-5's own closed-list prose (spec 0015) but
  the plan that first populated it (`docs/superpowers/plans/2026-09-16-telegram-bot-client-mvp.md`,
  Task 2) creates it anyway, per the project-wide `.claude/rules/code-conventions.md`
  "enums get their own package" rule, which is more specific and takes
  precedence — AD-5's prose is stale on this point and should be corrected to
  list `enums/` explicitly. The bot never imports `guidami_ai_patente`'s
  services/enums/DTOs (AD-1): every bot-side model/enum is declared
  independently even when it mirrors a wire shape 1:1.
- **Code specific to the Italian legal-definitions glossary** (extraction, translation,
  anything that reads/writes `glossary_entries`) goes in `src/glossary/`, a standalone
  package sibling to `labeling/`/`retrieval_evaluation/`: imports only `commons`/`domain`
  (AD-1), never `guidami_ai_patente_ingestor`/`labeling`/`guidami_ai_patente`/the bot. Unlike
  every other batch-pipeline/standalone-script package in this tree, it is wired with
  `pywire` field injection (`Autowired[T]`), not manual constructor injection — a deliberate,
  narrow exception (AD-1a) so a future second FastAPI-style app doesn't have to redo this
  package's DI. `GlossaryConfig` and the commons primitives pywire can't autowire
  (`PostgresClient`, `EmbeddingService`, `OpenRouterProvider`, `LlmCallTracker`) are built
  once in each entry point's `main()`/`translate_main()` and registered via
  `container.register_instance`, never autowired as self-constructing — see
  `.claude/rules/pywire-di.md`. Two independent `[project.scripts]` entry points
  (`build-glossary`, `translate-glossary-terms`) live at the package root, following the same
  `wiring.py`-plus-`main.py` shape as `labeling/`'s manually-wired scripts.
- **A closed vocabulary that is a shared shape** (a DB column's legal
  values, or a field name another module also needs) goes in
  `src/domain/enums/` as a `StrEnum` with `auto()`-derived values, never
  inside `domain/models/` — an enum is a vocabulary, not a data carrier
  (`.claude/rules/code-conventions.md`). `LexemeField` (`topic`/`text`/
  `image_description`, spec 0011 phase 2) is the first occupant; a
  vocabulary genuinely internal to one module instead follows the
  self-containment rule (`cli-structure.md`) and lives in that module's own
  `enums/` package.

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
gained a new `tracker.py` (a generator-function helper, not a class — see `docs/second-brain/patterns.md`).
ADR 0014 (a proposed **seventh** subpackage member, `VariantModelEmbeddingService[T]`, to
generalize quiz's dedup/omission/fan-out mechanics) was rejected — see
`docs/second-brain/adr/0014-embedding-composition-layer.md`, status `Rejected`; that logic stays local to
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

*Last updated: 2026-08-17 — verified against commit `b3ca8b30` (working tree ahead of it,
uncommitted, on `feat/backend`); `services/` and `repositories/` under
`src/guidami_ai_patente/` gained their first real classes
(`DependencyVersionRepository`, `HealthCheckService`), wired into `GET /health` via
`pywire>=0.3.1`'s native FastAPI integration (`wire(app)` called once in
`api/app.py::create_app`). See `docs/architecture.md` and
`adr/0016-pywire-native-fastapi-wiring.md` for the decision and detail.*

*Last updated: 2026-08-12 — verified against commit `507d2dfb`; noted PEP 561 `py.typed`
markers, added to `guidami_ai_patente_ingestor/`, `parsers/`, `retrieval_evaluation/`,
`scrapers/`, and `test_data_sampler/` (joining `guidami_ai_patente/`, which already had one).*

*Last updated: 2026-08-21 — verified against commit `e4977a94` (working tree ahead: spec
0011 phase 2, T-2/T-3/T-9/T-11); `domain/` gained `entities/evaluation/` (the golden-set
entities) and `enums/` (`LexemeField`, the project's first enum);
`retrieval_evaluation/` gained a second entry point, `label-golden-set`, plus
`repositories/` (`GoldenSetWriteRepository`, insert-only), `exceptions/` and `utils/`
alongside the pre-existing `agents/retrieval_judge/`. New placement bullets record the
`enums/` convention and where the golden-set write repository lives and why.*

*Last updated: 2026-08-19 — verified against commit `2dd56724` (working tree ahead:
spec 0011 phase 1, T-1); the read-DTO bullet now records that `RetrievedComma` carries
`article_commas.id`, closing the exception it used to be to the "read models carry `id`"
rule.*

*Last updated: 2026-08-21 — verified against commit `800d9924` (working tree ahead:
adopted the superpowers plugin, superseding the removed claude-planner plugin's SDD
conventions). `specs/` and the top-level `plans/` are gone; their contents
moved to `docs/superpowers/specs/` and `docs/superpowers/plans/` under the new
`YYYY-MM-DD-<topic>[-design|-phaseN-plan].md` naming. The `specs/` paragraph and the
`docs/` tree-comment above were rewritten accordingly.*

*Last updated: 2026-08-25 — verified against commit `2cc0710a` (working tree ahead: spec
0012, folded commit tasks 7+2+8); `domain/` gained a new `validators/` sub-package
(`require_canonical_lexeme_fields`, shared by `LabelingRunEntity` now and the future
`LabelingEpoch` in `labeling/`) and a second enum, `LabelingRunOrigin`.*

*Last updated: 2026-08-25 — verified against commit `440bad56` (working tree ahead: spec
0012, quiz-flow-api-phase1 plan Task 3); new top-level package `src/labeling/` created
(`configs/labeling_config.py::LabelingConfig`, moved out of
`guidami_ai_patente_ingestor/configs/` and promoted from a plain `BaseModel` to a
`BaseSettings` reading the new `configs/labeling.yaml`); `tests/labeling/` mirrors it.
Added the placement bullet for `labeling/` and a new placement bullet for the
`agents_dir` single-sourcing pattern (two defaultless, `AGENTS_DIR`-aliased fields,
one on `IngestorConfig` and one on `LabelingConfig`, cross-checked by `StatusInspector`).*

*Last updated: 2026-08-25 — verified against commit `564f3df8` (working tree ahead: spec
0012, quiz-flow-api-phase1 plan Task 4). `src/labeling/` gained `models/`
(`labeling_epoch.py::LabelingEpoch`) and `mappers/` (`labeling_epoch_mapper.py`,
`labeling_run_mapper.py`), each mirrored under `tests/labeling/`; updated the `labeling/`
placement bullet accordingly. `prompt_version` is imported into
`labeling/mappers/labeling_epoch_mapper.py` from `retrieval_evaluation.utils` as a
deliberate temporary bridge — Task 5's `git mv` of `run_provenance.py` into
`labeling/utils/` re-points it, per the plan's own Interfaces note for this task.*

*Last updated: 2026-08-25 — verified against commit `7005ad3f` (working tree ahead: spec
0012, quiz-flow-api-phase1 plan Task 5). Pure `git mv` sweep: `src/labeling/` gained the
rest of the judge stack — `agents/comma_labeler/`, `models/candidate_comma.py`,
`services/{candidate_set_service,question_lexeme_service,golden_set_labeling_service}.py`,
`repositories/golden_set_write_repository.py`, `exceptions/labeling_errors.py`, and
`utils/run_provenance.py` — each mirrored under `tests/labeling/`, resolving the
`retrieval_evaluation.utils` bridge noted in the Task 4 entry above.
`retrieval_evaluation/` now holds only `agents/retrieval_judge/`, `main.py`,
`label_main.py`, `services/retrieval_judge_evaluation_service.py`,
`models/retrieval_judge_item_result.py`, and a `wiring.py` trimmed to one builder,
`build_retrieval_judge_agent(agents_dir, provider, tracker)`. The other builders that
used to live in that `wiring.py` (Postgres client, OpenRouter provider, tracker,
quiz/corpus read repos, golden-set repository, comma-labeler config/agent) are not yet in
a shared `labeling/wiring.py` — Task 6 (builders reparameterisation) hasn't run — so they
are temporarily duplicated as private module-level helpers in both `main.py` and
`label_main.py`, each flagged with a comment pointing at Task 6 as the resolution. Added
`tests/labeling/test_module_boundary.py` (asserts `labeling/` imports nothing from
`retrieval_evaluation/`, `pywire`, or `guidami_ai_patente/`, and that `domain/` imports
nothing from `labeling/`) and updated the `labeling/`/`retrieval_evaluation/` placement
bullets accordingly.*

*Last updated: 2026-08-25 — verified against commit `2a639831` (working tree ahead: spec
0012, quiz-flow-api-phase1 plan Task 6). `labeling/` gained `wiring.py` (nine-plus manual
DI builders, all parameterised on `LabelingConfig`/plain values, never
`IngestorConfig`/`AppConfig`); `tests/labeling/` gained `test_wiring.py`. Both
`retrieval_evaluation/main.py` and `label_main.py` now import their builders from
`labeling.wiring` and no longer carry duplicated private `_build_*` helpers (resolving
the Task 5 duplication); both widen their pooled `PostgresClient`'s `pool_max_size` to
`max(config.postgres.pool_max_size, concurrency)` before building it (D7/D14).
`label_main.py`'s `labeling_runs` insert now goes through `LabelingEpochMapper`/
`LabelingRunMapper` instead of an inline `LabelingRunEntity(...)` stopgap.
`tests/retrieval_evaluation/test_wiring.py` was renamed to `test_entry_points.py`,
freeing the `test_wiring` basename for the new `tests/labeling/test_wiring.py` (pytest's
default import mode requires a unique module basename per test file across all of
`tests/`, since no test directory carries an `__init__.py`) — content unchanged, file
moved only.*

*Last updated: 2026-08-26 — verified against commit `546985b5` (working tree ahead: spec
0012, quiz-flow-api-phase2 plan Task 3). `guidami_ai_patente/` gained `clients/`, the app's
first `@client`-provider package (spec 0012, AD-16): `PostgresClientProvider` (wraps
`commons/` `PostgresClient` via `labeling.wiring.build_postgres_client`) and
`LabelingStackProvider` (loads `comma_labeler.yaml` through the new
`AgentConfigRepository`, derives the `LabelingEpoch` via `LabelingEpochMapper`).
`repositories/` gained `AgentConfigRepository` — the API's only door to `agents_dir` and
the agent prompt files (AD-22) — now re-exported from `repositories/__init__.py` (its
first re-export; the pre-existing `DependencyVersionRepository` is still imported
directly from its module).*

*Last updated: 2026-08-26 — verified against commit `64077e1f` (working tree ahead: spec 0012, quiz-flow-api-phase2 plan Task 5). `guidami_ai_patente/` gained `enums/`, holding closed vocabularies `ExplanationStatus` and `InsufficientKnowledgeReason` for the check and insufficient-knowledge responses.*

*Last updated: 2026-08-26 — verified against commit `a48633df` (working tree ahead: spec 0012, quiz-flow-api-phase2 plan Task 10). `guidami_ai_patente/mappers/` (a new top-level package) gained its first occupant, `QuizQuestionMapper` (plus the module-level `QUIZ_IMAGE_URL_PREFIX` constant), re-exported from `mappers/__init__.py`; `api/schemas/` gained its first non-`health` DTOs, `quiz_question.py::QuizQuestionResponse` and `quiz_topics.py::{QuizTopicResponse, QuizTopicsResponse}`; `services/` gained `QuizProposalService` (found-or-404 wrapper over `QuizQuestionRepository`'s `propose`/`fetch`/`topics`).*

*Last updated: 2026-08-28 — verified against commit `ab1b8f82`; `commons/ai/observability/`
no longer follows the plain five-subpackage template — the `observability/` paragraph is
rewritten to describe its current shape (`protocols/` now fully public, `adapters/` added
for the stateful `PydanticAILlmCallRecorder`, `entities/`/`enums/`/`configs/` added,
`mappers/` gone, `models/` repurposed for `TrackedCaller`, package-root
`tracker_factory.py`); `embedding/`'s paragraph split out on its own since it still
matches the original template. `domain/entities/observability/` is gone from both the
tree comment and the placement-guidance list — `LlmCallLogEntity` moved into
`commons/ai/observability/entities/`.*

*Last updated: 2026-09-01 — merged `feat/backend` into `feat/quiz-flow-api-phase1` ahead
of spec 0013 implementation; the two conflicting tree-comment/changelog regions above were
reconciled by hand (topics don't overlap — `domain/`+`labeling/`+`guidami_ai_patente/`
growth on this branch vs. the `commons/ai/observability/` restructure on `feat/backend`),
see `architecture.md`'s matching merge entry for the code-level reconciliation
(`retrieval_evaluation/`/`labeling/wiring.py`'s `build_tracker` removal).*

*Last updated: 2026-09-01 — verified against commit `51dcba1a`; fixed a stale
`adr/0020-context-manager-tracker-port.md` cross-reference — that ADR was renumbered to
0025 (see `database.md`'s matching entry for why: an ADR-number collision from the
`feat/backend` merge). Updated the `guidami_ai_patente/` tree-comment's `clients/`
placement bullet: since spec 0013 FR-2, `clients/` holds only `PostgresClientProvider`;
new sibling package `providers/` holds `LabelingStackProvider`, decorated `@provider`.
Flagging for a future pass, not addressed here: this file is well past the ~200-line
split threshold this skill's own guidance recommends (`layout.md` → `layout.md` +
`layout/<topic>.md`) — out of scope for spec 0013, but worth doing before much more
content accumulates.*

*Last updated: 2026-09-03 — verified against commit `e592b110` (quiz-flow-api-phase3
plan Task 14, close-out). Corrected two stale claims: the `guidami_ai_patente/`
tree-comment no longer says the explanation endpoint "is not implemented yet" (it is,
spec 0012 phase 3) and the endpoint count is now seven (`GET /health` plus six
quiz-domain routes, not five). `providers/` tree-comment now lists all three providers
(`LabelingStackProvider`, `LiveLabelingStackProvider`, `OpenRouterProviderComponent`,
`LlmCallTrackerProvider` — D3/D5, `adr/0029`/`adr/0031`), not just the first one.
`labeling/`'s `services/` enumeration gained `QuestionLabelingService` (`adr/0030`) and
a new `constants.py` (`EMBEDDING_MODEL_COLUMN`). The ~200-line split flagged in the
previous entry is still not addressed — deferred again, same reasoning.*

*Last updated: 2026-09-16 — verified against commit `1f6c7739` (spec 0015,
telegram-bot-client-mvp plan, Tasks 1-4 committed; Task 5 in progress). New
top-level package `src/guidami_ai_patente_bot/` created: `configs/` (`BotConfig`),
`enums/` (`ExplanationOutcome`), `models/` (`QuizQuestion`, `QuizExplanation`,
`QuizSession`), `exceptions/` (`QuizApiError`, `StaleQuestionError`), `clients/`
(`QuizApiClient`, a pywire `@async_component` — pywire bumped to v0.9.0 for this),
`services/` (`QuizFlowService`). Added the matching placement bullet and tree
entry, and flagged that AD-5's closed package-set prose in spec 0015 is stale
(omits `enums/`, which the plan's own Task 2 creates per the project-wide enum
placement rule).*

*Last updated: 2026-09-16 — verified against commit `f53ad73f` (telegram-bot-client-mvp
plan, all six tasks complete plus a final-review fix wave). `guidami_ai_patente_bot/`
gained its remaining two pieces: `handlers/` (`quiz_handlers.py` — `start_or_quiz`,
`handle_next_callback`, `handle_answer_callback`, each resolving `QuizFlowService`
via `pywire.get_default_container().resolve(...)` since plain PTB callables aren't
FastAPI routes; `error_handler.py` — the global PTB error boundary) and
`main.py` (entry point: loads `BotConfig` once, `register_instance`s it, then
`register_async_component(QuizApiClient)` **explicitly** — not via the
`@async_component` decorator, which would have registered it at import time on
the same process-wide default container `guidami_ai_patente`'s FastAPI app shares,
breaking that app's own `astart()` — then drives `python-telegram-bot`'s manual
async lifecycle inside `container.lifespan()`). This explicit-registration
correction was a Critical finding from the final whole-branch review (`uv run
pytest` broke for the whole API test suite the moment both test trees were
collected together — invisible to any single-task review); see ADR 0033, which
supersedes ADR 0032 accordingly. Corrected this file's own `clients/` tree-comment
bullet to describe the fix (it previously said `@async_component` bare-decorated,
now stale). `QuizFlowService.handle_answer` also gained a fallback: a failed
`get_explanation` call after a successful `check_answer` no longer strands the
graded answer — it falls back to an `INSUFFICIENT_KNOWLEDGE`-shaped
`QuizExplanation` instead of propagating uncaught.*

*Last updated: 2026-09-18 — verified against commit `68575993` (spec 0016, bot user
authorization & answer history — db-schema, backend, and telegram-bot plans, all three
implemented in sequence). `domain/entities/` tree comment gained `users/` (`UserEntity`).
`guidami_ai_patente/` tree comment: new `api/dependencies/` package
(`resolve_identity`/`require_registered_user`, plain `Depends()` functions gating every
business route), `UserRepository`/`QuizAnswerRepository`, `unregistered_user_error.py`;
endpoint count is now nine (added `GET /me`, `GET /quiz-answers/summary`).
`guidami_ai_patente_bot/` tree comment: new `container.py` (centralizes resolving a pywire
component through `Application.bot_data`, replacing each handler's own
`pywire.get_default_container().resolve(...)` call), new `messages.py` (centralized
user-facing strings), `exceptions/` gained `UnauthorizedError`; `/start`/`/quiz` split
into separate handlers (previously one combined `start_or_quiz`), new `/stop` handler.
Manual live-Telegram verification (spec 0016's Definition of Done item 4) and a possible
ADR for the `Application.bot_data` container-resolution pattern are both still open — see
`architecture.md`'s matching entry.*

*Last updated: 2026-09-20 — verified against commit `ed51081c` (spec 0018 backend,
explanation-translator plan, Tasks 1-5 on `feat/backend`). `guidami_ai_patente/` tree
comment: endpoint count corrected to eleven (the "Nine" figure predated the spec 0017
`/label` route and undercounted the quiz-domain routes) and the new
`POST /explanations/translate` route plus the files backing it listed. No new top-level
package: the feature is one router, one dependency, one service, one agent and one
exception slotted into existing `guidami_ai_patente/` packages.*

*Last updated: 2026-09-21 — verified against commit `61c290f1`. `guidami_ai_patente/`:
`models/` gained `topic_summary.py`/`wrong_question.py` (and `session_summary.py` now nests
them), `mappers/` gained `session_summary_mapper.py`. `guidami_ai_patente_bot/`: `models/`
gained the mirroring `topic_summary.py`/`wrong_question.py`; `messages.py` now also holds the
command list, the `/quiz` intro and `summary_message`, which renders the whole `/stop`
summary. Tests: `tests/guidami_ai_patente_bot/test_messages.py` and
`tests/guidami_ai_patente/mappers/test_session_summary_mapper.py` are new.*

*Last updated: 2026-09-25 — verified against commit `3c418a5d` (spec 0019, `src/glossary/`
package, a 16-task plan via `superpowers:subagent-driven-development`). New top-level
package `src/glossary/`, first occupant of a new placement-convention bullet; new mirroring
`tests/glossary/`. See `docs/second-brain/architecture.md`'s `glossary/` row for the full
component breakdown this file deliberately doesn't duplicate.*

*Last updated: 2026-09-25 — verified against commit `ae97d2e3` (working tree ahead).
`glossary/` gained a `utils/` package: the mechanical `split_into_chunks` moved out of
`services/` into `utils/chunking.py`, mirroring `guidami_ai_patente_ingestor/utils/`'s
existing convention for a stateless, domain-specific pure-function module. Mirroring
`tests/glossary/utils/` added.*

*Last updated: 2026-09-25 — verified against commit `459af9b5` (working tree ahead).
`glossary/utils/` gained `entry_markers.py` (the numeric/alphabetic marker regexes, now
shared with `chunking.py`, plus `count_expected_entries`, `is_abrogated`,
`is_cross_reference`), with `tests/glossary/utils/test_entry_markers.py` mirroring it.*

*Last updated: 2026-09-25 — verified against commit `f6e2c152` (working tree ahead).
`glossary/utils/` gained `normalization.py` (`normalize_term`, `capitalize_definition`),
used by `GlossaryExtractionService`; `tests/glossary/utils/test_normalization.py` mirroring
it.*

*Last updated: 2026-09-26 — verified against commit `3980e7ba` (spec 0021, on-demand
glossary enrichment, fully implemented on feat/backend). `guidami_ai_patente/` gained its
first `utils/` package (`merge_glossary_candidates.py`), mirroring the same
stateless-standalone-function convention already established in `guidami_ai_patente_ingestor/utils/`
and `glossary/utils/`; `enums/` gained `glossary_term_origin.py`; `agents/` gained
`glossary_enricher/` (agent + `dto/`). Mirroring `tests/guidami_ai_patente/utils/` and
`tests/guidami_ai_patente/agents/glossary_enricher/` added.*
