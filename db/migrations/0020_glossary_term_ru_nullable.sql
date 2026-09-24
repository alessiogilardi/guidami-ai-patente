-- Migration 0020 — glossary_entries.term_ru becomes nullable (spec 0019, AD-11).
--
-- build-glossary (FR-2/FR-6) always writes term_ru = NULL; only the separate
-- translate-glossary-terms script (FR-5) ever fills it in, later, via a plain UPDATE.
-- glossary_entries already exists on the dev stack via
-- db/migrations/0019_glossary_entries.sql (spec 0020's plan landed it first, with
-- term_ru TEXT NOT NULL) — this migration relaxes that constraint to match the
-- db/init.sql edit landing in the same change.
--
-- Idempotent: DROP NOT NULL is a no-op when the column is already nullable.
-- Transactional: either the whole migration applies, or none of it does.
--
--   psql -U "$POSTGRES__USER" -d guidami_ai_patente -f db/migrations/0020_glossary_term_ru_nullable.sql

BEGIN;

ALTER TABLE glossary_entries ALTER COLUMN term_ru DROP NOT NULL;

COMMIT;

-- ---------------------------------------------------------------------------
-- Rollback (manual, not run automatically) — only safe if every row's term_ru is
-- currently non-NULL:
-- ---------------------------------------------------------------------------
-- BEGIN;
-- ALTER TABLE glossary_entries ALTER COLUMN term_ru SET NOT NULL;
-- COMMIT;
