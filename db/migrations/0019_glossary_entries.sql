-- Migration 0019 — glossary_entries (spec 0019 schema, spec 0020 read path).
--
-- Applies the glossary_entries table to an EXISTING database. Applied here by
-- whichever of spec 0019's or spec 0020's implementation plan lands first — see
-- db/init.sql's own comment above this table and each spec's "Independence from
-- Spec 0019"/"Independence from Spec 0020" section. Named after spec 0019, which owns
-- this table's schema, regardless of which spec's plan applies it first.
--
-- Target state is defined by db/init.sql: this script and that file MUST produce the
-- same schema. Run the equivalence check at the bottom after applying, and treat any
-- difference as a bug in one of the two.
--
-- Idempotent: safe to run more than once (every statement is already IF NOT EXISTS; the
-- named constraint glossary_entries_at_least_one_vector is declared inline on
-- CREATE TABLE IF NOT EXISTS, not added after the fact via a separate ADD CONSTRAINT, so
-- this migration still needs none of 0011's/0012's DO $$ guards).
-- Transactional: either the whole migration applies, or none of it does.
--
--   psql -U "$POSTGRES__USER" -d guidami_ai_patente -f db/migrations/0019_glossary_entries.sql

BEGIN;

CREATE TABLE IF NOT EXISTS glossary_entries (
    id                BIGSERIAL PRIMARY KEY,
    source            TEXT NOT NULL,
    article_number    TEXT NOT NULL,
    comma_number      TEXT NOT NULL,
    term              TEXT NOT NULL,
    definition        TEXT NOT NULL,
    term_ru           TEXT NOT NULL,
    embedding_3_small VECTOR(1536),
    tsv_term          TSVECTOR GENERATED ALWAYS AS
                          (setweight(to_tsvector('italian', term), 'A')) STORED,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, article_number, comma_number, term),
    CONSTRAINT glossary_entries_at_least_one_vector
        CHECK (num_nonnulls(embedding_3_small) > 0)
);

CREATE INDEX IF NOT EXISTS idx_glossary_entries_tsv_term
    ON glossary_entries USING GIN (tsv_term);

COMMIT;

-- ---------------------------------------------------------------------------
-- Rollback (manual, not run automatically):
-- ---------------------------------------------------------------------------
-- BEGIN;
-- DROP INDEX IF EXISTS idx_glossary_entries_tsv_term;
-- DROP TABLE IF EXISTS glossary_entries;
-- COMMIT;
