# LLM provider decoupling — design spec (Phase 1: seam + OpenRouter only)

Date: 2026-09-25
Status: Draft, pending user review

## Context

Today the identity of the LLM provider is smuggled inside the model name: every
agent YAML (`configs/agents/*.yaml`) sets `model_name: openrouter/google/gemini-2.5-flash-lite`,
and `BaseAgent._parse_model_name` strips the `"openrouter/"` prefix before handing the
bare name to `OpenRouterModel`/`OpenAIChatModel`. The raw, prefixed string is also what
gets persisted verbatim in `llm_call_logs.model` and `labeling_runs.judge_model`
(the latter is part of the judge's "configuration epoch" unique index). Which
`Provider` object gets constructed is hardcoded as `OpenRouterProvider(api_key=...)`
in five separate wiring call sites (`glossary/wiring.py`, `labeling/wiring.py`,
`guidami_ai_patente_ingestor/cli/wiring.py`, `guidami_ai_patente/main.py` +
`open_router_provider_component.py`, `glossary/translate_main.py`), and `BaseAgent`
dispatches model-class selection via `isinstance(self._provider, OpenRouterProvider)`.

That single construction point is not the whole blast radius: **nine** agent classes
actually pass `provider=` into `BaseAgent`/its own builders — `ExplanationWriterAgent`,
`QuestionExplainerAgent`, `ExplanationTranslatorAgent`, `GlossaryExtractorAgent`,
`GlossaryTermTranslatorAgent`, `CommaLabelerAgent`, `RetrievalJudgeAgent`,
`RoadSignDescriberAgent`, `NormReferenceDescriberAgent`. Most of the pywire-registered
ones (`guidami_ai_patente`, `glossary`) do it via a zero-argument `__init__` that reads
`Autowired[OpenRouterProviderComponent].provider` and forwards it to
`super().__init__(provider=...)` (ADR 0017/0023's pywire-agent pattern);
`CommaLabelerAgent` goes through a dedicated `labeling/wiring.py::build_comma_labeler_agent`
helper that also types its parameter concretely as `OpenRouterProvider`. Every one of
these needs updating.

The user's underlying goal is being able to move at least some agents off OpenRouter
later (confirmed during brainstorming: real native Google Gemini API access, and
Ollama). That surfaced a structural limit worth fixing now: pydantic-ai's
`GoogleProvider`/`GoogleModel` do not implement `Provider[AsyncOpenAI]` — they wrap a
`google-genai` client, a fundamentally different interface from `OpenRouterProvider`/
`OllamaProvider`. A third `isinstance` branch bolted onto `BaseAgent` would not be
enough; the provider needs a real seam.

## Scope of this document — Phase 1 only

Grilling this design surfaced that the full scope (three real provider adapters, a
discriminated-union config, a new `google-genai` dependency) is speculative today:
**OpenRouter is the only provider actually in use**, and Ollama/Gemini's real
constraints (credentials, exact model catalog, whether Ollama runs locally at all)
aren't known yet. Building against guessed constraints risks a second rewrite once
they're known for real.

This document therefore scopes **Phase 1 only**: build the seam (an
`LlmModelProvider` port `BaseAgent` depends on instead of a concrete pydantic-ai
`Provider` type) and move every current consumer onto it, with **one adapter,
`OpenRouterModelProvider`, wrapping exactly today's behavior** — no config-driven
provider switching yet, no new dependency, no discriminated union. Phase 1 is a
behavior-preserving refactor: after it ships, every agent still talks to OpenRouter,
identically, just through the new seam. **Phase 2** (a second real adapter — Ollama,
Gemini, or whatever is actually chosen) is explicitly deferred to a future
brainstorming session, once its real constraints are known; this document does not
plan it.

## Goals (Phase 1)

- `BaseAgent` stops knowing anything about concrete provider types (`OpenRouterProvider`,
  `isinstance` dispatch, the `"openrouter/"` prefix parsing) — it depends on the
  `LlmModelProvider` port only.
- Provider becomes an explicit, typed concept (`LLMProvider` enum) wherever it's
  recorded, decoupled from the model name string (YAML, DB columns).
- `llm_call_logs`/`labeling_runs` gain an explicit `provider`/`judge_provider` column;
  `judge_provider` joins the judge's configuration-epoch key alongside `judge_model`.
- Adding a second provider later (Phase 2) touches only `commons/ai/providers/` (one
  new adapter file + one new `match` arm in the factory) — zero changes to `BaseAgent`
  or to any of the nine agent classes.

## Non-goals (Phase 1)

- Implementing Ollama or Gemini support — deferred to Phase 2, planned separately when
  actually needed.
- Config-driven provider switching — with one real provider there is nothing to switch
  between yet; the factory exists as the extension seam, not as a dispatcher.
- Per-agent provider selection (confirmed out of scope regardless of phase: provider is
  one global choice per deployment, shared by every agent).
- Any change to which agents exist or what they do.

## Design

### 1. `LLMProvider` enum

`src/domain/enums/llm_provider.py`:

```python
class LLMProvider(StrEnum):
    OPENROUTER = auto()
```

Re-exported from `domain/enums/__init__.py`, per the project's enum conventions (one
file per enum, `StrEnum` + `auto()`). A single member today; Phase 2 adds to this file
when a second provider is actually implemented — it is not pre-populated with
placeholder members that have no adapter behind them.

### 2. Provider credentials — unchanged

`commons/configs/open_router_config.py`'s `OpenRouterConfig` (`BaseSettings`,
`env_prefix="OPENROUTER_"`, `api_key: SecretStr`) is **not touched** in Phase 1: it
already does exactly what's needed (self-loads OpenRouter's one credential from env).
No discriminated union, no new config class — that machinery is only justified once a
second provider variant actually exists to discriminate against, which is Phase 2's
job.

