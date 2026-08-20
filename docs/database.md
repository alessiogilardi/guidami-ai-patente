# Database

## Engine and connection

- **PostgreSQL 16 + pgvector**, image `pgvector/pgvector:pg16`, run via
  `docker/docker-compose.yml`. Data persists to a host bind mount at
  `docker/.volumes/postgres_data` (untracked — see `.gitignore`)
  rather than a Docker-managed named volume, so the data directory is
  visible/removable directly from the repo tree; port/credentials
  configurable through `docker/.env` (`POSTGRES_USER`/`PASSWORD`/`DB`/`PORT`,
  default `guidami` / `guidami_ai_patente` / `5432`).
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
  `truncate(self, *table_names: str)` accepts one or more table names and
  emits **one** combined `TRUNCATE TABLE t1, t2, ...` statement — this is
  required, not just convenient: Postgres unconditionally refuses to
  `TRUNCATE` a table referenced by a live FK constraint (regardless of row
  count or the ordering of separate sequential `TRUNCATE` calls) unless the
  referencing table is named in the *same* statement, or `CASCADE` is used.
  `article_commas` (FK to `articles`) must always be named alongside
  `articles` in one call, e.g. `client.truncate("article_commas",
  "articles")` — `CASCADE` was deliberately rejected as the fix, since it
  would silently empty any future table that gains an FK to `articles`, not
  just the one known today. Every pre-existing single-table call site
  (`quiz_questions`, `llm_call_logs`, `UpsertStoreRepository`'s own
  table) is unaffected — a single positional argument is just a 1-tuple.
  Real consumer (spec 0001 T-16): `cli/commands/reset.py`'s `knowledge`
  branch calls `postgres_client.truncate(config.article_commas_table,
  config.articles_table)` directly — **not** two separate
  `ArticleCommaStoreRepository(...).truncate()` /
  `ArticleStoreRepository(...).truncate()` calls, which was the first
  implementation attempt and crashes against a live Postgres for exactly
  the FK reason above (each repository's `truncate()` only ever emits a
  single-table statement). The cross-table call bypasses the repository
  layer's `truncate()` for this one case since the capability is
  client-level, not repository-level.

## Main schema

Six tables, all defined in `db/init.sql` (the `vector` extension is
enabled at the top of that file).

