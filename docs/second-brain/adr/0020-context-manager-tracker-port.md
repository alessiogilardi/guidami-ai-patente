# ADR 0020: `LlmCallTracker.track` Becomes a Context-Manager Port

## Status

Proposed

## Context

`LlmCallTracker` (`commons/ai/observability/protocols/llm_call_tracker.py`) used to
expose a single method, `track(log: LlmCallLogEntity) -> None`. Building the
`LlmCallLogEntity` that method received was `BaseAgent`'s job: a
`@classmethod @contextmanager` factory
(`PydanticAILlmCallCapture.tracked(caller, model, prompt, system_prompt, tracker)`)
composed a fresh `PydanticAILlmCallCapture`, yielded it for the call, and in a
`finally` block called `tracker.track(capture.log)` — where `capture.log` went
through an intermediate DTO (`LlmCallCaptureModel`) and a real object-to-object
mapper (`LlmCallLogMapper.from_model_to_entity`) to become the entity.
`BaseAgent._tracked(prompt)` was a thin private binder over that factory, and
`BaseAgent._log_call_completed(capture)` — called from `run`/`run_sync` **after**
the tracked `with` block — read `capture.log` back out to emit the per-call
`info`/`warning` logs.

That shape put three separate touch points on `BaseAgent` for one concern
(open the tracked block, log completion afterward, and reason about the DTO/
mapper indirection through `_tracked`), and it had a real correctness gap: because
`_log_call_completed` ran *after* the `with` block, a call that raised inside it
never reached the completion log at all — a failed call's latency and status were
silently unobservable.

Splitting the module further, `commons/ai/observability/services/protocols/` held
a private, unexported `_LlmCallLogRepository` `Protocol` typing
`QueuedLlmCallTracker`'s constructor dependency — a duplicate of the sink contract,
kept private specifically because there was no public one to depend on instead.

## Decision

Change the port's method signature to:

```python
def track(
    self, tracked_caller: TrackedCaller, prompt: str
) -> AbstractContextManager[PydanticAILlmCallRecorder]: ...
```

`track` now *is* the context manager `BaseAgent` enters directly, yielding a
`PydanticAILlmCallRecorder` (new `adapters/` package — see the package-naming
convention this ADR also motivates, `.claude/rules/code-conventions.md`) rather
than requiring a separately-composed capture object built by a factory method
living outside the port. `TrackedCaller` (new `models/tracked_caller.py`, frozen)
carries the per-agent-lifetime identity — `caller`/`model`/`system_prompt`/
`expects_cost` — built once in `BaseAgent.__init__` instead of rebuilt (or bound
via a private `_tracked` closure) on every call.

`BaseAgent.run`/`run_sync` collapse to two touch points:

```python
with self._tracker.track(self._tracked_caller, prompt_text) as recorder:
    result = await self._agent.run(prompt_content)
    recorder.record(result)
```

`PydanticAILlmCallRecorder` owns the full lifecycle that used to be split across
`PydanticAILlmCallCapture`, `LlmCallCaptureModel`, `LlmCallLogMapper`, and
`BaseAgent._log_call_completed`:

- `__enter__` starts the stopwatch.
- `record(result: AgentRunResult[Any])` captures response/tokens/cost on success.
- `__exit__` **always** runs (success or failure): stamps latency/`end_time`,
  marks `status="error"` + `error_message` on an exception, emits the per-call
  `info` log unconditionally, emits the "no cost reported" `warning` only when
  `status == "success"` and `TrackedCaller.expects_cost`, and returns `False`
  (never swallows the exception).
- The `log` property builds `LlmCallLogEntity` directly from the recorder's own
  fields — no DTO, no mapper.

This closes the failure-path logging gap as a direct consequence of the shape
(`__exit__` runs on every exit), not as a special case that had to be remembered.

`LlmCallLogRepository` (the sink port) moves from the private
`services/protocols/` duplicate to the package's top-level `protocols/`, public
and re-exported — `QueuedLlmCallTracker` now depends on the real cross-package
port instead of a structurally-identical private stand-in. The `mappers/`
package, `models/llm_call_capture_model.py`, and
`services/pydantic_ai_llm_call_capture.py` are deleted outright — zero remaining
callers once the recorder replaces them.

## Alternatives considered

- **Keep `track(log) -> None`, fix only the failure-path logging gap** (e.g. move
  `_log_call_completed` into a `finally` around the `with` block in `BaseAgent`):
  rejected — it patches the symptom without touching the actual problem, which is
  that `BaseAgent` was doing three unrelated jobs (open tracking, build the
  entity through a DTO/mapper indirection, log the outcome) that belong on one
  cohesive collaborator.
- **Keep the DTO + mapper (`LlmCallCaptureModel`/`LlmCallLogMapper`), just fix the
  port**: rejected — once the recorder holds every field `LlmCallLogEntity` needs
  as instance state, routing them through an intermediate model and a real
  mapper method for a straight 1:1 copy adds a layer with no transformation to
  justify it. A mapper taking a spread of loose primitives was never a genuine
  object-to-object mapping to begin with.
- **Publicize the private `_LlmCallLogRepository` in place, without a broader
  restructure**: considered but folded into this change instead — once
  `services/protocols/` no longer had a reason to be private (nothing else in
  the private-protocol pattern remained once the DTO/mapper trio was removed),
  moving it to the top-level `protocols/` was strictly simpler than keeping two
  `protocols/` locations for one package.

## Consequences

- `BaseAgent`'s tracker-related contact surface drops from three touch points
  (build capture via `_tracked`, call, log completion via
  `_log_call_completed`) to two (`with tracker.track(...) as recorder: ...;
  recorder.record(result)`), and it no longer imports or reasons about
  `LlmCallLogEntity`, `LlmCallCaptureModel`, or a mapper at all.
- **Deliberate behavior change**: the per-call `info` log now fires on a failed
  call too, since it lives in `__exit__` rather than after the `with` block.
  Previously a raising call left the operation invisible in the logs beyond
  whatever the caller logged separately.
- `NullLlmCallTracker` and `QueuedLlmCallTracker` both construct a
  `PydanticAILlmCallRecorder` directly inside their own `track()` — there is no
  longer a shared factory function outside the port for them to call, since the
  port itself carries the context-manager shape.
- Every implementer of `LlmCallTracker` (today: `NullLlmCallTracker`,
  `QueuedLlmCallTracker`) must itself be a `@contextmanager` (or equivalent)
  returning `PydanticAILlmCallRecorder` — a slightly larger implementation
  surface per implementer than a plain method, accepted because there are only
  two implementers and the alternative pushes the same complexity onto every
  caller instead.
- The sink port (`LlmCallLogRepository`) is now genuinely public and reusable —
  a second backend (a file sink, an OTLP exporter) can depend on it directly
  instead of duplicating a private structural protocol.
