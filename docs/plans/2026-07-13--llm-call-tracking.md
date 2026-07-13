---
status: Implemented
effort: L
---
# Llm Call Tracking

References:
- `docs/plans/2026-07-11--llm-call-log-schema.md` (Implemented — table + entity this plan populates)
- `src/domain/entities/observability/llm_call_log.py` (`LlmCallLog` entity, already implemented)
- `src/commons/agents/base_agent.py` (interception point)
- `src/commons/clients/postgres_client.py` (sync psycopg wrapper, eager connect)
- `src/guidami_ai_patente_ingestor/repositories/db/_bulk_insert_store_repository.py` (repository style to mirror: `_to_db_row`, module-level columns)
- `.claude/rules/code-conventions.md` (entities as insertable projection; English-only)
- `.claude/rules/dependency-injection.md` (plain args first, dependencies last)
- `src/commons/clients/embeddings/litellm_embedding_client.py` (deferred `import litellm` pattern)

## Context and motivation

LLM calls made through `BaseAgent` leave no persistent trace. The `llm_call_logs` table and
`LlmCallLog` entity exist (schema plan `2026-07-11--llm-call-log-schema.md`, Implemented) but
nothing populates them. Build the tracking system that captures every agent call (prompt,
system prompt, response, token counts, computed `cost_usd`, status, latency) and persists it,
kept as decoupled as possible from call sites, respecting SOLID, DRY, KISS, Clean
Architecture, PEP 8. Persistence must be asynchronous/non-blocking: writing the log row must
not sit on the critical path of the LLM call or degrade main-flow performance.

Approach (agreed in design review): a `LlmCallTracker` **port** (Protocol) injected into
`BaseAgent` as an optional dependency; a per-call `LlmCallCapture` context manager measures
the call inside `run`/`run_sync` (the only scope where `result.usage()` is visible, since
`BaseAgent` strips the pydantic_ai result to `output` before returning); a
`QueuedLlmCallTracker` implementation persists logs from a background worker thread
(`queue.SimpleQueue` + daemon thread), computing `cost_usd` off the hot path via litellm's
bundled pricing map. Wiring happens only at the composition root (`cli.py`). Verified against
installed versions: pydantic_ai 1.107.0 (`RunUsage.input_tokens`/`output_tokens`,
`total_tokens` property) and litellm ≥ 1.80.15 (`litellm.cost_per_token` supports
`openrouter/...` model ids and raises on unknown models).

### Affected areas

- `src/commons/observability/` — new package: port, capture, queued tracker, cost calculator
- `src/commons/repositories/llm_call_log_repository.py` — new repository (+ `__init__` re-export)
- `src/commons/agents/base_agent.py` — interception (~15 lines) + explicit-attributes refactor
- `src/guidami_ai_patente_ingestor/orchestrators/{quiz_flows,knowledge_flows}.py` — `tracker` pass-through
- `src/guidami_ai_patente_ingestor/cli.py` — tracker lifecycle at the composition root
- `tests/commons/observability/`, `tests/commons/repositories/`, `tests/commons/agents/`, `tests/guidami_ai_patente_ingestor/`

### Success criteria

Every `BaseAgent` call (`run`, `run_sync`, success and error) yields one `llm_call_logs` row
with caller, model, prompts, response, tokens, best-effort `cost_usd`, latency, status.
Persistence is non-blocking: the LLM call result is returned without waiting for the DB
write, on both the async `run` and sync `run_sync` paths. Cost is computed from token counts
via pricing lookup, `NULL` when the model is unknown. Persistence failure logs a warning and
the pipeline continues (documented exception to the fail-explicit rule). Pending log writes
are flushed before process exit (no silently lost rows on normal shutdown). Call sites stay
unaware of tracking beyond composition-root wiring. `pytest`, `ruff`, `pyright` clean.

## Non-goals

- No embedding-call tracking (`LiteLLMEmbeddingClient`) — chat-style agent calls only.
- No schema changes (`llm_call_logs` is final).
- No reporting/dashboard/query layer over the logs.
- No fail-loud mode: tracking persistence failure must never abort the pipeline.
- No changes to agent behavior or prompt rendering.
- No tracking for `index`/`reset` CLI paths (no agent calls there).
- No configurability of the flush timeout or queue bounds (constants; YAGNI).

## Decisions

1. **Port injected into `BaseAgent`, not an external wrapper** — token usage exists only
   inside `run`/`run_sync` (`result.usage()`); an external decorator would force
   `BaseAgent.run` to return a rich result object, a breaking change for every enricher.
   `LlmCallTracker` is a `Protocol` with a single method `track(log: LlmCallLog) -> None`
   (contractually non-blocking). ISP: call sites see only `track`; lifecycle (`close`) lives
   on the concrete class, owned by the composition root. pydantic_ai's OTel instrumentation
   was rejected as over-machinery for three agents.
