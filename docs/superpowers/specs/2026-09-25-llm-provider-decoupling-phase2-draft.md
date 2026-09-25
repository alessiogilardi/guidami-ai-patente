# LLM provider decoupling — Phase 2 draft (Ollama + Gemini adapters)

Date: 2026-09-25
Status: **Tentative draft, not grilled** — builds on the grilled Phase 1 spec
(`2026-09-25-llm-provider-decoupling-design.md`), but this document itself has not
been through the same clarifying-questions/grilling pass. Treat every "Open question"
below as unresolved; do not hand this to `writing-plans` until they're answered.

## Preconditions

Phase 1 must be shipped first: `LlmModelProvider` port, `OpenRouterModelProvider`,
`model_provider_factory`, `BaseAgent` depending on the port, `model_provider`/
`judge_model_provider` DB columns already in place. Phase 2 is purely additive on top
of that seam — it touches no `BaseAgent` code and none of the nine agent classes.

## Goal

Make the second provider — Ollama, native Gemini, or both — a real, working
`LlmModelProvider` adapter, selectable by config instead of code.

## Open questions (unresolved — answer before implementing)

1. **Which provider first, Ollama or Gemini, or both in the same pass?** Doing both at
   once doubles the unverified surface (two sets of real credentials/endpoints to
   confirm) for a single Phase 2 pass.
2. **Ollama**: is a local Ollama instance actually running today, and at what
   `base_url`? Which models are pulled — do they cover what the 9 agents need
   (structured-output / tool-calling capable models), or would some agents need a
   different model entirely on Ollama than their current OpenRouter one?
3. **Gemini**: real Google AI Studio API key available? Google AI Studio (simple
   `api_key`) vs. Vertex AI (`credentials`/`project`/`location`, pydantic-ai's
   `GoogleCloudProvider`) — this design assumes AI Studio; Vertex is a different
   provider class entirely and changes `GeminiProviderSettings`'s shape.
4. **Per-agent model catalog**: whichever provider is chosen, every one of the 9
   YAML `model_name` values needs a real, working id in that provider's catalog
   (flagged as a caveat in Phase 1, Section 9) — this needs to be verified model by
   model, not assumed to "just work" by analogy to the OpenRouter names.
5. **Structured output / tool calling support**: several agents rely on pydantic-ai's
   structured output (`output_type=...`) and one (`CommaLabelerAgent`) on
   `ModelRetry`-driven `output_validator` retries — does the chosen Ollama model
   support this reliably? Not every locally-pulled model does.

## Tentative design (pending the above)

### 1. `LLMProvider` enum grows

`commons/ai/llm_providers/enums/llm_provider.py` gains the member(s) actually being
implemented this pass:

```python
class LLMProvider(StrEnum):
    OPENROUTER = auto()
    OLLAMA = auto()    # if in scope this pass
    GEMINI = auto()    # if in scope this pass
```

### 2. Discriminated-union provider settings

Replaces Phase 1's direct `OpenRouterConfig` usage with a small union, so the active
provider becomes one config value instead of a code choice:

```python
# commons/ai/llm_providers/configs/llm_provider_settings.py
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

# commons/ai/llm_providers/configs/llm_provider_config.py
class LlmProviderConfig(BaseConfig):
    """The active LLM provider and its credentials, discriminated by `provider`."""
    llm_config: LlmProviderSettings
```

Both files live under `commons/ai/llm_providers/configs/` — mirrors the existing
`commons/ai/observability/configs/observability_config.py` precedent (a `commons/ai/`
subsystem keeps its own config classes inside its own `configs/`, rather than in the
project-wide `commons/configs/`).

**Verified against the installed `pydantic`/`pydantic-settings` (2.13.4/2.14.1)** with
a throwaway script — three loading paths all work correctly against the discriminated
union, and an unknown `provider` value raises `ValidationError` (fail loud, no silent
fallback):

- **Nested env vars with `__`** (preferred — matches the existing `POSTGRES__USER`/
  `POSTGRES__PASSWORD` convention in `.env.example`, and `BaseConfig` already sets
  `env_nested_delimiter="__"`, so `LlmProviderConfig` gets this for free):
  ```
  LLM_CONFIG__PROVIDER=openrouter
  LLM_CONFIG__API_KEY=sk-or-...
  ```
