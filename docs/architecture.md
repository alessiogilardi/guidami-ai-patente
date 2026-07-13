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
| `commons/clients/embeddings/` | `EmbeddingClient` ABC (`embed_query`, `embed_passages`); `LiteLLMEmbeddingClient` (production) and `SentenceTransformerEmbeddingClient` (offline alternative, not hot-swappable — different dimension) | litellm (→ OpenRouter), sentence-transformers |
| `commons/agents/` | `BaseAgent[T_In, T_Out]` — wraps `pydantic_ai.Agent`, loads `AgentConfig` from YAML, renders prompts via `PromptRenderer`; optionally tracks every call via an injected `LlmCallTracker` port | pydantic-ai-slim[openrouter] |
| `commons/ai/observability/` | `LlmCallTracker` port (`protocols/`) + `PydanticAILlmCallCapture`/`QueuedLlmCallTracker`/`LlmCostCalculator` (`services/`) + `LlmCallLogRepository` (`repositories/`) + `LlmCallLogMapper`/`LlmCallCaptureModel` (`mappers/`, `models/`) — populates `llm_call_logs`; commons-level (not ingestor-only) because the future FastAPI app will track calls too | litellm (pricing map only), psycopg[binary] |
| `commons/clients/postgres_client.py` | Generic, table-agnostic Postgres/pgvector client | psycopg[binary], pgvector |
| `commons/use_cases/` | `UseCase`/`AsyncUseCase`, `ForEach`, `FlatMap` — generic composition primitives used across pipeline steps | — |
| `domain/entities/`, `domain/models/` | Persisted entities and shared cross-app models | pydantic |
| `flowstep` (external dependency) | Generic sequential-pipeline engine (`Flow`, `Step`, `FlowBuilder`, `FlowContext`, `ApplyStep`) | git dependency (github.com/alessiogilardi/flowstep) |
| `guidami_ai_patente_ingestor/` | Batch ingestion app — orchestrators, services, repositories, mappers, agents, models, configs (see flows below) | — |
| `guidami_ai_patente/` | FastAPI quiz bot — **not started** | FastAPI (planned) |
| `parsers/questions_pdf.py` | Quiz PDF → `data/parsed/quiz-patente-ab/` | pdfplumber, pymupdf |
| `scrapers/normattiva.py` | normattiva.it → `data/raw/` + `data/parsed/` | beautifulsoup4, lxml, httpx |

`parsers/questions_pdf.py` extracts each sub-question's image lazily: the
per-question default image (fallback for rows without their own nearby
image) is only extracted the first time a row actually needs it, not
eagerly when the question is created. Extracting it eagerly regardless of
use silently orphans files under `data/parsed/quiz-patente-ab/images/`
whenever every row of a question resolves its own row-level image instead.

LLM agents in use today (all `BaseAgent` subclasses under
`guidami_ai_patente_ingestor/agents/`):
- `ArticleContextualizerAgent` — knowledge-corpus enrichment (per-article context).
- `RoadSignDescriberAgent` — vision agent, quiz enrichment; deliberately
  answer-blind (see ADR below). Owns image-file reading via its
  `PromptRenderer`/`file_reader`; `ImageDescriptionEnricher` only passes
  image paths and holds no reader of its own.
- `NormReferenceDescriberAgent` — quiz enrichment, norm-reference metadata
  for future RAG retrieval.

Storage: Postgres 16 + pgvector — see `database.md`. Embedding: production
model is `text-embedding-3-small` (OpenAI), 1536-dim, via litellm routed
through OpenRouter, authenticated with `OPENROUTER_API_KEY`.

## Main flows

Entry point: `guidami_ai_patente_ingestor/cli.py` — `ingest
prepare|index|reset knowledge|quiz` (see command table in `CLAUDE.md`).
`run_preparation` wraps every preparation flow with idempotency (skips a
stage if its output file already exists, unless `--force`).

