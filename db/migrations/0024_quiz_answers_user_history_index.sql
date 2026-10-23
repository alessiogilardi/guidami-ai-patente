-- Migration 0024 — quiz_answers gains a composite (user_id, id) history index
-- (spec 2026-09-27-mastery-statistics-review-sessions, AD-1).
--
-- Mastery statistics and review sessions read a user's answer history in id order;
-- (user_id, id) serves both the filter and the ordering. It also covers every lookup
-- the old single-column idx_quiz_answers_user_id served, so that index is dropped.
-- The new index is created BEFORE the old one is dropped, so the table is never
-- left without a usable user_id index.
--
-- Idempotent: IF NOT EXISTS / IF EXISTS make a re-run a no-op.
-- Transactional: either the whole migration applies, or none of it does.
--
--   psql -U "$POSTGRES__USER" -d guidami_ai_patente -f db/migrations/0024_quiz_answers_user_history_index.sql

BEGIN;

CREATE INDEX IF NOT EXISTS idx_quiz_answers_user_id_id ON quiz_answers (user_id, id);
DROP INDEX IF EXISTS idx_quiz_answers_user_id;

COMMIT;

-- ---------------------------------------------------------------------------
-- Rollback (manual, not run automatically):
-- ---------------------------------------------------------------------------
-- BEGIN;
-- CREATE INDEX IF NOT EXISTS idx_quiz_answers_user_id ON quiz_answers (user_id);
-- DROP INDEX IF EXISTS idx_quiz_answers_user_id_id;
-- COMMIT;
