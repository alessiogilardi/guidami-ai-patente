# ADR 0023: `AppConfig` reaches the container as a registered instance, superseding ADR 0017's zero-arg-component and constructor-parameter decisions

## Status

Accepted

## Context

ADR 0017 (`pywire` v0.3.x) found no seam through which an externally-constructed
`AppConfig` instance could reach the container, and worked around that gap two ways:
`AppConfig` became a zero-arg `@component` that loads itself lazily on first
resolution (Decision item 1), and a class needing a test double declared that
dependency as an `Autowired[T]` **constructor parameter** rather than a class-level
field (Decision item 3) — a scoped exception to this package's field-only convention.

`pyproject.toml` now pins `pywire` at `v0.5.0` (`0613545d`; verified in
`.venv/Lib/site-packages/pywire/container.py`), which ships three methods that did
not exist when ADR 0017 was written: `register_instance(instance, *, as_type=None)`
(registers an already-built object as a type's singleton), `register_factory(target_type,
factory)` (registers a lazy builder), and `clear_instances()` (drops cached singletons
for test isolation, keeping registrations). This closes the exact gap ADR 0017's Context
found missing — recorded as a proposal in ADR 0017's amendment (Phase 1, quiz-flow-api
Task 11) and accepted by the user during the Phase 2 grilling/check session that preceded
this plan's implementation (2026-08-26).

## Decision

1. **`AppConfig` is loaded once at the entry point (`main.py`) and registered on the
   container**, exactly as `rules/python/architecture.md`'s general "config loaded at
   the entry point" rule already prescribes for every other root config in this repo:
   `main.py` builds `AppConfig()` and hands the instance to the container via
   `container.register_instance(app_config, as_type=AppConfig)`. This supersedes ADR
   0017's Decision item 1 (`AppConfig` as a zero-arg `@component` constructing itself
   lazily on first resolution).
2. **A class needing a substitute dependency for a unit test stays field-only
   `Autowired[T]`**, like every other pywire class in this package. The test registers
   a mock via `register_instance`/`register_factory` against the container (the default
   container, or an isolated one) before resolving the component under test, and calls
   `clear_instances()` between tests for isolation. This supersedes ADR 0017's Decision
   item 3 (the constructor-parameter testability exception): no class in
   `src/guidami_ai_patente/` needs `Autowired[T]` as a constructor parameter to be
   testable.
3. **ADR 0017's Decision item 2 is unaffected and remains in effect.** A component
   needing a real constructor argument the container cannot build zero-argument
   (`PostgresClientProvider` wrapping `PostgresClient(config.postgres)`) still builds it
   inside its own `__init__`, after its own `Autowired` fields are set (ADR 0017,
   confirmed by `Container._instrument`'s field-then-`__init__` ordering). `register_instance`/
   `register_factory` do not solve that problem any more cleanly than the existing
   pattern.

## Alternatives considered

- **Leave ADR 0017 as written and build Phase 2 against it**: keeps `AppConfig` a
  self-loading zero-arg `@component` and requires `QuizAnswerChecker`-style classes to
  take their dependencies as constructor parameters. Rejected: `AppConfig` no longer
  loading at the entry point is a deviation ADR 0017's own Consequences already flagged
  as a cost to fix, and the constructor-parameter exception was only ever a workaround
  for a capability gap that no longer exists in the pinned `pywire` version.
- **Hand-edit ADR 0017 in place instead of a new ADR**: simpler file count, but this
  project's ADR numbering convention (`docs/second-brain/adr/`) treats a superseding
  decision as a new, separately dated record rather than a silent rewrite of history —
  ADR 0017's Context/Decision/Alternatives remain an accurate account of what was true
  against `pywire` 0.3.x. Not chosen.
- **Defer this ADR to the end of Phase 2** (as the phase2 plan originally scheduled it,
  Task 14): technically valid — nothing in Tasks 1-13 requires the ADR file to exist
  before the code is written — but leaves the accepted decision undocumented for the
  whole implementation window, during which a reader would find ADR 0017 still marked
  `Proposed` for a pattern the code already uses. Not chosen; the user accepted the
  amendment during the pre-Phase-2 grilling session, so the record is written now.

## Consequences

- `.claude/rules/pywire-di.md` is updated to state the accepted pattern directly
  (`AppConfig` registered via `register_instance`, no constructor-parameter exception),
  replacing the guidance ADR 0017 had introduced.
- The Phase 2 plan (`docs/superpowers/plans/2026-08-24-quiz-flow-api-phase2-plan.md`)
  referred to this ADR as "ADR 0021" when it was written (2026-08-24); ADR numbers 0021
  and 0022 were claimed by Phase 1's own ADRs (`0021-shared-labeling-stack-extracted-
  into-labeling.md`, `0022-postgres-client-connection-pool.md`) before this one was
  filed. This is ADR 0023 — the plan's task text is stale on the number, not on the
  substance, and is corrected via an amendments note rather than a silent edit.
- ADR 0017 is amended in place to record its Decision items 1 and 3 as superseded by
  this ADR, with item 2 explicitly carried forward — see that file's amendment section.
- No code changes yet: this ADR documents an accepted decision ahead of the Phase 2
  implementation that exercises it (Tasks 1-2 build `create_app`/the session fixtures
  against this pattern).