2. **`LlmCallCapture` is a pure in-memory context manager** — per-call stopwatch
   (`time.perf_counter`), records response/usage on success; `__exit__` stamps latency and,
   on exception, `status="error"` + `error_message`, then returns `False` so the LLM failure
   always propagates unchanged. It produces the `LlmCallLog` via a `log` property; `cost_usd`
   stays `None` at this stage (computed by the worker, off the hot path).
3. **`QueuedLlmCallTracker`: `queue.SimpleQueue` + daemon worker thread** — `track()` is a
   `put()` (microseconds, thread-safe, no event-loop involvement), so one mechanism serves
   both `run` and `run_sync`. The worker drains: cost lookup → `repository.insert`. Lifecycle
   as context manager: `__enter__` starts the worker, `__exit__`/`close()` enqueues a
   sentinel and joins with a bounded timeout (module constant `_JOIN_TIMEOUT_S = 10.0`, not a
   ctor param — a configurable knob would force plain-data-with-default before required
   dependencies, and nobody asked for it). Queue is unbounded (ingestion volume is small).
4. **Worker catches `Exception` per item** — logs `logger.warning(..., exc_info=True)` and
   continues. This is a deliberate, documented exception to the "never swallow exceptions"
   rule, confirmed in brainstorm: observability must never break the main flow.
5. **Graceful degrade at the composition root** — `PostgresClient` connects eagerly and
   `prepare` does not otherwise need a DB, so `cli._run_prepare` wraps client construction in
   `try/except psycopg.OperationalError`: on failure it logs a warning and dispatches with
   `tracker=None`. The `with` statement at the root names the real types explicitly
   (`with postgres_client, QueuedLlmCallTracker(...) as tracker:`) — no factory that hides
   the try/except inside a constructor.
6. **`BaseAgent` stores explicit attributes, not the whole config** — replace
   `self.config = config` with `self._model_name = config.model_name` (original
   litellm-style id, needed by the pricing lookup — not the `:`-rewritten pydantic_ai
   variant) and `self._system_prompt = config.system`. Grep confirmed no external consumer of
   `agent.config`. Micro-refactor riding along with the feature (same lines, same file),
   flagged here for diff honesty.
7. **`caller` = `self._name`** — new ctor param `name: str | None = None` (plain data, before
   dependencies per the DI rule), fallback `type(self).__name__`; `from_yaml` passes its
   existing `name` argument through, so rows read `caller="road_sign_describer"`. New
   `__repr__` returns `f"{type(self).__name__}(name={self._name!r})"`.
8. **`tracker is None` short-circuits** — untracked agents run exactly today's code path,
   zero overhead, and existing tests keep passing unmodified. `run`/`run_sync` duplicate the
   ~8-line tracked skeleton; bridging sync/async with a shared helper costs more machinery
   than the duplication (KISS).
9. **Text-only persistence helpers in `base_agent.py`** — `_prompt_text` collapses the
   renderer's `str | list[str | BinaryContent]` union to its text part (images never
   persisted, schema Decision 8); `_response_text` serializes `BaseModel` outputs via
   `model_dump_json()`, else `str(output)`. `track()` is called in a `finally`, so error
   calls are logged too.
10. **`LlmCostCalculator` defers `import litellm` inside the method** — same pattern as
    `LiteLLMEmbeddingClient._embed`, keeping the heavy import off module import time.
    `litellm.cost_per_token` raises a bare `Exception` for unmapped models: caught, logged at
    INFO, returns `None`. Result quantized to `Decimal("0.000001")` (matches
    `NUMERIC(12,6)`).
