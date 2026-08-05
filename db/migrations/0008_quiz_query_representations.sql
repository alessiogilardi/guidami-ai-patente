-- Migration 0008 — Quiz query representations (spec 0008).
--
-- Applies the schema of spec 0008 to an EXISTING database, preserving the
-- embeddings already stored. Replaces the "wipe the volume and re-ingest"
-- workflow for this change.
--
-- Target state is defined by db/init.sql: this script and that file MUST
-- produce the same schema. Run the equivalence check at the bottom after
-- applying, and treat any difference as a bug in one of the two.
--
-- Idempotent: safe to run more than once.
-- Transactional: either the whole migration applies, or none of it does.
--
--   psql -U "$POSTGRES__USER" -d guidami_ai_patente -f db/migrations/0008_quiz_query_representations.sql
--
-- What it preserves:
--   * article_commas.embedding — untouched, no re-embedding of the corpus.
--   * quiz_questions.embedding — MOVED into quiz_question_embeddings as the
--     'search_queries' variant before the column is dropped, so the spec 0007
--     baseline arm survives the migration and never needs recomputing.
--
-- What still requires an ingest run afterwards:
--   * quiz_questions.vector_search_queries (populated from the enriched layer)
--   * quiz_images.description             (populated from the enriched layer)
--   * every variant other than 'search_queries'

BEGIN;

-- 1. Image descriptions: one row per distinct image, never per question.
--    Cardinality on the current data: 4147 questions reference 427 images.
CREATE TABLE IF NOT EXISTS quiz_images (
    filename    TEXT PRIMARY KEY,
    description TEXT
);

-- 2. Query representations on two orthogonal axes (spec 0008, AD-2 / AD-6):
--    variant = which text (a row); embedding_* = which model (a column).
--    pgvector encodes the dimension in the column type, so a model of a
--    different dimensionality needs its own column — see the template at the
--    bottom of this file for adding one.
CREATE TABLE IF NOT EXISTS quiz_question_embeddings (
    id                BIGSERIAL PRIMARY KEY,
    quiz_question_id  BIGINT NOT NULL REFERENCES quiz_questions (id) ON DELETE CASCADE,
    variant           TEXT NOT NULL,
    embedding_3_small VECTOR(1536),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (quiz_question_id, variant),
    CONSTRAINT quiz_question_embeddings_at_least_one_vector
        CHECK (num_nonnulls(embedding_3_small) > 0)
);

CREATE INDEX IF NOT EXISTS idx_quiz_question_embeddings_variant
    ON quiz_question_embeddings (variant);

-- 3. The phrases that produce the query vector become inspectable (spec 0008, AD-1).
ALTER TABLE quiz_questions ADD COLUMN IF NOT EXISTS vector_search_queries TEXT[];

-- 4. Preserve the existing vectors as the baseline variant BEFORE dropping the
--    column. Guarded on the column still existing so a re-run is a no-op rather
--    than an error.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'quiz_questions'
          AND column_name = 'embedding'
    ) THEN
        INSERT INTO quiz_question_embeddings (quiz_question_id, variant, embedding_3_small)
        SELECT id, 'search_queries', embedding
        FROM quiz_questions
        WHERE embedding IS NOT NULL
        ON CONFLICT (quiz_question_id, variant) DO NOTHING;
    END IF;
END $$;

-- 5. Only now is the old column redundant.
ALTER TABLE quiz_questions DROP COLUMN IF EXISTS embedding;

COMMIT;


-- ---------------------------------------------------------------------------
-- POST-MIGRATION CHECKS — run these, do not assume.
-- ---------------------------------------------------------------------------

-- 5a. Every previously embedded question must have survived as a variant.
--     Expected on the corpus as of 2026-08-05: 7098.
-- SELECT count(*) AS migrated_baseline_vectors
-- FROM quiz_question_embeddings WHERE variant = 'search_queries';

-- 5b. The old column must be gone and the new one present.
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'quiz_questions'
--   AND column_name IN ('embedding', 'vector_search_queries');

-- 5c. The corpus must be untouched. Expected: 3650.
-- SELECT count(*) AS corpus_vectors_intact
-- FROM article_commas WHERE embedding IS NOT NULL;

-- 5d. EQUIVALENCE CHECK — a migrated database and a freshly initialised one
--     must have identical schemas. Run this against both and diff the output;
--     any difference means db/init.sql and this migration have drifted.
-- SELECT table_name, column_name, data_type, is_nullable, udt_name
-- FROM information_schema.columns
-- WHERE table_schema = 'public'
-- ORDER BY table_name, column_name;


-- ---------------------------------------------------------------------------
-- ADDING A SECOND EMBEDDING MODEL — template, not part of this migration.
-- pgvector fixes the dimension in the column type, so a model of a different
-- dimensionality gets its own column rather than sharing this one. The CHECK
-- must be widened in the same transaction, or the new column can never be the
-- only one populated on a row.
-- ---------------------------------------------------------------------------
-- BEGIN;
-- ALTER TABLE quiz_question_embeddings
--     ADD COLUMN IF NOT EXISTS embedding_3_large VECTOR(3072);
-- ALTER TABLE quiz_question_embeddings
--     DROP CONSTRAINT IF EXISTS quiz_question_embeddings_at_least_one_vector;
-- ALTER TABLE quiz_question_embeddings
--     ADD CONSTRAINT quiz_question_embeddings_at_least_one_vector
--     CHECK (num_nonnulls(embedding_3_small, embedding_3_large) > 0);
-- COMMIT;


-- ---------------------------------------------------------------------------
-- ROLLBACK — restores the previous schema. The non-baseline variants are lost
-- (they are recomputable from the enriched layer); the baseline arm is restored
-- from the variant table, so no embedding spend is required either way.
-- ---------------------------------------------------------------------------
-- BEGIN;
-- ALTER TABLE quiz_questions ADD COLUMN IF NOT EXISTS embedding VECTOR(1536);
-- UPDATE quiz_questions q SET embedding = e.embedding_3_small
-- FROM quiz_question_embeddings e
-- WHERE e.quiz_question_id = q.id AND e.variant = 'search_queries';
-- ALTER TABLE quiz_questions DROP COLUMN IF EXISTS vector_search_queries;
-- DROP TABLE IF EXISTS quiz_question_embeddings;
-- DROP TABLE IF EXISTS quiz_images;
-- COMMIT;
