-- Migration 0011 — Retrieval golden set (spec 0011).
--
-- Applies the retrieval-foundation schema of spec 0011 to an EXISTING database:
-- materialized full-text search vectors on `articles` and `article_commas`, plus the
-- GIN indexes that make them usable. Also creates the three golden-set tables
-- (`labeling_runs`, `quiz_labelings`, `quiz_comma_labels`) that persist the labeling
-- run's output (phase 2).
--
-- Target state is defined by db/init.sql: this script and that file MUST produce the
-- same schema. Run the equivalence check at the bottom after applying, and treat any
-- difference as a bug in one of the two.
--
-- Idempotent: safe to run more than once.
-- Transactional: either the whole migration applies, or none of it does.
--
--   psql -U "$POSTGRES__USER" -d guidami_ai_patente -f db/migrations/0011_retrieval_golden_set.sql
--
-- This migration touches no data: no UPDATE, no INSERT, no DROP. Adding the generated
-- columns causes Postgres to rewrite both tables (an ACCESS EXCLUSIVE lock for the
-- duration of the rewrite), which is expected and is not a data change — run it when no
-- ingest is in flight.

BEGIN;

-- 1. `articles.tsv_title` — band A of the weighted tsvector (spec 0011, FR-1). Guarded by
--    an explicit existence check rather than `ADD COLUMN IF NOT EXISTS`, because that
--    clause cannot be combined with a generated-column definition in a way that is safe
--    to re-run.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'articles'
          AND column_name = 'tsv_title'
    ) THEN
        ALTER TABLE articles
            ADD COLUMN tsv_title TSVECTOR
                GENERATED ALWAYS AS (setweight(to_tsvector('italian', title), 'A')) STORED;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_articles_tsv_title ON articles USING GIN (tsv_title);

-- 2. `article_commas.tsv_text` — band B of the weighted tsvector (spec 0011, FR-1). Same
--    guard rationale as step 1.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'article_commas'
          AND column_name = 'tsv_text'
    ) THEN
        ALTER TABLE article_commas
            ADD COLUMN tsv_text TSVECTOR
                GENERATED ALWAYS AS (setweight(to_tsvector('italian', text), 'B')) STORED;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_article_commas_tsv_text ON article_commas USING GIN (tsv_text);

-- 3. `labeling_runs` — one row per labeling pass, recording its run provenance (spec
--    0011, FR-11). `CREATE TABLE IF NOT EXISTS` is already idempotent, so no `DO $$`
--    guard is needed here.
CREATE TABLE IF NOT EXISTS labeling_runs (
    id                 BIGSERIAL PRIMARY KEY,
    judge_model        TEXT NOT NULL,
    prompt_version     TEXT NOT NULL,
    candidate_variant  TEXT NOT NULL,
    dense_k            INT NOT NULL,
    text_k             INT NOT NULL,
    shuffle_seed       BIGINT NOT NULL,
    corpus_commit      TEXT NOT NULL,
    corpus_comma_count INT NOT NULL,
    question_limit     INT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. `quiz_labelings` — one row per labeled question within a run. The outcome of a
--    labeling is the count of its `quiz_comma_labels` children: zero children means
--    the corpus does not justify the question, a missing row means "never labeled"
--    (AD-6). No outcome column exists by design.
CREATE TABLE IF NOT EXISTS quiz_labelings (
    id               BIGSERIAL PRIMARY KEY,
    run_id           BIGINT NOT NULL REFERENCES labeling_runs (id) ON DELETE CASCADE,
    quiz_question_id BIGINT NOT NULL REFERENCES quiz_questions (id) ON DELETE CASCADE,
    rationale        TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, quiz_question_id)
);

CREATE INDEX IF NOT EXISTS idx_quiz_labelings_run_id ON quiz_labelings (run_id);

-- 5. `quiz_comma_labels` — the judge's chosen commas for a labeling, most-justifying
--    first (`judge_rank`). FR-7's three-label maximum is deliberately not a database
--    constraint but a prompt policy enforced on the agent response model
--    (CommaLabelerResponse, spec 0011 T-7). `quiz_comma_labels_unique_judge_rank`
--    guards against a *code* defect rather than a model one: CommaLabelerResponse
--    already rejects a repeated ordinal, so a duplicate rank here can only arise from
--    a mis-built loop. Both layers are intentional; do not drop either as redundant.
CREATE TABLE IF NOT EXISTS quiz_comma_labels (
    labeling_id      BIGINT NOT NULL REFERENCES quiz_labelings (id) ON DELETE CASCADE,
    article_comma_id BIGINT NOT NULL REFERENCES article_commas (id) ON DELETE CASCADE,
    judge_rank       INT NOT NULL CHECK (judge_rank > 0),
    dense_rank       INT,
    text_rank        INT,
    PRIMARY KEY (labeling_id, article_comma_id),
    CONSTRAINT quiz_comma_labels_at_least_one_arm
        CHECK (dense_rank IS NOT NULL OR text_rank IS NOT NULL),
    CONSTRAINT quiz_comma_labels_unique_judge_rank
        UNIQUE (labeling_id, judge_rank)
);

COMMIT;


-- ---------------------------------------------------------------------------
-- POST-MIGRATION CHECKS — run these, do not assume.
-- ---------------------------------------------------------------------------

-- 2a. The corpus's embedded rows must be untouched by the rewrite.
-- SELECT count(*) AS corpus_vectors_intact
-- FROM article_commas WHERE embedding IS NOT NULL;

-- 2b. EQUIVALENCE CHECK — a migrated database and a freshly initialised one must have
--     identical schemas for the new columns and indexes. Run this against both and diff
--     the output; any difference means db/init.sql and this migration have drifted.
-- SELECT table_name, column_name, data_type, is_nullable, is_generated, udt_name
-- FROM information_schema.columns
-- WHERE table_schema = 'public'
--   AND (table_name, column_name) IN (('articles', 'tsv_title'), ('article_commas', 'tsv_text'))
-- ORDER BY table_name, column_name;
--
-- SELECT indexname, indexdef FROM pg_indexes
-- WHERE indexname IN ('idx_articles_tsv_title', 'idx_article_commas_tsv_text')
-- ORDER BY indexname;
--
-- SELECT table_name, column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_schema = 'public'
--   AND table_name IN ('labeling_runs', 'quiz_labelings', 'quiz_comma_labels')
-- ORDER BY table_name, ordinal_position;


-- ---------------------------------------------------------------------------
-- ROLLBACK — restores the previous schema. No data is lost: both columns are generated,
-- so nothing but the derived tsvector itself is dropped.
-- ---------------------------------------------------------------------------
-- BEGIN;
-- DROP TABLE IF EXISTS quiz_comma_labels, quiz_labelings, labeling_runs;
-- DROP INDEX IF EXISTS idx_articles_tsv_title;
-- DROP INDEX IF EXISTS idx_article_commas_tsv_text;
-- ALTER TABLE articles DROP COLUMN IF EXISTS tsv_title;
-- ALTER TABLE article_commas DROP COLUMN IF EXISTS tsv_text;
-- COMMIT;
