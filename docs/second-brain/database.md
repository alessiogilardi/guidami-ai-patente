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
  Real consumer (spec 0001 T-16, widened by spec 0012 Task 9/FR-17/AD-28):
  `cli/commands/reset.py`'s `knowledge` branch calls
  `postgres_client.truncate(config.quiz_comma_labels_table,
  config.quiz_labelings_table, config.article_commas_table,
  config.articles_table)` directly — **not** four separate per-repository
  `.truncate()` calls, which was the first implementation attempt (`article_commas`/
  `articles` only) and crashes against a live Postgres for exactly the FK reason
  above; `quiz_comma_labels` (added on `feat/backend` after that first attempt,
  spec 0012) has a live FK into `article_commas`, so the original two-table
  statement is broken against the current schema, not merely incomplete. The
  cross-table call bypasses the repository layer's `truncate()` for this one case
  since the capability is client-level, not repository-level. The branch also
  guards the wipe: `_validated_labeling_count` (CLI-only helper,
  `cli/commands/reset.py`, counts `quiz_labelings` rows with `validated_at IS NOT
  NULL`) makes it refuse with `SystemExit` when a human-validated labeling would
  be destroyed, unless `--force` is passed — the preview stays fully
  connection-free per FR-17 (no live count shown without `--apply`).
- **`ingest reset quiz` is known broken, deliberately deferred (spec 0012,
  AD-28 addressed only the `knowledge` branch above).** `quiz_labelings.
  quiz_question_id` references `quiz_questions` with `ON DELETE CASCADE`
  (same table above), so `cli/commands/reset.py`'s `quiz` branch — still
  `postgres_client.truncate(config.quiz_question_embeddings_table,
  config.quiz_questions_table)`, a two-table statement — fails against the
  live schema with the identical FK error the `knowledge` branch was fixed
  for, and does so today with 14 rows present in `quiz_labelings`. The fix
  is the same shape (name `quiz_comma_labels` and `quiz_labelings` in the
  same `TRUNCATE`, add the validated-labeling guard) and is out of scope for
  this plan — recorded in code as a `KNOWN BROKEN, deferred` comment at the
  `case "quiz":` branch rather than silently left to surface as a bare FK
  error.

## Main schema

