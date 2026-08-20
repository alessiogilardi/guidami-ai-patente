-- Migration 0011 — Retrieval golden set, phase 1 (spec 0011).
--
-- Applies the retrieval-foundation schema of spec 0011 to an EXISTING database:
-- materialized full-text search vectors on `articles` and `article_commas`, plus the
-- GIN indexes that make them usable.
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


-- ---------------------------------------------------------------------------
-- ROLLBACK — restores the previous schema. No data is lost: both columns are generated,
-- so nothing but the derived tsvector itself is dropped.
-- ---------------------------------------------------------------------------
-- BEGIN;
-- DROP INDEX IF EXISTS idx_articles_tsv_title;
-- DROP INDEX IF EXISTS idx_article_commas_tsv_text;
-- ALTER TABLE articles DROP COLUMN IF EXISTS tsv_title;
-- ALTER TABLE article_commas DROP COLUMN IF EXISTS tsv_text;
-- COMMIT;
