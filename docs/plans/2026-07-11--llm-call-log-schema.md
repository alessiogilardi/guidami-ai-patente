---
status: Implemented
effort: M
---
# Llm Call Log Schema

References:
- `docs/database.md` (existing `knowledge_chunks` / `quiz_questions` schema + migration policy)
- `src/domain/entities/knowledge/knowledge_chunk.py`, `src/domain/entities/quiz/quiz_question.py` (entity ↔ table 1:1 convention)
- `src/commons/agents/base_agent.py` (pydantic_ai call site — future instrumentation source, out of scope here)
- `.claude/rules/code-conventions.md` — "Entities — insertable projection of the table row" (DB-generated columns omitted from entities)

## Context and motivation

Add persistence for LLM call behavior: a new `llm_call_logs` table and a matching
`LlmCallLog` domain entity, to enable cost/token/quality observability of LLM calls. Design
scope only — the DDL and the entity (+ its package `__init__`). The tracking/instrumentation
mechanism (where to intercept `BaseAgent` calls, cost computation, repository, mapper, wiring)
is deliberately a separate, later discussion.

LLM calls in the ingestor currently go through `pydantic_ai.Agent` (wrapped by `BaseAgent`)
and leave no persistent trace: there is no way to attribute cost per pipeline stage, audit
token consumption over time, or inspect prompt/response pairs when RAG output quality
regresses. This plan lays the storage foundation for that observability without wiring any
capture logic yet.

### Affected areas

- `db/init.sql` — new `llm_call_logs` table + indexes on `created_at` and `caller`
- `src/domain/entities/observability/llm_call_log.py` — new `LlmCallLog` entity
- `src/domain/entities/observability/__init__.py` — new sub-package re-export
- `tests/domain/entities/observability/test_llm_call_log.py` — entity smoke test
- `docs/database.md` — schema doc update (third table)

### Success criteria

`llm_call_logs` table defined in `db/init.sql` with columns: `id`, `created_at`, `caller`,
`model`, `system_prompt`, `prompt`, `response`, `input_tokens`, `output_tokens`,
`total_tokens`, `cost_usd` (`NUMERIC`), `status`, `error_message`, `latency_ms`, plus indexes
on `created_at` and `caller`. `LlmCallLog` Pydantic entity models the insertable projection
of the table (per `.claude/rules/code-conventions.md`): it omits the DB-generated `id` and
`created_at`, and marks failure-nullable fields `Optional`.
`docs/database.md` documents the new table. `uv run pytest`, `ruff`, and `pyright` clean.

## Non-goals

- No tracking/instrumentation code: no interception in `BaseAgent`, no cost-computation
  logic, no repository, no mapper, no CLI wiring.
- No changes to how LLM calls are made.
- No migration tooling: `init.sql` remains the single schema source; applying the change
  requires a manual volume recreate (`docker compose down -v && up -d`), explicitly deferred
  and run consciously by the user, not by this plan.
- No index tuning beyond `created_at` and `caller`.
- Images / binary payloads are not stored (only the rendered text prompt).
- No `CHECK` constraint enforcing `total_tokens = input_tokens + output_tokens` (see Decision 5).
- No ADR: this is a routine additive log table, not an architectural trade-off — documented
  in `docs/database.md` only.

## Decisions

1. **Flat token columns, not a JSONB value object** — `input_tokens`, `output_tokens`,
   `total_tokens` are dedicated `INTEGER` columns (approach A), not a nested `TokenUsage`
   embedded as JSONB (approach B). Cost/token reporting is the reason the table exists, so
   the counters must stay aggregable with native SQL (`SUM`, `AVG` grouped by `caller`).
   JSONB is reserved for heterogeneous/nested data (as with `quiz_metadata`), not three
   homogeneous integers.
2. **`cost_usd` is `NUMERIC(12,6)`, nullable, best-effort** — money is never stored as
   float. It is nullable because `pydantic_ai`'s `result.usage()` returns token counts but
   **not** cost: cost must be computed later from a pricing lookup by the (out-of-scope)
   instrumentation. Until then the column stays `NULL`. `NUMERIC(12,6)` covers per-call cost
   with margin.