11. **`LlmCallLogRepository` in `src/commons/repositories/`** — the future FastAPI app will
    track calls too, so the repository is commons-level (unlike the ingestor's store repos).
    It does not extend `BulkInsertStoreRepository` (truncate + bulk-reload contract does not
    fit an append-only log): plain `insert(log)` with module-level `_COLUMNS` tuple,
    `_INSERT_QUERY` built once with `sql.Identifier`/`sql.Placeholder`, and a static
    `_to_db_row`. `Decimal` adapts to `NUMERIC` natively (no cast; unlike pgvector).
12. **Flow builders take `tracker: LlmCallTracker | None = None`** — only the two enrichment
    flow builders (the ones constructing agents) gain the parameter and forward it to
    `from_yaml`. Cleaning/indexing builders are untouched.

## Open questions / Risks

- **Rows lost on hard kill** — a crashed/killed process loses queued rows (daemon thread).
  Accepted: observability data, bounded by queue drain speed; normal shutdown flushes.
- **`prepare` runs concurrently with tracking DB writes** — single connection used only by
  the worker thread (psycopg connections are not thread-safe, but only one thread touches
  it). The composition root must not share this `PostgresClient` with other consumers; the
  `prepare` path has none today.
- **litellm pricing map drift** — costs are best-effort snapshots of litellm's bundled map;
  historical rows are not recomputed when prices change. Accepted (schema Decision 2 already
  frames `cost_usd` as best-effort).
- **TDD divergence** — tests below are intent; if the red phase diverges, update this plan
  (write-plan "Note on tests").

**Note on tests (implementation-phase divergence):** Decision 5 / task 5 specify
`cli._run_prepare` catching `psycopg.OperationalError` around `PostgresClient(...)`
construction. Implemented as `except psycopg.Error` instead (the common base class of
`OperationalError`, `ProgrammingError`, etc.) because the six pre-existing `prepare`-path
tests in `tests/guidami_ai_patente_ingestor/test_cli.py` (not part of this plan's TDD
scope, not to be modified) construct `IngestorConfig` as a bare `MagicMock()` without
patching `PostgresClient`; a real `PostgresClient(config.postgres)` call against that mock
raises `psycopg.ProgrammingError` (bad `connect_timeout` value), not `OperationalError`,
client-side, before any network attempt. Catching the shared base class keeps those tests
green while preserving Decision 5's intent unchanged: any failure while establishing the
tracking connection degrades to `tracker=None` rather than aborting `prepare`, since
`prepare` has no other use for the connection. `test_prepare_degrades_without_postgres`
(which raises `psycopg.OperationalError` explicitly) still passes, as `OperationalError`
is a subclass of `psycopg.Error`.

## Implementation tasks

### 1. Port + capture — `src/commons/observability/`

Create the package: `llm_call_tracker.py` (`LlmCallTracker` `Protocol`, single method
`track(log: LlmCallLog) -> None`, docstring stating the non-blocking contract) and
`llm_call_capture.py` (`LlmCallCapture` per Decision 2: ctor
`(caller, model, prompt, system_prompt)`, `__enter__`/`__exit__` latency + error stamping,
`record(response: str, usage: RunUsage)`, `log` property building `LlmCallLog`).
`__init__.py` re-exports both with `__all__`.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- `tests/commons/observability/test_llm_call_capture.py::test_success_path` — enter, record,
  exit → `status="success"`, response/tokens set, `latency_ms >= 0`, `cost_usd is None`.
- `...::test_error_path_propagates_and_records` — exception inside the `with` propagates
  (`pytest.raises`) and `log` carries `status="error"`, `error_message`, `None` tokens.

### 2. Cost calculator — `llm_cost_calculator.py`

`LlmCostCalculator.cost_usd(model, input_tokens, output_tokens) -> Decimal | None` per
Decision 10: `None` tokens → `None`; deferred `import litellm`; `litellm.cost_per_token`
wrapped in `try/except Exception` → INFO log + `None`; result
`Decimal(str(prompt_cost + completion_cost)).quantize(Decimal("0.000001"))`. Re-export in the
package `__init__.py`.

**Tests** (intent, not contract):
- `...::test_known_model_returns_quantized_decimal` — a mapped openrouter model returns a
  positive `Decimal` with exponent ≥ -6.
- `...::test_unknown_model_returns_none` — unmapped model id → `None`, no raise.
- `...::test_missing_tokens_return_none` — `None` input or output tokens → `None`.

### 3. Repository — `src/commons/repositories/llm_call_log_repository.py`

`LlmCallLogRepository` per Decision 11: `__init__(client: PostgresClient)`,
`insert(log: LlmCallLog) -> None` executing the module-level `_INSERT_QUERY` with
`_to_db_row(log)` (static, `tuple(getattr(log, c) for c in _COLUMNS)`; `_COLUMNS` lists the
12 insertable columns in table order). Re-export via `src/commons/repositories/__init__.py`.

**Tests** (intent, not contract):
- `tests/commons/repositories/test_llm_call_log_repository_integration.py::test_insert_round_trip`
  (`@pytest.mark.integration`) — insert a full success log and a minimal error log; fetch
  back; `id`/`created_at` DB-populated, `cost_usd` round-trips as `Decimal`, `status` correct.

### 4. Queued tracker — `queued_llm_call_tracker.py`

`QueuedLlmCallTracker` per Decisions 3–4: ctor `(repository, cost_calculator)`;
`__enter__` starts the daemon worker; `track()` = `SimpleQueue.put`; `_drain` loops until the
module-level `_SHUTDOWN` sentinel; `_persist` computes cost, inserts
`log.model_copy(update={"cost_usd": cost})`, catches `Exception` → `logger.warning(...,
exc_info=True)`; `close()` puts the sentinel, joins with `_JOIN_TIMEOUT_S`, warns if the
worker is still alive. Re-export in the package `__init__.py`.

**Tests** (intent, not contract):
- `...test_queued_llm_call_tracker.py::test_track_persists_with_cost` — fake repository +
  stub calculator; `track` + `close` → exactly one insert, `cost_usd` attached.
- `...::test_repository_failure_degrades` — raising fake repository → warning in `caplog`,
  no exception escapes, a subsequent log is still persisted.
- `...::test_close_flushes_pending` — N tracked logs all inserted after `close()`.
- `...::test_track_does_not_block` — fake repository blocking on a `threading.Event`;
  `track()` returns while the insert is still pending.

### 5. `BaseAgent` interception + refactor

Per Decisions 6–9: ctor becomes `(config, name: str | None = None, file_reader=None,
tracker: LlmCallTracker | None = None)`; store `_name`, `_model_name`, `_system_prompt`,
`_tracker`; drop `self.config`. `from_yaml` gains `tracker` and passes `name` through. Add
`__repr__`. In `run`/`run_sync`: `tracker is None` → today's exact path; else build
`LlmCallCapture`, wrap the pydantic_ai call, `capture.record(_response_text(result.output),
result.usage())`, `finally: self._tracker.track(capture.log)`. Add module-private
`_prompt_text` and `_response_text`. Import the port from `..observability`.

**Tests** (intent, not contract — additions to `tests/commons/agents/test_base_agent.py`):
- `test_tracked_run_sync_records_success` — `FunctionModel` override + list-collecting fake
  tracker → one log with `caller`, original `model_name`, rendered prompt text, serialized
  response, `status="success"`.
- `test_tracked_run_records_success` — same via the async path.
- `test_tracked_error_propagates_and_logs` — failing model → exception reaches caller and
  fake tracker got a `status="error"` log.
- `test_untracked_agent_unchanged` — `tracker=None` → no capture involved (existing tests
  passing unmodified is the regression gate for the refactor).
- `test_repr` — `repr(agent)` is `ClassName(name='...')`.

### 6. Wiring — flow builders + CLI composition root

Per Decisions 5 and 12: `build_quiz_enrichment_flow` and `build_knowledge_enrichment_flow`
gain `tracker: LlmCallTracker | None = None`, forwarded to the `from_yaml` calls. In
`cli.py`, extract the current `_run_prepare` match body into `_dispatch_prepare(config,
layer_resolver, args, tracker)`; `_run_prepare` builds `PostgresClient(config.postgres)` in
`try/except psycopg.OperationalError` (warning + `tracker=None` dispatch on failure),
otherwise dispatches inside `with postgres_client, QueuedLlmCallTracker(
LlmCallLogRepository(postgres_client), LlmCostCalculator()) as tracker:`.

**Tests** (intent, not contract):
- `tests/guidami_ai_patente_ingestor/test_cli.py::test_prepare_degrades_without_postgres` —
  monkeypatched `PostgresClient` raising `OperationalError` → prepare dispatch still runs,
  warning logged, flows receive `tracker=None`.
- Builder pass-through covered indirectly by agent tests; no dedicated builder test.

### 7. Second-brain docs update

Run the `second-brain:update` skill: `docs/architecture.md` (observability flow: agent →
port → queued tracker → repository), `docs/patterns.md` (port-injected observability;
degrade-gracefully exception to fail-explicit), `docs/layout.md` (`commons/observability/`
package, commons-level repository).

**Tests** (intent, not contract): none — documentation only.

## Definition of Done

Variable block (plan-specific):

- [ ] `uv run python -c "from commons.observability import LlmCallTracker, LlmCallCapture, QueuedLlmCallTracker, LlmCostCalculator"` succeeds
- [ ] `uv run python -c "from commons.repositories import LlmCallLogRepository"` succeeds
- [ ] `uv run python -c "import inspect; from commons.agents import BaseAgent; p = inspect.signature(BaseAgent.__init__).parameters; assert list(p)[1:] == ['config', 'name', 'file_reader', 'tracker']"` succeeds
- [ ] `grep -n "self.config" src/commons/agents/base_agent.py` returns no matches (explicit-attributes refactor done)
- [ ] `grep -n "__repr__" src/commons/agents/base_agent.py` matches
- [ ] `grep -n "tracker" src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py src/guidami_ai_patente_ingestor/cli.py` matches in all three files
- [ ] `grep -n "except Exception" src/commons/observability/queued_llm_call_tracker.py` matches (documented degrade point)
- [ ] `grep -rn "integration" tests/commons/repositories/test_llm_call_log_repository_integration.py` matches (integration round-trip exists)
- [ ] `uv run pytest -m integration tests/commons/repositories/test_llm_call_log_repository_integration.py` green with Postgres up (manual, DB required)

Fixed block (same for every plan):

- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Plan updated to `status: Implemented`
