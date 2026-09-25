# LLM provider decoupling — design spec

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

The user wants to move off OpenRouter for at least some agents in the future
(confirmed during brainstorming: real native Google Gemini API access, not Gemini
served through OpenRouter as today). This surfaced a structural limit: pydantic-ai's
`GoogleProvider`/`GoogleModel` do not implement `Provider[AsyncOpenAI]` — they wrap a
`google-genai` client, a fundamentally different interface from `OpenRouterProvider`/
`OllamaProvider`. A third `isinstance` branch in `BaseAgent` is not enough; the
provider needs a real seam.

## Goals

- Provider becomes an explicit, typed concept (`LLMProvider` enum: `OPENROUTER`,
  `OLLAMA`, `GEMINI`), decoupled from the model name string everywhere it appears
  (YAML, DB columns, in-process types).
- Switching the active provider for the whole deployment is a **config change**, not a
  code change across five wiring files.
- `BaseAgent` stops knowing anything about concrete provider types.
- `llm_call_logs`/`labeling_runs` gain an explicit `provider`/`judge_provider` column;
  `judge_provider` joins the judge's configuration-epoch key alongside `judge_model`.

## Non-goals

- Per-agent provider selection (confirmed out of scope: provider is one global choice
  per deployment, shared by every agent).
- Gemini via OpenRouter is out of scope as a distinct concept — it already works today
  and is unaffected; "GEMINI" in this design means the native Google API.
- No change to which agents exist or what they do.

## Design

### 1. `LLMProvider` enum

`src/domain/enums/llm_provider.py`:

```python
class LLMProvider(StrEnum):
    OPENROUTER = auto()
    OLLAMA = auto()
    GEMINI = auto()
```

Re-exported from `domain/enums/__init__.py`, per the project's enum conventions
(one file per enum, `StrEnum` + `auto()`).

### 2. Provider credential settings — discriminated union

`src/commons/configs/llm_provider_settings.py`:

```python
class OpenRouterProviderSettings(BaseModel):
    provider: Literal[LLMProvider.OPENROUTER] = LLMProvider.OPENROUTER
    api_key: SecretStr

class OllamaProviderSettings(BaseModel):
    provider: Literal[LLMProvider.OLLAMA] = LLMProvider.OLLAMA
    base_url: str

class GeminiProviderSettings(BaseModel):
    provider: Literal[LLMProvider.GEMINI] = LLMProvider.GEMINI
    api_key: SecretStr

LlmProviderSettings = Annotated[
    OpenRouterProviderSettings | OllamaProviderSettings | GeminiProviderSettings,
    Field(discriminator="provider"),
]
```

Plain `BaseModel`s (not settings classes themselves) — they exist to be validated as
one discriminated union, not to self-load from the environment individually.

`src/commons/configs/llm_provider_config.py`:

```python
class LlmProviderConfig(BaseConfig):
    """The active LLM provider and its credentials, discriminated by `provider`."""

    llm_config: LlmProviderSettings
```

A single self-loading root: one env var carries the whole union as JSON
(`LLM_CONFIG={"provider":"openrouter","api_key":"sk-..."}`; pydantic-settings decodes
JSON automatically for a complex/union field), or the equivalent nested block via
`.load(config_override=...)`'s YAML path. The `provider` field both selects which
union member validates and supplies every field that member needs — no separate
selector class, no risk of reading the wrong provider's env-prefixed block.

**Removes `commons/configs/open_router_config.py` (`OpenRouterConfig`) entirely** —
every existing use of it is LLM-provider wiring, all superseded by `LlmProviderConfig`.

### 3. `LlmModelProvider` port + adapters

Mirrors the existing `commons/ai/observability/` shape (`protocols/` + `services/` +
a package-root factory function, see `LlmCallTracker`/`build_llm_call_tracker`):

```
commons/ai/providers/
├── protocols/
│   └── llm_model_provider.py       # LlmModelProvider(Protocol)
├── services/
│   ├── open_router_model_provider.py
│   ├── ollama_model_provider.py
│   └── gemini_model_provider.py
└── model_provider_factory.py       # create_llm_model_provider(settings) -> LlmModelProvider
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

Each adapter (`OpenRouterModelProvider`, `OllamaModelProvider`, `GeminiModelProvider`)
is constructed with its own `*ProviderSettings` (injected dependency) and owns exactly
the logic `BaseAgent` currently inlines:

- `OpenRouterModelProvider.create_model` → `OpenRouterModel(model_name, provider=OpenRouterProvider(api_key=...))`.
- `OllamaModelProvider.create_model` → `OpenAIChatModel(model_name, provider=OllamaProvider(base_url=...))`.
- `GeminiModelProvider.create_model` → `GoogleModel(model_name, provider=GoogleProvider(api_key=...))`.
- `create_model_settings` — only `OpenRouterModelProvider` overrides it, attaching
  `openrouter_usage={"include": True}` (today's `OpenRouterModelSettings` branch).
- `expects_cost` — `True` only for `OpenRouterModelProvider`.

`model_provider_factory.py`:

```python
def create_llm_model_provider(settings: LlmProviderSettings) -> LlmModelProvider:
    match settings:
        case OpenRouterProviderSettings():
            return OpenRouterModelProvider(settings)
        case OllamaProviderSettings():
            return OllamaModelProvider(settings)
        case GeminiProviderSettings():
            return GeminiModelProvider(settings)
