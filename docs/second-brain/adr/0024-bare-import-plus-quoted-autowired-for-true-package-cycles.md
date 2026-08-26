# ADR 0024: Resolve a true `clients`<->`repositories` package-init cycle with a bare module import plus a quoted `Autowired[...]` forward reference

## Status

Proposed

## Context

ADR 0016/AD-16 established `guidami_ai_patente/clients/` for objects the
`pywire` container cannot build itself, shared with the pre-pywire
`commons`/`labeling` packages. `clients/__init__.py` imports
`labeling_stack_provider.py`, whose class body needs
`AgentConfigRepository` from `guidami_ai_patente.repositories` (package
re-export) — so `clients` depends on `repositories` finishing its own
`__init__.py`.

Task 6 of the quiz-flow-api-phase2 plan (`QuizQuestionRepository`) first hit
this from the other direction: a new file under `repositories/` needed
`PostgresClientProvider` from `clients`. Its fix — documented in
`patterns.md` — was to import the target submodule directly
(`from guidami_ai_patente.clients.postgres_client_provider import
PostgresClientProvider`) instead of going through the `clients` package
re-export. That works because `PostgresClientProvider` is a true *leaf*: its
own module has no back-reference into `repositories`, so loading it "out of
turn", before `clients/__init__.py` reaches its own line for it, has nothing
to wait on.

Task 7 (`GoldenSetReadRepository`) needed `LabelingStackProvider` itself —
not a leaf. `GoldenSetReadRepository` is re-exported from
`repositories/__init__.py`, and now `repositories` depends on `clients`
*for a class defined by the exact module whose own import is what pulled
`repositories` in, in the `clients`-first import order*. Concretely, in that
order:

1. `clients/__init__.py` starts executing; `sys.modules['...clients']` is
   registered but not yet fully populated.
2. Its first line imports `labeling_stack_provider.py`, which is now itself
   mid-execution, registered but not yet past its own imports.
3. That module's `from guidami_ai_patente.repositories import
   AgentConfigRepository` triggers a first-time import of the
   `repositories` package, which (per the codebase's "prefer `__init__.py`
   re-exports" convention, `.claude/rules/python/imports.md`) runs
   `repositories/__init__.py` top to bottom, which imports
   `golden_set_read_repository.py`.
4. That file's `from guidami_ai_patente.clients import LabelingStackProvider`
   re-enters step 2's module — already in `sys.modules`, so Python does not
   re-execute it, it just returns the *existing, partial* module object.
   But that module's own `class LabelingStackProvider:` statement has not
   run yet (execution is still stuck at step 3's import, several frames
   up) — so the name is not yet an attribute of the module, and the import
   raises `ImportError: cannot import name 'LabelingStackProvider' from
   partially initialized module`.

Verified empirically (fresh `uv run python -c ...` process per order) that
Task 6's direct-submodule trick does **not** generalize to this case: a
direct submodule import only skips *re-executing* a package's `__init__.py`
when the package is already mid-import elsewhere on the call stack (a true
re-entrant case) — on a first-time import of a package, `import
pkg.sub` still runs `pkg/__init__.py` to completion before loading `sub`, so
it cannot help when the requested submodule is the very one blocking that
completion. This is a genuine self-reference: `LabelingStackProvider`'s
class statement cannot run until `repositories/__init__.py` completes, and
`repositories/__init__.py` cannot complete until `LabelingStackProvider`'s
class statement has run. No import *path* trick removes that ordering
constraint — only deferring *when* the name needs to be bound does.

`pywire`'s own annotation machinery (`pywire.markers.evaluate_annotation` /
`resolve_autowired_type`, consumed by `pywire.plans.InjectionPlan.for_class`)
turns out to already support exactly this: an `Autowired[...]` argument may
be a string (a forward reference), which is `eval()`'d against the
*defining module's own live globals* — not at class-definition time, but
lazily, the first time the container actually plans/resolves that class
(`container.resolve(...)`), which happens well after every module in the
process has finished importing.

## Decision

In `src/guidami_ai_patente/repositories/golden_set_read_repository.py`:

- Keep Task 6's direct-submodule import for `PostgresClientProvider`
  (a true leaf, unaffected by this problem):
  `from guidami_ai_patente.clients.postgres_client_provider import
  PostgresClientProvider`, with `postgres: Autowired[PostgresClientProvider]`
  unchanged (eager, bound name).
- For `LabelingStackProvider`, use a **bare module import** —
  `import guidami_ai_patente.clients as clients` — instead of any
  `from ... import LabelingStackProvider` form, package- or submodule-level.
  A bare `import pkg as alias` performs no attribute lookup; it only needs
  `pkg` to be *resolvable* (present in `sys.modules`, even mid-init), which
  it always is here, in both import orders — confirmed empirically.
- Annotate the field with a **quoted** forward reference instead of a bound
  name: `labeling_stack: Autowired["clients.LabelingStackProvider"]`.
  `pywire` evaluates this string lazily, against
  `golden_set_read_repository.py`'s own globals, only when the container
  resolves `GoldenSetReadRepository` — by which point `clients` (the module
  object the bare import bound) is fully populated, so
  `clients.LabelingStackProvider` resolves like any other attribute access.

`labeling_stack_provider.py` itself is **unchanged** — the fix lives
entirely on the side performing the problematic eager lookup
(`golden_set_read_repository.py`), not on the side that merely happens to
trigger the chain.

Verified:

- Both import orders succeed in a fresh process:
  `uv run python -c "import guidami_ai_patente.repositories; import
  guidami_ai_patente.clients"` and the reverse.