```text
articles
├── id (PK, BIGSERIAL)
├── source (TEXT, NOT NULL)               -- "cds" | "cap" | "reg" | "amb"
├── number (TEXT, NOT NULL)
├── title (TEXT, NOT NULL)
├── url (TEXT, NOT NULL)
├── scraped_at (TIMESTAMPTZ, NOT NULL)    -- no default; always app-supplied by ArticleMapper
├── is_repealed (BOOLEAN, NOT NULL DEFAULT FALSE)
├── tsv_title (TSVECTOR, GENERATED ALWAYS ... STORED)  -- setweight(to_tsvector('italian', title), 'A')
├── UNIQUE (source, number)
└── INDEX idx_articles_tsv_title (tsv_title) USING GIN

article_commas
├── id (PK, BIGSERIAL)
├── article_id (BIGINT, NOT NULL, REFERENCES articles(id) ON DELETE CASCADE)
├── comma_number (TEXT, NOT NULL)
├── position (INT, NOT NULL)              -- source order within the article
├── text (TEXT, NOT NULL)
├── is_repealed (BOOLEAN, NOT NULL DEFAULT FALSE)
├── embedding (VECTOR(1536), nullable)
├── tsv_text (TSVECTOR, GENERATED ALWAYS ... STORED)  -- setweight(to_tsvector('italian', text), 'B')
├── UNIQUE (article_id, comma_number)
├── INDEX idx_article_commas_article_id (article_id)
└── INDEX idx_article_commas_tsv_text (tsv_text) USING GIN

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
├── vector_search_queries (TEXT[], nullable) -- phrases the query vector is built from
├── rule_explanation (TEXT, nullable)       -- serving payload, not a retrieval key
├── created_at (TIMESTAMPTZ, NOT NULL DEFAULT now())  -- load-batch timestamp
├── INDEX idx_quiz_questions_topic (topic)
└── INDEX idx_quiz_questions_question_id (question_id)

quiz_question_embeddings                    -- query representations, two axes
├── id (PK, BIGSERIAL)
├── quiz_question_id (BIGINT, NOT NULL, REFERENCES quiz_questions(id) ON DELETE CASCADE)
├── variant (TEXT, NOT NULL)                -- WHICH TEXT was embedded: a row
├── embedding_3_small (VECTOR(1536), nullable) -- WHICH MODEL produced it: a column
├── created_at (TIMESTAMPTZ, NOT NULL DEFAULT now())
├── UNIQUE (quiz_question_id, variant)
├── CHECK (num_nonnulls(embedding_3_small) > 0)  -- widen when adding a model column
└── INDEX idx_quiz_question_embeddings_variant (variant)

quiz_images                                 -- one row per image, not per question
├── filename (PK, TEXT)                     -- matches quiz_questions.image_filename
└── description (TEXT, nullable)            -- vision-generated, see ADR 0003

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

`articles.tsv_title` and `article_commas.tsv_text` (spec 0011, FR-1) are the
materialized halves of the corpus full-text index. They are **two** columns
rather than one because the weighting in use spans both tables — article title
in band A, comma text in band B, matching `_WEIGHTED_TSVECTOR` in
`src/commons/repositories/db/corpus_read_repository.py` — and a generated column
can only read its own row; ranking queries concatenate them
(`a.tsv_title || c.tsv_text`) via `ts_rank`/`ts_rank_cd`. Being
`GENERATED ALWAYS ... STORED`, they are never written by application code and
cannot fall behind their source text. The two-argument
`to_tsvector('italian', ...)` form is required: the one-argument form depends on
`default_text_search_config` and is not `IMMUTABLE`, so `STORED` would be
rejected.

Matching against *both* columns cannot be a plain `a.tsv_title @@ q OR
c.tsv_text @@ q`: PostgreSQL never turns a predicate whose `OR` branches
reference two different joined relations into an index condition on either
side — it can only evaluate it as a post-join filter, so neither GIN index is
ever touched, regardless of join strategy or statistics. `CorpusReadRepository`'s
`text_match_top_k` (`_text_match_query`) instead unions two single-relation id
sets — one filtered by `idx_articles_tsv_title`, one by
`idx_article_commas_tsv_text` — and rejoins the union for projection/scoring.
See `docs/adr/0015-union-decomposed-cross-relation-text-match.md` for the
full alternatives considered.

`articles`/`article_commas` replaced the former single `knowledge_chunks`
table (spec 0001 T-7): one row per article plus one row per comma, FK-linked
with `ON DELETE CASCADE`, instead of one row per comma with the article's
fields duplicated on every row. Domain entities:
`src/domain/entities/knowledge/article.py::ArticleEntity` and
`article_comma.py::ArticleCommaEntity` (both plain `BaseModel`s, no `id` field —
DB-generated; `ArticleCommaEntity.article_id` **is** included, since it's a
caller-supplied FK, not DB-generated). The superseded `KnowledgeChunk` entity
and `knowledge_chunks` table (one row per comma with the article's fields
duplicated on every row) have both been fully removed (spec 0001 T-7/T-15).
`ArticleEntity.scraped_at` is application-supplied (not DB-generated).
`CleanedArticleModel.scraped_at` is itself typed `datetime` (pydantic v2
auto-parses the ISO-8601 string produced by `ParsedArticleModel.scraped_at`
at the parsed→cleaned mapping boundary), so
`ArticleMapper.from_cleaned_to_article_entity` just copies the value through
— see `docs/adr/0007-utc-timestamp-convention.md` for the project's full UTC
timestamp convention (app/log/DB).

The former `quiz_metadata` JSONB blob was flattened into the retrieval/payload
columns above (see `docs/adr/0002-flatten-quiz-metadata-columns.md`);
`vector_search_queries` joined them later, once it stopped being pure embedder
input and became the thing under test — and is now the one metadata field actually
persisted on `quiz_questions` (spec 0008 Phase 1); `core_concepts`/`exact_keywords`/
`rule_explanation` continue to flatten the same way. The metadata columns are
all-or-nothing: `NULL` on rows for which no `QuizMetadata` was generated.
`quiz_questions` now writes through upsert (on `number`) + reconciliation
(`QuizQuestionStoreRepository.delete_missing`, whole-table scope — quiz has a
single source, unlike `ArticleStoreRepository.delete_missing`'s per-source scope)
instead of truncate + bulk-insert (spec 0008 Phase 1, superseding the `DbStoreStep`
full-reload path — see `docs/patterns.md`), so `quiz_questions.created_at`, like
`articles`/`article_commas`' upsert path (spec 0010), now survives across runs
instead of recording each load-batch's timestamp.

Quiz vectors live in `quiz_question_embeddings`, not on `quiz_questions`, along
two orthogonal axes: **which text** was embedded is a row (`variant`), **which
model** produced the vector is a column (`embedding_*`). pgvector fixes the
dimension in the column type, so models of different dimensionality cannot share
a column. A representation never computed is an absent row; a model not yet run
for an existing row is a `NULL` column — hence the table-level `CHECK` rather than
a per-column `NOT NULL`. Adding a representation costs an ingest run; adding a
model costs one `ADD COLUMN` plus widening that `CHECK`.

`quiz_images` is keyed by filename because a description belongs to an image, not
to a question: 4147 questions reference 427 distinct images
(`docs/adr/0003-group-road-sign-description-by-image.md`).

No index exists on any embedding column (no ivfflat/hnsw) — vector search runs as
an exact `<=>` scan. No index yet on the `TEXT[]` metadata columns (GIN/FTS
deferred with the hybrid-search work).

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

There is still no migration **tool** (no Alembic). `db/init.sql` remains the
definition of the target schema: it's mounted read-only into the Postgres
container's `/docker-entrypoint-initdb.d/` and only runs when the data directory
is empty, so it alone can never alter an existing database.

Two paths now exist, and a schema change must take **both**:

1. **Fresh environment** — edit `db/init.sql`; a newly created volume gets the
   new schema automatically.
   ```bash
   docker compose -f docker/docker-compose.yml down
   rm -rf docker/.volumes/postgres_data
   docker compose -f docker/docker-compose.yml up -d
   ```
2. **Existing database** — write a matching script under `db/migrations/`, named
   after the spec that introduces it, and apply it with `psql -f`. Migration
   scripts are idempotent (`IF EXISTS`/`IF NOT EXISTS`, guarded `DO $$` blocks) and
   wrapped in a single transaction, so a re-run is a no-op and a failure leaves the
   schema untouched. Data-preserving steps come *before* destructive ones: see
   `db/migrations/0008_quiz_query_representations.sql`, which moves
   `quiz_questions.embedding` into the variant table before dropping the column.
   `db/migrations/0011_retrieval_golden_set.sql` (purely additive: the two generated
   `tsvector` columns and their GIN indexes) shows the other idempotency shape — a
   generated column cannot be added with `ADD COLUMN IF NOT EXISTS`, so each
   `ALTER TABLE` sits inside a `DO $$` block guarded on `information_schema.columns`,
   while the indexes use plain `CREATE INDEX IF NOT EXISTS`.

Because there is no tool enforcing it, the two paths can silently diverge — a
migrated database and a freshly initialised one drifting apart is the standing risk
of this arrangement. Every migration therefore ships an `information_schema`
equivalence check to be run against both and diffed; treat any difference as a bug
in one of the two files, not as an acceptable variation.

There is no changelog file tracking schema history beyond `git log db/init.sql`
and the contents of `db/migrations/`.

> **Current state:** `db/init.sql` and `db/migrations/0008_*.sql` carry the spec
> 0008 schema (spec status: `ready`). The Python write path now covers all three
> new/changed tables: `quiz_questions` (via `QuizQuestionStoreRepository`, upsert +
> reconciliation), `quiz_images` (via `QuizImageStoreRepository`, upsert-only — no
> reconciliation, orphaned rows are a deferred open question), and, as of Phase 2,
> `quiz_question_embeddings` (via `QuizQuestionEmbeddingStoreRepository`, upsert on
> `(quiz_question_id, variant)`, likewise no reconciliation for a variant that stops
> being produced — same deferred-open-question shape). `StoreQuizStep`
> (`orchestrators/steps/quiz/store_quiz_step.py`) upserts all three in one step,
> resolving each question's DB-generated `id` via `upsert_returning_ids` before
> writing its variant rows against it.

*Last updated: 2026-08-04 — verified against commit `2248dcc`; switched the Postgres
volume from a named Docker volume to a bind mount at `docker/.volumes/postgres_data`
(gitignored; moved here from a repo-root `.volumes/` in the same change); `down -v`
in the reset instructions replaced with an explicit `rm -rf docker/.volumes/postgres_data`
since there is no named volume left for `-v` to remove.*

*Last updated: 2026-08-04 — verified against commit `2248dcc`; `articles` gained a
required `scraped_at TIMESTAMPTZ NOT NULL` column (no default), populated from
`CleanedArticleModel.scraped_at` (now typed `datetime`, not `str`) via
`ArticleMapper.from_cleaned_to_article_entity` (`docs/adr/0007-utc-timestamp-convention.md`)
— previously computed by the scraper and silently dropped before persistence.*

*Last updated: 2026-08-01 — verified against commit `3cce407`; `knowledge_chunks`
replaced by `articles`/`article_commas` (spec 0001 T-7/T-8); `PostgresClient.truncate()`
widened to accept multiple table names (FK-truncate fix); documented `reset.py`'s
real usage of it (T-16) after a two-repository-calls first attempt was caught crashing
against a live Postgres; `KnowledgeChunk` entity deleted, spec 0001 fully implemented (T-15);
`Article`/`ArticleComma` entities renamed to `ArticleEntity`/`ArticleCommaEntity`;
`articles.source` gained `"reg"` as a third value (spec 0003 Phase 1, FR-4) — no DDL
change, `UNIQUE (source, number)` already prevented collision with CdS's overlapping
article numbers.*

*Last updated: 2026-08-05 — verified against commit `6d96b7d`; `quiz_questions` gained
`vector_search_queries TEXT[]` and lost `embedding`, which moved to the new
`quiz_question_embeddings` table (variant = which text, `embedding_*` = which model);
new `quiz_images` table keyed by filename. The Migrations section now documents the
`db/migrations/` path alongside the wipe-and-reinit one, and their drift risk (spec 0008,
ADR 0010). Not yet applied to the local dev database.*

*Last updated: 2026-08-06 — verified against commit `068c765`; `articles`/`article_commas`
moved off the truncate + bulk-insert reload strategy onto upsert-on-natural-key plus a
reconciling delete scoped to the run (spec 0010, AD-1/AD-2) — `ArticleStoreRepository`/
`ArticleCommaStoreRepository` now extend `UpsertStoreRepository` (renamed from
`BulkInsertStoreRepository`, which is deleted) and no longer expose `delete_source`. The
`created_at` caveat under "Main schema" is narrowed to `quiz_questions`, the one table it
ever applied to; it still holds until spec 0008's FR-6 replaces the quiz write path too.*

*Last updated: 2026-08-06 — verified against commit `598690c`; `articles.source` gained
`"amb"` as a fourth value (D.Lgs. 152/2006, Codice dell'Ambiente — spec 0009 FR-3) — no
DDL change, `UNIQUE (source, number)` already prevented collision.*

*Last updated: 2026-08-06 — verified against commit `598690c`; `quiz_questions` moved off
truncate + bulk-insert onto upsert (on `number`) + whole-table reconciliation
(`QuizQuestionStoreRepository.delete_missing`, no `source` param — quiz has a single
source, unlike the knowledge side), so its `created_at` caveat no longer applies (spec
0008 Phase 1, superseding the `DbStoreStep`/`StoreRepository` full-reload path — both
deleted, zero remaining callers). New `QuizImageStoreRepository` (upsert-only on
`filename`, no reconciliation — orphaned rows are a deferred open question) writes
`quiz_images`. `quiz_question_embeddings` still has no write path (Phase 2). Corrected
the stale "Current state" note under Migrations: `db/init.sql` already carries the
target schema and spec 0008's status is `ready`, not `draft`.*

*Last updated: 2026-08-07 — verified against commit `bbbb291`; spec 0008 Phase 2 landed
the write path for `quiz_question_embeddings`: new `QuizQuestionEmbeddingStoreRepository`
(upsert on `(quiz_question_id, variant)`, no reconciliation — same deferred-open-question
shape as `quiz_images`), populated via a new variant registry (`quiz_variant_registry.py`,
six representations — `text`/`topic_text`/`search_queries`/`combined`/
`combined_description`/`image_description`) and `EmbedQuizVariantsService`, which replaces
`EmbedQuizMetadata`. `StoreQuizStep` now writes all three quiz tables (questions, images,
variant rows) in one step, resolving `quiz_question_id` via `upsert_returning_ids` before
the variant rows are built. The "Current state" note under Migrations no longer lists a
missing write path — the schema is unchanged, only the Python side caught up.*

*Last updated: 2026-08-07 — verified against commit `bbec1a0` (working tree ahead of it,
uncommitted on `feat/ingestion`); `EmbedQuizVariants` → `EmbedQuizVariantsService` (no schema
change, `services/`-folder naming rename only).*

*Last updated: 2026-08-19 — verified against commit `2dd56724` (working tree ahead:
spec 0011 phase 1, T-2/T-3); `articles` gained the generated `tsv_title` and `article_commas`
the generated `tsv_text`, each with a GIN index, plus a paragraph on why the corpus
full-text vector is two columns and not one, and the Migrations section now names
`0011_retrieval_golden_set.sql` as the guarded-`DO $$` idempotency shape.*

*Last updated: 2026-08-19 — verified against commit `2dd56724` (working tree ahead:
spec 0011 phase 1 round 2, AD-13/AD-14); corrected the full-text-match paragraph — the
two generated columns are no longer matched with a plain cross-table `OR`, which
PostgreSQL can never turn into an index condition; `text_match_top_k` now unions two
single-relation-filtered id sets instead (ADR 0015).*
