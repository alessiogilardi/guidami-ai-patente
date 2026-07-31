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
  `execute_many_returning`/`fetch`/`truncate`. `execute_many_returning` runs
  a batched `executemany(..., returning=True)` and drains each statement's
  `RETURNING` rows (`fetchall()` + `cursor.nextset()` loop), returning one
  row per input row, in input order — the way to get DB-generated ids back
  from a bulk insert without a follow-up `SELECT`. All query-accepting
  methods take `sql.SQL | sql.Composed` (not just `sql.Composed`), since a
  literal `sql.SQL(...)` with no `.format()` call is not itself `Composed`.
  The `%s::vector` cast requirement for vector parameters is documented in
  `.claude/rules/code-conventions.md` — see there for the rule, not
  restated here.

## Main schema

Three tables, all defined in `db/init.sql` (the `vector` extension is
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
├── exact_keywords (TEXT[], nullable)       -- CdS technical terms, retrieval key
├── rule_explanation (TEXT, nullable)       -- serving payload, not a retrieval key
├── created_at (TIMESTAMPTZ, NOT NULL DEFAULT now())  -- load-batch timestamp
├── embedding (VECTOR(1536), nullable)
├── INDEX idx_quiz_questions_topic (topic)
└── INDEX idx_quiz_questions_question_id (question_id)

llm_call_logs
├── id (PK, BIGSERIAL)
├── created_at (TIMESTAMPTZ, NOT NULL DEFAULT now())
├── caller (TEXT, NOT NULL)               -- agent/pipeline stage, e.g. "image_description"
├── model (TEXT, NOT NULL)
├── system_prompt (TEXT, nullable)
├── prompt (TEXT, NOT NULL)               -- rendered user prompt, text only (no images)
├── response (TEXT, nullable)             -- NULL on failed calls
├── input_tokens (INTEGER, nullable)
├── output_tokens (INTEGER, nullable)
├── total_tokens (INTEGER, nullable)      -- provider value verbatim, not enforced == input + output
├── cost_usd (NUMERIC(12,6), nullable)    -- OpenRouter's own reported cost, summed per call; NULL when absent
├── status (TEXT, NOT NULL DEFAULT 'success')  -- "success" | "error"
├── error_message (TEXT, nullable)
├── latency_ms (INTEGER, nullable)         -- monotonic duration (time.perf_counter), not derived from start/end_time
├── start_time (TIMESTAMPTZ, nullable)     -- wall-clock call start
├── end_time (TIMESTAMPTZ, nullable)       -- wall-clock call end
├── INDEX idx_llm_call_logs_created_at (created_at)
└── INDEX idx_llm_call_logs_caller (caller)
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

`llm_call_logs` is populated by every tracked `BaseAgent` call — see
`docs/patterns.md` (observability rows), `docs/architecture.md` (prepare-path
wiring), and `docs/adr/0004-openrouter-native-cost-tracking.md` for the
mechanism; this section documents only what each column holds. Column
semantics worth noting: `start_time`/`end_time` are wall-clock
`datetime.now(UTC)` stamps, whereas `latency_ms` is measured separately with the
monotonic `time.perf_counter()`, so it is not guaranteed to equal
`end_time - start_time` under clock adjustments. `cost_usd` is OpenRouter's own
reported cost, summed synchronously in `PydanticAILlmCallCapture.record()` across
every `ModelResponse` in the call (no litellm pricing lookup, no deferred
computation); it stays `NULL` when OpenRouter omits a cost. Failures are
first-class: `status`/`error_message` are always populated, while `response` and
the token/cost/latency/timestamp columns are nullable so a failed call is still
loggable. Tracking is opt-in per `BaseAgent` instance (`tracker` ctor param,
`None` by default) — only the ingestor's `prepare` CLI path wires it today.

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

*Last updated: 2026-07-31 — verified against commit `d512325`.*