### 3. `LlmModelProvider` port + `OpenRouterModelProvider` adapter

Mirrors the existing `commons/ai/observability/` shape (`protocols/` + `services/` +
a package-root factory function, see `LlmCallTracker`/`build_llm_call_tracker`):

```
commons/ai/providers/
├── protocols/
│   └── llm_model_provider.py       # LlmModelProvider(Protocol)
├── services/
│   └── open_router_model_provider.py
└── model_provider_factory.py       # create_llm_model_provider(config) -> LlmModelProvider
```

```python
class LlmModelProvider(Protocol):
    """Port BaseAgent uses to build its pydantic-ai Model, provider-agnostically."""

    def create_model(self, model_name: str) -> Model: ...
    def create_model_settings(self, base: ModelSettings) -> ModelSettings: ...

    @property
    def expects_cost(self) -> bool: ...

    @property
    def provider(self) -> LLMProvider: ...
```

`OpenRouterModelProvider` is constructed with the existing `OpenRouterConfig`
(injected dependency) and owns exactly the logic `BaseAgent` currently inlines:

- `create_model` → `OpenRouterModel(model_name, provider=OpenRouterProvider(api_key=self._config.api_key.get_secret_value()))`.
- `create_model_settings` → attaches `openrouter_usage={"include": True}` (today's
  `OpenRouterModelSettings` branch) — unconditionally, since this adapter is only ever
  built for OpenRouter.
- `expects_cost` → `True`.
- `provider` → `LLMProvider.OPENROUTER` (a constant on this class).

`model_provider_factory.py`:

```python
def create_llm_model_provider(config: OpenRouterConfig) -> LlmModelProvider:
    return OpenRouterModelProvider(config)
```

A single-branch function today, deliberately — it is the one place Phase 2 extends
(`match` on a discriminated config once a second variant exists) without touching any
caller. Callers already depend on `LlmModelProvider`, not on `OpenRouterModelProvider`
directly, so that future extension is additive.

### 4. `BaseAgent` refactor

`BaseAgent.__init__`/`from_yaml` replace `provider: Provider[AsyncOpenAI]` with
`llm_model_provider: LlmModelProvider`. Removed entirely: `_is_openrouter`,
`_create_model`'s isinstance branch (delegates to `llm_model_provider.create_model`),
`_create_model_settings`'s isinstance branch (delegates to
`llm_model_provider.create_model_settings`), and `_parse_model_name` (dead: YAML no
longer carries a prefix to strip). `TrackedCaller.expects_cost` and the new
`TrackedCaller.provider` are read from `llm_model_provider.expects_cost`/`.provider`.

### 5. Call sites

The five hardcoded `OpenRouterProvider(api_key=...)` construction sites become:

```python
llm_model_provider = create_llm_model_provider(OpenRouterConfig())  # pyright: ignore[reportCallIssue]
```

`guidami_ai_patente`'s pywire `OpenRouterProviderComponent` is renamed/replaced by
`LlmModelProviderComponent` (`@provider`), `Autowired[OpenRouterConfig]`, calling the
factory in its `__init__` and exposing `.model_provider: LlmModelProvider` instead of
`.provider: OpenRouterProvider`. Every one of the nine agent classes updates its
`Autowired[OpenRouterProviderComponent]` field to
`Autowired[LlmModelProviderComponent]` and its `super().__init__(provider=...)` call
to `super().__init__(llm_model_provider=self.<field>.model_provider)`.
`labeling/wiring.py::build_comma_labeler_agent`'s `provider: OpenRouterProvider`
parameter becomes `llm_model_provider: LlmModelProvider`.

### 6. Observability

- `TrackedCaller` and `LlmCallLogEntity` gain `provider: LLMProvider`.
- `PydanticAILlmCallRecorder` copies `provider` from `TrackedCaller` into the entity,
  the same way it already copies `model`.
- `BaseAgent` populates `TrackedCaller.provider` from `llm_model_provider.provider`.

### 7. `LabelingEpoch` / judge configuration epoch

