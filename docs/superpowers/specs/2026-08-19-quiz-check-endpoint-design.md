<!--
SPEC — the contract. Durable, git-tracked, never deleted (superseded instead).
The user signs scope; the compiling skill asserts feasibility with codebase evidence.
Downstream plans are extracted from this document and reference FR ids: every
requirement must be individually testable and traceable.
Status lifecycle: draft → ready → in-progress → implemented → superseded.
Every status beyond draft is written by the user alone — skills only propose:
draft → ready at sign-off; ready → in-progress when the first plan is extracted;
in-progress → implemented once the Definition of Done is verified.
-->

# Spec 0011: Quiz-check endpoint

| | |
|---|---|
| **Id** | 0011 |
| **Status** | draft |
| **Date** | 2026-08-19 |
| **Discussion log** | specs/discussions/quiz-check-endpoint.md |
| **Supersedes / superseded by** | — |

## Problem & Motivation

The end goal of this project is a quiz bot that checks driving-exam answers
deterministically and explains them via RAG. The FastAPI app that will serve it
(`src/guidami_ai_patente/`) currently exposes only a liveness probe (`GET /health`);
no route yet lets a client submit an answer to a quiz question and learn whether it
was correct. The quiz bank itself (`quiz_questions`, true/false statements) is
already fully ingested and queryable in Postgres. Building the deterministic
check first — before the RAG-explanation increment that will follow it — gives
the app its first real, buildable vertical slice: request in, a single indexed
lookup, verdict out, no LLM call and no new state to design.

## Functional Requirements

### FR-1: Check a submitted answer against the stored correct answer

Given a quiz question identified by its `number`, the endpoint compares a
client-submitted boolean answer against the question's persisted
`correct_answer` and reports whether it matches.

**Acceptance criteria:**
- Given a `quiz_questions` row exists with `number = "0001"` and
  `correct_answer = true`, when a client sends `POST /quiz-questions/0001/check`
  with body `{"answer": true}`, then the response is `200 OK` with body
  `{"correct": true}`.
- Given the same row, when the client sends `POST /quiz-questions/0001/check`
  with body `{"answer": false}`, then the response is `200 OK` with body
  `{"correct": false}`.
- Given the same row, then the response body contains no field other than
  `correct` (in particular, no `rule_explanation`).

### FR-2: Unknown question number returns 404

Given no `quiz_questions` row matches the requested `number`, the endpoint
reports the resource as not found instead of attempting a check.

**Acceptance criteria:**
- Given no `quiz_questions` row exists with `number = "9999"`, when a client
  sends `POST /quiz-questions/9999/check` with a well-formed body (e.g.
  `{"answer": true}`), then the response is `404 Not Found`.

## Non-Goals

- RAG-based explanation of why an answer is correct/incorrect
  (`rule_explanation`) — a separate, later increment; not returned by this
  endpoint even though the column is already populated and free to serve.
- Generic retrieval/RAG unrelated to the quiz bank.
- User identity, authentication, or session handling — the endpoint is
  stateless.
- Persisting submitted answers, building an answer history, or computing a
  score — no new write path or persisted state is introduced.

## Architectural Decisions

### AD-1: Continue on the existing `feat/backend` branch/worktree, keep the pywire scaffold and ADR 0015 as-is
- **Rationale:** `feat/backend` already has a scaffolded FastAPI layout for
  `src/guidami_ai_patente/` and an **Accepted** ADR 0015 adopting `pywire`
  (Spring-style field injection) scoped to this package only, diverging
  deliberately from the ingestor's manual constructor injection. Building on
  top of this avoids discarding real, recent scaffold work and DI-choice
  churn unrelated to this endpoint.
- **Rejected alternatives:** Revisiting the pywire DI choice before proceeding;
  restarting on `feat/ingestion` instead — both rejected as unnecessary churn.