Eleven tables, all defined in `db/init.sql` (the `vector` extension is
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

labeling_runs                               -- one row per golden-set labeling pass (spec 0011 phase 2;
                                             -- origin/lexeme_fields/nullable corpus_commit: spec 0012, AD-8)
├── id (PK, BIGSERIAL)
├── judge_model (TEXT, NOT NULL)
├── prompt_version (TEXT, NOT NULL)         -- sha256(system + user)[:16], see run_provenance.py
├── candidate_variant (TEXT, NOT NULL)      -- quiz_question_embeddings.variant used for retrieval
├── dense_k (INT, NOT NULL)
├── text_k (INT, NOT NULL)
├── lexeme_fields (TEXT[], NOT NULL)        -- sixth epoch field (spec 0012); canonicalised sorted
│                                           -- (LabelingRunEntity / require_canonical_lexeme_fields),
│                                           -- compared as a whole array by FR-8's precedence query
├── shuffle_seed (BIGINT, NOT NULL)         -- seeds both the presentation shuffle and --limit's subset draw
├── corpus_commit (TEXT, nullable)          -- `git rev-parse HEAD` at run time; NULL only for a live run
├── corpus_comma_count (INT, NOT NULL)      -- count(*) over article_commas, unfiltered
├── question_limit (INT, nullable)          -- NULL means an unrestricted (full) pass
├── origin (TEXT, NOT NULL DEFAULT 'batch') -- CHECK IN ('batch', 'live'); LabelingRunOrigin
├── created_at (TIMESTAMPTZ, NOT NULL DEFAULT now())
├── CHECK (origin <> 'batch' OR corpus_commit IS NOT NULL)  -- labeling_runs_batch_has_corpus_commit
└── UNIQUE INDEX uq_labeling_runs_live_config
        (judge_model, prompt_version, candidate_variant, dense_k, text_k, lexeme_fields)
        WHERE origin = 'live'               -- one live run per configuration epoch (spec 0012, AD-8/FR-9)

quiz_labelings                              -- one row per labeled question within a run
├── id (PK, BIGSERIAL)
├── run_id (BIGINT, NOT NULL, REFERENCES labeling_runs(id) ON DELETE CASCADE)
├── quiz_question_id (BIGINT, NOT NULL, REFERENCES quiz_questions(id) ON DELETE CASCADE)
├── rationale (TEXT, NOT NULL)              -- the judge's own rationale, empty-list case included
├── validated_at (TIMESTAMPTZ, nullable)    -- human validation of the labeling as a whole (spec 0012, AD-9)
├── validated_by (TEXT, nullable)
├── has_supporting_commas (BOOLEAN, NOT NULL DEFAULT FALSE)  -- denormalised outcome (spec 0012, AD-10);
│                                           -- computed by GoldenSetWriteRepository.insert_labeling from the
│                                           -- same comma-id array that feeds quiz_comma_labels, never
│                                           -- caller-supplied — see patterns.md
├── created_at (TIMESTAMPTZ, NOT NULL DEFAULT now())
├── UNIQUE (run_id, quiz_question_id)
├── CHECK ((validated_at IS NULL) = (validated_by IS NULL))  -- quiz_labelings_validation_complete
├── INDEX idx_quiz_labelings_run_id (run_id)
└── INDEX idx_quiz_labelings_question_recent (quiz_question_id, created_at DESC)  -- hot read-by-question path
    -- pre-spec-0012 the outcome had no column at all (derived purely by counting
    -- quiz_comma_labels children); has_supporting_commas denormalises that same fact
    -- for a hot read path, but the derivation rule (0 children = "corpus doesn't
    -- justify it") and its transactional computation are unchanged, see AD-6/AD-10

quiz_comma_labels                           -- the judge's per-candidate verdicts (<=3 per labeling)
├── labeling_id (BIGINT, NOT NULL, REFERENCES quiz_labelings(id) ON DELETE CASCADE)
├── article_comma_id (BIGINT, NOT NULL, REFERENCES article_commas(id) ON DELETE CASCADE)
├── judge_rank (INT, NOT NULL, CHECK > 0)   -- judge's own order, most-justifying first (1-based)
├── dense_rank (INT, nullable)              -- 1-based rank within the dense arm, NULL if not retrieved there
├── text_rank (INT, nullable)               -- 1-based rank within the text arm, NULL if not retrieved there
├── PRIMARY KEY (labeling_id, article_comma_id)
├── CHECK (dense_rank IS NOT NULL OR text_rank IS NOT NULL)  -- quiz_comma_labels_at_least_one_arm
└── UNIQUE (labeling_id, judge_rank)        -- quiz_comma_labels_unique_judge_rank: guards a *code*
    -- defect (a mis-built loop), not a model one — CommaLabelerResponse already rejects a
    -- repeated ordinal before the write path is reached (spec 0011 phase 2, T-1)

users                                       -- Telegram user whitelist for the bot (spec 0016, AD-2)
├── id (PK, BIGSERIAL)
├── telegram_user_id (BIGINT, NOT NULL, UNIQUE)
├── registered (BOOLEAN, NOT NULL DEFAULT false)  -- flipped manually by the project owner
└── created_at (TIMESTAMPTZ, NOT NULL DEFAULT now())

quiz_answers                                -- one row per submitted answer (spec 0016, AD-3)
├── id (PK, BIGSERIAL)
├── user_id (BIGINT, NOT NULL, REFERENCES users(id))
├── quiz_id (BIGINT, NOT NULL, REFERENCES quiz_questions(id))
├── session_id (TEXT, NOT NULL)              -- opaque tag copied from the bot's per-QuizSession seed
├── user_answer (BOOLEAN, NOT NULL)          -- raw submitted value; correctness always derived via JOIN
├── answer_datetime (TIMESTAMPTZ, NOT NULL DEFAULT now())
├── INDEX idx_quiz_answers_user_id (user_id)
├── INDEX idx_quiz_answers_quiz_id (quiz_id)
└── INDEX idx_quiz_answers_session_id (session_id)
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
See `docs/second-brain/adr/0015-union-decomposed-cross-relation-text-match.md` for the
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
— see `docs/second-brain/adr/0007-utc-timestamp-convention.md` for the project's full UTC
timestamp convention (app/log/DB).

The former `quiz_metadata` JSONB blob was flattened into the retrieval/payload
columns above (see `docs/second-brain/adr/0002-flatten-quiz-metadata-columns.md`);
`vector_search_queries` joined them later, once it stopped being pure embedder
input and became the thing under test — and is now the one metadata field actually
persisted on `quiz_questions` (spec 0008 Phase 1); `core_concepts`/`exact_keywords`/
`rule_explanation` continue to flatten the same way. The metadata columns are
all-or-nothing: `NULL` on rows for which no `QuizMetadata` was generated.
`quiz_questions` now writes through upsert (on `number`) + reconciliation
(`QuizQuestionStoreRepository.delete_missing`, whole-table scope — quiz has a
single source, unlike `ArticleStoreRepository.delete_missing`'s per-source scope)
instead of truncate + bulk-insert (spec 0008 Phase 1, superseding the `DbStoreStep`
full-reload path — see `docs/second-brain/patterns.md`), so `quiz_questions.created_at`, like
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
(`docs/second-brain/adr/0003-group-road-sign-description-by-image.md`).

`users`/`quiz_answers` (spec 0016, AD-2/AD-3) back the bot's authorization gate and
answer history. A `users` row is provisioned on first Telegram contact with
`registered = false`; there is no in-app tooling to flip it — the project owner does
so with a direct `UPDATE users SET registered = true WHERE telegram_user_id = ...`
(spec 0016 Non-Goals). `quiz_answers.user_id`/`quiz_id` are surrogate FKs, never
resolved to a Python value anywhere in the design; `session_id` is a plain `TEXT` tag,
not a FK, since nothing needs session-level metadata beyond grouping answers by it —
it is the same opaque seed the bot's `QuizSession` already carries (spec 0015, AD-2).
`user_answer` stores only the raw submitted boolean: correctness is always derived by
joining back to `quiz_questions.correct_answer` at read time (`QuizAnswerRepository
.session_summary`), never cached, so it cannot drift out of sync — the same rule
AD-3 already applies to answer-checking elsewhere in this spec. No deduplication: the
same question answered twice (same or different session) produces two rows.

No index exists on any embedding column (no ivfflat/hnsw) — vector search runs as
an exact `<=>` scan. No index yet on the `TEXT[]` metadata columns (GIN/FTS
deferred with the hybrid-search work).

`llm_call_logs` is populated by every tracked `BaseAgent` call — see
`docs/second-brain/patterns.md` (observability rows), `docs/second-brain/architecture.md` (prepare-path
wiring), `docs/second-brain/adr/0004-openrouter-native-cost-tracking.md` for the cost
mechanism, and `docs/second-brain/adr/0025-context-manager-tracker-port.md` for the
tracker port shape. Its row entity, `LlmCallLogEntity`, lives at
`src/commons/ai/observability/entities/llm_call_log.py` (moved out of the now-removed
`domain/entities/observability/`). The table name itself is no longer hardcoded:
`ObservabilityConfig.table` (default `"llm_call_logs"`, `src/commons/ai/observability/configs/`)
is passed into `PostgresLlmCallLogRepository`'s constructor — this section documents the
default schema, not a fixed one. Column
semantics worth noting: `start_time`/`end_time` are wall-clock
`datetime.now(UTC)` stamps, whereas `latency_ms` is measured separately with the
monotonic `time.perf_counter()`, so it is not guaranteed to equal
`end_time - start_time` under clock adjustments. `cost_usd` is OpenRouter's own
reported cost, summed synchronously in `PydanticAILlmCallRecorder.record()` (via
the module-level `_call_cost()` helper, `adapters/pydantic_ai_llm_call_recorder.py`)
across every `ModelResponse` in the call (no litellm pricing lookup, no deferred
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
   `db/migrations/0012_quiz_flow_api.sql` (spec 0012) shows a third shape — a plain
   column takes `ADD COLUMN IF NOT EXISTS`, but a named `CHECK`/`UNIQUE` constraint has
   no `IF NOT EXISTS` form at all, so each is guarded by a `DO $$` block checking
   `pg_constraint.conname` first. It also backfills two columns
   (`labeling_runs.lexeme_fields` from the config value the pre-existing runs were
   produced under, `quiz_labelings.has_supporting_commas` from the existing
   `quiz_comma_labels` child count) before dropping the temporary `DEFAULT` that made
   the `ADD COLUMN ... NOT NULL` step possible on non-empty tables.

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
`ArticleMapper.from_cleaned_to_article_entity` (`docs/second-brain/adr/0007-utc-timestamp-convention.md`)
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
single-relation-filtered id sets instead (ADR 0018).*

*Last updated: 2026-08-25 — verified against commit `2cc0710a` (working tree ahead:
spec 0012, folded commit tasks 7+2+8); `labeling_runs` gained `origin` (batch/live
provenance) and `lexeme_fields` (the sixth configuration-epoch field, canonicalised
sorted) plus the partial unique index `uq_labeling_runs_live_config` enforcing one
live run per epoch; `corpus_commit` became nullable, guarded by
`labeling_runs_batch_has_corpus_commit` so a batch run still requires it.
`quiz_labelings` gained `validated_at`/`validated_by` (paired by
`quiz_labelings_validation_complete`) and the denormalised `has_supporting_commas`
outcome flag, plus `idx_quiz_labelings_question_recent` for the hot read-by-question
path. New migration `db/migrations/0012_quiz_flow_api.sql`.*

*Last updated: 2026-08-21 — verified against commit `e4977a94` (working tree ahead:
spec 0011 phase 2, T-1/T-2/T-9); three new tables — `labeling_runs`, `quiz_labelings`,
`quiz_comma_labels` — persist the retrieval golden set. Outcome is derived by counting
`quiz_comma_labels` children, never stored (AD-6); `insert_labeling` writes a labeling's
parent row and its children atomically via a single data-modifying CTE, worked around
`PostgresClient` having no transaction API (PD-15). Noted the `truncate()` convention now
also covers `quiz_comma_labels`/`quiz_labelings`'s new FKs.*

*Last updated: 2026-08-25 — verified against commit `b6e34f4d` (working tree ahead:
spec 0012 Task 9, FR-17/AD-28); `reset knowledge` widened to a single four-table
`TRUNCATE` (`quiz_comma_labels, quiz_labelings, article_commas, articles`) — the
prior two-table statement was already broken against this schema once
`quiz_comma_labels` landed, not just prospectively incomplete — and gained a
`--force`-overridable guard refusing to destroy a human-validated `quiz_labelings`
row.*

*Last updated: 2026-08-25 — verified against commit `c77de38a` (quiz-flow-api-phase1
plan Task 11); recorded that `ingest reset quiz` is known broken for the identical FK
reason `reset knowledge` was, deliberately deferred rather than fixed in this plan
(spec 0012, AD-28 — the AD's own fix covered only the `knowledge` branch).*

*Last updated: 2026-08-28 — verified against commit `ab1b8f82`; the `llm_call_logs`
paragraph now points at `LlmCallLogEntity`'s new location
(`commons/ai/observability/entities/llm_call_log.py`, moved out of the removed
`domain/entities/observability/`) and notes the table name is configurable via
`ObservabilityConfig.table` (default unchanged, `"llm_call_logs"`) rather than
hardcoded — see `adr/0025-context-manager-tracker-port.md`.*

*Last updated: 2026-08-28 — verified against commit `ee22bcdf`; fixed an internal
inconsistency left by the previous edit in this same paragraph — the `cost_usd`
sentence still named the deleted `PydanticAILlmCallCapture.record()`; corrected to
`PydanticAILlmCallRecorder.record()` (which delegates to the module-level
`_call_cost()` helper in `adapters/pydantic_ai_llm_call_recorder.py`).*

*Last updated: 2026-09-01 — verified against commit `51dcba1a`; fixed two stale
`adr/0020-context-manager-tracker-port.md` cross-references — the `feat/backend` merge
brought that ADR in under number 0020, colliding with this branch's own pre-existing
ADR 0020 (`dual-agents-dir-single-sourced-by-env-var.md`); renumbered the merged-in one
to ADR 0025 (`0020-dual-agents-dir...` keeps its original number, per the ADR-numbering
collision rule — the later-merged one renumbers).*

*Last updated: 2026-09-18 — verified against commit `68575993` (spec 0016, bot user
authorization & answer history, db-schema + backend plans). Two new tables: `users`
(Telegram whitelist, `registered` flipped manually, no in-app tooling by design) and
`quiz_answers` (one row per submitted answer, surrogate FKs to `users`/`quiz_questions`,
`session_id` a plain `TEXT` tag copied from the bot's `QuizSession` seed, no
deduplication). `AppConfig` gained `users_table`/`quiz_answers_table` fields, matching
every other table-name field's convention. Existing integration-test FK-truncate fixture
lists (`tests/guidami_ai_patente/api/routers/test_quiz_questions.py` and siblings) had to
widen to include `quiz_answers` once its FK into `quiz_questions` landed — see
`testing.md` for the fixture-list convention this confirms.*
