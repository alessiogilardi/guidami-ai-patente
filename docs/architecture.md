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
  (`knowledge_chunk`, `quiz_question`, `quiz_metadata`, `retrieval_result`).

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
| `commons/agents/` | `BaseAgent[T_In, T_Out]` — wraps `pydantic_ai.Agent`, loads `AgentConfig` from YAML, renders prompts via `PromptRenderer` | pydantic-ai-slim[openrouter] |
| `commons/clients/postgres_client.py` | Generic, table-agnostic Postgres/pgvector client | psycopg[binary], pgvector |
| `commons/use_cases/` | `UseCase`/`AsyncUseCase`, `ForEach`, `FlatMap` — generic composition primitives used across pipeline steps | — |
| `domain/entities/`, `domain/models/` | Persisted entities and shared cross-app models | pydantic |
| `flowstep` (external dependency) | Generic sequential-pipeline engine (`Flow`, `Step`, `FlowBuilder`, `FlowContext`, `ApplyStep`) | git dependency (github.com/alessiogilardi/flowstep) |
| `guidami_ai_patente_ingestor/` | Batch ingestion app — orchestrators, services, repositories, mappers, agents, models, configs (see flows below) | — |
| `guidami_ai_patente/` | FastAPI quiz bot — **not started** | FastAPI (planned) |
| `parsers/questions_pdf.py` | Quiz PDF → `data/parsed/quiz-patente-ab/` | pdfplumber, pymupdf |
| `scrapers/normattiva.py` | normattiva.it → `data/raw/` + `data/parsed/` | beautifulsoup4, lxml, httpx |

LLM agents in use today (all `BaseAgent` subclasses under
`guidami_ai_patente_ingestor/agents/`):
- `ArticleContextualizerAgent` — knowledge-corpus enrichment (per-article context).
- `RoadSignDescriberAgent` — vision agent, quiz enrichment; deliberately
  answer-blind (see ADR below).
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

**Knowledge corpus** (per source, `cds`/`cap` — `orchestrators/knowledge_flows.py`):
1. *Cleaning*: `LoadJsonStep` → `ApplyStep(ForEach(ArticleCleaner))` → `WriteJsonStep` (parsed → cleaned).
2. *Enrichment*: `LoadJsonStep` → `ApplyStep(ForEach(ArticleMapper.from_parsed_to_enriched), ContextEnricher(ArticleContextualizerAgent))` → `WriteJsonStep` (cleaned → enriched).
3. *Indexing*: `LoadJsonStep` → `ApplyStep(FlatMap(ArticleChunker))` → `EmbedChunksStep` → `ApplyStep(ForEach(ArticleMapper.from_embeddable_chunk_to_knowledge_chunk))` → `StoreChunksStep` (deletes only that source's rows, then inserts — scoped full-reload).

**Quiz bank** (`orchestrators/quiz_flows.py`):
1. *Cleaning*: `LoadJsonStep` → `ApplyStep(FlatMap(QuizMapper.from_parsed_to_cleaned_all), DeduplicateQuizItems())` → `WriteJsonStep` (parsed → cleaned; dedup on normalized-text + correct_answer + image identity).
2. *Enrichment*: `LoadJsonStep` → `ApplyStep(ForEach(QuizMapper.from_cleaned_to_enriched), ImageDescriptionEnricher(RoadSignDescriberAgent), NormReferenceEnricher(NormReferenceDescriberAgent))` → `WriteJsonStep` (cleaned → enriched).
3. *Indexing*: `LoadJsonStep` → `ApplyStep(DeduplicateQuizItems(), ForEach(QuizMapper.from_enriched_to_embeddable))` → `ApplyStep(EmbedQuizMetadata)` → `ApplyStep(ForEach(QuizMapper.from_embeddable_to_quiz_question))` → `DbStoreStep` (full truncate + bulk insert). Embeddings are computed from `quiz_metadata.vector_search_queries`, not raw quiz text — items without `quiz_metadata` end up with `embedding=None`.

## Relevant architectural decisions

See `adr/` for the full history. Currently accepted:

- **Road sign describer is answer-blind** — `RoadSignDescriberAgent`
  never receives `correct_answer` in its request DTO, by design, to avoid
  the description leaking the answer. Still true in code today.

*Last updated: 2026-07-10 — verified against commit `66593a7`.*
