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
discarding every already-successful labeling alongside it. A labeling test run
observed exactly this: a single hallucinated ordinal aborted the run after 14 of
20 questions had already been labeled successfully, discarding all 14. (Note:
this is an informal observation from that run, not a citation of the
project's own AD-30 — AD-30, spec 0012, is an unrelated decision about
golden-set cache pre-warming strategy.)

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

Four alternatives were explored and rejected in favor of the chosen design
(AD-1/AD-2 below); recorded here so the exploration isn't silently lost:

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
- **`input_type: type[T_In]` class attribute, mirroring `output_type`**: this
  spec's own first draft. Typing `self._agent: Agent[T_In, T_Out]` requires
  passing `deps_type=` to the wrapped `Agent(...)` with a real runtime value
  whose static type is `type[T_In]` — otherwise pyright rejects the
  construction outright (confirmed: `Agent(...)` without `deps_type=` infers
  `Agent[None, T_Out]`, and assigning that to a variable annotated
  `Agent[T_In, T_Out]` fails with `"Agent[None, T_Out]" is not assignable to
  "Agent[T_In, T_Out]"` — `AgentDepsT` is contravariant and `None` is not a
  supertype of an arbitrary `T_In`). The only way to supply that value is a new
  required class attribute on every subclass, exactly like `output_type`.
  Rejected after verifying with pyright that a simpler `Agent[Any, T_Out]`
  typing on `BaseAgent` gives **identical** type-safety inside
  `CommaLabelerAgent`'s own validator: pyright checks a function body against
  its own declared parameter annotations, independent of how the enclosing
  `Agent` is (erased-)typed. Confirmed both ways with `reveal_type(ctx.deps)`
  (returns the concrete request type in both cases) and a deliberately
  mistyped attribute access (`reportAttributeAccessIssue` in both cases).
  `Agent[Any, T_Out]` gets the same safety where it actually matters, without
  touching the 4 unrelated agents or the 3 test doubles at all.

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

### FR-2: `BaseAgent`'s wrapped `Agent` is typed `Agent[Any, T_Out]` — no new class attribute required

`self._agent`'s declared type widens from `Agent[None, T_Out]` to
`Agent[Any, T_Out]`. No `deps_type=` kwarg is passed to the wrapped
`Agent(...)` constructor — it keeps defaulting to `NoneType` at runtime, which
is irrelevant, since pydantic-ai never checks a passed `deps` value against
`deps_type` (FR-1). The `Any` widening only relaxes the type pyright assigns
to `self._agent`'s own `deps` parameter; it has no effect on how precisely
`CommaLabelerAgent`'s own validator is typed (FR-3), since a function's
parameter annotations are checked against its own declared signature,
independent of how the object it's registered on is (erased-)typed.

**Acceptance criteria:**
- `self._agent: Agent[Any, T_Out]` in `BaseAgent.__init__` (not
  `Agent[None, T_Out]`, not `Agent[T_In, T_Out]`).
- No new class attribute on `BaseAgent` or on any of its 5 concrete
  subclasses or 3 test doubles; `output_type` remains the only required one.