- **A single JSON env var** also works (pydantic-settings JSON-decodes a complex/union
  field's raw string automatically): `LLM_CONFIG={"provider":"openrouter","api_key":"sk-..."}`.
  No reason to prefer this over the nested form in `.env` — it exists mainly as a
  fallback for a context where nested env vars aren't practical (e.g. a single
  CLI-injected override).
- **A nested YAML block**, via `BaseConfig.load(config_override=...)`, works
  natively (no JSON-encoding needed — YAML is already structured):
  ```yaml
  llm_config:
    provider: openrouter
    api_key: sk-...
  ```

One self-loading root (`LlmProviderConfig`) either way. Supersedes
`commons/configs/open_router_config.py::OpenRouterConfig` (Phase 1 left it untouched;
Phase 2 is what finally retires it) — every existing use of it is LLM-provider wiring.

### 3. New adapters

```
commons/ai/llm_providers/
├── configs/
│   ├── llm_provider_settings.py    # OpenRouter/Ollama/GeminiProviderSettings + union
│   └── llm_provider_config.py      # LlmProviderConfig(BaseConfig)
└── providers/
    ├── open_router_model_provider.py   # unchanged from Phase 1
    ├── ollama_model_provider.py        # new
    └── gemini_model_provider.py        # new
```

- `OllamaModelProvider.create_model` → `OpenAIChatModel(model_name, provider=OllamaProvider(base_url=self._settings.base_url))`. `expects_cost` → `False` (no cost reporting from a local model). `create_model_settings` → base settings, unmodified (no Ollama-specific settings needed today).
- `GeminiModelProvider.create_model` → `GoogleModel(model_name, provider=GoogleProvider(api_key=self._settings.api_key.get_secret_value()))`. `expects_cost` → `False` (OpenRouter is the only provider that reports per-call cost). `create_model_settings` → base settings, unmodified.

`model_provider_factory.py` grows a real `match`:

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

### 4. Wiring

Every Phase-1 call site's `create_llm_model_provider(OpenRouterConfig())` becomes
`create_llm_model_provider(LlmProviderConfig().llm_config)`. `guidami_ai_patente`'s
`LlmModelProviderComponent` switches its `Autowired` field from `OpenRouterConfig` to
`LlmProviderConfig`. No other call site changes — this is exactly the seam Phase 1
built for.

### 5. New dependency

`uv add "pydantic-ai-slim[google]"` (or whichever extra ships `google-genai`) — only
needed if Gemini is in this pass. Confirmed today: importing
`pydantic_ai.providers.google` without it raises `ModuleNotFoundError` immediately.

### 6. Database

**No migration needed** — `model_provider`/`judge_model_provider` (Phase 1) are
already plain `TEXT` columns; Phase 2 just writes a different value into them
(`'ollama'`/`'gemini'`) once that provider is actually selected.

### 7. Cutover — separate from "Phase 2 ships"

Building the adapter is not the same as switching to it. Actually flipping
`LLM_CONFIG`'s `provider` field, and rewriting every relevant YAML's `model_name` to
the new provider's own catalog naming (Phase 1 Section 9's caveat), is a deliberate,
separate operational step — done once the adapter is verified working, not bundled
into the same commit that adds it. Recommend a real smoke test (one live call through
the new adapter, end to end through `BaseAgent`) before flipping any agent's
`model_name`.

## Testing (tentative)

- Unit tests per new adapter, mirroring Phase 1's `OpenRouterModelProvider` test
  shape — but these can only assert *construction* (right `Model`/`Provider` type,
  right `expects_cost`), not real API behavior, without live credentials.
- `LlmProviderConfig`/`LlmProviderSettings` — discriminated union parses each shape
  from a JSON env value; rejects a payload whose `provider` doesn't match a known
  member.
- A live smoke test against whichever provider is actually configured — genuinely
  needs real credentials/endpoint, so it's a manual verification step (or a
  CI-skipped integration test gated on an env var being present), not something this
  plan can make automatic.