### AD-2: Lookup key is `quiz_questions.number`, not `id` or `question_id`
- **Rationale:** `number` is already the domain-stable identifier used
  elsewhere in the quiz pipeline (`UNIQUE(number)`). `id` is a
  storage-internal `BIGSERIAL`; exposing it in a public API path leaks a
  persistence detail instead of a domain identifier.
- **Rejected alternatives:** `id` — internal, not a stable domain concept to
  expose externally; `question_id` — its uniqueness/meaning was not verified
  as guaranteed (possibly just a source-PDF reference), so not chosen without
  that verification.

### AD-3: `POST /quiz-questions/{number}/check`, body `{"answer": bool}`, response `{"correct": bool}`
- **Rationale:** `POST` is the correct verb for an action that evaluates user
  input (not safe/idempotent-in-spirit like `GET`), and keeps the submitted
  answer out of query strings and access logs.
- **Rejected alternatives:** `GET .../{number}?answer=...` — semantically
  wrong for evaluating user input via `GET`, and leaks the submitted answer
  into server/proxy access logs; `PUT .../{number}/answer` — more RESTfully
  "pure" (treats the answer as a resource) but adds no practical value given
  the endpoint is stateless and persists nothing.

### AD-4: New lean repository local to `src/guidami_ai_patente/repositories/`, not an extension of `commons.QuizReadRepository`
- **Rationale:** The check only needs a plain `SELECT number, correct_answer
  FROM quiz_questions WHERE number = %s` — no join to
  `quiz_question_embeddings`. `commons.QuizReadRepository` is scoped to the
  retrieval-evaluation aggregate; a join-less, by-number lookup doesn't
  belong there and is only ever needed by this app, so it stays local as a
  pywire `@repository`.
- **Rejected alternatives:** Extending `commons.QuizReadRepository` with a
  `fetch_by_number` method — would muddy its retrieval-evaluation scoping
  and mix constructor injection (`commons` style) into a pywire-driven
  dependency graph for no real benefit.

### AD-5: `AppConfig` becomes a pywire `@component`, zero-arg constructible from env + `configs/app_config.yaml`
- **Rationale:** `pywire.Container.resolve` always instantiates an
  unresolved type via a zero-argument call, and the container has no
  instance-registration/provider mechanism. ADR 0015's original plan
  ("`AppConfig` stays plain data ... exposed to the container") is therefore
  not implementable as written. `AppConfig` instead becomes a `@component`
  itself, sourcing required fields (e.g. `postgres`) from env/`.env`/yaml the
  same way `guidami_ai_patente_ingestor.configs.IngestorConfig` already does.
- **Rejected alternatives:** Continuing to look for a provider/instance-
  registration mechanism that doesn't exist in the current pywire code — not
  viable without extending pywire itself, out of scope here.

### AD-6: Objects needing constructor arguments (e.g. `commons.PostgresClient`) are built inside a pywire component's own `__init__`, after its `Autowired` fields are set — not autowired directly
- **Rationale:** pywire's instrumented `__init__` wrapper resolves and sets
  every `Autowired[T]` field before calling the class's own `__init__` body,
  so a `@component`'s hand-written `__init__` can read its own autowired
  fields to construct something pywire itself cannot build directly.
  Concretely: a new `@client class PostgresClientProvider`
  (`guidami_ai_patente/clients/`) declares `config: Autowired[AppConfig]` and
  builds `PostgresClient(self.config.postgres)` in its own `__init__`.
  Because pywire's default scope is `SINGLETON`, every
  `Autowired[PostgresClientProvider]` elsewhere resolves to the same wrapped
  connection.
- **Rejected alternatives:** Each `@repository` autowiring `AppConfig` and
  building its own `PostgresClient` independently — opens a separate DB
  connection per repository, wasteful; reaching into `Container._registry`
  directly to pre-seed an instance — relies on a private attribute, fragile.
