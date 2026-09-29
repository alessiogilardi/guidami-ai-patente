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

# Spec 0013: Labeling/API dependency-injection cleanup

| | |
|---|---|
| **Id** | 0013 |
| **Status** | implemented |
| **Date** | 2026-08-27 |
| **Discussion log** | — (discussed live in conversation) |
| **Supersedes / superseded by** | Supersedes ADR 0024's workaround (removes it, does not merely amend it) |

## Problem & Motivation

Phase 1 and phase 2 of the quiz-flow API (spec 0012) landed on
`feat/quiz-flow-api-phase1` with five DI/config-organization issues surfaced in
review, before any further feature work continues on this branch:

1. `AppConfig` embeds `LabelingConfig` — a `BaseSettings` in its own right — as
   a lazily-defaulted field, instead of the two root configs being loaded and
   composed explicitly at the entry point.
2. `guidami_ai_patente/clients/labeling_stack_provider.py` sits in `clients/`
   even though it isn't a thin external-API adapter — it composes config and a
   repository read into a derived domain value.
3. That placement forces a real circular import between `clients/` and
   `repositories/` (`clients` needs `AgentConfigRepository` from
   `repositories`; `repositories` needs `LabelingStackProvider` from
   `clients`, via `GoldenSetReadRepository`), currently worked around with a
   bare-module-import-plus-quoted-`Autowired[...]` trick (ADR 0024). ADR
   0024's own Consequences section already flags this as worth revisiting at
   the root if it recurs.
4. Several `@service` classes under `src/guidami_ai_patente/services/` and
   `src/labeling/services/` are one-method, one-conceptual-input domain logic
   units that fit the existing `UseCase`/`AsyncUseCase` contract
   (`src/commons/use_cases/use_case.py`) already mandated elsewhere in the
   codebase (`.claude/rules/use-case-invocation.md`), but aren't using it.

This spec is a structural cleanup, not a feature change: no endpoint,
response shape, or persisted behavior changes. It exists so the branch's DI
shape is sound before phase 3 (RAG explanation) adds more services on top of
it.

## Functional Requirements

### FR-1: `AppConfig` and `LabelingConfig` are independently loaded and composed, not nested

`AppConfig` stops declaring `labeling: LabelingConfig` as a
`default_factory`-defaulted field. `main.py` loads both root configs
explicitly and registers each as its own instance on the pywire container.
Every consumer that today reads `self.config.labeling.X` instead declares
`labeling_config: Autowired[LabelingConfig]` and reads `self.labeling_config.X`.

**Acceptance criteria:**
- `AppConfig` has no `labeling` field.
- `main.py` constructs `LabelingConfig()` and `AppConfig()` separately and
  registers both with `register_instance`.
- Both current readers of the nested field switch to an autowired
  `LabelingConfig`, not `AppConfig.labeling`: `AgentConfigRepository`
  (`agents_dir`) and `LabelingStackProvider` (the whole config object, passed
  to `LabelingEpochMapper.from_config_to_epoch`).
- `uv run pytest` (including the `AppConfig`/`LabelingConfig` construction
  tests) passes with the same effective runtime values as before (same env
  vars, same `configs/labeling.yaml`).

### FR-2: `LabelingStackProvider` moves to a new `providers/` package

A new `src/guidami_ai_patente/providers/` package holds `LabelingStackProvider`
and documents the pattern it is the reference example of: **a Provider is an
infrastructure-layer component that implements a contract the inner layers (a
`UseCase`, a `*Service`, the domain) rely on, to supply a technical service or
access to an external resource, while those inner layers stay completely
unaware of the implementation detail behind it** (AD-16, revised — see
`.claude/rules/pywire-di.md`'s "`@provider`" section for the full definition
and its "is this a provider" test). The test is the *direction of the
dependency* — infrastructure supplying the inner layers, never the reverse —
not how many arguments a constructor takes or whether a method takes
parameters: AD-16's original "zero-argument `__init__`" wording described the
two examples this project had at the time, but was never the defining
property, and this spec retires it in favor of the direction-of-dependency
test. `PostgresClientProvider` fits the revised definition conceptually — it
hands the pooled DB client to every repository that reads through it, none of
which knows how the pool was built — but stays decorated `@client` and
physically in `clients/`; its placement there is temporary, pending
`commons/` itself adopting pywire, and this spec deliberately does not change
its decorator without also moving its file (see the `@provider`/`@client`
paragraph below).