- `pywire.plans.InjectionPlan.for_class(GoldenSetReadRepository).fields`
  resolves `labeling_stack` to the real `LabelingStackProvider` class (not
  just "imports without error" — the DI wiring itself was exercised).
- `ruff check` raises no `F401` on the `clients` import (it is genuinely
  referenced, inside the string) and `pyright` reports zero errors on the
  file.
- `uv run pytest tests/guidami_ai_patente` passes in full (25 non-integration
  + 24 integration), including all of `tests/guidami_ai_patente/repositories`
  (22 integration tests: Task 6's 13 plus this task's 9).

## Alternatives considered

- **Reorder `clients/__init__.py` or `repositories/__init__.py`'s import
  lines**: traced through both orders by hand; reordering only moves *which*
  side of the cycle fails first, since the underlying constraint (each
  module needs an attribute the other has not yet defined) is symmetric. No
  ordering of the four import statements involved resolves both directions
  at once.
- **Apply Task 6's direct-submodule trick to both sides**
  (`labeling_stack_provider.py` importing
  `guidami_ai_patente.repositories.agent_config_repository` directly, and
  `golden_set_read_repository.py` importing
  `guidami_ai_patente.clients.labeling_stack_provider` directly): traced
  through both orders by hand and confirmed this still fails in the
  `clients`-first order, for the reason in Context — a first-time package
  import still runs `__init__.py` to completion regardless of which
  submodule path triggered it, and `clients.labeling_stack_provider` is the
  one submodule that cannot be "already loaded" ahead of itself.
- **`TYPE_CHECKING`-only import of `LabelingStackProvider` plus a bare
  string annotation**: satisfies `pyright` but not `pywire` — pywire's
  lazy `eval()` still needs the name bound in the module's *real* (runtime)
  globals by resolve time, and a `TYPE_CHECKING` block never executes at
  runtime, so the field would always raise `AnnotationResolutionError` at
  `container.resolve()` time, cycle or no cycle. Rejected: breaks DI
  resolution unconditionally, not just during the import-order edge case.
- **Local import inside `GoldenSetReadRepository.__init__`**: rejected for
  the same underlying reason — `pywire.plans.InjectionPlan.for_class`
  inspects field annotations to plan construction *before* an instance is
  built, so a name bound only inside `__init__`'s local scope is invisible
  to the planning step; the annotation must resolve against the *module's*
  globals, which a function-local import never populates.
- **`# noqa` / `# type: ignore` suppression around a `from ... import`
  that fails at one point in the cycle**: never on the table — the repo has
  zero precedent for either suppression, and neither would fix the
  underlying `ImportError` (a lint suppression does not change import
  order); this ADR's mechanism is a genuine fix, not a silenced symptom.
- **Restructure `repositories/__init__.py` to not re-export
  `GoldenSetReadRepository`, importing it via its full module path at each
  call site instead**: rejected — the task's own test fixture (and every
  other repository in this package) does
  `from guidami_ai_patente.repositories import X`, per the codebase's
  "prefer `__init__.py` re-exports" convention
  (`.claude/rules/python/imports.md`); breaking that for one class only to
  dodge an import-order problem would be a worse trade than the mechanism
  chosen here.

## Consequences

- A new, generalizable pattern exists for the *specific* case Task 6's
  trick does not cover — a true mutual package-init cycle, where component
  A (package P) needs component B (package Q) as an `Autowired` field, and
  B's own module transitively needs something from P: import Q with a bare
  `import Q as q`, and write the field as `Autowired["q.B"]` (quoted). Keep
  the direct-submodule-import trick for genuine leaf dependencies with no
  back-reference — it is simpler and keeps the annotation a plain bound
  name where the cycle doesn't force otherwise.
- The trade-off is a less obvious annotation: a reader has to know pywire
  resolves quoted `Autowired[...]` arguments lazily to understand why the
  type is a string instead of the class itself. Mitigated with an inline
  comment at the import site (present in
  `golden_set_read_repository.py`) rather than relying on this ADR alone.
- `pyright` and `ruff` both validate the string correctly (pyright resolves
  the dotted forward reference; ruff does not flag the bare `clients`
  import as unused, since the name is referenced inside the string) — no
  suppression of any kind was needed, so this does not erode the "no
  `noqa`" precedent.
- If a *third* package joins this cycle in a future task, this ADR's
  mechanism generalizes (bare-import the package that closes the loop,
  quote the one field that needs it) without further restructuring —
  but if cycles between `clients` and `repositories` keep recurring across
  tasks, that is itself a signal worth revisiting (e.g. whether
  `LabelingStackProvider` belongs in a package one level below both, to
  remove the cycle at its root instead of routing around it repeatedly).
