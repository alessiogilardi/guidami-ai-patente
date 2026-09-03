# ADR 0030: `QuestionLabelingService` Is the One Shared Per-Question Labeling Unit

## Status

Proposed

## Context

ADR 0021 extracted the labeling machinery into `src/labeling/` specifically so
the batch pass and a future live judge could share **one** implementation,
because `labeling_runs`' `prompt_version` cache key cannot distinguish two
judging implementations that happen to agree today. That extraction moved the
machinery into the package; it did not yet split "judge this question and
record the verdict" out of the batch driver as its own reusable unit.

Before spec 0012 phase 3 Task 5, that logic lived inside
`GoldenSetLabelingService.label_all`, entangled with the batch's own selection
(`--topic`/`--limit`) and concurrency (`asyncio.Semaphore`) concerns. Spec 0012
phase 3 (AD-25) needs a live judge callable from an `async def` FastAPI route
(`CommaSelectorService`), and `GoldenSetLabelingService` as written is not that
shape: it drives a whole run over the entire bank, not a single question, and
its concurrency model (a per-run semaphore sized for a batch pass) has nothing
to do with a single incoming HTTP request.

Two implementations of "judge this question" — one for the batch, one
hand-written for the live path — would reproduce exactly the risk ADR 0021
exists to prevent: the epoch key records the judge's identity (model, prompt
hash, arm depths, variant, lexeme fields) but not the presentation shuffle, the
absent-image fallback text, the no-candidate rationale, or the retry policy —
details the judge reads on every call. A second implementation could drift on
any of those without the epoch key ever noticing, silently mixing verdicts
from two different judges under one `prompt_version`.

This is quiz-flow-api-phase3 plan decision D8 (with D3 covering the provider
split that exposes it to the API, ADR 0029), implemented in Task 5 and
consumed by Task 9's `LiveLabelingStackProvider` and Task 10's
`CommaSelectorService`.

## Decision

Extract the per-question judging logic into `QuestionLabelingService`
(`src/labeling/services/question_labeling_service.py`,
`AsyncUseCase[QuestionLabelingRequest, int | None]`), the **one** implementation
of "retrieve candidates, shuffle, judge, resolve ordinals, write":

- **Input**: `QuestionLabelingRequest(row: QuizEvaluationRow, resolve_run_id:
  Callable[[], int])`. `resolve_run_id` is a callback, not a plain `int`,
  specifically so the run id can be resolved **after** the judge has answered
  rather than before — see "Lazy run-id resolution" below.
- **Output**: the new labeling's id, or `None` when another writer already won
  the `(run_id, quiz_question_id)` race (AD-19) — not an error, interpreted
  differently by each caller (a `warning` for the batch, the designed outcome
  for two concurrent live misses).
- Two callers, one implementation:
  - `GoldenSetLabelingService.execute` (the batch fan-out) —
    `resolve_run_id=lambda: run_id`, trivial, since the batch already created
    its run id once, before the pass, exactly as before this extraction.
  - `guidami_ai_patente/services/comma_selector_service.py::CommaSelectorService._label_live`
    (the live cache fill) — `resolve_run_id=lambda: self._live_run_id(epoch)`,
    which does real work: `GoldenSetWriteRepository.find_or_create_live_run`.
- **`asyncio.to_thread` lives inside the unit, not at each call site.** Both
  the candidate-set retrieval and the write cross `asyncio.to_thread` inside
  `QuestionLabelingService.execute` itself (AD-25). This is what lets a
  genuinely synchronous batch caller (`GoldenSetLabelingService`, driven by
  `asyncio.gather` under a semaphore) and a genuinely async API caller
  (`CommaSelectorService`, awaited from an `async def` route) invoke the exact
  same code without either one special-casing the other's concurrency model.
  It also changes the batch's own behaviour: candidate-set retrieval and the
  insert now fan out under the batch's semaphore instead of serialising on the
  event-loop thread, which is what `label_main.py` sizing its pool at
  `concurrency + 1` (not `concurrency`) is for.
- **Lazy run-id resolution.** `_write` calls `request.resolve_run_id()` after
  the judge has already returned a verdict, immediately before the labeling
  insert — not before the judge call. For the live path this makes "no row is
  written to any golden-set table" literally true on a judge failure: an
  eagerly-created `labeling_runs` row would otherwise survive as an orphan
  even though the judge never answered. The batch path is unaffected in
  practice (its `resolve_run_id` is a trivial closure over an id created
  upfront), but shares the same mechanism rather than a second one.

## Alternatives considered

- **Leave the logic in `GoldenSetLabelingService`, have `CommaSelectorService`
  call it with a one-question, no-concurrency invocation** — rejected: the
  method's shape (drives a whole run, owns selection and a semaphore) has no
  clean single-question entry point without threading run-scoped concerns
  (topics, limit, concurrency) through a call that needs none of them.
- **Write a second, live-only implementation, hand-tuned for the API** —
  rejected outright: this is exactly the divergence risk ADR 0021 exists to
  prevent, reproduced one layer down.
- **Have each caller cross `asyncio.to_thread` itself, keep the unit plain
  synchronous `def`** — rejected: would force the batch's existing
  `asyncio.gather`-based caller to also learn about threading, and would leave
  a plain synchronous method un-callable from `CommaSelectorService`'s
  `async def` context without a wrapper at every call site rather than once,
  inside the unit.
- **Resolve the run id eagerly, before the judge call, and roll back on
  failure** — rejected: `PostgresClient` runs `autocommit=True` with no
  multi-statement transaction API (see `patterns.md`), so "roll back" would
  mean a second `DELETE`, adding a failure mode (the delete itself failing)
  the lazy-resolution design avoids by construction.

## Consequences

- The batch pass and the live cache fill are now provably one code path, not
  two synchronized-by-convention copies: a future prompt or retrieval change
  edits `QuestionLabelingService` once, and both callers pick it up.
- `GoldenSetLabelingService` is now pure selection-and-concurrency glue
  (`--topic`/`--limit` filtering, semaphore fan-out) with no judging logic of
  its own — a smaller, more focused class, and a second reference for "shared
  unit + thin per-caller orchestration" alongside `patterns.md`'s existing
  entries.
- The batch pass fans out more DB work concurrently than before this
  extraction (candidate-set retrieval and inserts now cross `to_thread` too),
  which is why `label_main.py`'s pool sizing changed from `concurrency` to
  `concurrency + 1` — a connection can now be held by the to-thread hop
  independently of whichever connection the triggering coroutine itself holds.
- `resolve_run_id` as a callback (rather than a plain `int` parameter) is a
  small API surface cost, paid once, in exchange for making "the run id isn't
  created until the judge has answered" a property of the shared unit itself,
  not something each caller has to remember to preserve.
