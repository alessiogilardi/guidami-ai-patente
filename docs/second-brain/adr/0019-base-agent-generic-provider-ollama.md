# ADR 0019: `BaseAgent` Takes a Generic `Provider`, Dispatching Model/Settings/Warning by Provider Type

## Status

Proposed

## Context

`BaseAgent.__init__`/`from_yaml` required an `OpenRouterProvider` and
unconditionally built a `pydantic_ai.models.openrouter.OpenRouterModel`
with `openrouter_usage={"include": True}` (ADR 0004). That worked because
every agent in this codebase talked to OpenRouter, but it made it
impossible to point a `BaseAgent` at any other OpenAI-compatible backend
— in particular a local Ollama server, wanted for offline/low-cost agent
runs.

`pydantic_ai` already ships `pydantic_ai.providers.ollama.OllamaProvider`,
documented upstream as meant to pair with the generic
`pydantic_ai.models.openai.OpenAIChatModel` (not `OpenRouterModel`, which
carries OpenRouter-specific behavior: cache-control headers, the
`openrouter_usage` setting, and `provider_details["cost"]` in every
response). Both `OpenRouterProvider` and `OllamaProvider` are
`pydantic_ai.providers.Provider[AsyncOpenAI]` implementations, so a single
generic constructor parameter can accept either.

## Decision

Widen `BaseAgent.__init__`/`from_yaml`'s `provider` parameter from
`OpenRouterProvider` to `Provider[AsyncOpenAI]`. Three call sites inside
`BaseAgent` now dispatch on `isinstance(self._provider, OpenRouterProvider)`
(exposed as the `_is_openrouter` property):

- `_create_model`: `OpenRouterProvider` → `OpenRouterModel`; any other
  provider (e.g. `OllamaProvider`) → generic `OpenAIChatModel`.
- `_create_model_settings`: the `openrouter_usage={"include": True}` model
  setting is only attached for `OpenRouterProvider` — a non-OpenRouter
  backend would not understand it.
- `_log_call_completed`: the "OpenRouter reported no cost" `warning` only
  fires for `OpenRouterProvider` calls. Every Ollama call has
  `cost_usd is None` (a local model has no cost), so without this gate
  every single Ollama call would log a false warning — violating this
  project's logging convention that `warning` means a recoverable/
  degraded condition, not expected behavior (`.claude/rules/logging.md`).

`PydanticAILlmCallCapture._call_cost` (ADR 0004) is untouched: it already
just reads `ModelResponse.provider_details["cost"]` when present and
returns `None` otherwise, which is correct for both providers as-is.

Scope is deliberately limited to `BaseAgent` itself. No `OllamaConfig`
Pydantic settings class or `build_ollama_provider` wiring function was
added to `cli/wiring.py` / `retrieval_evaluation/wiring.py` — no agent in
this codebase is wired to Ollama yet, so that wiring would be speculative
until a concrete Ollama-backed agent is needed.

## Alternatives considered

- **A provider-specific `BaseAgent` subclass per backend** (e.g.
  `OllamaAgent(BaseAgent)`): rejected. Every existing subclass
  (`RoadSignDescriberAgent`, `RetrievalJudgeAgent`, ...) would need a
  second parallel hierarchy, and the only actual difference is which
  `Model`/settings/warning-gate to use — a `Provider` type check inside
  the existing class is far less code for the same result.
- **Keep `openrouter_usage` unconditional and let non-OpenRouter providers
  ignore the unknown setting key**: rejected without verifying it's
  actually harmless for every current and future OpenAI-compatible
  provider `pydantic_ai` might route through `OpenAIChatModel`; gating it
  explicitly is a one-line `isinstance` check and removes the risk
  entirely.
- **Keep the "no cost" warning unconditional**: rejected — it would fire
  on every successful Ollama call, training log-readers to ignore
  `warning`-level agent logs entirely (alert fatigue), which is exactly
  what `.claude/rules/logging.md` warns against.

## Consequences

- Any `BaseAgent` subclass can now be constructed with either
  `OpenRouterProvider` or `OllamaProvider` (or, in principle, any other
  `Provider[AsyncOpenAI]` `pydantic_ai` ships) with no subclass changes —
  model/settings/warning dispatch happens once, in the base class.
  `cost_usd` stays `NULL` for non-OpenRouter calls, same as ADR 0004's
  existing "no fallback estimate" stance, just now without a misleading
  warning attached.
- Wiring a concrete agent to Ollama end-to-end (config, `cli/wiring.py`
  builder) is left as a deliberate follow-up, not part of this change.
- If `pydantic_ai` later ships a provider that is neither
  `OpenRouterProvider` nor OpenAI-compatible-via-`OpenAIChatModel`, the
  `isinstance` dispatch in `_create_model` would need a third branch —
  not a risk today since `Provider[AsyncOpenAI]` is exactly the OpenAI-
  compatible family.
