# ADR 0017: `AppConfig` as a pywire component, constructor-built dependents, and a constructor-parameter testability exception

## Status

Proposed

## Context

ADR 0015 adopted `pywire` for dependency injection in `src/guidami_ai_patente/`, but
scoped its own claims to what the package looked like at the time: no route needed a
config-dependent dependency, so ADR 0015's Consequences state "`AppConfig` stays plain
data, loaded once at the entry point and exposed to the container rather than autowired
as a component itself." Designing the first endpoint that actually needs Postgres (the
quiz-check endpoint, `specs/discussions/quiz-check-endpoint.md`, D-6/D-7/D-10) exercised
that claim against `pywire`'s real, pinned implementation and found it unimplementable as
written, plus a second, independent gap in the field-injection convention that blocks unit
testing.

**`AppConfig` cannot be "exposed to the container" as ADR 0015 describes.** Verified
against `pywire.Container` (`.venv/Lib/site-packages/pywire/container.py:40-53`):
`resolve()` always instantiates an unresolved type via a **zero-argument** `target_type()`
call, and the container exposes no `register_instance`/provider mechanism — confirmed
against the full public API (`pywire/__init__.py`: `Autowired`, `BeanDefinition`,
`Container`, `DependencyResolutionError`, and the decorators; nothing else). There is no
seam through which an externally-constructed `AppConfig` instance (e.g. one loaded in
`main.py` from `.env`) could be handed to the container for later `Autowired[AppConfig]`
resolution.

**Field-only `Autowired[T]` gives dependents no way to accept a constructor argument,
including a real one like `PostgresConnectionConfig`.** `commons.clients.PostgresClient`
requires a `PostgresConnectionConfig`, which nothing in the container can build
zero-argument. `Container._instrument`'s patched `__init__`
(`container.py:129-153`), however, resolves and `setattr`s every `Autowired[T]` field
**before** calling the wrapped class's own `original_init` — so a `@component`'s
hand-written `__init__` body can already read its own autowired fields and use them to
construct something pywire itself could never build directly.

**Field-only injection also gives unit tests no override hook.** The same patched
`__init__` unconditionally resolves every raw class-level `Autowired[T]` annotation
through the real, process-wide default container on *every* instantiation — with no
parameter to substitute a mock. Concretely, `QuizAnswerChecker()`, even called directly
by a test rather than through the container, would cascade into a real
`QuizQuestionRepository()` → a real `PostgresClientProvider()`, whose `__init__` (this
ADR's own Decision, item 2) eagerly opens an actual Postgres connection — before a test
gets any chance to substitute a repository double. pywire's *constructor*-parameter path
is different: `ctor_autowired_params` resolution (`container.py:98-103,163-169`) honors
explicitly passed keyword arguments over auto-resolution ("Explicitly passed keyword
arguments win over auto-resolution").

Also verified: `pywire`'s default scope is `SINGLETON` (`BeanDefinition.scope`,
`definitions.py:17`) and `resolve()` caches the first-built instance
(`container.py:50-53`), so every `Autowired[PostgresClientProvider]` elsewhere in the app
resolves to the same wrapped connection.

## Decision

1. **`AppConfig` becomes a `@component` itself**, zero-arg constructible the same way
   `guidami_ai_patente_ingestor.configs.IngestorConfig` already is
   (`env_file=".env"`, `yaml_file="configs/app_config.yaml"`): `AppConfig()` — truly
   zero arguments — succeeds standalone, sourcing required fields (e.g. `postgres`) from
   env/`.env`/yaml. This supersedes ADR 0015's "`AppConfig` stays plain data ... exposed
   to the container" clause outright — that plan is not implementable against pywire's
   actual API.
2. **Components needing constructor arguments are built inside their own `__init__`,
   after their own `Autowired` fields are set** — not autowired directly. Concretely: a
   new `@client class PostgresClientProvider` (`guidami_ai_patente/clients/`, the
   `clients/` role already established in `rules/python/architecture.md`) declares
   `config: Autowired[AppConfig]` and builds
   `self._client = PostgresClient(self.config.postgres)` in its own `__init__`. Because
   of pywire's default `SINGLETON` scope, every `Autowired[PostgresClientProvider]`
   elsewhere in the app resolves to the same wrapped connection, avoiding one Postgres
   connection per repository.
3. **A class that must be unit-testable with a substitute dependency declares that
   dependency as an `Autowired[T]` *constructor parameter*, not a class-level field** —
   a scoped, explicitly sanctioned exception to ADR 0015's "class-level fields, not
   constructor parameters" default. First applied to `QuizAnswerChecker`
   (`repository: Autowired[QuizQuestionRepository]` as an `__init__` parameter): a test
   calls `QuizAnswerChecker(repository=mock)`, and the explicit keyword wins over
   auto-resolution, bypassing the container — and any real Postgres connection —
   entirely. Classes with no such testability need (e.g. `QuizQuestionRepository`
   itself, only ever exercised through a real-Postgres integration test) keep the
   field-only default.

## Alternatives considered

- **Reach into `Container._registry` directly to pre-seed an `AppConfig` instance**:
  would let `main.py` build `AppConfig` once and hand it to the container, closer to the
  general "config loaded at the entry point" rule (`rules/python/architecture.md`) — but
  relies on a private/underscore attribute never intended as public API, fragile to a
  future `pywire` refactor. Not chosen.
- **Each `@repository` autowiring `AppConfig` and building its own `PostgresClient`
  independently**, instead of a shared `PostgresClientProvider`: works mechanically (same
  `__init__`-ordering trick) but opens a separate DB connection per repository class —
  wasteful and inconsistent with how `commons.PostgresClient` is used elsewhere (one
  client, reused). Not chosen.
- **Bypass pywire's `__new__`/`__init__` in tests** (`object.__new__(QuizAnswerChecker)` +
  manual `setattr`) instead of a constructor-parameter exception: keeps the field-only
  convention untouched everywhere, but makes every such test depend on pywire's
  undocumented internals rather than a public, documented override mechanism. Not chosen.
