# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

**guidami-ai-patente** is a tool that makes Italian driving exam information freely accessible. It aggregates official questions, regulations, and reference material — currently scraped from the web and from PDFs — so users can study and query it without paywalls.

The end goal is a **quiz bot** (FastAPI) that checks answers deterministically and explains them using RAG over the corpus normativo (CdS + CAP). The project is currently in the **data ingestion phase**: infrastruttura Postgres/pgvector operativa, pipeline di ingestion corpus + quiz bank implementate. L'app FastAPI non è ancora avviata.

## Environment & Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run a single test
uv run pytest tests/path/to/test_file.py::test_name

# Add a dependency
uv add <package>

# Lint / format / type check
uv run ruff check src tests
uv run ruff format src tests
uv run pyright
```

### Infrastructure

```bash
# Start Postgres + pgvector (required for integration tests and ingestion)
cd docker && docker compose up -d

# Recreate DB from scratch (required after schema changes in db/init.sql)
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d
```

### Available scripts

| Command | Entry point | Description |
|---|---|---|
| `uv run scrape-codice` | `scrapers.normattiva:main_cds` | Scrapes CdS → `data/raw/cds/`, `data/parsed/cds/codice_della_strada.json` |
| `uv run scrape-cap` | `scrapers.normattiva:main_cap` | Scrapes CAP → `data/raw/cap/`, `data/parsed/cap/codice_rca.json` |
| `uv run parse-domande` | `parsers.questions_pdf:main_questions` | Parses quiz PDF → `data/parsed/quiz-patente-ab/` |
| `uv run ingest-knowledge --source <cds\|cap>` | `guidami_ai_patente_ingestor.main:main` | Runs `build_knowledge_indexing_flow` for one source (`enriched` → chunk → embed → `knowledge_chunks`) |
| `uv run reset-knowledge-db` | `guidami_ai_patente_ingestor.reset_db:main` | Truncates `knowledge_chunks` without re-ingesting |
| `uv run reset-quiz-db` | `guidami_ai_patente_ingestor.reset_quiz_db:main` | Truncates `quiz_questions` without re-ingesting |

Register new CLI commands under `[project.scripts]` in `pyproject.toml`.

> ⚠️ The ingestion pipelines were rebuilt on a `flowstep`-based orchestrator (see below); CLI cutover
> for quiz indexing and for both preparation flows (knowledge + quiz) is **pending** — their old
> entry points (`quiz_main.py`, `prepare_knowledge_main.py`) were removed and not yet rewired. Only
> `ingest-knowledge` is currently wired to the new flow.

### Secrets required

Copy `.env.example` to `.env` and fill in:
- `POSTGRES__USER` / `POSTGRES__PASSWORD` — DB credentials (double underscore = nested delimiter for `IngestorConfig.postgres`)
- `OPENROUTER_API_KEY` — required for embedding (`LiteLLMEmbeddingClient`) and future LLM steps; read by litellm from the environment, not loaded explicitly in code

## Architettura

- Progettazione (anche non ancora implementata): `plans/`. Prima di iniziare un
  task implementativo, leggere sempre i piani partendo da
  [plans/architecture-index.md](plans/architecture-index.md) e seguendo i
  documenti collegati.
- Decisioni architetturali **effettivamente implementate**:
  [.claude/architectures/index.md](.claude/architectures/index.md). Al termine
  di un task implementativo, invocare l'agente `architecture-doc-keeper`
  (definito in [.claude/agents/architecture-doc-keeper.md](.claude/agents/architecture-doc-keeper.md))
  per aggiornare questa cartella con le decisioni prese e il design
  effettivamente realizzato — non modificare direttamente i file in
  `.claude/architectures/`.

### Package layout

Ingestion pipelines are built on an in-house `commons/flowstep` toolkit (`Flow`/`FlowBuilder`/`Step`
+ `FlowContext`): each pipeline is a linear chain of thin `Step`s wired by a `*_flows.py` factory.
Full design rationale lives in `.claude/architectures/ingestor/` (start at
[index.md](.claude/architectures/ingestor/index.md)); current layout:

```
src/
  commons/                              # Shared between ingestor and future app — no dependencies on either
    flowstep/                           # Generic Flow/FlowBuilder/Step/FlowContext toolkit + validator
    entities/knowledge/                 # KnowledgeChunk (knowledge_chunks row)
    entities/quiz/                      # QuizQuestion (quiz_questions row)
    models/knowledge/                   # RetrievalResult (chunk + similarity score)
    clients/embeddings/                 # EmbeddingClient (ABC), LiteLLMEmbeddingClient, SentenceTransformerEmbeddingClient
    clients/postgres_client.py          # Generic psycopg v3 wrapper (table-agnostic)
    configs/                            # EmbeddingConfig, PostgresConnectionConfig (frozen BaseModel, not BaseSettings)

  guidami_ai_patente_ingestor/          # Batch ingestion service — depends on commons
    entities/                           # Article only (quiz source/enriched DTOs live in models/quiz/)
    models/knowledge/                   # EnrichedArticle
    models/quiz/                        # QuizBankModel/EnrichedQuizModel/EmbeddableQuizModel chain
    mappers/knowledge/                  # EnrichedArticleMapper
    mappers/quiz/                       # QuizMapper (single consolidated mapper, all 1:1 stage transitions)
    services/layer_resolver.py          # LayerResolver(layers, sources).path(layer, source) -> Path
    services/knowledge/                 # ArticleCleaner, ArticleChunker
    services/quiz/                      # QuizEnrichmentService + enrichers/ (QuizEnricher Protocol, ImageDescriptionEnricher)
    repositories/json/                  # ArticleRepository, EnrichedArticleRepository, QuizBankRepository, EnrichedQuizBankRepository
    repositories/db/                    # KnowledgeChunkStoreRepository, QuizQuestionStoreRepository
    orchestrators/knowledge_flows.py    # build_knowledge_indexing_flow, build_knowledge_cleaning_flow, build_knowledge_enrichment_flow
    orchestrators/quiz_flows.py         # build_quiz_indexing_flow, build_quiz_preparation_flow
    orchestrators/preparation_runner.py # run_preparation(flow, out_path, force) — per-source idempotent runner
    orchestrators/steps/knowledge/      # thin Step subclasses for both knowledge flows
    orchestrators/steps/quiz/           # thin Step subclasses for both quiz flows
    configs/ingestor_config.py          # IngestorConfig (BaseSettings, frozen)
    main.py / reset_db.py / reset_quiz_db.py  # only wired CLI entry points today (see table above)

  guidami_ai_patente/                   # Future FastAPI app — not yet started
  scrapers/                             # Web scrapers (normattiva.it)
  parsers/                              # PDF parsers (quiz bank)