```

### 4. `BaseAgent` refactor

`BaseAgent.__init__`/`from_yaml` replace `provider: Provider[AsyncOpenAI]` with
`llm_model_provider: LlmModelProvider`. Removed entirely: `_is_openrouter`,
`_create_model`'s isinstance branch (delegates to `llm_model_provider.create_model`),
`_create_model_settings`'s isinstance branch (delegates to
`llm_model_provider.create_model_settings`), and `_parse_model_name` (dead: YAML no
longer carries a prefix to strip). `TrackedCaller.expects_cost` is read from
`llm_model_provider.expects_cost`.

### 5. Wiring

The five hardcoded `OpenRouterProvider(api_key=...)` call sites collapse to:

```python
llm_provider_config = LlmProviderConfig()  # or .load(...) where a config file is used
llm_model_provider = create_llm_model_provider(llm_provider_config.llm_config)
```

`guidami_ai_patente`'s pywire `OpenRouterProviderComponent` is replaced by
`LlmModelProviderComponent` (`@provider`), `Autowired[LlmProviderConfig]`, calling the
same factory in its `__init__` and exposing `.model_provider: LlmModelProvider`.
`main.py` loads `LlmProviderConfig()` once and registers it exactly where
`OpenRouterConfig` is registered today.

### 6. Observability

- `TrackedCaller` and `LlmCallLogEntity` gain `provider: LLMProvider`.
- `PydanticAILlmCallRecorder` copies `provider` from `TrackedCaller` into the entity,
  the same way it already copies `model`.
- `BaseAgent` populates `TrackedCaller.provider` by reading `llm_model_provider.provider`
  (see the port's `provider` property, Section 3).

### 7. `LabelingEpoch` / judge configuration epoch

`LabelingEpoch` gains a 7th field, `judge_provider: LLMProvider`, next to
`judge_model`. `LabelingEpochMapper.from_config_to_epoch` gains a `provider:
LLMProvider` parameter (no longer derivable from `agent_config`, since YAML no longer
carries it) — both call sites (`retrieval_evaluation/label_main.py`,
`guidami_ai_patente/providers/labeling_stack_provider.py`) already have access to the
active `LlmProviderConfig`/`LLMProvider` at that point.

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
provider ever used), so the backfill is a safe, full rewrite — no ambiguous rows.

### 9. YAML

All 9 files under `configs/agents/` lose the `"openrouter/"` prefix from
`model_name` (e.g. `openrouter/google/gemini-2.5-flash-lite` →
`google/gemini-2.5-flash-lite`). Mechanical, no field added — `AgentConfig` itself is
unchanged; the provider concept never lived on `AgentConfig` and still doesn't.

**Important caveat, not eliminated by this design**: the string that remains after
stripping the prefix is still in *OpenRouter's own* catalog syntax
(`vendor/model`, e.g. `google/gemini-2.5-flash-lite`) — it is not a provider-neutral
identifier. Native Gemini's own id for that same model is `gemini-2.5-flash-lite` (no
`google/`), and Ollama has an entirely different tag catalog (`llama3.2`, `gemma2:9b`,
...) with no Gemini models at all. Switching the active provider (`LLM_CONFIG`) still
requires updating `model_name` in every YAML to that provider's own naming — this
design does not, and cannot, make one `model_name` value valid across providers. What
it removes is the *code* changes (five hardcoded wiring call sites) and the DB/log
ambiguity between "provider" and "model name" baked into one string — not the need to
re-point `model_name` when the provider actually changes.

### 10. New dependency

`uv add "pydantic-ai-slim[google]"` (or the extra that ships `google-genai`), required
for `GeminiModelProvider`/`GoogleModel`/`GoogleProvider` to import at all.

## Testing

- Unit tests per adapter (`OpenRouterModelProvider`, `OllamaModelProvider`,
  `GeminiModelProvider`): given settings, asserts the right `Model`/`Provider` type is
  constructed and `expects_cost` is correct.
- `model_provider_factory` — one test per union member asserting the right adapter
  type comes back.
- `LlmProviderConfig` — discriminated union parses each of the three shapes from a
  JSON env value; rejects a payload whose `provider` doesn't match a known member.
- `BaseAgent` — existing tests swap their `Provider[AsyncOpenAI]` double for an
  `LlmModelProvider` double; behavior (model/settings built, `expects_cost` wired into
  `TrackedCaller`) re-verified against the new seam.
- `LabelingEpochMapper` — existing epoch tests gain `judge_provider` as an input/output
  assertion.
- Migration — integration test (or manual verification per `CLAUDE.md`'s migration
  section) confirming row counts unchanged and every backfilled row satisfies
  `provider = 'openrouter' AND model NOT LIKE 'openrouter/%'`.

## Risks / edge cases

- **Silent epoch invalidation**: shipping `judge_provider` into the unique index
  invalidates every cached `live` labeling the moment the migration runs (same
  mechanism as any other epoch-field change) — expected, not a bug, but worth calling
  out explicitly since it is a side effect of a column addition, not of an intentional
  judge-config change.
- **`google-genai` at import time**: confirmed today that importing
  `pydantic_ai.providers.google` without the package installed raises
  `ModuleNotFoundError` immediately. Resolved by `uv add "pydantic-ai-slim[google]"`
  (Section 10) making `google-genai` an always-installed project dependency, same tier
  as `openai` (already required for `AsyncOpenAI`) — so `GeminiModelProvider`'s module
  can be imported eagerly from `commons/ai/providers/services/__init__.py` like its
  siblings, no lazy-import workaround needed.
- **`uq_labeling_runs_live_config` DROP+CREATE**: doing this on the live dev stack is
  transiently a window with no unique constraint; acceptable for a low-traffic
  personal dev DB but worth doing inside a transaction in the migration script.