- **Drop the unit test for `QuizAnswerChecker` and cover its logic only via a router-level
  integration test**: simplest, no DI exception needed at all — but makes a one-line
  boolean comparison slow and Docker-dependent to exercise, and sets a bad precedent for
  every future pywire `@service` with real logic. Not chosen.
- **Two separate ADRs** (one for the `AppConfig`/`PostgresClientProvider` construction
  mechanics, one for the constructor-parameter testability exception): cleaner separation
  of concerns, independently supersedable later — but both stem from the same root cause
  (the first pywire dependency chain with a real DB connection and a route that needs
  testing) and would otherwise cross-reference each other constantly. Not chosen; see
  `specs/discussions/quiz-check-endpoint.md` D-13.

## Consequences

- `rules/python/architecture.md`'s general "root configuration loaded at the entry point,
  injected into builders/services" rule is further overridden for
  `src/guidami_ai_patente/`, beyond what ADR 0015 already carved out for DI style itself:
  `AppConfig` now loads itself, lazily, on first container resolution — not necessarily at
  `main.py` startup, and not by being handed in from outside. `main.py` still triggers the
  app's construction, but no longer literally constructs `AppConfig` and threads it
  through as a parameter for anything DB-touching.
- `api/app.py::create_app`'s existing `config: AppConfig` parameter (and
  `app.state.config`) becomes dead for any pywire-resolved, DB-touching dependency chain:
  `PostgresClientProvider` resolves its own `AppConfig` through the container,
  independently of whatever instance a caller passes to `create_app`. This is currently
  harmless only because `GET /health` never touches `app.state.config`
  (`api/routers/health.py`) — a future cleanup should either remove the parameter or make
  it actually feed the container, so the two can't silently diverge.
- Two DI idioms now coexist *within* `guidami_ai_patente/` itself (field-level `Autowired`
  as the default, constructor-parameter `Autowired` as a documented, narrow exception for
  testability) — on top of the two idioms ADR 0015 already documented coexisting across
  packages (pywire vs. manual constructor injection). `.claude/rules/pywire-di.md` needs
  updating to state both exceptions explicitly, so they read as sanctioned patterns rather
  than inconsistency.
- Router-level integration tests for any DB-touching pywire-resolved endpoint can only
  steer the real connection target by setting `POSTGRES__*` env vars before the *first*
  container resolution of `AppConfig`/`PostgresClientProvider` in the whole pytest
  session (SINGLETON caching, `container.py:50-53`) — or, as chosen for the quiz-check
  endpoint's integration test, by bypassing the pywire-resolved chain for test *setup*
  entirely and seeding data with a directly constructed
  `PostgresClient(postgres_test_config)`, mirroring the ingestion tests' existing pattern
  (`tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_flows_integration.py`,
  `tests/commons/repositories/db/test_quiz_read_repository.py`).

## Amendment (2026-08-26, proposal — not yet accepted, quiz-flow-api-phase1 plan Task 11)