3. **Failures are first-class** — `status TEXT NOT NULL DEFAULT 'success'` (`'success'` |
   `'error'`) plus `error_message TEXT`. `response`, `input_tokens`, `output_tokens`,
   `total_tokens`, `cost_usd`, `latency_ms` are all nullable so a failed call is still
   loggable. A log that only records successes discards half the diagnostic value.
4. **`created_at` is DB-managed and omitted from the entity** — `TIMESTAMPTZ NOT NULL
   DEFAULT now()`, not in any future INSERT column list, and **no field** on `LlmCallLog`.
   Entities model the insertable projection of the row: DB-generated columns are omitted,
   never declared `Optional` "populated only on read" (see
   `.claude/rules/code-conventions.md`; same treatment as `QuizQuestion`, whose docstring
   states `created_at` "has no corresponding field here").
5. **`total_tokens` is stored as returned, no arithmetic constraint** — providers may count
   reasoning/cache tokens differently, so `total` is not guaranteed to equal
   `input + output`. Persist the provider value verbatim; no `CHECK` (see Non-goals).
6. **New `observability/` sub-package** — the entity lives in
   `src/domain/entities/observability/`, re-exported via its `__init__.py` (pattern of
   `entities/quiz/__init__.py`). `observability` (not `llm`) names the cross-cutting concern
   and leaves room for future observability entities. The entity goes in `domain/` because
   both the ingestor and the future FastAPI app make LLM calls (per `docs/layout.md`).
7. **`caller` is free `TEXT`, indexed** — identifies the agent/pipeline stage that issued the
   call (e.g. `"image_description"`, `"norm_reference"`). Kept as free text (not an enum/FK)
   for flexibility; new callers must not require a schema change. Indexed for per-stage
   aggregation.
8. **Prompt stored split and text-only** — `system_prompt TEXT` (nullable, not every call
   sets one) and `prompt TEXT NOT NULL` (rendered user prompt). Only text is captured;
   multimodal image inputs are not persisted.
9. **Two indexes only** — `created_at` (time-window queries) and `caller` (per-stage
   aggregation). No index on `model` (YAGNI; add later if a reporting need appears).
10. **Entity omits `id`** — the auto-generated `BIGSERIAL` PK is not a field on `LlmCallLog`,
    consistent with `KnowledgeChunk` and `QuizQuestion` (same insertable-projection rule as
    Decision 4).

## Open questions / Risks

- **DB recreate is destructive and manual.** `docker compose down -v` wipes the volume;
  `knowledge_chunks` and `quiz_questions` are lost and must be re-ingested. Deferred
  (non-goal), run consciously by the user — not by this plan.
- **`cost_usd` stays `NULL` until instrumentation exists.** The column and entity field are
  provisioned now, but no code populates them yet; cost computation (pricing lookup) is the
  next discussion. Accepted: the schema must be ready before the capture logic.
- **`Decimal` ↔ `NUMERIC` adaptation.** psycopg adapts Python `Decimal` to Postgres `NUMERIC`
  natively (no explicit cast, unlike the pgvector `%s::vector` case). This will be exercised
  by the future repository, not in this design-only plan.

## Implementation tasks

