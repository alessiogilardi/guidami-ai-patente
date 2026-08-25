# ADR 0022: `PostgresClient` Is Backed by a `psycopg_pool.ConnectionPool`, Shipped in Plan 1 Gated on the Batch Suite

## Status

Proposed

## Context

`commons/clients/postgres_client.py::PostgresClient` opened exactly one
`psycopg.connect(..., autocommit=True)` connection at construction and held it
for the client's lifetime — a process-wide `pywire` singleton on the FastAPI
side, and a single shared instance across every ingestion pipeline stage on
the batch side. psycopg3 guards a connection with an internal lock, so every
threaded SQL call issued against that one connection queues behind every
other one, regardless of how many worker threads/tasks are otherwise free to
run concurrently.

Spec 0012 (`docs/superpowers/specs/2026-08-24-quiz-flow-api-design.md`, AD-25)
adds concurrency at the LLM boundary for both the batch labeler
(`label-golden-set --concurrency N`) and the future live judge. AD-25's
concurrency gain would be silently given straight back at the database: `N`
judge calls finishing their LLM round-trip in parallel would still serialise
their `INSERT`s behind the single locked connection, turning a concurrency
win into a database-side bottleneck that AD-25 never intended to introduce.
Fixing this only inside the labeling code (e.g. a private pool just for
`GoldenSetWriteRepository`) would leave the same defect wherever else
`PostgresClient` is used concurrently, and would mean the app and the
ingestor no longer share the exact client the shared read repositories are
tested against.

The pgvector adapter registration (`register_vector`) was previously done
once, on the single connection, at `__init__` time — a pool needs it done
**per connection**, since AD-13 (the dense retrieval arm) depends on a
`VECTOR` column deserialising into a Python list without bespoke parsing on
every connection a caller happens to borrow, not just the first one opened.

This change reaches outside spec 0012's own scope: `PostgresClient` lives in
`commons/` and is shared by the ingestor, the batch labeling/judge scripts,
and (eventually) the FastAPI app. `label-golden-set` already accepts
`--concurrency` for in-flight judge calls; today those calls' DB writes
serialise *implicitly* behind the single connection, which is safe but slow.
With a pool, those writes become genuinely concurrent — safe here because
they are independent `INSERT`s under `autocommit=True`, guarded by the same
unique constraints AD-19 relies on, but still a real behaviour change to
already-working code the API design does not otherwise touch. The spec (AD-26)
places this change in **plan 1** (the ingestion-side batch plan this ADR
belongs to) rather than folding it unannounced into a later HTTP-serving
plan, with the existing batch test suite passing unchanged as the gate that
proves the change is behaviour-preserving for every current caller.

This is quiz-flow-api-phase1 plan Tasks 1/2 (spec 0012, AD-25/AD-26).

## Decision

`PostgresClient.__init__` builds a `psycopg_pool.ConnectionPool` instead of a
single `psycopg.connect(...)` call:

- **Pool size** comes from `PostgresConnectionConfig.pool_min_size`/
  `pool_max_size` (new fields, defaults 1/8) — plain deployment
  configuration, not judge identity. It is declared on `AppConfig` and
  `IngestorConfig`, deliberately **never** on `LabelingConfig` (ADR 0020/AD-27):
  putting pool capacity inside the configuration epoch would invalidate every
  cached labeling (7099 rows) on a purely operational capacity change that has
  nothing to do with what the judge actually decided.
- **Opened eagerly, `wait=True`** — the pool blocks in `__init__` until it can
  establish its minimum connections, so an unreachable database raises from
  `PostgresClient.__init__` itself (D3), preserving the single-connection
  failure mode `ingest status --online` and `cli/commands/prepare.py` already
  relied on catching as `psycopg.Error` at construction, not discovering it
  only at the first query several stages later.
- **`configure=_configure` hook** registers the pgvector adapter on every
  connection the pool opens, not once at startup — the same effect the prior
  single-connection `__init__` had, generalised to however many connections
  the pool ends up holding.