This ADR was written against `pywire` v0.3.x, whose only public registration API was
`register()`/`@component`-style class registration plus the `Autowired[T]`
constructor-parameter override this ADR's Decision item 3 relies on. `pyproject.toml`
now pins `pywire` at `v0.5.0` (`0613545d`, pre-dating this plan), whose `Container`
(`.venv/Lib/site-packages/pywire/container.py`) ships three methods that did not exist
when this ADR's Context established "there is no seam through which an
externally-constructed `AppConfig` instance ... could be handed to the container":

- **`register_instance(instance, *, as_type=None)`** (`container.py:157-198`) —
  registers an already-built object as the singleton for its own type (or `as_type`).
  Stored as a factory returning the object handed in, so `clear_instances()` treats it
  uniformly with every other registration. This is exactly the seam this ADR's Context
  found missing: `main.py` can now build `AppConfig()` once, the way
  `rules/python/architecture.md`'s general "config loaded at the entry point" rule
  already asks for, and hand the instance to the container via `register_instance`,
  rather than requiring `AppConfig` to be a zero-arg `@component` that constructs
  itself lazily on first resolution.
- **`register_factory(target_type, factory)`** (`container.py:121-155`) — registers a
  callable that builds `target_type`'s singleton on first resolution, for objects the
  container cannot construct itself. A narrower-scoped alternative to
  `register_instance` for callers that want lazy construction without a full
  `@component` class.
- **`clear_instances()`** (`container.py:255-273`) — drops every cached singleton while
  keeping every registration, explicitly intended (per its own docstring) "for test
  isolation of the module-level default container ... and for any caller that wants a
  fresh object graph without rebuilding the registry." This directly addresses the
  motivation behind this ADR's Decision item 3 (the constructor-parameter testability
  exception): a test no longer needs `QuizAnswerChecker(repository=mock)` to dodge a
  real Postgres connection cascading through field-only `Autowired` resolution — it can
  register a mock/factory before resolution and call `clear_instances()` between tests
  instead.

**What this proposes superseding, if accepted:**

- **Decision item 1** (`AppConfig` becomes a zero-arg `@component`, constructing itself
  lazily from `.env`/YAML on first container resolution) — superseded by: `main.py`
  loads `AppConfig` once, at the entry point, exactly as
  `rules/python/architecture.md`'s general rule already prescribes for every other
  package in this repo, and registers that single instance via
  `container.register_instance(app_config)`. This closes the exact deviation this ADR's
  Consequences flagged as a cost: `AppConfig` no longer "loads itself, lazily ... not
  necessarily at `main.py` startup" — plan 2 makes `main.py` construct it and thread it
  into the container explicitly, the way every other root config in this codebase is
  already loaded.
- **Decision item 3** (a class needing a substitute dependency declares it as an
  `Autowired[T]` *constructor parameter* rather than a class-level field, as a scoped
  testability exception) — superseded by: tests register a mock via
  `register_instance`/`register_factory` against a container instance (or the default
  container, cleared with `clear_instances()` before/after), and resolve the
  component-under-test normally through field-only `Autowired[T]`. This removes the
  need for the exception ADR 0017 carved out of `pywire-di.md`'s "class-level fields,
  not constructor parameters" default — `QuizAnswerChecker.repository` could revert to
  a field, tested by pre-registering a mock repository rather than by passing one in
  through `__init__`.
- **Decision item 2** (components needing constructor arguments build them inside their
  own `__init__`, after their own `Autowired` fields are set — `PostgresClientProvider`
  wrapping `PostgresClient`) is **not** affected: it addresses a different problem (an
  object pywire cannot construct zero-argument at all, e.g. one needing a
  `PostgresConnectionConfig`), which `register_factory`/`register_instance` do not
  independently solve any more cleanly than the existing pattern already does.

**Why this is a proposal, not an accepted change:** `register_instance`/
`register_factory`/`clear_instances` are new library capability, not yet exercised by
any code in this repository — no test currently calls `clear_instances()`, and no
entry point currently calls `register_instance()`. Adopting this amendment means
rewriting `main.py`'s composition-root wiring and `QuizAnswerChecker`'s test suite,
neither of which is in scope for the quiz-flow-api-phase1 plan (an ingestion-side,
non-HTTP plan). This amendment is filed here — as the Second Brain's record that the
capability gap motivating ADR 0017 no longer exists — for the user to accept,
edit, or reject before any code changes to `src/guidami_ai_patente/` are made on
its basis. `Status` above is left as this ADR's pre-existing value, not `Accepted`,
until that decision is made.