**LLM call observability** (`prepare` path only, no agent calls on `index`/`reset`):
`cli._run_prepare` opens a `PostgresClient` and, inside `with postgres_client,
QueuedLlmCallTracker(LlmCallLogRepository(postgres_client), LlmCostCalculator()) as
tracker:`, dispatches to `_dispatch_prepare(..., tracker)`, which forwards `tracker`
into `build_knowledge_enrichment_flow`/`build_quiz_enrichment_flow` → the agents'
`from_yaml(..., tracker=tracker)`. Inside `BaseAgent.run`/`run_sync`, a tracked call is
wrapped in `PydanticAILlmCallCapture` (records prompt/response/tokens/latency/status synchronously)
and `tracker.track(capture.log)` enqueues the log for the background worker, which
computes `cost_usd` (litellm pricing lookup) and inserts via `LlmCallLogRepository` —
off the hot path, so a slow/failing DB write never blocks the LLM call. If
`PostgresClient` construction fails (`psycopg.Error`), `_run_prepare` logs a warning and
dispatches with `tracker=None`: the untracked path is byte-for-byte what `BaseAgent` ran
before this feature (see `docs/patterns.md`).

**Knowledge corpus** (per source, `cds`/`cap` — `orchestrators/knowledge_flows.py`):
1. *Cleaning*: `LoadJsonStep` → `ApplyStep(ForEach(ArticleCleaner))` → `WriteJsonStep` (parsed → cleaned).
2. *Enrichment*: `LoadJsonStep` → `ApplyStep(ForEach(ArticleMapper.from_parsed_to_enriched), ContextEnricher(ArticleContextualizerAgent))` → `WriteJsonStep` (cleaned → enriched).
3. *Indexing*: `LoadJsonStep` → `ApplyStep(FlatMap(ArticleChunker))` → `EmbedChunksStep` → `ApplyStep(ForEach(ArticleMapper.from_embeddable_chunk_to_knowledge_chunk))` → `StoreChunksStep` (deletes only that source's rows, then inserts — scoped full-reload).

**Quiz bank** (`orchestrators/quiz_flows.py`):
1. *Cleaning*: `LoadJsonStep` → `ApplyStep(FlatMap(QuizMapper.from_parsed_to_cleaned_all), DeduplicateQuizItems())` → `WriteJsonStep` (parsed → cleaned; dedup on normalized-text + correct_answer + image identity).
2. *Enrichment*: `LoadJsonStep` → `ApplyStep(ForEach(QuizMapper.from_cleaned_to_enriched), ImageDescriptionEnricher(RoadSignDescriberAgent), NormReferenceEnricher(NormReferenceDescriberAgent))` → `WriteJsonStep` (cleaned → enriched).
3. *Indexing*: `LoadJsonStep` → `ApplyStep(DeduplicateQuizItems(), ForEach(QuizMapper.from_enriched_to_embeddable))` → `ApplyStep(EmbedQuizMetadata)` → `ApplyStep(ForEach(QuizMapper.from_embeddable_to_quiz_question))` → `DbStoreStep` (full truncate + bulk insert). Embeddings are computed from `quiz_metadata.vector_search_queries`, not raw quiz text — items without `quiz_metadata` end up with `embedding=None`. `QuizMetadata` stays a cohesive nested object through the ingestion models (`EnrichedQuizModel`/`EmbeddableQuizModel`) and is flattened onto the `QuizQuestion` entity columns **only** at the boundary, inside `from_embeddable_to_quiz_question`.

## Relevant architectural decisions

See `adr/` for the full history. Currently accepted:

- **Road sign describer is answer-blind** — `RoadSignDescriberAgent`
  never receives `correct_answer` in its request DTO, by design, to avoid
  the description leaking the answer. Still true in code today.
- **Quiz metadata flattened into columns** — the retrieval-relevant
  `QuizMetadata` fields are first-class `quiz_questions` columns and
  `QuizMetadata` is a transient ingestion model, not a persisted entity
  (`adr/0002-flatten-quiz-metadata-columns.md`).
- **LLM call tracking is a port injected into `BaseAgent`, not an external
  wrapper** — token usage (`result.usage()`) only exists inside
  `run`/`run_sync`; an external decorator would force `BaseAgent.run` to
  return a rich result object, breaking every enricher. `LlmCallTracker`
  persistence failures degrade gracefully (log a warning, never abort the
  pipeline) — a deliberate, documented exception to "never swallow
  exceptions" (`docs/plans/2026-07-13--llm-call-tracking.md`).

*Last updated: 2026-07-13 — verified against commit `5398b2d`.*
