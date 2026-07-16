# ADR 0004: LLM Call Cost From OpenRouter's Own Response, Not A litellm Pricing Table

## Status

Accepted

## Context

`LlmCallLog.cost_usd` was computed via `litellm.cost_per_token`, a static
pricing table bundled with (and periodically re-fetched by) `litellm`.
That table had no entry for the models this project actually routes
through OpenRouter — confirmed missing for both `openrouter/google/gemini-2.5-flash-lite`
(the model behind every agent: `ArticleContextualizerAgent`,
`RoadSignDescriberAgent`, `NormReferenceDescriberAgent`) and
`openrouter/openai/text-embedding-3-small`, checked against both the
locally bundled map and the live-fetched upstream JSON. `cost_usd` was
silently `NULL` for every agent call in practice.

Separately, agent calls never went through `litellm` at all: `BaseAgent`
talks to OpenRouter directly via `pydantic_ai`'s `OpenAIChatModel`.
`litellm` was only invoked standalone, after the fact, purely to estimate
a cost from token counts — an estimate that was unreliable for exactly
the models in use.

`pydantic_ai` ships a purpose-built `OpenRouterModel`
(`pydantic_ai.models.openrouter`) that, combined with the model setting
`openrouter_usage={"include": True}`, surfaces OpenRouter's own
authoritative per-call cost in `ModelResponse.provider_details["cost"]` —
the real amount OpenRouter billed for that request, not a table lookup.

## Decision

Switch `BaseAgent` from `OpenAIChatModel` to `pydantic_ai.models.openrouter.OpenRouterModel`,
with `openrouter_usage={"include": True}` set unconditionally in
`_create_model_settings` (every `BaseAgent` already requires an
`OpenRouterProvider`, so there's no path where this would be
inapplicable).

`PydanticAILlmCallCapture.record()` computes `cost_usd` synchronously,
summing `provider_details["cost"]` across every `ModelResponse` in
`result.new_messages()` — not just the last one, so a call retried by
`config.num_retries` (pydantic_ai validation retries, each a real billed
OpenRouter request) is logged with its true total cost, mirroring how
`result.usage` already aggregates `input_tokens`/`output_tokens` across
the same retries.

`LlmCostCalculator` (the litellm-pricing-table estimator) and its
`_CostCalculator` protocol are deleted outright. `QueuedLlmCallTracker`
no longer takes a cost-calculator dependency — it persists whatever
`cost_usd` the capture already computed. There is no fallback estimate:
if OpenRouter's response doesn't carry a cost for a given call (its own
mapping in `pydantic_ai` drops falsy/missing `usage.cost` via
`if cost := usage.cost`), `cost_usd` stays `NULL` for that row.

Computing cost synchronously, inside `record()`, is a deliberate reversal
of the earlier approach, which deferred cost computation to
`QueuedLlmCallTracker`'s background worker. That
earlier deferral existed specifically because `litellm.cost_per_token`
was a *fallible external lookup* (wrapped in `except Exception`). Reading
`provider_details["cost"]` is a pure dict read on data already fetched
over the network as part of the agent call itself — no I/O, no new
exception risk — so the original rationale for staying off the hot path
doesn't apply here.

## Alternatives considered

- **Keep `LlmCostCalculator` as a fallback** for calls where OpenRouter
  omits cost: rejected. It would keep a rarely-exercised code path alive
  indefinitely and mix an exact figure with an occasional litellm-table
  guess in the same column — a NULL is a more honest signal than a
  silently-approximate one.
- **Defer the cost summation to the async worker** (store raw
  `provider_details` fragments on the capture, sum them in
  `QueuedLlmCallTracker._persist`): rejected. There's no expensive or
  fallible work being deferred — just added indirection, and it would
  leak `pydantic_ai`'s response shape into a layer that today only deals
  with `LlmCallLog`/`Decimal`.
- **Rely on `pydantic_ai`'s own `Usage` aggregation** instead of manually
  summing `provider_details["cost"]`: not viable — `RunUsage.details` is
  typed `dict[str, int]` and `cost` is a `float`; `pydantic_ai` doesn't
  expose an aggregated cost anywhere else today.

## Consequences

- `cost_usd` on agent calls is now the real dollar amount OpenRouter
  billed, not an estimate — and it's populated for every model in
  production use, including ones litellm's pricing table never had.
- `commons/ai/observability/` drops its `litellm` dependency entirely
  (embedding still uses `litellm` independently via
  `LiteLLMEmbeddingClient`, which is unrelated and untouched — embeddings
  were never wired into `llm_call_logs`/cost tracking in the first
  place).
- If a future `pydantic_ai` upgrade or OpenRouter API change alters how
  `provider_details["cost"]` is populated, `cost_usd` silently reverts to
  `NULL` for affected calls with no fallback and no alert — an accepted
  trade-off (see "Alternatives considered"), not a new risk, but there is
  no monitoring today on "`cost_usd` NULL rate" that would catch it in
  practice.
- Streaming (`Agent.run_stream`) is untouched by this decision:
  `BaseAgent` never calls it, so `OpenRouterStreamedResponse`'s separate
  cost-mapping path is never exercised by this codebase.