- **Constraint carried forward (AD-15 in the discussion log):** every
  consumer autowires `Autowired[AppConfig]` whole and reads the field it
  needs — there is no per-sub-config wrapper component (e.g. no
  `Autowired[PostgresConnectionConfig]` directly). This was deliberately
  explored and rejected: pywire has no "publish"/provider primitive
  equivalent to Spring Boot's `@Bean` factory methods, and every workaround
  found (wrapper component copying the value out of `AppConfig`, decorating
  the shared `commons.PostgresConnectionConfig` type, extending pywire
  itself) was rejected as either contradicting `AppConfig`'s single-source-
  of-truth role or out of scope. Revisit only if pywire gains such a
  mechanism.

### AD-7: 404 via a domain exception + a global FastAPI exception handler; router stays a thin controller
- **Rationale:** `QuizQuestionRepository.get_correct_answer(number) -> bool |
  None` (`None` = not found) → `QuizAnswerChecker.check(number, answer) ->
  bool` raises a new `QuestionNotFoundError` when the repository returns
  `None` → an exception handler registered on the `FastAPI` app maps
  `QuestionNotFoundError` to a 404 response. Keeps the router free of
  `try/except` and HTTP-status knowledge; the error→HTTP mapping stays in
  `api/`, not in `services/`.
- **Rejected alternatives:** Raising/catching `HTTPException` directly in the
  router — simpler, but spreads "what does not-found mean" across both the
  router and the service instead of keeping it a pure domain concept
  translated to a transport concern in exactly one place.