- **`reset=_reset` hook** (D4) documents and asserts the invariant that no
  session state survives a connection being returned to the pool — a no-op
  today (no caller relies on session state surviving a borrow), but the
  explicit hook is where a real `ROLLBACK`/`DISCARD` would go if a future
  caller ever violated that invariant, rather than the violation surfacing as
  a mystery bug in an unrelated later borrower.
- **Public method surface is unchanged**: `truncate`, `execute`,
  `execute_many`, `execute_many_returning`, `fetch`, `close`, `__enter__`,
  `__exit__` — every call site now borrows a connection via `with
  self._pool.connection()` internally, but no caller's code changes.
- **`psycopg_pool.PoolTimeout` is asserted to subclass `psycopg.Error`** (D12,
  `tests/commons/clients/test_postgres_client_integration.py::
  test_pool_failures_are_catchable_as_psycopg_errors`) — a canary pinning an
  upstream library invariant `status.py`/`prepare.py` both depend on when they
  catch broad `psycopg.Error` to report "database unreachable"; if a future
  `psycopg_pool` release ever stopped `PoolTimeout` subclassing it, this test
  fails at that dependency bump instead of the regression only surfacing as an
  uncaught traceback under load.
- **Pool size at the entry points is widened from the caller's own fan-out**,
  not left at the config default: `label_main.py`'s `main()` and
  `retrieval_evaluation/main.py`'s `main()` both build their `PostgresClient`
  from `config.postgres.model_copy(update={"pool_max_size":
  max(config.postgres.pool_max_size, args.concurrency)})` before opening it
  (D7/D14) — `--concurrency` LLM calls fanning out over a pool smaller than
  their own concurrency would otherwise starve each other under the pool's
  bounded `timeout`, defeating AD-25's concurrency gain from the database side
  even after pooling.

## Alternatives considered

- **`min=1, max=1` for the batch path**, preserving today's implicit
  serialisation as if it were a requirement rather than an accident — rejected:
  it freezes a limitation nobody asked for and defeats AD-25's whole purpose
  for the batch labeler specifically.
- **A second, separate pooled client just for the FastAPI app**, leaving the
  ingestor's `PostgresClient` a single connection — rejected: two clients over
  one database, and the app's client would drift from the one the shared
  `commons/repositories/db/` repositories are tested against, reopening the
  exact "two independently-loaded, independently-drifting things" failure
  mode ADR 0020 was written to close for `agents_dir`.
- **Fix the concurrency problem only inside `GoldenSetWriteRepository`** (a
  private pool scoped to the labeling write path) — rejected: leaves every
  other concurrent `PostgresClient` caller, present or future, with the same
  serialisation defect, and duplicates pooling/adapter-registration logic that
  belongs on the shared client once.

## Consequences

- Every `PostgresClient` consumer — ingestion pipelines, the batch
  labeler/judge scripts, and eventually the FastAPI app — gets genuine
  connection concurrency for free, with no call-site changes; the pool is an
  internal implementation swap behind an unchanged public method surface.
- `PostgresConnectionConfig` gains two new fields (`pool_min_size`,
  `pool_max_size`) that every settings source (`.env`, YAML, init args) can
  now override — a small surface-area increase, justified by pool sizing
  being genuine deployment configuration rather than a hardcoded constant.
- The batch test suite (`uv run pytest` and `uv run pytest -m integration`)
  passing unchanged is this ADR's own acceptance gate, per AD-26 — a pooling
  change to already-relied-upon shared infrastructure ships only once proven
  behaviour-preserving for every existing caller, not merely for the new
  labeling/judge concurrency it was motivated by.
- Pool capacity now needs to be reasoned about at two different entry points
  (static config default vs. the caller-fan-out widening at `main()`/
  `label_main.py`) rather than being a single fixed number — a small added
  cognitive load in exchange for `--concurrency` never being able to starve
  itself against its own pool.
