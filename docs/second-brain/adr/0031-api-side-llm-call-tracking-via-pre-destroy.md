# ADR 0031: API-Side LLM Call Tracking, Owned by `pywire`'s `@pre_destroy`

## Status

Proposed

## Context

`QueuedLlmCallTracker` (`commons/ai/observability/`) writes `LlmCallLogEntity`
rows through a background worker fed by an internal queue — the batch harness
(`retrieval_evaluation/main.py`, `label_main.py`,
`guidami_ai_patente_ingestor/cli/commands/prepare.py`) has always used it via
`build_llm_call_tracker`, entered as a context manager around the whole run, so
the worker is drained and joined when the `with` block exits.

Spec 0012's original design specified no observability for the API path at
all (this is not a gap the API introduces; it is a scope boundary spec 0012
drew deliberately). Before this decision, `labeling.wiring.build_comma_labeler_agent`
accordingly documented its `tracker` parameter as unusable from the API: a
`QueuedLlmCallTracker`'s background worker needs *something* to own its
lifecycle and drain it on shutdown, and until pywire 0.6.0 there was no
request-independent place to put that ownership — a per-request tracker would
mean starting and draining a worker on every single call, defeating the point
of a queue-backed tracker.

pywire 0.6.0 added `@pre_destroy`: a bean method `Container.close()` calls
once, in reverse build order, when the container's owner (here, the ASGI
app's `pywire_lifespan`) shuts down. `PostgresClientProvider` already uses
this shape to release its pool (spec 0013 FR-6). The same mechanism removes
the API tracker's blocking obstacle: a container-scoped bean can now own the
tracker's lifecycle across the whole process lifetime, entered once at
startup and drained once at shutdown, exactly like the batch's per-run
context manager but scoped to the container instead of to one run.

This is quiz-flow-api-phase3 plan decision D5, implemented in Task 2
(`LlmCallTrackerProvider`) and consumed by Task 9's `LiveLabelingStackProvider`
(ADR 0029) and Task 6's `ExplanationWriterAgent`.

## Decision

Add `LlmCallTrackerProvider` (`guidami_ai_patente/providers/llm_call_tracker_provider.py`,
`@provider`, `Autowired[ObservabilityConfig, PostgresClientProvider]`):

- `__init__` enters `build_llm_call_tracker(observability_config,
  postgres.client)`'s context manager once, through an `ExitStack`, and exposes
  the result as `self.tracker: LlmCallTracker`.
- A `@pre_destroy`-decorated `close` method calls `self._stack.close()`,
  draining the tracker's background worker exactly once, when
  `Container.close()` runs at ASGI shutdown.
- Depends on `Autowired[PostgresClientProvider]` deliberately, even though it
  only needs `.client`: `Container.close()` runs `@pre_destroy` hooks in
  reverse build order, so this dependency edge is what guarantees the tracker's
  queue drains **before** the pool it writes through closes. Removing the edge
  (e.g. resolving the client some other way) would invert that order and risk
  losing the tail of the queue on shutdown.
- With `ObservabilityConfig.enabled` false, `build_llm_call_tracker` yields
  `NullLlmCallTracker` instead — the provider's shape is identical either way,
  so disabling tracking is a configuration change, never a code branch this
  provider has to special-case.

Both real callers of `labeling.wiring.build_comma_labeler_agent` now pass a
tracker — the batch through `build_llm_call_tracker` directly (unchanged), the
API through `LlmCallTrackerProvider.tracker`. The `tracker` parameter stays
optional on the builder itself (a caller with no sink can still omit it — e.g.
a unit test), but the "API runs untracked" premise recorded in that builder's
docstring no longer holds and the docstring is corrected in the same task that
records this decision (Task 14).

## Alternatives considered

- **A per-request tracker, entered and drained on every call** — rejected:
  defeats the reason `QueuedLlmCallTracker` is queue-backed (batching writes
  across calls); would also pay worker start/stop cost on every single
  explanation request.
- **A module-level singleton tracker, built lazily on first use, with no
  formal teardown** — rejected: exactly the "background lifecycle has no
  request-scoped owner" problem this decision solves, just moved to an
  implicit global instead of an explicit one; would leak the worker (and any
  buffered rows) on process exit, and violates this repo's "no global state,
  config/resources loaded once at a composition root" convention
  (`~/.claude/rules/python/architecture.md`).
- **Extend `pywire` to the batch harness too, and unify both trackers behind
  one construction path** — out of scope for this decision: `commons/`,
  `labeling/` and `guidami_ai_patente_ingestor/` deliberately keep manual
  constructor injection (ADR 0015); folding the batch onto `pywire` is a
  separate, much larger change with no immediate driver here.

## Consequences

- The live explanation path (judge call + writer call) is now observable the
  same way the batch is — cost, tokens, latency, one `LlmCallLogEntity` row
  per call — closing the gap spec 0012 deliberately left open and spec 0013
  FR-6 closes.
- `LiveLabelingStackProvider` (ADR 0029) must keep its `Autowired[LlmCallTrackerProvider]`
  edge even though nothing in its own body reads from it directly beyond
  passing `.tracker` to `build_comma_labeler_agent` — the edge exists for
  teardown ordering as much as for construction, and removing it "because
  nothing seems to use it" would silently reintroduce the drain-before-close
  race this decision closes.
- `labeling.wiring.build_comma_labeler_agent`'s docstring, and any other
  documentation written against the pre-0.6.0 "API runs untracked" premise,
  needed a one-time correction once this decision landed (done in the same
  task, Task 14) — a stale docstring here would actively mislead a future
  reader into believing the API still has no request-scoped tracker owner.