### AD-8: Test both layers — a unit test on `QuizAnswerChecker` (mocked repository) plus one router-level integration test against the real ephemeral Postgres stack
- **Rationale:** Mirrors how `GET /health` proved its own DI wiring
  end-to-end (ADR 0016) — this endpoint gets the same end-to-end proof, but
  for a real DB round-trip. The unit test keeps the comparison logic fast and
  DB-independent; the integration test (`@pytest.mark.integration`) is the
  only place a real `SELECT` against `quiz_questions` is exercised, using the
  project's existing ephemeral Postgres stack — never the dev DB. The
  integration test seeds data by constructing a real
  `PostgresClient(postgres_test_config)` directly (mirroring the ingestion
  tests' existing pattern), rather than routing test setup through
  `AppConfig`/env vars. The app's own pywire-resolved chain is pointed at that
  same ephemeral stack by a single session-scoped `AppConfig` fixture in
  `tests/guidami_ai_patente/conftest.py`, which builds
  `AppConfig(postgres=<test-stack config>)` before any container resolution:
  pywire caches the first constructed instance as the process-wide singleton,
  so that one fixture fixes the DB target for every `Autowired[AppConfig]` in
  the session. `tests/guidami_ai_patente/api/routers/test_health.py` is
  refactored onto the same fixture so that no second `AppConfig` is ever built,
  and `tests/conftest.py`'s Docker-free connection values are split out of
  `postgres_test_config` so the `/health` test keeps running without Docker.
- **Rejected alternatives:** Unit-only — never proves the router → pywire →
  repository → Postgres wiring actually works; integration-only — proves the
  wiring but makes the fast/common-case logic test slow and Docker-dependent.
- **Rejected alternatives (DB target):** Setting `POSTGRES__*` env vars in a
  session fixture and letting `AppConfig()` self-load them (the mechanism ADR
  0017 sketches) — works, but leaves two ways to build an `AppConfig` in the
  suite and still requires removing `test_health.py`'s explicit construction,
  which would otherwise win the singleton race and silently point the
  integration test at the **dev** stack's port 5432; dropping the router-level
  test and exercising repository + service directly — removes the risk but
  abandons the end-to-end wiring proof that is AD-8's whole point.

### AD-9: The comparison is a stateless `evaluate_answer` function; `QuizAnswerChecker` stays a thin, field-injected `@service`

The not-found check and the boolean comparison live in a module-level
`evaluate_answer(stored_answer: bool | None, submitted_answer: bool) -> bool`
that raises `QuestionNotFoundError` when `stored_answer is None`.
`QuizAnswerChecker` keeps the package-default class-level
`Autowired[QuizQuestionRepository]` field and only sequences the repository
call into that function. The unit test targets `evaluate_answer` directly and
never touches the container.

- **Rationale:** pywire's instrumented `__new__` caches the first constructed
  instance as the process-wide singleton and returns it for every later
  construction, whose `__init__` then early-returns on `_di_initialized`. A
  constructor-parameter `Autowired[T]` override therefore isolates nothing: a
  second `QuizAnswerChecker(repository=other_double)` silently returns the
  first instance holding the first double — so FR-1's two acceptance criteria
  cannot both be exercised — and that double-injected instance is exactly what
  `Autowired[QuizAnswerChecker]` resolves to afterwards in AD-8's router
  integration test, which would then never reach Postgres at all. Extracting
  the logic sidesteps the container entirely, preserves AD-8's fast,
  DB-independent half, leaves the package's field-injection convention
  untouched (no DI exception to sanction), and follows the standing "separate
  I/O from business logic" rule the other packages already apply.
- **Rejected alternatives:** Constructor-parameter `Autowired[T]` on
  `QuizAnswerChecker` (this AD's own previous form) — proven not to isolate,
  and it actively corrupts the integration test; a test-only autouse fixture
  resetting `Container._registry[...].instance` between tests — restores
  isolation but reaches into a private attribute and leaves the
  singleton-poisoning hazard latent for every future test that forgets the
  fixture; `object.__new__(QuizAnswerChecker)` + manual `setattr` — never
  contacts the container, but couples the test to pywire's instrumentation
  shape; dropping the unit test — abandons AD-8's "fast, DB-independent" half
  for logic that is cheap to test properly.
- **Consequence for ADR 0017:** its Decision item 3 (the constructor-parameter
  testability exception) is removed rather than amended — ADR 0017 is still
  `Proposed` and describes no existing code (see AD-12).

### AD-10: `QuestionNotFoundError` inherits from a new `GuidamiApiError(Exception)` base
- **Rationale:** No custom exception exists anywhere in this repository
  today — `QuestionNotFoundError` is the first. `rules/python/architecture.md`
  already lists `exceptions/` as a standard top-level package role, and a
  RAG-explanation increment (deferred, see Non-Goals) will need its own
  error(s) — a shared `GuidamiApiError` base lets the future global exception
  handler match broadly where useful and narrowly where not, without a later
  retrofit. Placement: new `guidami_ai_patente/exceptions/` package,
  `GuidamiApiError` re-exported from its `__init__.py` alongside
  `QuestionNotFoundError`.
- **Rejected alternatives:** `QuestionNotFoundError(Exception)` directly,
  flat, deferring a base until a second exception exists (YAGNI) — the
  precedent-setting cost of getting the package's first exception design
  wrong later (once call sites exist) was judged to outweigh the small
  amount of now-unused structure.

### AD-11: Request/response schemas in a new `api/schemas/quiz_check.py`, classes `QuizCheckRequest`/`QuizCheckResponse`
- **Rationale:** One schema file per *endpoint* rather than per domain. With
  a RAG-explanation increment already deferred onto the same `quiz` domain, a
  shared `quiz.py` would need to grow heterogeneously across unrelated
  endpoints; a dedicated `quiz_check.py` keeps this route's contract
  independently readable and avoids that future churn.
- **Rejected alternatives:** Domain-level `quiz.py` shared across all quiz
  endpoints — matches `api/schemas/health.py`'s current precedent more
  closely, but that precedent is only single-route by accident, not a
  deliberate one-file-per-domain choice.

### AD-12: ADR 0017 documents the `AppConfig`-as-component and constructor-built-dependent patterns (AD-5/AD-6) as an amendment to ADR 0015
- **Rationale:** ADR 0015's Consequences ("`AppConfig` stays plain data ...
  exposed to the container") are made stale by AD-5/AD-6; the rest of ADR 0015
  (adopt pywire, scope it to `guidami_ai_patente/` only, class-level fields
  rather than constructor parameters) remains valid — AD-9 no longer touches
  the field-injection clause. A single new ADR 0017 amends the stale clause,
  following the incremental-amendment precedent ADR 0016 already set for this
  same ADR (amending the route-param wiring mechanism without marking 0015
  `Superseded`). Written ahead of implementation (Status: Proposed) so the
  pattern is a reviewable, explicit target for whoever implements it. The
  drafted file currently also carries a third Decision item (the
  constructor-parameter testability exception) and a matching Consequences
  paragraph: both are deleted as part of implementing this spec, per AD-9.
- **Rejected alternatives:** Hand-editing ADR 0015's stale clause in place —
  simpler, but breaks the incremental-ADR precedent and discards the
  historical record of why the original plan proved unimplementable; keeping
  ADR 0017's constructor-parameter item as a documented-but-unused pattern —
  would sanction a mechanism AD-9 has since shown does not work.

## Data Model

No schema changes. The endpoint introduces a new read-only query against the
already-existing `quiz_questions` table, selecting only `number` and
`correct_answer` for a single row matched by the unique `number` column
(`db/init.sql:33-47`, `UNIQUE(number)` at line 46). No migration is required.

## Constraints

- `pywire` remains scoped to `src/guidami_ai_patente/` only; `commons/` and
  `guidami_ai_patente_ingestor/` keep manual constructor injection unchanged
  (ADR 0015).
- The router (`api/routers/`) contains no `try/except` or HTTP-status
  mapping logic — that stays in the global exception handler (AD-7).
- No DI exception is introduced: every class in `src/guidami_ai_patente/`
  keeps class-level field injection (AD-9). A class needing a fast unit test
  extracts its logic into a stateless function rather than taking a
  constructor parameter.
- At most one `AppConfig` is constructed per pytest session, through the
  shared session fixture (AD-8) — pywire's singleton cache makes any second
  construction silently ineffective, and a stale one can point the suite at
  the dev database.
- No per-sub-config pywire component is introduced; every component
  autowires `Autowired[AppConfig]` whole (AD-6's carried-forward constraint).
- Integration tests target only the isolated, ephemeral test Postgres stack
  (`docker/docker-compose.test.yml`, `tests/conftest.py`) — never the dev
  database.

## Feasibility Evidence

- **AD-1** — supported by: `docs/adr/0015-pywire-di-for-fastapi-app.md:20-33`, `.claude/rules/pywire-di.md:1-15` — ADR 0015 is Accepted and scopes pywire to `guidami_ai_patente/` only (verified 2026-08-18 @ b3ca8b30)
- **AD-2** — supported by: `db/init.sql:33-47` — `quiz_questions.number` is `UNIQUE` (line 46); `id` is `BIGSERIAL PRIMARY KEY` (line 34), a storage-internal identifier (verified 2026-08-18 @ b3ca8b30)
- **AD-3** — supported by: `src/guidami_ai_patente/api/routers/health.py:1-17` — existing precedent for a route declared with a bare `Autowired[T]` parameter via `pywire.fastapi.wire(app)`, the mechanism this new route follows (verified 2026-08-18 @ b3ca8b30)
- **AD-4** — supported by: `src/commons/repositories/db/quiz_read_repository.py:36-68` — `QuizReadRepository`'s only read method (`fetch_with_vectors`) requires an embedded variant/model column and joins `quiz_question_embeddings`, confirming it does not fit a plain by-number lookup (verified 2026-08-18 @ b3ca8b30)
- **AD-5** — supported by: `.venv/Lib/site-packages/pywire/container.py:40-53` — `Container.resolve` always instantiates via a zero-argument call, no instance-registration API exists; `src/guidami_ai_patente_ingestor/configs/ingestor_config.py:19-25` — the `SettingsConfigDict(env_file=".env", yaml_file=...)` pattern `AppConfig` will mirror (verified 2026-08-18 @ b3ca8b30)
- **AD-6** — supported by: `.venv/Lib/site-packages/pywire/container.py:129-153` — the instrumented `__init__` wrapper sets every `Autowired[T]` field via `setattr` before calling the class's own `original_init` (verified 2026-08-18 @ b3ca8b30)
- **AD-7** — supported by: `src/guidami_ai_patente/api/routers/health.py:1-17` — existing thin-controller precedent (no `try/except`, no status-code logic in the router body) that the new route's exception-handler split must preserve (verified 2026-08-18 @ b3ca8b30)
- **AD-8** — supported by: `tests/conftest.py:59-76` — `postgres_test_config` fixture, fixed values (`host=localhost`, `port=5433`, ...), never the dev DB; `tests/commons/repositories/db/test_quiz_read_repository.py:18-23` — the direct-`PostgresClient`-construction pattern the integration test mirrors; `tests/guidami_ai_patente/api/routers/test_health.py:11-20` — the existing second `AppConfig(postgres=...)` construction (its `port` defaults to 5432, the dev stack's) that the shared session fixture must absorb; `.venv/Lib/site-packages/pywire/container.py:113-127` — the patched `__new__` caches the first constructed instance in the registry, which is what lets one early construction fix the DB target for the whole session (verified 2026-08-19 @ b3ca8b30)
- **AD-9** — supported by: `.venv/Lib/site-packages/pywire/container.py:113-127` — the patched `__new__` returns the cached `definition.instance` for every construction after the first, so a later `Checker(repository=other)` never gets its own instance; `.venv/Lib/site-packages/pywire/container.py:134-135` — the patched `__init__` early-returns on `_di_initialized`, so the discarded keyword is never re-applied either; both confirmed empirically (a second constructor-injected double is dropped, and the first one leaks into the container-resolved singleton) (verified 2026-08-19 @ b3ca8b30)
- **AD-10** — supported by: `src/guidami_ai_patente/repositories/__init__.py:1-5` — this package (and its siblings `services/`, `models/`, `mappers/`) is still an empty, docstring-only scaffold; a repo-wide `grep -rn "^class \w+(Error|Exception)\("  src` returns no matches, confirming no exception class exists anywhere in the codebase yet (verified 2026-08-18 @ b3ca8b30)
- **AD-11** — supported by: `src/guidami_ai_patente/api/schemas/health.py:1-10` — the existing one-file precedent this spec deliberately diverges from (per-endpoint instead of per-domain) (verified 2026-08-18 @ b3ca8b30)
- **AD-12** — supported by: `docs/adr/0017-appconfig-component-and-testable-autowiring.md:55-83` — drafted (Status: Proposed); Decision items 1/2 cover AD-5/AD-6, item 3 is the constructor-parameter exception AD-9 removes (verified 2026-08-19 @ b3ca8b30)

## Open Questions

- [ ] **non-blocking** — `.claude/rules/pywire-di.md` needs a documentation update reflecting the one sanctioned exception that survives (constructor-built dependents inside `__init__`) plus the `AppConfig`-as-`@component` change, per ADR 0017's Consequences — owner: whoever implements this spec (routine doc upkeep, not a design gap)

## Sign-off

- **Scope approved by user:** pending
- **Feasibility asserted:** by write-spec on 2026-08-18, based on Feasibility Evidence above

## Changelog

- **2026-08-19** — Amended AD-8, AD-9, AD-12, Constraints and the matching
  Feasibility Evidence after re-verifying the spec against `pywire`'s actual
  instrumentation. Two decisions did not survive the check: AD-9's
  constructor-parameter override isolates nothing (the patched `__new__` caches
  the first instance process-wide, so a second construction's keyword is
  discarded and the doubled instance leaks into AD-8's integration test), and
  AD-8 left the integration test's DB target unpinned while `test_health.py`'s
  own `AppConfig(...)` would win the singleton race and aim it at the dev
  stack's port 5432. Replaced with a stateless `evaluate_answer` function
  (AD-9) and a single session-scoped `AppConfig` fixture (AD-8); ADR 0017 loses
  its third Decision item as a consequence. Material change — status stays
  `draft`, scope needs re-approval.