`pywire` was bumped to v0.6.0 (during this same work session, ahead of this
spec's implementation) and ships a native `provider` decorator — previously
just `client`/`service`/`repository`/`agent`, all aliases of the same
`component()` registration (`pywire/aliases.py`). `LabelingStackProvider`
switches its decorator from `@client` to `@provider`, matching AD-16's
criterion now that the alias exists and the class is moving into
`providers/` anyway. `PostgresClientProvider` keeps `@client`: its
placement in `clients/` is itself temporary, pending `commons/` adopting
pywire, and changing its decorator without moving its file would blur the
distinction this FR is drawing rather than sharpen it — the file-move is
what marks a class as "the `providers/` pattern," not the decorator alone.

**Acceptance criteria:**
- `guidami_ai_patente/providers/__init__.py` exists, re-exports
  `LabelingStackProvider`, and its module docstring states the revised AD-16
  definition above (infrastructure implementing an inner-layer contract, not
  the retired zero-arg-constructor wording).
- `guidami_ai_patente/clients/` no longer contains `labeling_stack_provider.py`;
  it still contains `postgres_client_provider.py`.
- `LabelingStackProvider` is decorated `@provider` (from `pywire`), not
  `@client`; `PostgresClientProvider` keeps its existing `@client` decorator.
- No other existing `@service`/`@repository` class is reclassified as a
  provider by this spec (in particular, `QuizImageService` stays a `@service`:
  it decides a business rule — the DB-first authorization ordering — so it
  does not keep business logic unaware of implementation detail, which
  disqualifies it under the revised definition just as it did under the
  original one).
- Every consumer of `LabelingStackProvider` updates its import to
  `guidami_ai_patente.providers`.

### FR-6: `PostgresClientProvider` releases its pool via pywire's teardown hook

`pywire` 0.6.0 adds bean teardown: a `@pre_destroy`-decorated instance method
is discovered automatically at registration time — independent of which
registration decorator (`@client`, `@provider`, ...) the class itself
carries — and run by `Container.close()`, in reverse build order, when the
container is closed. `PostgresClient` (`commons/`)
already exposes a synchronous `close()`. Before this FR, the pool this
provider opens in `__init__` was never released — pywire had no teardown
mechanism at all when spec 0012 introduced it (see this spec's original
Non-Goals, written against pywire 0.5.0).

`PostgresClientProvider` gains a `@pre_destroy`-decorated method that calls
`self.client.close()`. The API's shutdown path — `create_app`'s `_lifespan`,
after its `yield` — closes the default container, crossing to a worker
thread like every other call into the sync stack (AD-25): closing a pool is
blocking I/O, same reasoning as the FR-14 startup check.

**Acceptance criteria:**
- `PostgresClientProvider` has exactly one `@pre_destroy`-decorated method,
  which calls `self.client.close()` and nothing else.
- `_lifespan` calls `await asyncio.to_thread(get_default_container().close)`
  after `yield`, unconditionally (unlike the FR-14 startup check, a shutdown
  teardown failure is allowed to propagate and be logged by uvicorn — nothing
  downstream depends on the process surviving it).
- A unit test constructs `PostgresClientProvider` with a fake `client` (per
  `docs/second-brain/testing.md`'s `object.__new__` pattern is not usable
  here since `__init__` does real work — construct it against a fake
  `PostgresClient` double instead) and asserts calling the `@pre_destroy`
  method invokes the fake's `close()` exactly once.
- An integration test resolves `PostgresClientProvider` through a real
  container against the test Postgres stack, calls `container.close()`, and
  asserts it does not raise.

### FR-3: The `clients`↔`repositories` circular import is removed at the root, not routed around

`GoldenSetReadRepository.find_current_labeling` stops reading
`Autowired[LabelingStackProvider]` itself. Its signature gains an explicit
`epoch: LabelingEpoch` parameter; the repository field `labeling_stack` is
removed. The one caller, `ExplanationStatusService.resolve`, passes
`self.labeling_stack.epoch` (it already autowires `LabelingStackProvider` for
`candidate_variant`, so this adds no new dependency edge for that class).
ADR 0024's bare-import-plus-quoted-`Autowired` mechanism is deleted from
`golden_set_read_repository.py` along with the field it existed to support.

**Acceptance criteria:**
- `repositories/` contains no import of anything from `clients/` or
  `providers/` other than `PostgresClientProvider` (a true leaf — unaffected
  by this change, and importable from the `clients` package re-export like
  any other consumer once the cycle is gone).
- `import guidami_ai_patente.repositories; import guidami_ai_patente.providers`
  and the reverse order both succeed in a fresh process (the empirical check
  ADR 0024 itself used).
- A new ADR records this as superseding ADR 0024 (marks it superseded, does
  not delete it — decision history is kept).
- Existing `GoldenSetReadRepository`/`ExplanationStatusService` tests pass
  with the new signature; a test asserting `find_current_labeling` is a pure
  function of its two parameters (no hidden state read) is added or confirmed
  to already exist.

### FR-4: Services whose public contract is one input → one output become `UseCase`/`AsyncUseCase`

Per the general criterion now recorded in
`.claude/rules/use-case-invocation.md`: a class is `UseCase`-shaped when it
exposes exactly one public operation with one well-defined input and one
well-defined output — regardless of how many repositories, services,
config objects it depends on, and regardless of how much internal
orchestration (including concurrency/retries) it takes to produce that
output. Dependency count and internal complexity do **not** disqualify a
class; only a **multi-operation** public surface or a **void/no-output**
contract does.

The following convert to `UseCase[T_In, T_Out]` or `AsyncUseCase[T_In, T_Out]`
subclasses, invoked via `__call__` per `.claude/rules/use-case-invocation.md`
(that rule's stated scope is extended to cover these two locations as part of
this spec):
- `guidami_ai_patente/services/`: `ExplanationStatusService`, `QuizImageService`,
  `QuizAnswerChecker`
- `labeling/services/`: `CandidateSetService`, `QuestionLexemeService`,
  `GoldenSetLabelingService` (`AsyncUseCase[int, int]` — `run_id` in, the
  labeled-question count out; its concurrency/retry machinery is internal to
  `execute` and does not change the contract). Confirmed in during design
  discussion: the earlier instinct to exclude it for being an async
  orchestrator was the wrong axis — `UseCase` shape and `orchestrators/`-style
  *placement* are independent (see the rule file). Whether it *additionally*
  belongs in `orchestrators/` as a `*Pipeline` is a separate placement
  question, deliberately left open (see Non-Goals) — it stays in
  `labeling/services/` for this spec regardless of that outcome.

Each gets a request DTO when its current method takes more than one scalar
argument (e.g. `QuizAnswerChecker`'s `(number, submitted_answer)`); a
single-argument method keeps that argument as `T_In` directly (no
one-field-wrapper DTO for its own sake).

The following stay excluded — multi-operation or void-output — with the
reason recorded inline as a class-docstring note so a future reader doesn't
re-propose the conversion without re-litigating it:
- `QuizProposalService`, `HealthCheckService` — multiple, unrelated public
  operations grouped by domain/router convenience; splitting each into its
  own `UseCase` class multiplies files and, for `HealthCheckService`, forces
  a no-op request DTO for two argument-less methods, for no behavioral
  benefit (YAGNI).
- `JudgeCoherenceChecker` — a void, side-effecting startup diagnostic; it has
  no meaningful `T_Out` to type.

**Acceptance criteria:**
- All six listed classes subclass `UseCase`/`AsyncUseCase`
  (`GoldenSetLabelingService` → `AsyncUseCase`, matching its existing
  `async def label_all`; the other five are synchronous today and convert to
  synchronous `UseCase`), implement `execute`, and every call site invokes
  them via `__call__` (`self._x(request)`), not `.execute(request)`.
- pywire's field-injection convention is unchanged: the three `guidami_ai_patente`
  classes remain `@service`-decorated with `Autowired[T]` fields; `UseCase`
  inheritance and pywire decoration are independent axes and both apply where
  relevant. The `labeling/services/` classes keep manual constructor injection
  (FR-5) — `UseCase` inheritance there is likewise independent of DI style.
- The two multi-operation/void-output excluded classes each carry a
  one-to-two-sentence docstring note stating why they were deliberately left
  out.
- `.claude/rules/use-case-invocation.md`'s scope line is updated to include
  `src/guidami_ai_patente/services/` and `src/labeling/services/` for the six
  converted classes (not a blanket extension to every class in those
  directories).

### FR-5: `src/labeling/` remains pywire-free; the batch harness is untouched

No change to ADR 0021 (`src/labeling/` has no `pywire` import and no
dependency on `guidami_ai_patente`, enforced by
`tests/labeling/test_module_boundary.py`) and no change to
`src/guidami_ai_patente_ingestor/` or `src/retrieval_evaluation/`'s manual DI.

**Acceptance criteria:**
- `tests/labeling/test_module_boundary.py` passes unmodified.
- `retrieval_evaluation/label_main.py` and `retrieval_evaluation/main.py`
  require no changes to *how* `GoldenSetLabelingService` and its
  collaborators are constructed (manual constructor injection, unchanged
  argument list) or wired (`labeling/wiring.py` builder functions, unchanged
  signatures) — this is what "the batch harness is untouched" means. The one
  exception, forced by FR-4's own `__call__`-only invocation rule: three
  existing call sites change from method calls to `__call__`, one of them in
  `label_main.py` and two internal to `labeling/services/` itself —
  `label_main.py`'s `service.label_all(run_id)` → `service(run_id)`, and
  (inside `GoldenSetLabelingService`/`CandidateSetService` respectively)
  `self._candidate_set_service.build(row)` → `self._candidate_set_service(row)`
  and `self._lexeme_service.build(row)` → `self._lexeme_service(row)`. These
  are one-line call-syntax updates at existing call sites, not new
  dependencies, new construction logic, or a DI-style change — the original
  "no changes" wording undersold this and is corrected here.

## Non-Goals

- Migrating `commons/` (in particular `PostgresClient`) to pywire — out of
  scope; `PostgresClientProvider`'s placement in `clients/` is explicitly
  temporary pending that future migration, not something this spec resolves.
- Extending pywire to `src/guidami_ai_patente_ingestor/` or
  `src/retrieval_evaluation/` (the batch harness) — explicitly rejected during
  design discussion: at the time of that discussion, pywire's `Container` had
  no resource-teardown mechanism (`clear_instances()` only dropped the cache,
  it did not call `close()`/`__exit__` on anything), which the batch harness
  relies on for deterministic Postgres-pool and `QueuedLlmCallTracker`
  cleanup. **Update:** pywire 0.6.0 (bumped mid-session, see FR-6) adds
  `@pre_destroy`/`on_close` teardown via `Container.close()`, so the
  technical blocker behind this rejection no longer holds. The rejection
  itself stands unchanged for this spec — migrating the batch harness to
  pywire is a separate, larger decision than a DI cleanup — but a future spec
  revisiting it would no longer need to solve the teardown problem first.
- Converting `QuizProposalService`, `HealthCheckService`, or
  `JudgeCoherenceChecker` to `UseCase` (see FR-4).
- Any change to endpoint contracts, response schemas, or persisted behavior.
- Moving `GoldenSetLabelingService` to `orchestrators/` as a `*Pipeline` —
  it converts to `AsyncUseCase` in place (FR-4) but its *placement* is a
  separate, deliberately deferred decision.

## Architectural Decisions

### AD-1: `providers/` is defined by the direction of the dependency (revised AD-16), not as a general "supplies a resource" category
- **Rationale:** the alternative (any component that hands a resource back to
  its caller) has no crisp boundary against `*Service` — nearly every service
  in this codebase "provides" something to its caller. AD-16 originally drew
  that boundary with a mechanically-checkable proxy (zero-arg `__init__` that
  performs I/O once) matching the two examples this project had at the time
  (`LabelingStackProvider`, `PostgresClientProvider`) precisely — but a proxy
  is not the property itself, and would wrongly exclude a future provider
  whose method legitimately takes a parameter. This spec revises AD-16 to the
  actual property: a provider is infrastructure implementing a contract the
  inner layers rely on to supply a technical service or external-resource
  access, keeping those inner layers unaware of the implementation detail —
  the test is whether the class *decides* something or only *supplies*
  something, not its constructor's arity (`.claude/rules/pywire-di.md`'s
  "`@provider`" section carries the full definition going forward).
- **Consequence:** `QuizImageService` stays a `@service` despite superficially
  "reading and handing back a resource" — it *decides* something (the FR-12
  DB-first authorization ordering is a business rule it enforces, not a
  detail it hides), which disqualifies it under the revised test exactly as
  it did under the retired one.

### AD-2: The circular import is fixed by removing the dependency edge, not by generalizing ADR 0024's workaround
- **Rationale:** ADR 0024 itself names this exact fix as the better long-term
  option in its Consequences section. `GoldenSetReadRepository` reading
  "which epoch is current" via an autowired provider was a repository making
  a business-logic decision (which config epoch applies); passing `epoch` as
  a parameter moves that decision to the service layer where it already
  partly lives (`ExplanationStatusService` already autowires
  `LabelingStackProvider` for `candidate_variant`).
- **Consequence:** `GoldenSetReadRepository.find_current_labeling` becomes a
  pure function of its parameters — easier to unit-test, no hidden state.

### AD-3: `PostgresClientProvider` gets a `@pre_destroy` hook now that pywire 0.6.0 makes it possible, rather than deferring it to the future `commons/`-adopts-pywire migration

- **Rationale:** the pool leak was always there (spec 0012 shipped it
  unclosed because pywire had nothing to close it with); fixing it does not
  need to wait for `PostgresClientProvider`'s eventual move out of `clients/`
  — the two are independent. `@pre_destroy` is a one-method addition with no
  interaction with the FR-2 file move or the FR-1 config split.
- **Consequence:** the API process now closes its Postgres pool
  deterministically on shutdown instead of relying on process exit; the
  pattern (`@pre_destroy` on a provider, `container.close()` in the ASGI
  lifespan shutdown) becomes the reference example for any future pywire
  bean that owns a resource.

## Migration Notes (for the implementation plan)

This spec deliberately does not sequence the work — that is the
`writing-plans` skill's job. Two ordering constraints worth carrying into the
plan:
- FR-1 (config split) should land before FR-2/FR-3, since FR-2's new
  `providers/` module and FR-3's parameter-passing both read more naturally
  against the post-split `Autowired[LabelingConfig]` shape than against the
  nested one.
- FR-4 (UseCase conversion) is independent of FR-1–FR-3 and can be sequenced
  either before or after; keeping it last is likely lower-risk since it
  touches the largest number of files for the least architecturally
  load-bearing reason.
- FR-6 (teardown) is independent of every other FR — it touches only
  `PostgresClientProvider` and `_lifespan`. No ordering dependency on FR-2:
  FR-2 leaves `PostgresClientProvider`'s decorator untouched (it stays
  `@client`), so there is no shared line to sequence around.
