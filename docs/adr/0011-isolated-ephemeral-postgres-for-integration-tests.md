# ADR 0011: Isolated, Ephemeral Postgres Stack for Integration Tests

## Status

Proposed

## Context

Every `@pytest.mark.integration` test that touches Postgres opened a
connection built from a hardcoded `PostgresConnectionConfig(host="localhost",
port=5432, dbname="guidami_ai_patente", ...)` — the exact same connection
details as the dev stack in `docker/docker-compose.yml`, whose data persists
to the `docker/.volumes/postgres_data` bind mount. These fixtures truncated
`articles`/`article_commas`/`quiz_questions`/`llm_call_logs` in setup and
teardown to keep each test isolated from the others.

There was never a dedicated test database. Running the integration suite
(`uv run pytest -m integration`) against a dev stack that held real,
paid-for ingested data (corpus articles/commas, quiz questions, embeddings)
silently wiped it — which is exactly what happened. Nothing in `docs/` or
`docs/adr/` documented this connection convention or its risk; it was an
oversight, not a deliberate choice (confirmed by checking `docs/testing.md`,
`docs/database.md`, and ADR 0006, none of which cover pytest integration
test isolation — ADR 0006 only addresses the ingest CLI's `--config`
test-data profile, a different mechanism that intentionally shares the dev
tables).

## Decision

Integration tests run against a dedicated, ephemeral Postgres stack defined
in `docker/docker-compose.test.yml`:

- a separate container, on a separate port (5433, vs. 5432 for dev),
- a `tmpfs` data directory — never a bind mount, so it cannot persist and
  cannot be confused with dev data,
- the same `db/init.sql` schema as the dev stack, mounted read-only.

`tests/conftest.py` gained two session-scoped fixtures:

- `_postgres_test_stack` runs `docker compose -f docker/docker-compose.test.yml
  -p guidami-ai-patente-test up -d --wait` the first time a collected test
  requests it (transitively, via `postgres_test_config`), and `down -v` once
  at the end of the pytest session.
- `postgres_test_config` depends on `_postgres_test_stack` and returns the
  `PostgresConnectionConfig` for the isolated stack, with a defensive
  `assert config.port != 5432` against ever pointing back at the dev
  database.

Every integration test fixture that used to build its own
`PostgresConnectionConfig` now requests `postgres_test_config` instead —
isolation is structural (different container, different port), not just a
matter of every fixture getting a database name string right.

## Alternatives considered

- **A second database in the same dev Postgres instance** (e.g.
  `guidami_ai_patente_test` alongside `guidami_ai_patente`): cheaper (one
  container instead of two) but isolation depends entirely on every fixture
  naming the right database — the exact class of mistake that caused the
  data loss this ADR responds to. Also requires a one-off manual migration
  against the already-running dev container/volume, since Postgres init
  scripts only run against a freshly created data directory. Rejected: it
  keeps the failure mode alive, just at one more layer of indirection.
- **Keep the single dev database, add only a runtime guard** (e.g. refuse to
  truncate unless `dbname` matches a `_test` suffix or an env var is set):
  zero new infrastructure, but the protection is a single check that a
  future edit can bypass or misconfigure — defense in depth, not isolation.
  Rejected as the sole mechanism; not needed once physical isolation exists.
- **A persistent (non-`tmpfs`) test container, started once and left
  running**: avoids the per-session startup cost. Rejected: the fixture
  already starts the stack in a few seconds via `--wait` on a Postgres
  healthcheck, and a long-lived container reintroduces exactly the
  "accumulated state nobody remembers to clean up" risk this ADR is trying
  to eliminate.

## Consequences

**Easier**: integration tests can never truncate real dev data again,
regardless of what any individual fixture's config literal says — the dev
and test stacks are different containers on different ports, and the test
stack has no bind mount to persist anything even if that guarantee were
somehow bypassed. The stack starts/stops automatically per pytest session;
no manual `docker compose` step is needed to run integration tests.

**Harder**: a second Postgres image must come up during the integration
test session (small, `tmpfs`-backed, a few seconds of startup); Docker must
be running for `-m integration` to work at all, same as before but now on
two containers instead of one when both dev and test stacks are up.

**Also harder — and this is the debt being accepted knowingly**: running the
test suite against a freshly initialized schema (always exactly
`db/init.sql`) surfaced pre-existing drift between the current schema and
code/tests that had only ever run against the stale, incrementally-migrated
dev volume — e.g. `QuizQuestionStoreRepository`/`QuizQuestionEntity` still
reference a `quiz_questions.embedding` column that migration 0008 dropped in
favor of `quiz_question_embeddings`. This ADR does not fix that drift; it
only makes it visible. Tracked separately.
