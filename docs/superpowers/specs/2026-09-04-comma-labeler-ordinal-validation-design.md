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

# Spec 0014: Comma-labeler ordinal self-correction via pydantic-ai output validator

| | |
|---|---|
| **Id** | 0014 |
| **Status** | draft |
| **Date** | 2026-09-04 |
| **Discussion log** | — (discussed live in conversation) |
| **Supersedes / superseded by** | — |

## Problem & Motivation

`QuestionLabelingService._resolve_labels` (spec 0011) validates each ordinal in
`CommaLabelerResponse.comma_numbers` **after** the LLM call has already returned,
checking it against `[1, len(presented)]`. On the first out-of-range ordinal it
raises `CandidateNumberOutOfRangeError` — today with **zero retry**.

On the live API path this becomes a `503` for one request. On the batch path
(`GoldenSetLabelingService`) it is worse: `asyncio.gather` runs without
`return_exceptions=True` by design (PD-9, spec 0011 — "any failure propagates and
aborts the whole run"), so one hallucinated ordinal kills the *entire* run,
discarding every already-successful labeling alongside it. AD-30's test run
observed exactly this: a single hallucinated ordinal aborted the run after 14 of
20 questions had already been labeled successfully, discarding all 14.

`CommaLabelerResponse` already has a precedent for asking pydantic-ai to retry a
bad response: `_reject_repeated_numbers` (a `@model_validator(mode="after")`
raising `ValueError` when the same candidate number appears twice) is retried
transparently by pydantic-ai's own output-retry mechanism
(`retries=config.num_retries` on `BaseAgent`'s wrapped `Agent`). The out-of-range
case has no equivalent today because the DTO alone cannot know the candidate
count (`len(presented)`) — that information lives only in the caller
(`QuestionLabelingService`), which builds the request from a shuffled subset of
retrieved candidates whose size varies per question.

This spec closes that gap: give the model a chance to self-correct an
out-of-range ordinal *within the same call*, using the request it was actually
given, before falling back to today's hard failure.

### Approaches considered and rejected

Three alternatives were explored and rejected in favor of the chosen design
(AD-1 below); recorded here so the exploration isn't silently lost:

- **Dynamic per-call `output_type=`**: build a narrower Pydantic model per call
  with `Annotated[int, Field(ge=1, le=len(presented))]` and pass it as an
  `output_type=` override to `.run()`. Rejected: requires either two
  `@overload`s or a new method on `BaseAgent` to avoid the project's
  "no `T | Sequence[T]`-shaped union return" convention
  (`.claude/rules/code-conventions.md`), plus building/caching one dynamic
  model class per distinct candidate count — more moving parts than the chosen
  approach for the same retry-budget benefit.
- **`validation_context=`**: verified against `pydantic_ai==1.107.0`'s actual
  source and confirmed empirically (`FunctionModel` spike) that
  `validation_context` is a Agent-**construction-time** parameter (not a
  per-call `.run()` kwarg, contrary to an initial assumption in this
  discussion), which only varies per call when given as a
  `Callable[[RunContext[AgentDepsT]], Any]` reading `ctx.deps` — meaning it
  requires the exact same `deps=` plumbing as the chosen approach, plus an
  extra, unnecessary `dict[str, Any]` indirection between `ctx.deps` (already
  the fully-typed request) and the DTO's `info.context.get(...)` lookup.
- **`@agent.result_validator`**: does not exist in the installed pydantic-ai
  version — confirmed via `hasattr(Agent, "result_validator") is False` and a
  live `AttributeError` on a constructed `Agent`. It is the pre-1.0 name for
  what is now `Agent.output_validator` (same rename family as
  `result_type`→`output_type`, `RunResult`→`AgentRunResult`).

## Functional Requirements

### FR-1: `BaseAgent` threads the caller's request as pydantic-ai `deps` on every call

`BaseAgent.run`/`run_sync` pass `request` (already an in-scope parameter) as
`deps=request` to the wrapped `Agent.run`/`run_sync` call. The **public**
signature of `BaseAgent.run`/`run_sync` does not change — this is purely an
internal wiring change.

**Acceptance criteria:**
- `self._agent.run(prompt_content, deps=request)` (async) and
  `self._agent.run_sync(prompt_content, deps=request)` (sync) replace today's
  calls without `deps=`.
- No change to `BaseAgent.run`'s or `run_sync`'s parameter list or return type.
- Every existing `BaseAgent` caller (all 5 concrete agents) keeps working
  unchanged: passing `deps=` has no runtime effect for an agent that never
  registers an `output_validator` reading `ctx.deps` — pydantic-ai does not
  runtime-check a passed `deps` value against the agent's declared
  `deps_type` (confirmed in `pydantic_ai/agent/__init__.py`: "We could do
  runtime type checking of deps against `self._deps_type`, but that's a
  slippery slope" — it does not).

### FR-2: `BaseAgent` subclasses declare an explicit `input_type: type[T_In]`, mirroring `output_type`

For `self._agent.run(..., deps=request)` (FR-1) to type-check, the wrapped
`Agent` must be `Agent[T_In, T_Out]` (not today's `Agent[None, T_Out]`), which
requires a real `deps_type=` value at construction. Python does not preserve a
class's own generic type arguments as an introspectable runtime value, so —
exactly like the existing `output_type: type[T_Out]` class attribute — every
`BaseAgent` subclass declares `input_type: type[T_In]`. `BaseAgent.__init__`
passes `deps_type=self.input_type` to the wrapped `Agent(...)`.

**Acceptance criteria:**
- `BaseAgent` declares `input_type: type[T_In]` (bare annotation, no default —
  same style as `output_type`) and `self._agent: Agent[T_In, T_Out]` typed
  accordingly.
- All 5 concrete agents gain `input_type = <ThisAgent'sRequest>` alongside
  their existing `output_type = ...`: `ExplanationWriterAgent`,
  `RetrievalJudgeAgent`, `CommaLabelerAgent`, `RoadSignDescriberAgent`,
  `NormReferenceDescriberAgent`.
- All 3 test-double `BaseAgent` subclasses under `tests/commons/ai/agents/`
  (`test_base_agent.py`, `test_base_agent_openrouter_cost_integration.py`,
  `test_base_agent_from_yaml_injection.py`) gain a matching `input_type = ...`
  so they keep constructing successfully.
- No behavior change for the 4 agents other than `CommaLabelerAgent`: `deps` is
  threaded but never read by any of them.

### FR-3: `CommaLabelerAgent` retries an out-of-range ordinal via `ModelRetry`

`CommaLabelerAgent` registers an `output_validator` — via
`self._agent.output_validator(self._validate_comma_numbers)`, called from an
overridden `__init__` after `super().__init__(...)` — that inspects
`ctx.deps.candidates` (the same `CommaLabelerRequest` the model was prompted
with) and raises `pydantic_ai.ModelRetry` when any entry of
`response.comma_numbers` falls outside `[1, len(ctx.deps.candidates)]`. The
`ModelRetry` message states the offending number(s) and the valid range, so the
retried prompt carries concrete corrective guidance.

This reuses `retries=config.num_retries` — the exact same output-retry budget
that already retries `CommaLabelerResponse._reject_repeated_numbers` — with no
new orchestration. Verified empirically (a `pydantic_ai.models.function.
FunctionModel`-based spike: an agent configured with `deps_type`, an
`output_validator` raising `ModelRetry` on the first, out-of-range attempt, and
a valid response on the second, converges to the correct output after exactly 2
model calls) and in `pydantic_ai/result.py`, where `ValidationError` and
`ModelRetry` are caught in the identical `except` clause (lines 92 and 302 of
the installed 1.107.0 source) and funneled through the same
`consume_output_retry` budget.

**Acceptance criteria:**
- `CommaLabelerAgent.__init__` mirrors `BaseAgent.__init__`'s parameter list,
  calls `super().__init__(...)`, then registers the validator.
- `_validate_comma_numbers(self, ctx: RunContext[CommaLabelerRequest], data:
  CommaLabelerResponse) -> CommaLabelerResponse` raises `ModelRetry` on any
  out-of-range ordinal and otherwise returns `data` unchanged.
- New test file `tests/labeling/agents/comma_labeler/test_comma_labeler_agent.py`
  (following the `FunctionModel`-based pattern already used in
  `tests/commons/ai/agents/test_base_agent.py`) covers:
  - an out-of-range ordinal on attempt 1, in-range on attempt 2 → the agent
    returns the attempt-2 response after exactly 2 model calls;
  - an ordinal that stays out of range for every attempt → the run raises
    `pydantic_ai.exceptions.UnexpectedModelBehavior` once
    `config.num_retries` is exhausted (confirmed message shape in
    `pydantic_ai/_agent_graph.py`: `"Exceeded maximum output retries (N)"`).

### FR-4: `QuestionLabelingService._resolve_labels`'s manual guard is unchanged

The existing bounds check in `_resolve_labels` and
`CandidateNumberOutOfRangeError` are **not** modified, weakened, or removed.

**Acceptance criteria:**
- `question_labeling_service.py` and `labeling_errors.py` have no functional
  changes.
- The existing test `test_an_out_of_range_number_raises_and_writes_nothing`
  (`tests/labeling/services/test_question_labeling_service.py`) keeps passing
  unchanged — it exercises `_resolve_labels` through `_RecordingAgent`, a test
  double that returns a bare `_FakeResponse` dataclass and never goes through
  `BaseAgent`/pydantic-ai's output-validation pipeline at all, so FR-3 does not
  touch that path.

## Non-Goals

- Removing or weakening `_resolve_labels`'s manual guard (FR-4) — it stays as
  the contract's defensive final check for any caller/test double that
  supplies an agent-like object outside pydantic-ai's own validation pipeline.
- Changing PD-9's abort-on-failure semantics: `GoldenSetLabelingService` still
  aborts the whole run on the first propagating exception. FR-3 makes an
  out-of-range ordinal far less likely to *become* such an exception (the
  model gets a chance to self-correct in-call); it does not change what
  happens once retries are exhausted (`UnexpectedModelBehavior` still
  propagates, still aborts the run, exactly as `_reject_repeated_numbers`'s
  own exhausted retries already do today).
- Applying `deps`-aware output validation to any agent other than
  `CommaLabelerAgent`. `ExplanationWriterAgent`, `RetrievalJudgeAgent`,
  `RoadSignDescriberAgent`, and `NormReferenceDescriberAgent` gain `input_type`
  (FR-2) and unused `deps` plumbing (FR-1) but no new validator and no
  behavior change.
- Any change to `CommaLabelerResponse`'s own `_reject_repeated_numbers`
  validator or its retry behavior.

## Architectural Decisions

### AD-1: Mechanism is `Agent.output_validator` + `ModelRetry`, reusing `deps=` — not `output_type=` override, not `validation_context=`

- **Rationale:** `deps=` is already a first-class, per-call `Agent.run`/
  `run_sync` parameter requiring no new orchestration; an `output_validator`
  reading `ctx.deps` gets the fully-typed request directly, with no
  intermediate structure. `ModelRetry` and a schema-level `ValidationError`
  are provably interchangeable to pydantic-ai's retry machinery (same `except`
  clause, same `consume_output_retry` budget) — verified in the installed
  1.107.0 source, not assumed. `validation_context=` was verified to require
  identical `deps=` plumbing to vary per call (it is a construction-time
  parameter, evaluated per-call only when given as a callable reading
  `ctx.deps`), so it adds an unnecessary `dict[str, Any]` layer between
  `ctx.deps` and the DTO's `info.context.get(...)` lookup, for no benefit.
  Dynamic per-call `output_type=` narrowing was rejected as needing more new
  surface (a second `run` overload/method plus per-count model caching) for a
  retry-budget benefit `output_validator` already provides for free.
- **Consequence:** `BaseAgent[T_In, T_Out]`'s wrapped `Agent` becomes
  `Agent[T_In, T_Out]` (deps_type=T_In) instead of `Agent[None, T_Out]`; every
  subclass declares `input_type` alongside `output_type` (FR-2), a small,
  uniform, mechanical addition across 5 production agents and 3 test doubles.

### AD-2: `@agent.result_validator` is confirmed dead code in this dependency, not a viable alternative

- **Rationale:** `hasattr(Agent, "result_validator")` is `False` on
  `pydantic_ai==1.107.0`, and calling it on a live `Agent` instance raises
  `AttributeError: 'Agent' object has no attribute 'result_validator'`. It is
  the pre-1.0 name for what this version calls `output_validator` (same
  rename family as `result_type`→`output_type`).
- **Consequence:** no code in this spec references `result_validator`; any
  future reader who finds it in older pydantic-ai documentation should read
  `output_validator` instead.

### AD-3: `_resolve_labels`'s manual guard is kept because it protects a different boundary than FR-3 does

- **Rationale:** against the real `CommaLabelerAgent`, FR-3's validator
  inspects every `comma_numbers` entry on every attempt, so an out-of-range
  ordinal either self-corrects within the retry budget or the run raises
  `UnexpectedModelBehavior` *before* `_resolve_labels` is ever reached — it
  cannot structurally reach `_resolve_labels` with an out-of-range value via
  the live agent path once FR-3 lands. `_resolve_labels`'s guard is exercised
  today, and remains exercised, only by `QuestionLabelingService`'s own unit
  tests, which double the agent with a bare object (`_RecordingAgent`,
  `_SequencedAgent`) returning a `_FakeResponse` dataclass that never passes
  through `BaseAgent` or pydantic-ai's validation pipeline at all. Removing
  the guard would silently assume every future caller of
  `QuestionLabelingService` goes through a real, correctly-validated
  `CommaLabelerAgent` — an assumption the test suite itself does not make.
- **Consequence:** no deletions in `question_labeling_service.py` or
  `labeling_errors.py`; `CandidateNumberOutOfRangeError` keeps its existing
  meaning and test coverage.

## Migration Notes (for the implementation plan)

This spec deliberately does not sequence the work — that is the
`writing-plans` skill's job. Two ordering constraints worth carrying into the
plan:
- FR-1 and FR-2 are not independently shippable: `self._agent.run(...,
  deps=request)` (FR-1) does not type-check without `Agent[T_In, T_Out]`
  (FR-2) already in place. They land as one change.
- FR-3 depends on FR-1+FR-2 landing first: `RunContext[CommaLabelerRequest]`
  inside `_validate_comma_numbers` requires `CommaLabelerAgent.input_type =
  CommaLabelerRequest` to already exist.
- FR-4 requires no code change, only verification that the existing test
  (`test_an_out_of_range_number_raises_and_writes_nothing`) still passes
  unchanged after FR-1–FR-3 land.