- `uv run pyright src tests` introduces no new errors beyond the pre-existing
  63-error baseline (measured 2026-09-04, entirely in
  `tests/labeling/services/test_candidate_set_service.py` and
  `tests/labeling/test_wiring.py`, unrelated to this spec's files) — the
  count after this change is 63, not a delta the implementer must eyeball.

### FR-3: `CommaLabelerAgent` retries an out-of-range ordinal via `ModelRetry`

`CommaLabelerAgent` registers an `output_validator` — via
`self._agent.output_validator(self._validate_comma_numbers)`, called from an
overridden `__init__` after `super().__init__(...)` — that inspects
`ctx.deps.candidates` (the same `CommaLabelerRequest` the model was prompted
with) and raises `pydantic_ai.ModelRetry` when any entry of
`response.comma_numbers` falls outside `[1, len(ctx.deps.candidates)]`. The
`ModelRetry` message states the offending number(s) and the valid range, so the
retried prompt carries concrete corrective guidance — **in Italian**: pydantic-ai
injects this message back into the live conversation as the model's next-turn
context, and `comma-labeler`'s system/user prompts are entirely Italian
(`configs/agents/comma_labeler.yaml`), so an English correction would splice a
language switch into an otherwise all-Italian conversation. This extends
`.claude/rules/code-conventions.md`'s existing "prompt-facing text" exception
(previously scoped to response-DTO docstrings/`Field(description=...)`) to
`ModelRetry` messages specifically — updated as part of this spec.

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

Before raising, `_validate_comma_numbers` logs a `warning` — the canonical
level for "a retry happened" per `.claude/rules/logging.md`. Without this, the
retry is invisible unless the budget is later exhausted (at which point
`UnexpectedModelBehavior` propagates and is logged elsewhere, but every
self-corrected attempt in between leaves no trace). `CommaLabelerRequest`
carries no quiz identifier (`CommaLabelerAgent` is a "pure LLM wrapper" by its
own docstring, with no knowledge of quiz identity), so the message reports
only the offending ordinal(s) and the valid range — not which question
triggered it. No `exc_info=True`: this is the detection point, not a handler
for an already-active exception.

**Acceptance criteria:**
- `CommaLabelerAgent` overrides `__init__` with the exact same typed
  parameter list as `BaseAgent.__init__` (`config`, `provider`, `file_reader`,
  `tracker` — no `*args`/`**kwargs`, per the project's "type hints everywhere"
  standard), calls `super().__init__(config, provider, file_reader, tracker)`,
  then calls `self._agent.output_validator(self._validate_comma_numbers)`.
- `_validate_comma_numbers(self, ctx: RunContext[CommaLabelerRequest], data:
  CommaLabelerResponse) -> CommaLabelerResponse` calls `logger.warning` in
  English, with lazy `%s` args (`.claude/rules/logging.md` — never an
  f-string, enforced by ruff's `G004`), carrying the offending ordinal(s) and
  the valid range; then raises `ModelRetry` with a **separate, Italian**
  message carrying the same facts, since it is prompt content sent back into
  `comma-labeler`'s all-Italian conversation, not a logging call (`G004`
  does not apply to it — see the extended exception in
  `.claude/rules/code-conventions.md`). Otherwise returns `data` unchanged
  with no log.
- New test file `tests/labeling/agents/comma_labeler/test_comma_labeler_agent.py`
  (following the `FunctionModel`-based pattern already used in
  `tests/commons/ai/agents/test_base_agent.py`) covers:
  - an out-of-range ordinal on attempt 1, in-range on attempt 2 → the agent
    returns the attempt-2 response after exactly 2 model calls, and exactly
    one `warning` record was emitted (via `caplog`);
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

### FR-5: `comma-labeler`'s `num_retries` is raised from the default (3) to 5

`configs/agents/comma_labeler.yaml` does not override `num_retries` today, so
it inherits `AgentConfig`'s default of 3 — a budget originally sized for one
failure mode (`_reject_repeated_numbers`). FR-3 adds a second, independent
condition that competes for the same budget (`ModelRetry` on an out-of-range
ordinal), so the shared budget is raised to leave room for one mistake of
each kind plus margin, without guessing at a much larger number the next
labeling run's data hasn't justified yet.

**Acceptance criteria:**
- `configs/agents/comma_labeler.yaml` sets `num_retries: 5` explicitly (no
  other agent's YAML config changes).
- `uv run ingest status` (or the equivalent config-loading test) confirms the
  loaded `AgentConfig` for `comma-labeler` reflects `num_retries == 5`.

### FR-6: `_reject_repeated_numbers`'s retry message switches to Italian

Verified in `pydantic_ai/_output.py:121-129` (`_make_retry_prompt`): a
`ValidationError`'s content sent back to the model is
`e.errors(include_url=False, include_context=False)` — pydantic's structured
error list, whose `msg` field carries the custom message from the
`raise ValueError(...)` inside the validator. This is exactly as
prompt-facing as a `ModelRetry` message (FR-3): both are injected into the
live conversation as retry feedback. `_reject_repeated_numbers`'s message
("comma_numbers must not repeat a candidate number") predates this spec and
is in English, splicing a language switch into `comma-labeler`'s all-Italian
conversation on every retry it triggers — the same inconsistency FR-3 avoids
introducing. This FR closes that pre-existing gap rather than leaving it as a
second, inconsistent precedent alongside FR-3's new Italian `ModelRetry`
message.

**Acceptance criteria:**
- The `raise ValueError(...)` inside `CommaLabelerResponse._reject_repeated_numbers`
  (`src/labeling/agents/comma_labeler/dto/comma_labeler_response.py`) carries
  an Italian message stating the same fact (no repeated ordinal allowed),
  in a tone consistent with the class's existing Italian docstring and
  `Field(description=...)` text.
- An inline comment immediately above the `raise` states *why* the message is
  Italian (the WHY, not the WHAT — code-conventions.md style): it is
  prompt-facing text sent back to the model as retry feedback, per
  `.claude/rules/code-conventions.md`'s "prompt-facing text" exception
  (extended by FR-3/this spec to cover validator retry messages, not only
  DTO docstrings/`Field(description=...)`).
- `tests/labeling/agents/comma_labeler/dto/test_comma_labeler_response.py:19`
  (`pytest.raises(ValidationError, match="must not repeat a candidate
  number")`) is updated to match the new Italian message text — this test
  pins the literal English string today and will fail otherwise.

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
  `RoadSignDescriberAgent`, and `NormReferenceDescriberAgent` gain unused
  `deps` plumbing (FR-1) but no new class attribute, no new validator, and no
  behavior change.
- Changing `_reject_repeated_numbers`'s *retry behavior* (it keeps rejecting
  on any repeated ordinal, unconditionally) — only its message text changes
  (FR-6).
- Tuning `num_retries` beyond the FR-5 bump to 5, or introducing a distinct
  retry budget per failure mode. Further tuning is deferred to a future pass
  once FR-3's new `warning` logs give real data on how often each failure
  mode actually fires.

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
- **Consequence:** `BaseAgent[T_In, T_Out]`'s wrapped `Agent` is retyped
  `Agent[Any, T_Out]` (FR-2) so `deps=request` (FR-1) type-checks; no new
  class attribute is needed on any of the 5 production agents or 3 test
  doubles — only `CommaLabelerAgent` and its own response DTO gain new code
  (FR-3, FR-6).

### AD-2: `Agent[Any, T_Out]`, not `Agent[T_In, T_Out]` + `input_type` — verified with pyright to give identical safety where it matters

- **Rationale:** forcing `self._agent: Agent[T_In, T_Out]` requires a new
  `input_type: type[T_In]` class attribute on every subclass (see "Approaches
  considered and rejected" above for the concrete pyright error this
  produces without one). Two isolated probes were run through `uv run
  pyright` to compare the alternative directly: with `Agent[Any, T_Out]` on
  `BaseAgent` and no `input_type` anywhere, `CommaLabelerAgent`'s own
  `_validate_comma_numbers(ctx: RunContext[CommaLabelerRequest], data:
  CommaLabelerResponse)` still resolves `reveal_type(ctx.deps)` to the
  concrete request type and still flags a mistyped attribute access
  (`reportAttributeAccessIssue`) — identical to the `input_type` variant. The
  `Any` widening only affects the *wiring* boundary inside `BaseAgent`
  (whether pyright cross-checks the declared `deps_type` against what's
  passed to `.run()`), not the *validator body* boundary (checked from its
  own explicit annotation regardless) — and only the latter is where a real
  mistake (e.g. reading the wrong field off `ctx.deps`) would actually be
  caught.
- **Consequence:** `ExplanationWriterAgent`, `RetrievalJudgeAgent`,
  `RoadSignDescriberAgent`, `NormReferenceDescriberAgent`, and the 3
  `BaseAgent` test doubles under `tests/commons/ai/agents/` need no change at
  all beyond inheriting `deps=request` being passed with no effect.

### AD-3: `@agent.result_validator` is confirmed dead code in this dependency, not a viable alternative

- **Rationale:** `hasattr(Agent, "result_validator")` is `False` on
  `pydantic_ai==1.107.0`, and calling it on a live `Agent` instance raises
  `AttributeError: 'Agent' object has no attribute 'result_validator'`. It is
  the pre-1.0 name for what this version calls `output_validator` (same
  rename family as `result_type`→`output_type`).
- **Consequence:** no code in this spec references `result_validator`; any
  future reader who finds it in older pydantic-ai documentation should read
  `output_validator` instead.

### AD-4: `_resolve_labels`'s manual guard is kept because it protects a different boundary than FR-3 does

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
`writing-plans` skill's job. Ordering constraints worth carrying into the
plan:
- FR-1 and FR-2 are not independently shippable: `self._agent.run(...,
  deps=request)` (FR-1) does not type-check unless `self._agent` is already
  typed `Agent[Any, T_Out]` (FR-2). They land as one change, entirely within
  `base_agent.py`.
- FR-3 depends on FR-1+FR-2 landing first: `CommaLabelerAgent`'s overridden
  `__init__` calls `self._agent.output_validator(...)` on the `self._agent`
  that FR-1/FR-2 already construct.
- FR-4 requires no code change, only verification that the existing test
  (`test_an_out_of_range_number_raises_and_writes_nothing`) still passes
  unchanged after FR-1–FR-3 land.
- FR-5 (the YAML config bump) is independent of FR-1–FR-4 and can land in any
  order relative to them — it touches only `configs/agents/comma_labeler.yaml`.
- FR-6 (the `_reject_repeated_numbers` message translation) is independent of
  FR-1–FR-5 — it touches only `comma_labeler_response.py` and its own test —
  but should land in the same commit or immediately alongside FR-3, since
  both establish the same new convention (Italian retry-feedback messages)
  and reviewing them apart would make the convention easy to miss.
