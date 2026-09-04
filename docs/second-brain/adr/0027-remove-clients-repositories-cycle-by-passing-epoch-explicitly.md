# ADR 0027: Remove the `clients`<->`repositories` cycle by passing the epoch explicitly, superseding ADR 0024

## Status

Proposed

## Context

ADR 0024 resolved a true `clients`<->`repositories` package-init cycle
(`GoldenSetReadRepository` needing `LabelingStackProvider`, whose own module
transitively needs `AgentConfigRepository` back from `repositories`) with a
bare-module-import-plus-quoted-`Autowired["clients.LabelingStackProvider"]`
forward reference. That mechanism worked and was verified in both import
orders, but ADR 0024's own Consequences section already named the better
long-term fix: "if cycles between `clients` and `repositories` keep
recurring across tasks, that is itself a signal worth revisiting (e.g.
whether `LabelingStackProvider` belongs in a package one level below both,
to remove the cycle at its root instead of routing around it repeatedly)."

Spec 0013 (labeling/API dependency-injection cleanup) revisited this
directly: `GoldenSetReadRepository.find_current_labeling` was reading
"which configuration epoch is current" via the autowired
`LabelingStackProvider` — a business-logic decision (which epoch counts)
made inside a repository, not a data-access read. `ExplanationStatusService`
already autowired `LabelingStackProvider` for its own `candidate_variant`
need, so the service layer was already the natural place for this decision
to live.

## Decision

`GoldenSetReadRepository.find_current_labeling` gained an explicit
`epoch: LabelingEpoch` parameter and lost its `labeling_stack:
Autowired[...]` field entirely — its signature is now
`find_current_labeling(number: str, epoch: LabelingEpoch) -> CurrentLabeling
| None`. The one caller, `ExplanationStatusService.execute`, reads
`epoch = self.labeling_stack.epoch` once and passes it explicitly into
`find_current_labeling(request, epoch)` (it already autowired
`LabelingStackProvider` for `epoch.candidate_variant`, so this adds no new
dependency edge for that class).

This deletes ADR 0024's entire mechanism from
`golden_set_read_repository.py`: the bare `import guidami_ai_patente.clients
as clients` line, the quoted `Autowired["clients.LabelingStackProvider"]`
field, and the class-body comment explaining why. `GoldenSetReadRepository`
now imports nothing from `clients`/`providers` except `PostgresClientProvider`
(a true leaf, unaffected by any of this) — from the `clients` package
re-export, not a direct-submodule import: once the cycle was confirmed gone,
the post-review fix wave simplified this off its former direct-submodule
exception too.

Verified:

- `import guidami_ai_patente.repositories; import
  guidami_ai_patente.providers; import guidami_ai_patente.clients; import
  guidami_ai_patente.services` succeeds with no output, and the fully
  reversed order also succeeds — the cycle is gone at the root: there is no
  remaining edge from `repositories/` back to `clients/`/`providers/` for
  `pywire` to route around, in either direction.
- `tests/guidami_ai_patente/repositories/test_golden_set_read_repository_unit.py`
  (new) asserts `find_current_labeling` is a pure function of its two
  parameters with no hidden state: two calls with identical `(number,
  epoch)` arguments send byte-identical query parameters to a fake Postgres
  client, and only the epoch-derived parameters change when the epoch does.
- The full integration suite in
  `tests/guidami_ai_patente/repositories/test_golden_set_read_repository.py`
  passes with the new two-argument signature.

## Alternatives considered

- **Keep ADR 0024's mechanism, just also apply it wherever a future cycle
  appears**: this is the option ADR 0024 itself flagged as inferior once a
  cycle recurs — it treats the symptom (an import-order deadlock) rather
  than the cause (a repository making a business-logic decision it doesn't
  own). Rejected per ADR 0024's own Consequences section.
- **Move `LabelingStackProvider` one level below both `clients/` and
  `repositories/`** (ADR 0024's other suggested option, and the literal
  motivation for spec 0013's separate FR-2, which moved it to a new
  `providers/` package): this alone does not remove the cycle — `providers/`
  would still need `AgentConfigRepository` from `repositories/`, and
  `repositories/` would still need the provider back, just via a different
  package name. FR-2 (the package move) and FR-3 (this ADR, the parameter
  change) are complementary, not alternatives: FR-2 fixes *where the class
  lives* (spec 0013's provider/service categorization), FR-3 fixes *who
  decides the epoch* (the actual cycle-causing dependency edge). Only FR-3
  removes the cycle itself.
- **Autowire `LabelingStackProvider` on `ExplanationStatusService` only, and
  have it call a new `GoldenSetReadRepository` method that still autowires
  the provider internally as a fallback**: rejected as needless complexity —
  once the caller already holds the epoch, threading it through as a plain
  argument is strictly simpler than keeping two paths to the same value.

## Consequences

- `GoldenSetReadRepository.find_current_labeling` is now a pure function of
  its two parameters — easier to unit-test (no container, no real Postgres
  needed for the "no hidden state" tests), and a reader no longer needs to
  know pywire's lazy string-annotation resolution mechanism to understand
  this file at all.
- The `clients`<->`repositories` cycle ADR 0024 routed around is removed at
  the root, not relocated: `repositories/` now imports nothing from
  `clients`/`providers` except the pre-existing `PostgresClientProvider` leaf
  import, and the reverse direction (`providers`/`clients` importing from
  `repositories`) was never true. Import order no longer matters for these
  four packages.
- ADR 0024's mechanism (bare-import-plus-quoted-`Autowired`) remains valid,
  documented history for the general "true mutual package-init cycle" case —
  it is not deleted or invalidated as a technique, only no longer needed for
  this specific call site. A future genuine cycle elsewhere may still reach
  for it; ADR 0024's Status is updated to note this supersession without
  erasing its own record.

## Supersedes

ADR 0024 (`0024-bare-import-plus-quoted-autowired-for-true-package-cycles.md`).