```

### Data directory convention

Pipelines use a four-stage layout on disk, resolved by `LayerResolver.path(layer, source)`:

| Directory | Content | Produced by |
|---|---|---|
| `data/raw/<source>/` | Raw HTML from scrapers | `scrape-*` |
| `data/parsed/<source>/` | Parsed JSON (normattiva markup still present) | `scrape-*` / `parse-domande` |
| `data/cleaned/<source>/` | Cleaned JSON, markup stripped | `build_knowledge_cleaning_flow` (corpus). For the quiz bank there is no separate "clean" stage — `parse-domande`'s output **is** the `cleaned` layer input directly. |
| `data/enriched/<source>/` | Self-contained enriched JSON (corpus: article + per-comma `contexts`; quiz: quiz bank + `image_description` per sub-question) | `build_knowledge_enrichment_flow` (corpus) / `build_quiz_preparation_flow` (quiz) |

Knowledge indexing reads from `data/enriched/`; quiz indexing reads from `data/enriched/quiz-patente-ab/`
(produced by `build_quiz_preparation_flow`, not yet wired to a CLI entry point).

### Database schema

Two tables in one Postgres (`pgvector/pgvector:pg16`). Schema in `db/init.sql`.

- **`knowledge_chunks`** — corpus normativo chunkato per comma. Columns: `source` ("cds"/"cap"), `article_number`, `article_title`, `comma_index`, `chunk_text`, `is_repealed`, `source_url`, `embedding VECTOR(1536)`. Unique on `(source, article_number, comma_index)`.
- **`quiz_questions`** — flat quiz bank. Columns: `number`, `question_id`, `topic`, `text`, `correct_answer`, `image_filename`, `embedding VECTOR(1536)`. Unique on `(number)`.

Embedding dimension is **1536** (`text-embedding-3-small`). Changing the model to one with a different dimension requires `db/init.sql` update + Docker volume recreate + full re-ingest.

### Ingestion pipelines

Each pipeline is a linear `Flow` (`commons.flowstep`) assembled by a factory in `orchestrators/*_flows.py`.
Preparation flows (parsed/cleaned → enriched) are idempotent at the file level via the shared
`run_preparation(flow, out_path, force)` runner: skips `flow.run()` if `out_path` already exists,
unless `force=True`. Indexing flows are **always full-reload** (truncate + bulk insert), not idempotent.

**Knowledge corpus** (per-source, `--source cds`/`--source cap`):
1. `build_knowledge_cleaning_flow`: `data/parsed/<source>/` → `ArticleCleaner` → `data/cleaned/<source>/`.
2. `build_knowledge_enrichment_flow`: `data/cleaned/<source>/` → `ArticleContextualizerAgent` (per-comma `contexts`) → `EnrichedArticleMapper` → `data/enriched/<source>/`.
3. `build_knowledge_indexing_flow` (wired to `uv run ingest-knowledge --source <cds|cap>`): `data/enriched/<source>/` → `ArticleChunker` → filters `is_repealed` chunks (unless `embed_repealed=True`) → `LiteLLMEmbeddingClient.embed_passages([chunk.embedded_text])` in batches → `KnowledgeChunkStoreRepository.delete_source(source) + bulk_insert()`. `embedded_text = f"{article_title} {chunk_text}"`.

**Quiz bank** (single source `"quiz"`, no CLI entry point wired yet for either flow):
1. `build_quiz_preparation_flow`: `data/cleaned/quiz-patente-ab/` → `QuizMapper.from_quiz_bank_to_enriched` base-map → `QuizEnrichmentService` applies enrichers in order (currently `ImageDescriptionEnricher`: vision-LLM description per unique image, deduped, via `RoadSignDescriberAgent`; missing file or describe failure → skip + warning, never raises) → `data/enriched/quiz-patente-ab/`. Open/Closed: adding an enricher only changes the factory's enricher list, never the step/service.
2. `build_quiz_indexing_flow`: `data/enriched/quiz-patente-ab/` → flatten + dedup sub-questions (key `(text.strip(), correct_answer, image)`) via `MapToEmbeddableStep` → `QuizMapper.from_enriched_quiz_item_to_embeddable` → embed → `QuizMapper.from_embeddable_to_quiz_question` → `QuizQuestionStoreRepository.truncate() + bulk_insert()`. `embedded_text = f"{topic} {text}"`. Dedup historically removes 8 exact duplicates (7098 final rows).

`embed_passages` is batched (`embedding_batch_size=64` in config) for both pipelines.

### Configuration pattern

`IngestorConfig` (`pydantic_settings.BaseSettings`, `frozen=True`) uses two layers:

- **`configs/ingestor_config.yaml`** (committed, non-secret): paths, batch sizes, `embedding.model_name`, `postgres.host/port/dbname`, table names.
- **`.env`** (gitignored, secrets only): `POSTGRES__USER`, `POSTGRES__PASSWORD`, `OPENROUTER_API_KEY`.

`commons` has no dependency on `pydantic-settings` — `PostgresConnectionConfig` is a plain `BaseModel` populated by the caller. Config is loaded **only at the entry point** (`main.py`), never inside builders or services.

## Code Conventions

- Pydantic config classes (anything under `configs/`) must set `model_config = ConfigDict(frozen=True)`.
- Root configuration classes at entry points use `pydantic_settings.BaseSettings` with the two-level pattern above.
- `PostgresClient` requires `%s::vector` cast for vector params — psycopg adapts `list[float]` to `array`, incompatible with the `<=>` operator.
- Logging: `logging.basicConfig(...)` only in entry points (`main.py`). All modules use `logger = logging.getLogger(__name__)` at module level. Log messages in English.
- `@pytest.mark.integration` marks tests that require external services (Postgres, model downloads). Run plain `uv run pytest` to skip them.

## Data Notes

- `data/docs/domande AB italiano 23 04 2025.pdf` — official question bank for categories A/B, Italian language, dated April 2025.
- `data/parsed/cap/codice_rca.json` — 96 articles relevant to RCA/patente (subset of full CAP).
- When scraping, prefer storing raw HTML/PDF alongside parsed output so re-parsing is possible without re-fetching.
- Source URLs and scrape timestamps must be recorded with every document.