### 1. Schema — `db/init.sql`
Append a `CREATE TABLE IF NOT EXISTS llm_call_logs (...)` block after `quiz_questions` with
columns: `id BIGSERIAL PRIMARY KEY`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`,
`caller TEXT NOT NULL`, `model TEXT NOT NULL`, `system_prompt TEXT`, `prompt TEXT NOT NULL`,
`response TEXT`, `input_tokens INTEGER`, `output_tokens INTEGER`, `total_tokens INTEGER`,
`cost_usd NUMERIC(12,6)`, `status TEXT NOT NULL DEFAULT 'success'`, `error_message TEXT`,
`latency_ms INTEGER`. Add `CREATE INDEX IF NOT EXISTS idx_llm_call_logs_created_at ON
llm_call_logs (created_at)` and `idx_llm_call_logs_caller ON llm_call_logs (caller)`. Do not
touch the existing two tables.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- None here: the DDL will be validated by a future integration repository round-trip (out of
  scope). No SQL unit test.

### 2. Entity — `LlmCallLog` + sub-package
Create `src/domain/entities/observability/llm_call_log.py` with a Pydantic `BaseModel`
mirroring the table, omitting `id`: `caller: str`, `model: str`, `prompt: str`,
`system_prompt: str | None = None`, `response: str | None = None`,
`input_tokens: int | None = None`, `output_tokens: int | None = None`,
`total_tokens: int | None = None`, `cost_usd: Decimal | None = None`,
`status: Literal["success", "error"] = "success"`, `error_message: str | None = None`,
`latency_ms: int | None = None`. No `id` or `created_at` field (DB-generated, omitted —
Decisions 4 and 10). Docstring: `"""Row of the `llm_call_logs` table (see db/init.sql)."""`
plus a note that `id` and `created_at` are DB-managed and have no field here (pattern of
`QuizQuestion`'s docstring). Create
`src/domain/entities/observability/__init__.py` with a module docstring plus
`from .llm_call_log import LlmCallLog` and `__all__ = ["LlmCallLog"]` (pattern of
`entities/quiz/__init__.py`).

**Tests** (intent, not contract):
- Add `tests/domain/entities/observability/test_llm_call_log.py::test_llm_call_log_mirrors_table`
  — asserts `model_fields` is exactly the 12 insertable columns, with neither `id` nor
  `created_at`.
- Add `...::test_defaults` — a minimal instance (`caller`, `model`, `prompt` only) has
  `status == "success"` and all optional fields `None`.
- Add `...::test_cost_is_decimal` — `cost_usd` accepts a `Decimal` and rejects a non-numeric
  string (Pydantic validation).

### 3. Second-brain docs update — `docs/database.md`
Run the `second-brain:update` skill to add `llm_call_logs` as the third table under "Main
schema": its column list, the two indexes, and a note that `cost_usd` is `NUMERIC` populated
best-effort by future instrumentation (nullable). Update the section intro ("Two tables,
both defined in `db/init.sql`" → three). Keep the migration-policy section unchanged
(still applies).

**Tests** (intent, not contract): none — documentation only.

## Definition of Done

Variable block (plan-specific):

- [ ] `grep -n "CREATE TABLE IF NOT EXISTS llm_call_logs" db/init.sql` matches
- [ ] `grep "input_tokens INTEGER" db/init.sql && grep "output_tokens INTEGER" db/init.sql && grep "total_tokens INTEGER" db/init.sql && grep -E "cost_usd NUMERIC\(12, ?6\)" db/init.sql && grep "status TEXT NOT NULL DEFAULT 'success'" db/init.sql && grep -E "created_at TIMESTAMPTZ NOT NULL DEFAULT now\(\)" db/init.sql` exits 0 (all six columns present)
- [ ] `grep -E "idx_llm_call_logs_created_at|idx_llm_call_logs_caller" db/init.sql` matches both indexes
- [ ] `uv run python -c "from domain.entities.observability import LlmCallLog; f=set(LlmCallLog.model_fields); assert 'id' not in f and 'created_at' not in f and {'caller','model','prompt','system_prompt','response','input_tokens','output_tokens','total_tokens','cost_usd','status','error_message','latency_ms'} == f"` succeeds
- [ ] `uv run python -c "from decimal import Decimal; from domain.entities.observability import LlmCallLog; m=LlmCallLog(caller='a', model='b', prompt='c'); assert m.status=='success' and m.cost_usd is None and m.total_tokens is None"` succeeds
- [ ] `grep -n "llm_call_logs" docs/database.md` matches (schema docs updated)

Fixed block (same for every plan):

- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Plan updated to `status: Implemented`
