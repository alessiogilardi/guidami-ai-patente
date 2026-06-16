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
| `uv run ingest-knowledge` | `guidami_ai_patente_ingestor.main:main` | Runs CleaningPipeline + IndexingPipeline (CdS + CAP → `knowledge_chunks`) |
| `uv run reset-knowledge-db` | `guidami_ai_patente_ingestor.reset_db:main` | Truncates `knowledge_chunks` without re-ingesting |
| `uv run ingest-quiz` | `guidami_ai_patente_ingestor.quiz_main:main` | Runs QuizIndexingPipeline (quiz bank → `quiz_questions`) |
| `uv run reset-quiz-db` | `guidami_ai_patente_ingestor.reset_quiz_db:main` | Truncates `quiz_questions` without re-ingesting |

Register new CLI commands under `[project.scripts]` in `pyproject.toml`.

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

```
src/
  commons/                              # Shared between ingestor and future app — no dependencies on either
    entities/knowledge/                 # KnowledgeChunk (knowledge_chunks row)
    entities/quiz/                      # QuizQuestion (quiz_questions row)
    models/knowledge/                   # RetrievalResult (chunk + similarity score)
    clients/embeddings/                 # EmbeddingClient (ABC), LiteLLMEmbeddingClient, SentenceTransformerEmbeddingClient
    clients/postgres_client.py          # Generic psycopg v3 wrapper (table-agnostic)
    configs/                            # EmbeddingConfig, PostgresConnectionConfig (frozen BaseModel, not BaseSettings)

  guidami_ai_patente_ingestor/          # Batch ingestion service — depends on commons
    orchestrators/knowledge_cleaning/   # CleaningPipeline + Builder
    orchestrators/knowledge_indexing/   # IndexingPipeline + Builder
    orchestrators/quiz_indexing/        # QuizIndexingPipeline + Builder
    repositories/                       # ArticleRepository, KnowledgeChunkStoreRepository, QuizBankRepository, QuizQuestionStoreRepository
    services/knowledge/                 # ArticleCleaner, ArticleChunker
    services/quiz/                      # QuizQuestionMapper
    configs/ingestor_config.py          # IngestorConfig (BaseSettings, frozen)
    main.py / reset_db.py               # CLI entry points for knowledge corpus
    quiz_main.py / reset_quiz_db.py     # CLI entry points for quiz bank

  guidami_ai_patente/                   # Future FastAPI app — not yet started
  scrapers/                             # Web scrapers (normattiva.it)
  parsers/                              # PDF parsers (quiz bank)
```

### Data directory convention

Pipelines use a three-stage layout on disk:

| Directory | Content | Produced by |
|---|---|---|
| `data/raw/<source>/` | Raw HTML from scrapers | `scrape-*` |
| `data/parsed/<source>/` | Parsed JSON (normattiva markup still present) | `scrape-*` / `parse-domande` |
| `data/cleaned/<source>/` | Cleaned JSON, markup stripped | `CleaningPipeline` (idempotent: skips if already exists) |

Knowledge pipeline reads from `data/cleaned/`, quiz pipeline reads from `data/parsed/quiz-patente-ab/`.

### Database schema

Two tables in one Postgres (`pgvector/pgvector:pg16`). Schema in `db/init.sql`.

- **`knowledge_chunks`** — corpus normativo chunkato per comma. Columns: `source` ("cds"/"cap"), `article_number`, `article_title`, `comma_index`, `chunk_text`, `is_repealed`, `source_url`, `embedding VECTOR(1536)`. Unique on `(source, article_number, comma_index)`.
- **`quiz_questions`** — flat quiz bank. Columns: `number`, `question_id`, `topic`, `text`, `correct_answer`, `image_filename`, `embedding VECTOR(1536)`. Unique on `(number)`.

Embedding dimension is **1536** (`text-embedding-3-small`). Changing the model to one with a different dimension requires `db/init.sql` update + Docker volume recreate + full re-ingest.

### Ingestion pipelines

**Knowledge corpus** (`uv run ingest-knowledge`):
1. `CleaningPipeline`: `data/parsed/` → `ArticleCleaner` → `data/cleaned/` (idempotent, skips if cleaned file exists)
2. `IndexingPipeline`: `data/cleaned/` → `ArticleChunker` → `_filter_chunks` (skips `is_repealed` unless `embed_repealed=True`) → `LiteLLMEmbeddingClient.embed_passages([chunk.embedded_text])` in batches → `KnowledgeChunkStoreRepository.truncate() + bulk_insert()`. `embedded_text = f"{article_title} {chunk_text}"`.

**Quiz bank** (`uv run ingest-quiz`):
1. `QuizIndexingPipeline`: `data/parsed/quiz-patente-ab/quiz-patente-ab.json` → `QuizQuestionMapper` (flatten + dedup 8 exact duplicates → 7098 rows) → `_assign_embeddings` → `QuizQuestionStoreRepository.truncate() + bulk_insert()`. `embedded_text = f"{topic} {text}"`.

Both pipelines are **full-reload** (truncate + bulk insert). `embed_passages` is batched (`embedding_batch_size=64` in config).

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
