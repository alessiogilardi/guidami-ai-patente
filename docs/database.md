# Database

## Engine and connection

- **PostgreSQL 16 + pgvector**, image `pgvector/pgvector:pg16`, run via
  `docker/docker-compose.yml`. Single named volume (`postgres_data`);
  port/credentials configurable through `docker/.env`
  (`POSTGRES_USER`/`PASSWORD`/`DB`/`PORT`, default `guidami` /
  `guidami_ai_patente` / `5432`).
- **App-side connection config**: `PostgresConnectionConfig`
  (`src/commons/configs/postgres_connection_config.py`) — frozen Pydantic
  model with `host`, `port`, `user`, `password: SecretStr`, `dbname`,
  `sslmode`, `connect_timeout`. Populated from `.env` via
  `IngestorConfig.postgres` (`src/guidami_ai_patente_ingestor/configs/ingestor_config.py`),
  a `pydantic-settings` `BaseSettings` with `env_nested_delimiter="__"` —
  hence the `POSTGRES__USER` / `POSTGRES__PASSWORD` naming in `.env`
  (source precedence: init args > env/`.env` > `configs/ingestor_config.yaml`).
- **Client**: `PostgresClient` (`src/commons/clients/postgres_client.py`) —
  generic, table-agnostic psycopg3 wrapper; registers the pgvector adapter
  on connect; autocommit; context-manager support; `execute`/`execute_many`/
  `fetch`/`truncate`. The `%s::vector` cast requirement for vector
  parameters is documented in `.claude/rules/code-conventions.md` — see
  there for the rule, not restated here.

## Main schema

Two tables, both defined in `db/init.sql` (the `vector` extension is
enabled at the top of that file).

```text
knowledge_chunks
├── id (PK, BIGSERIAL)
├── source (TEXT, NOT NULL)               -- "cds" | "cap"
├── article_number (TEXT, NOT NULL)
├── article_title (TEXT, NOT NULL)
├── comma_index (INT, NOT NULL)
├── chunk_text (TEXT, NOT NULL)
├── context (TEXT, NOT NULL DEFAULT '')   -- LLM-generated context prefix
├── is_repealed (BOOLEAN, NOT NULL DEFAULT FALSE)
├── source_url (TEXT, NOT NULL)
├── embedding (VECTOR(1536), nullable)
└── UNIQUE (source, article_number, comma_index)

quiz_questions
├── id (PK, BIGSERIAL)
├── number (TEXT, NOT NULL, UNIQUE)
├── question_id (INTEGER, NOT NULL)
├── topic (TEXT, NOT NULL)
├── text (TEXT, NOT NULL)
├── correct_answer (BOOLEAN, NOT NULL)
├── image_filename (TEXT, nullable)
├── core_concepts (TEXT[], nullable)        -- flattened QuizMetadata retrieval key
├── named_entities (TEXT[], nullable)       -- named entities mentioned in the question
├── exact_keywords (TEXT[], nullable)       -- CdS technical terms, retrieval key
├── rule_explanation (TEXT, nullable)       -- serving payload, not a retrieval key
├── created_at (TIMESTAMPTZ, NOT NULL DEFAULT now())  -- load-batch timestamp
├── embedding (VECTOR(1536), nullable)
├── INDEX idx_quiz_questions_topic (topic)
└── INDEX idx_quiz_questions_question_id (question_id)
```

The former `quiz_metadata` JSONB blob was flattened into the four
retrieval/payload columns above (see `docs/adr/0002-flatten-quiz-metadata-columns.md`).
The metadata's `vector_search_queries` field is **not** persisted — it is only
the embedding input, consumed to produce `embedding`. The four metadata columns
are all-or-nothing: `NULL` on rows for which no `QuizMetadata` was generated
(aligned with `embedding` being `NULL` there). `created_at` is DB-managed and,
under the truncate + bulk-insert reload strategy, records the load-batch time,
not first ingestion.

No index exists on either `embedding` column (no ivfflat/hnsw) — vector
search currently runs as an exact `<=>` scan. No index yet on the `TEXT[]`
metadata columns (GIN/FTS deferred with the hybrid-search work).

## Migrations

There is no migration tool (no Alembic, no versioned migration files).
`db/init.sql` is the single source of schema truth: it's mounted
read-only into the Postgres container's `/docker-entrypoint-initdb.d/`
and only runs on **first** volume creation. Any schema change requires
tearing down and recreating the volume:

```bash
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d
```

(see also the "Infrastructure" section of `CLAUDE.md`). There is no
changelog file tracking schema history beyond `git log db/init.sql`.

*Last updated: 2026-07-11 — verified against commit `f4a0936`.*