`LabelingEpoch` gains a 7th field, `judge_provider: LLMProvider`, next to
`judge_model`. `LabelingEpochMapper.from_config_to_epoch` gains a `provider:
LLMProvider` parameter (no longer derivable from `agent_config`, since YAML no longer
carries it) — both call sites (`retrieval_evaluation/label_main.py`,
`guidami_ai_patente/providers/labeling_stack_provider.py`) already have access to the
`LlmModelProvider`/`LLMProvider` value at that point.

### 8. Database

```sql
ALTER TABLE llm_call_logs ADD COLUMN IF NOT EXISTS provider TEXT;
UPDATE llm_call_logs
SET provider = 'openrouter', model = regexp_replace(model, '^openrouter/', '')
WHERE model LIKE 'openrouter/%';
ALTER TABLE llm_call_logs ALTER COLUMN provider SET NOT NULL;

ALTER TABLE labeling_runs ADD COLUMN IF NOT EXISTS judge_provider TEXT;
UPDATE labeling_runs
SET judge_provider = 'openrouter', judge_model = regexp_replace(judge_model, '^openrouter/', '')
WHERE judge_model LIKE 'openrouter/%';
ALTER TABLE labeling_runs ALTER COLUMN judge_provider SET NOT NULL;

DROP INDEX IF EXISTS uq_labeling_runs_live_config;
CREATE UNIQUE INDEX IF NOT EXISTS uq_labeling_runs_live_config
    ON labeling_runs (judge_model, judge_provider, prompt_version, candidate_variant,
                      dense_k, text_k, lexeme_fields)
    WHERE origin = 'live';
```

Written as a new idempotent file under `db/migrations/`, applied directly to the dev
stack (path 2 per `CLAUDE.md`), with the matching shape mirrored into `db/init.sql`
for future fresh environments. Every existing row is provably `openrouter` (the only
provider ever used), so the backfill is a safe, full rewrite — no ambiguous rows. No
explicit `BEGIN`/`COMMIT` wrapping: existing migrations (`0011`, `0012`) don't use one
either, so this follows the established convention.

### 9. YAML

All 9 files under `configs/agents/` lose the `"openrouter/"` prefix from
`model_name` (e.g. `openrouter/google/gemini-2.5-flash-lite` →
`google/gemini-2.5-flash-lite`). Mechanical, no field added — `AgentConfig` itself is
unchanged; the provider concept never lived on `AgentConfig` and still doesn't.

**Important caveat**: the string that remains after stripping the prefix is still in
*OpenRouter's own* catalog syntax (`vendor/model`) — it is not a provider-neutral
identifier, and this design does not attempt to make it one. Native Gemini's id for
that same model is `gemini-2.5-flash-lite` (no `google/`), and Ollama has an entirely
different tag catalog with no Gemini models at all. Whichever Phase 2 provider gets
chosen, `model_name` in each YAML will need updating to that provider's own naming at
that time — this design only removes the *code* duplication (five hardcoded wiring
call sites, nine agent classes' constructor calls) and the DB/log ambiguity between
"provider" and "model name" baked into one string.

## Testing

- `OpenRouterModelProvider` — unit test asserting `create_model`/`create_model_settings`/
  `expects_cost`/`provider` match today's `BaseAgent._create_model`/
  `_create_model_settings`/`_is_openrouter` behavior exactly (this is a
  behavior-preserving refactor; the test is the proof).
- `model_provider_factory` — asserts `create_llm_model_provider` returns an
  `OpenRouterModelProvider`.
- `BaseAgent` — existing tests swap their `Provider[AsyncOpenAI]` double for an
  `LlmModelProvider` double; behavior (model/settings built, `expects_cost`/`provider`
  wired into `TrackedCaller`) re-verified against the new seam.
- `LabelingEpochMapper` — existing epoch tests gain `judge_provider` as an input/output
  assertion.
- Migration — integration test (or manual verification per `CLAUDE.md`'s migration
  section) confirming row counts unchanged and every backfilled row satisfies
  `provider = 'openrouter' AND model NOT LIKE 'openrouter/%'`.
- End-to-end: run the existing quiz/labeling flows against the real dev stack after
  the refactor and confirm `llm_call_logs`/`labeling_runs` rows look identical to
  pre-refactor ones except for the new `provider`/`judge_provider` columns and the
  stripped `model`/`judge_model` prefix.

## Risks / edge cases

- **Nine call sites, not five**: the actual diff touches every agent class, not just
  the five provider-construction points — sized accordingly in the implementation
  plan (Section "Call sites" above enumerates all nine).
- **Epoch invalidation timing**: adding `judge_provider` to the unique index does
  **not** invalidate anything at migration time — the backfill sets every historical
  row's `judge_provider` to `'openrouter'`, matching the still-active provider right
  after this ships. It only invalidates cached `live` labelings the first time the
  provider is genuinely switched later (Phase 2) — the same mechanism as any other
  epoch-field change, and the correct, intended behavior at that point.
