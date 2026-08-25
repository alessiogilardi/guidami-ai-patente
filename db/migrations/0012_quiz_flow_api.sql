-- Migration 0012 — The sixth epoch field and live-run provenance (spec 0012).
--
-- Applies the schema amendments of spec 0012 to an EXISTING database that already has
-- the spec 0011 golden-set tables: batch-vs-live provenance on `labeling_runs`
-- (`origin`), the sixth configuration-epoch field (`lexeme_fields`), a relaxed
-- `corpus_commit` (nullable for a live run), the partial unique index enforcing one
-- live run per configuration epoch, human validation of a `quiz_labelings` row
-- (`validated_at`/`validated_by`), and its denormalised outcome flag
-- (`has_supporting_commas`).
--
-- Target state is defined by db/init.sql: this script and that file MUST produce the
-- same schema. Run the equivalence check at the bottom after applying, and treat any
-- difference as a bug in one of the two.
--
-- Idempotent: safe to run more than once.
-- Transactional: either the whole migration applies, or none of it does.
--
--   psql -U "$POSTGRES__USER" -d guidami_ai_patente -f db/migrations/0012_quiz_flow_api.sql

BEGIN;

-- 1. Batch vs live provenance, and the live configuration epoch (spec 0012, AD-8).
ALTER TABLE labeling_runs
    ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'batch';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'labeling_runs_origin_check'
    ) THEN
        ALTER TABLE labeling_runs
            ADD CONSTRAINT labeling_runs_origin_check CHECK (origin IN ('batch', 'live'));
    END IF;
END $$;

-- A live run cannot know the corpus commit, but a batch run still must: `corpus_commit()`
-- deliberately lets `git rev-parse` fail rather than record a placeholder, relying on this
-- column's NOT NULL. The conditional CHECK preserves that guarantee exactly where it
-- applied and relaxes it only where it cannot be honoured.
ALTER TABLE labeling_runs ALTER COLUMN corpus_commit DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'labeling_runs_batch_has_corpus_commit'
    ) THEN
        ALTER TABLE labeling_runs
            ADD CONSTRAINT labeling_runs_batch_has_corpus_commit
                CHECK (origin <> 'batch' OR corpus_commit IS NOT NULL);
    END IF;
END $$;

-- `lexeme_fields` completes the configuration epoch. Backfilled with the value the three
-- existing runs were produced under, which is the current setting — these runs predate
-- the column, and assuming anything else would misreport them. Sorted, matching the
-- canonical form LabelingEpochMapper writes.
ALTER TABLE labeling_runs
    ADD COLUMN IF NOT EXISTS lexeme_fields TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];

UPDATE labeling_runs
SET lexeme_fields = ARRAY['image_description', 'text', 'topic']
WHERE lexeme_fields = ARRAY[]::TEXT[];

ALTER TABLE labeling_runs ALTER COLUMN lexeme_fields DROP DEFAULT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_labeling_runs_live_config
    ON labeling_runs (judge_model, prompt_version, candidate_variant, dense_k, text_k,
                      lexeme_fields)
    WHERE origin = 'live';

-- 2. Human validation of a labeling as a whole (AD-9).
ALTER TABLE quiz_labelings
    ADD COLUMN IF NOT EXISTS validated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS validated_by TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'quiz_labelings_validation_complete'
    ) THEN
        ALTER TABLE quiz_labelings
            ADD CONSTRAINT quiz_labelings_validation_complete
                CHECK ((validated_at IS NULL) = (validated_by IS NULL));
    END IF;
END $$;

-- 3. Denormalised outcome (AD-10), written transactionally with its children (FR-15).
--    DEFAULT FALSE, then backfilled from the child count. Measured on 2026-08-24, 3 of
--    the 14 existing labelings have zero children: a DEFAULT TRUE would mark them
--    "explainable" and the endpoint would try to explain citing nothing — precisely the
--    impossible state AD-10 undertakes to avoid, present from the first migration.
--    FALSE is also the safe direction if the backfill fails halfway.
--    The DEFAULT is kept after the backfill: no caller supplies this column (FR-15), it
--    is computed by the INSERT itself, so the default only ever covers a hand-written row.
ALTER TABLE quiz_labelings
    ADD COLUMN IF NOT EXISTS has_supporting_commas BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE quiz_labelings l
SET has_supporting_commas = EXISTS (
    SELECT 1 FROM quiz_comma_labels cl WHERE cl.labeling_id = l.id
);

-- 4. The hot read is by question, which no existing index serves.
CREATE INDEX IF NOT EXISTS idx_quiz_labelings_question_recent
    ON quiz_labelings (quiz_question_id, created_at DESC);

COMMIT;


-- ---------------------------------------------------------------------------
-- POST-MIGRATION CHECKS — run these, do not assume.
-- ---------------------------------------------------------------------------

-- EQUIVALENCE CHECK — a migrated database and a freshly initialised one must have
-- identical schemas for the new columns and indexes. Run this against both and diff
-- the output; any difference means db/init.sql and this migration have drifted.
-- SELECT table_name, column_name, data_type, is_nullable, udt_name
-- FROM information_schema.columns
-- WHERE table_schema = 'public'
--   AND (table_name, column_name) IN (
--       ('labeling_runs', 'origin'), ('labeling_runs', 'lexeme_fields'),
--       ('labeling_runs', 'corpus_commit'), ('quiz_labelings', 'validated_at'),
--       ('quiz_labelings', 'validated_by'), ('quiz_labelings', 'has_supporting_commas')
--   )
-- ORDER BY table_name, column_name;
--
-- SELECT indexname, indexdef FROM pg_indexes
-- WHERE indexname IN ('uq_labeling_runs_live_config', 'idx_quiz_labelings_question_recent')
-- ORDER BY indexname;
--
-- SELECT conname, contype FROM pg_constraint
-- WHERE conname IN ('labeling_runs_origin_check', 'labeling_runs_batch_has_corpus_commit',
--                    'quiz_labelings_validation_complete')
-- ORDER BY conname;


-- ---------------------------------------------------------------------------
-- ROLLBACK — restores the previous schema. Data loss: any row with origin = 'live',
-- validated_at/validated_by, or a non-default lexeme_fields is lost.
-- ---------------------------------------------------------------------------
-- BEGIN;
-- DROP INDEX IF EXISTS idx_quiz_labelings_question_recent;
-- DROP INDEX IF EXISTS uq_labeling_runs_live_config;
-- ALTER TABLE quiz_labelings DROP COLUMN IF EXISTS has_supporting_commas;
-- ALTER TABLE quiz_labelings DROP COLUMN IF EXISTS validated_by;
-- ALTER TABLE quiz_labelings DROP COLUMN IF EXISTS validated_at;
-- ALTER TABLE labeling_runs DROP COLUMN IF EXISTS lexeme_fields;
-- ALTER TABLE labeling_runs ALTER COLUMN corpus_commit SET NOT NULL;
-- ALTER TABLE labeling_runs DROP COLUMN IF EXISTS origin;
-- COMMIT;
