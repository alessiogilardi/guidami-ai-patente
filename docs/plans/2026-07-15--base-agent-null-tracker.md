---
status: Reviewed
effort: M
---
# Base Agent Null Tracker

References:

## Context and motivation

BaseAgent.run/run_sync duplicate a 6-line if self._tracker is None / else with self._tracked(...) branch (12 duplicated lines total). Introduce a Null Object (NullLlmCallTracker, no-op track()) so BaseAgent always goes through the tracked code path, removing the branching duplication.

### Affected areas

src/commons/ai/observability/services/null_llm_call_tracker.py (new), src/commons/ai/observability/services/__init__.py, src/commons/ai/observability/__init__.py, src/commons/ai/agents/base_agent.py, tests/commons/ai/observability/services/test_null_llm_call_tracker.py (new)

### Success criteria

run/run_sync no longer branch on tracker is None; existing test_base_agent.py suite passes unchanged; ruff/pyright clean

## Non-goals

Do not collapse run/run_sync into a single async/sync helper (event-loop risk from recent AsyncApplyStep incident, out of scope). Do not change the LlmCallTracker protocol, QueuedLlmCallTracker, or PydanticAILlmCallCapture.

## Decisions

1. **`NullLlmCallTracker` as a plain concrete class, not a subclass** — it satisfies the
   `LlmCallTracker` `Protocol` structurally (duck typing), matching how `QueuedLlmCallTracker`
   already does it. Lives in `commons/ai/observability/services/`, one class per file, same
   package as its sibling tracker implementation.
2. **`BaseAgent` normalizes `tracker` to a concrete instance in `__init__`** —
   `self._tracker: LlmCallTracker = tracker if tracker is not None else NullLlmCallTracker()`.
   The public constructor signature (`tracker: LlmCallTracker | None = None`) is unchanged;
   only the internal field stops being `Optional`. This removes the need for `run`/`run_sync`
   to branch on `tracker is None`, and removes the defensive `assert self._tracker is not None`
   in `_tracked`.
3. **No extraction of shared helpers in `run`/`run_sync` (Approach A, not B)** — the two
   methods keep their current shape (render prompt, debug log, `with self._tracked(...)`
   block, info log, return), just without the `is None` branch. The ~4 remaining identical
   lines are intrinsic to having two entry points (async vs sync) and are explicitly out of
   scope (see Non-goals) — adding private helpers for them would trade a small amount of
   duplication for an extra layer of indirection, not worth it for this plan's scope.
4. **Accept the always-build cost of `PydanticAILlmCallCapture`/`LlmCallLog` on the untracked
   path** — previously, an untracked agent skipped building the capture entirely; now it is
   always built and its `log` is always mapped, just discarded by `NullLlmCallTracker.track`.
   This is pure CPU (no I/O) and negligible next to LLM call network latency (seconds).
   Discussed and accepted trade-off.

## Open questions / Risks

None outstanding. Behavior parity on the untracked path relies on the existing
`test_untracked_agent_unchanged` in `test_base_agent.py`, which already asserts the
output is unaffected — no new test is added there per this plan's scope.

## Implementation tasks
### 1. Add `NullLlmCallTracker`

New file `src/commons/ai/observability/services/null_llm_call_tracker.py`: a
`NullLlmCallTracker` class with a single method `track(self, log: LlmCallLog) -> None` that
is a no-op (discards `log`). Docstring notes it is `BaseAgent`'s default collaborator when no
tracker is injected.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- Add: `tests/commons/ai/observability/services/test_null_llm_call_tracker.py::test_track_is_noop` — calling `track()` with a valid `LlmCallLog` does not raise and has no observable side effect.

### 2. Export `NullLlmCallTracker` from the observability package

- `src/commons/ai/observability/services/__init__.py`: add `from .null_llm_call_tracker import NullLlmCallTracker` and add it to `__all__`.
- `src/commons/ai/observability/__init__.py`: add `NullLlmCallTracker` to the `from .services import ...` line and to `__all__`, mirroring how `QueuedLlmCallTracker` is already exported.

**Tests**: none dedicated — covered mechanically by the DoD's import check.

### 3. Wire `NullLlmCallTracker` into `BaseAgent`, remove the `is None` branching

File `src/commons/ai/agents/base_agent.py`:
- Import `NullLlmCallTracker` alongside the existing `LlmCallTracker`, `PydanticAILlmCallCapture` import from `commons.ai.observability`.
- `__init__`: change `self._tracker = tracker` to `self._tracker: LlmCallTracker = tracker if tracker is not None else NullLlmCallTracker()`. Update the `tracker` parameter's docstring (it currently says "When `None`, `run`/`run_sync` run today's untracked path unchanged" — this is no longer accurate; describe the `NullLlmCallTracker` fallback instead).
- `run`: remove the `if self._tracker is None: ... return result.output` branch; always execute the `with self._tracked(...)` body.
- `run_sync`: same removal, mirroring `run`.
- `_tracked`: remove `assert self._tracker is not None` and the docstring sentence "Callers must have already checked `self._tracker is not None` (both do, via their early-return branch)" — no longer true once `self._tracker` is never `None`.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- No changes expected in `tests/commons/ai/agents/test_base_agent.py`: `test_tracked_run_sync_records_success`, `test_tracked_run_records_success`, `test_tracked_error_propagates_and_logs`, and `test_untracked_agent_unchanged` already exercise both the tracked and untracked paths through the public API and should pass unchanged.

## Definition of Done

Variable block (plan-specific):

- [ ] `grep -n "self._tracker is None" src/commons/ai/agents/base_agent.py` returns no matches
- [ ] `uv run python -c "from commons.ai.observability import NullLlmCallTracker"` succeeds
- [ ] `uv run pytest tests/commons/ai/agents/test_base_agent.py tests/commons/ai/observability/services/test_null_llm_call_tracker.py -v` all pass

Fixed block (same for every plan):

- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Plan updated to `status: Implemented`
