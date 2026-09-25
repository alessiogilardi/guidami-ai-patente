-- Migration 0022 — glossary_entries gains definition_plain (spec 0022).
--
-- Plain-language rendering of `definition`, filled independently by the new
-- simplify-glossary-definitions script. NULL until simplified; a row is a complete,
-- servable glossary entry either way (spec 0022 AD-4).
--
-- Idempotent: ADD COLUMN IF NOT EXISTS is a no-op when the column already exists.
-- Transactional: either the whole migration applies, or none of it does.
--
--   psql -U "$POSTGRES__USER" -d guidami_ai_patente -f db/migrations/0022_glossary_definition_plain.sql

BEGIN;

ALTER TABLE glossary_entries ADD COLUMN IF NOT EXISTS definition_plain TEXT;

COMMIT;

-- ---------------------------------------------------------------------------
-- Rollback (manual, not run automatically):
-- ---------------------------------------------------------------------------
-- BEGIN;
-- ALTER TABLE glossary_entries DROP COLUMN IF EXISTS definition_plain;
-- COMMIT;
