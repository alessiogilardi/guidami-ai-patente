# LLM provider decoupling — design spec (Spec 0025, Phase 1: seam + existing providers)

Date: 2026-09-25 (revised 2026-09-29 after grilling + clean-architecture review)
Status: Draft, grilled — pending user approval

## Context

Today the identity of the LLM provider is smuggled inside the model name: every
agent YAML (`configs/agents/*.yaml`, **11 files**) sets e.g.
`model_name: openrouter/google/gemini-2.5-flash-lite`, and `BaseAgent._parse_model_name`
strips the `"openrouter/"` prefix before handing the bare name to
`OpenRouterModel`/`OpenAIChatModel`. The raw, prefixed string is also what gets
persisted verbatim in `llm_call_logs.model` and `labeling_runs.judge_model` (the latter
is part of the judge's configuration epoch — spec 0012, AD-8), and what the API
returns as `provenance.judge_model` on `GET /quiz-questions/{number}/explanation`.

`BaseAgent` (`src/commons/ai/agents/base_agent.py`) takes a
`pydantic_ai.providers.Provider[AsyncOpenAI]` and dispatches on
`isinstance(self._provider, OpenRouterProvider)` (`_is_openrouter`) in three places:
model class (`OpenRouterModel` vs generic `OpenAIChatModel`), model settings
(`openrouter_usage={"include": True}`), and `TrackedCaller.expects_cost`. The
non-OpenRouter branch is not dead: **ADR 0019** introduced it deliberately so
`BaseAgent` can run against any OpenAI-compatible backend (e.g. `OllamaProvider`). It is
exercised by `tests/commons/ai/agents/test_base_agent.py` but not used by any `src/`
wiring today.

The concrete `OpenRouterProvider` reaches the 11 agents through three different
mechanisms:

| Mechanism | Agents | Where the provider comes from |
|---|---|---|
| pywire `Autowired[OpenRouterProviderComponent]` (ADR 0017/0023) | `ExplanationWriterAgent`, `QuestionExplainerAgent`, `ExplanationTranslatorAgent`, `GlossaryEnricherAgent` (`guidami_ai_patente/agents/`) | `guidami_ai_patente/providers/open_router_provider_component.py` |
| pywire `Autowired[Provider[AsyncOpenAI]]` + `register_instance` | `GlossaryExtractorAgent`, `GlossaryTermTranslatorAgent`, `GlossaryDefinitionSimplifierAgent` (`glossary/agents/`) | `glossary/main.py`, `translate_main.py`, `simplify_main.py` |
| plain constructor / `from_yaml` argument | `CommaLabelerAgent` (`labeling/wiring.py::build_comma_labeler_agent`, also via `guidami_ai_patente/providers/live_labeling_stack_provider.py`), `RetrievalJudgeAgent` (`retrieval_evaluation/wiring.py`), `RoadSignDescriberAgent` + `NormReferenceDescriberAgent` (`guidami_ai_patente_ingestor/orchestrators/quiz_flows.py`, threaded through `cli/commands/prepare.py`) | see below |

`OpenRouterProvider(api_key=...)` is built by **three duplicated helpers** named
`build_open_router_provider` (`labeling/wiring.py`, `glossary/wiring.py`,
`guidami_ai_patente_ingestor/cli/wiring.py`), called from **seven composition roots**:
`retrieval_evaluation/main.py`, `retrieval_evaluation/label_main.py`, `glossary/main.py`,
`glossary/translate_main.py`, `glossary/simplify_main.py`,
`guidami_ai_patente_ingestor/cli/main.py`, and (through pywire)
`OpenRouterProviderComponent`.

The user's underlying goal is being able to move agents off OpenRouter later (native
Google Gemini API, Ollama). pydantic-ai's `GoogleProvider`/`GoogleModel` do not
implement `Provider[AsyncOpenAI]` — they wrap a `google-genai` client — so a third
`isinstance` branch in `BaseAgent` cannot absorb them. The provider needs a real seam.

## Scope — Phase 1

Build the seam — an `LlmModelProvider` port that `BaseAgent` depends on instead of a
concrete pydantic-ai `Provider` type — and move every current consumer onto it, with
**two adapters wrapping exactly today's two behaviors**:

- `OpenRouterModelProvider` — today's `_is_openrouter` branch; the only one wired in
  production.
- `OllamaModelProvider` — today's generic `OpenAIChatModel` branch (ADR 0019),
  preserved as an adapter rather than dropped.

Phase 1 is a behavior-preserving refactor: after it ships, every agent still talks to
OpenRouter, identically, through the new seam. **Phase 2** (config-driven provider
selection, a Gemini adapter, a provider factory) is deferred to its own grilling pass —
see `2026-09-25-llm-provider-decoupling-phase2-draft.md`.

## Goals (Phase 1)

- `BaseAgent` stops knowing concrete provider types (`OpenRouterProvider`,
  `isinstance` dispatch, `"openrouter/"` prefix parsing) — it depends on the
  `LlmModelProvider` port only.
- Provider becomes an explicit, typed concept (`LlmProvider` enum) wherever it is
  recorded, decoupled from the model-name string (YAML, DB columns, API provenance).
- `llm_call_logs`/`labeling_runs` gain `model_provider`/`judge_model_provider`
  (mirroring `model`/`judge_model`); `judge_model_provider` becomes a full member of the
  judge's configuration epoch.
- Adding a provider later means one new adapter in `commons/ai/llm_providers/providers/`
  plus composition-root wiring — **zero** changes to `BaseAgent` or any agent class.
  (It does *not* mean zero call-site changes: Phase 2's config-driven selection changes
  what the composition roots construct. That is expected; the seam protects the agents,
  not the entry points.)

## Non-goals (Phase 1)

- A Gemini adapter, the `google-genai` dependency, config-driven provider switching,
  a provider factory/dispatcher (D1) — all Phase 2.
- Wiring `OllamaModelProvider` into any composition root — it exists as a preserved,
  tested capability, not an active deployment option.
- Per-agent provider selection (out of scope regardless of phase: provider is one
  global choice per deployment, shared by every agent).
- **Embeddings.** `EmbeddingClientConfig.model_name = "openrouter/openai/text-embedding-3-small"`
  (and `configs/ingestor_config.yaml`) goes through litellm, where the `openrouter/`
  prefix is litellm's own routing syntax and must stay. Untouched.
- A provider-neutral model identifier. `model_name` stays in the active provider's
  own catalog syntax (see §9).
- Any change to which agents exist or what they do.

## Decisions (from grilling, 2026-09-29)

- **D1 — No factory in Phase 1.** Each composition root constructs
  `OpenRouterModelProvider(OpenRouterConfig)` directly and hands it on as
  `LlmModelProvider`. A single-branch `create_llm_model_provider(config: OpenRouterConfig)`
  would shield nothing: Phase 2 changes its signature (`OpenRouterConfig` →
  `LlmProviderSettings`) and every call site anyway. The factory is born in Phase 2,
  when there is a real `match` to write. The three `build_open_router_provider`
  helpers are deleted.
- **D2 — Ollama kept as an adapter.** `OllamaModelProvider` preserves ADR 0019's
  capability through the new port. A new ADR records the port and marks ADR 0019
  superseded (its `isinstance` dispatch is gone; its capability lives on in the adapter).
- **D3 — API exposes the provider.** `provenance.judge_model_provider` is added next to
  `provenance.judge_model` on the explanation response (additive). Without it, the
  stripped `judge_model` would lose information today's string carries.
- **D4 — Migration rewrites history in both tables.** The `openrouter/` prefix is
  stripped from both `labeling_runs.judge_model` (mandatory: the epoch must match the
  stripped YAML) and `llm_call_logs.model` (one format per column; the information
  moves to `model_provider`).
- **D5 — The epoch reads the provider from the wired adapter.** The epoch's
  `judge_model_provider` is `llm_model_provider.provider` of the adapter actually in
  use — never a separately declared config value that could diverge from it.
- **D6 — `judge_model_provider` is fully part of the epoch.** In the unique index, in
  `LabelingEpoch`, and in both SQL epoch matches. Rationale: every real provider switch
  also changes `judge_model` (model ids are catalog-specific, §9), so excluding the
  provider would not avoid invalidation in practice — it would only make run-level
  provenance lie (new labelings attached to a run created under another provider) and
  leave the index and the lookup queries disagreeing.

## Design

### 1. `LlmProvider` enum

`src/commons/ai/llm_providers/enums/llm_provider.py`:

```python
class LlmProvider(StrEnum):
    """The backend an LLM call is routed through.

    Values are written explicitly, not via `auto()`: they are persisted in
    `llm_call_logs.model_provider` and `labeling_runs.judge_model_provider` and returned
    by the API, so they are an external contract that must survive a member rename.
    """

    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
```

Named `LlmProvider` (not `LLMProvider`) to match the project's `Llm*` casing
(`LlmCallTracker`, `LlmCallLogEntity`). Lives inside `commons/ai/llm_providers/`, not
`domain/enums/`, following the `commons/ai/observability/enums/tracker_backend.py`
precedent. One member per adapter that exists — no placeholder members.

### 2. Provider credentials — unchanged

`commons/configs/open_router_config.py::OpenRouterConfig` is not touched. It is still
loaded at each entry point and injected into `OpenRouterModelProvider`.
`OllamaModelProvider` takes a plain `base_url: str` (no config class: nothing loads it
from the environment in Phase 1).

### 3. `LlmModelProvider` port + adapters

```
commons/ai/llm_providers/
├── __init__.py                         # re-exports LlmProvider, LlmModelProvider, both adapters
├── enums/
│   ├── __init__.py
│   └── llm_provider.py                 # LlmProvider(StrEnum)
├── protocols/
│   ├── __init__.py
│   └── llm_model_provider.py           # LlmModelProvider(Protocol)
└── providers/
    ├── __init__.py
    ├── open_router_model_provider.py   # OpenRouterModelProvider
    └── ollama_model_provider.py        # OllamaModelProvider
```

Named `llm_providers/` to avoid colliding with `guidami_ai_patente/providers/` (pywire
`@provider` components). The implementation folder is `providers/` rather than
`services/`: every file in it is literally a `*ModelProvider` implementing the port.

```python
class LlmModelProvider(Protocol):
    """Port `BaseAgent` uses to build its pydantic-ai model, provider-agnostically."""

    @property
    def provider(self) -> LlmProvider: ...

    @property
    def expects_cost(self) -> bool: ...

    def create_model(self, model_name: str) -> Model: ...

    def create_model_settings(self, base: ModelSettings) -> ModelSettings: ...
```

**`OpenRouterModelProvider(config: OpenRouterConfig)`** — owns exactly the logic
`BaseAgent` inlines today:

- Builds **one** `pydantic_ai.providers.openrouter.OpenRouterProvider` in `__init__`
  and reuses it for every `create_model` call — preserving today's "one shared
  provider (one HTTP client) per process" property of `OpenRouterProviderComponent`.
- `create_model(model_name)` → `OpenRouterModel(model_name, provider=self._provider)`.
  Raises `ValueError` when `model_name` still starts with `openrouter/`: with
  `_parse_model_name` gone, a stale prefixed YAML would otherwise surface only as a
  model-not-found error on the first real call; this makes it a startup failure
  (`BaseAgent.__init__` builds the model).
- `create_model_settings(base)` → `OpenRouterModelSettings(**base, openrouter_usage={"include": True})`.
- `expects_cost` → `True`; `provider` → `LlmProvider.OPENROUTER`.

**`OllamaModelProvider(base_url: str)`** — today's generic branch:

- Builds one `pydantic_ai.providers.ollama.OllamaProvider(base_url=base_url)` in
  `__init__`.
- `create_model(model_name)` → `OpenAIChatModel(model_name, provider=self._provider)`.
- `create_model_settings(base)` → `base` unchanged.
- `expects_cost` → `False`; `provider` → `LlmProvider.OLLAMA`.

### 4. `BaseAgent` refactor

`BaseAgent.__init__`/`from_yaml` replace `provider: Provider[AsyncOpenAI]` with
`llm_model_provider: LlmModelProvider` (same position: an injected dependency, before
the optional `file_reader`/`tracker`). Removed: `_is_openrouter`, both `isinstance`
branches, `_parse_model_name`, and the `openai`/`OpenRouter*`/`OpenAIChatModel`/
`Provider` imports. `_create_model` delegates to `llm_model_provider.create_model`;
`_create_model_settings` builds the base settings (temperature, timeout, max_tokens) and
passes them through `llm_model_provider.create_model_settings`.
`TrackedCaller.expects_cost` and the new `TrackedCaller.model_provider` are read from
the port. `AgentConfig.model_name`'s `description` example drops the `openrouter/`
prefix.

### 5. Call sites

| Where | Change |
|---|---|
| `labeling/wiring.py`, `glossary/wiring.py`, `guidami_ai_patente_ingestor/cli/wiring.py` | delete `build_open_router_provider` |
| 6 CLI composition roots (`retrieval_evaluation/main.py`, `label_main.py`, `glossary/main.py`, `translate_main.py`, `simplify_main.py`, `guidami_ai_patente_ingestor/cli/main.py`) | `llm_model_provider = OpenRouterModelProvider(<OpenRouterConfig instance>)` |
| `glossary/{main,translate_main,simplify_main}.py` | `register_instance(llm_model_provider, as_type=LlmModelProvider)` instead of `Provider[AsyncOpenAI]` |
| `glossary/agents/*` (3) | `provider_dep: Autowired[LlmModelProvider]`; constructor override param `llm_model_provider: LlmModelProvider \| None` |
| `guidami_ai_patente/providers/open_router_provider_component.py` | replaced by `llm_model_provider_component.py::LlmModelProviderComponent` (`@provider`, `Autowired[OpenRouterConfig]`, exposes `.model_provider: LlmModelProvider`) |
| `guidami_ai_patente/agents/*` (4) | `Autowired[LlmModelProviderComponent]`, `super().__init__(llm_model_provider=self.<field>.model_provider, ...)` |
| `guidami_ai_patente/providers/live_labeling_stack_provider.py` | autowires `LlmModelProviderComponent` instead of `OpenRouterProviderComponent` |
| `labeling/wiring.py::build_comma_labeler_agent`, `CommaLabelerAgent.__init__` | `llm_model_provider: LlmModelProvider` |
| `retrieval_evaluation/wiring.py`, `quiz_flows.py`, `cli/commands/prepare.py` | parameter type/name `llm_model_provider: LlmModelProvider` |
| `guidami_ai_patente/api/app.py` | import/registration list updated for the renamed component |

### 6. Observability

- `TrackedCaller` and `LlmCallLogEntity` gain `model_provider: LlmProvider`.
- `PydanticAILlmCallRecorder` copies `model_provider` from `TrackedCaller` into the
  entity, the same way it copies `model`.
- `PostgresLlmCallLogRepository` persists the new column.

### 7. Judge configuration epoch

- `LabelingEpoch` gains `judge_model_provider: LlmProvider` next to `judge_model`
  (seven fields; docstring updated).
- `LabelingEpochMapper.from_config_to_epoch(config, agent_config, provider: LlmProvider)`
  — the provider is no longer derivable from `agent_config` (D5).
  - API: `LabelingStackProvider` autowires `LlmModelProviderComponent` and passes
    `.model_provider.provider`. It still constructs no LLM client itself — it reads the
    identity of the one the component already owns, which keeps ADR 0029's
    "identity only" split.
  - Batch: `retrieval_evaluation/label_main.py` passes `llm_model_provider.provider`.
- `LabelingRunEntity` gains `judge_model_provider: str` — `str`, not `LlmProvider`:
  `domain/` imports nothing from `commons/` today (the dependency runs
  `commons` → `domain`), and typing a `domain` entity with a `commons` enum would
  introduce a package cycle (ADP). The entity is a DB-row projection, like
  `judge_model: str` next to it; `LabelingRunMapper` copies the epoch's `LlmProvider`
  (a `StrEnum`, hence a `str`) into it.
- `golden_set_write_repository.py`: `_RUN_COLUMNS` gains `judge_model_provider`, and the
  live-run lookup after `INSERT … ON CONFLICT DO NOTHING` filters on it (D6) — without
  it, two live runs differing only by provider would both match and `rows[0]` would be
  arbitrary.
- `golden_set_read_repository.py` precedence query adds `r.judge_model_provider = %s`
  to the non-validated branch, and selects `r.judge_model_provider` for provenance.

### 8. API provenance (D3)

`CurrentLabeling` gains `judge_model_provider: LlmProvider`; `ExplanationMapper` copies
it; the explanation response schema (`guidami_ai_patente/api/schemas/quiz_explanation.py`)
gains `judge_model_provider: str` next to `judge_model`. Additive for clients;
`guidami_ai_patente_bot` does not read provenance. `judge_model`'s *value* loses the
`openrouter/` prefix — a visible, intended change.

### 9. Database — `db/migrations/0025_llm_provider_decoupling.sql`

Follows the established shape of `0011`/`0012`: wrapped in a single `BEGIN`/`COMMIT`,
idempotent, with a commented `information_schema` equivalence check for diffing a
migrated database against a fresh `init.sql` one (`database.md`, Migrations).

```sql
BEGIN;

ALTER TABLE llm_call_logs ADD COLUMN IF NOT EXISTS model_provider TEXT;
UPDATE llm_call_logs
SET model_provider = 'openrouter', model = regexp_replace(model, '^openrouter/', '')
WHERE model_provider IS NULL;
ALTER TABLE llm_call_logs ALTER COLUMN model_provider SET NOT NULL;

ALTER TABLE labeling_runs ADD COLUMN IF NOT EXISTS judge_model_provider TEXT;
UPDATE labeling_runs
SET judge_model_provider = 'openrouter',
    judge_model = regexp_replace(judge_model, '^openrouter/', '')
WHERE judge_model_provider IS NULL;
ALTER TABLE labeling_runs ALTER COLUMN judge_model_provider SET NOT NULL;

DROP INDEX IF EXISTS uq_labeling_runs_live_config;
CREATE UNIQUE INDEX uq_labeling_runs_live_config
    ON labeling_runs (judge_model, judge_model_provider, prompt_version, candidate_variant,
                      dense_k, text_k, lexeme_fields)
    WHERE origin = 'live';

COMMIT;
```

The backfill keys on `*_provider IS NULL` (not on the prefix), so every pre-existing
row — all of which were produced through OpenRouter, the only provider ever wired — is
tagged, and a re-run touches nothing. Stripping is 1:1, so it cannot create a
unique-index collision among existing live runs. `db/init.sql` gets the same final
shape (both columns `NOT NULL`, the seven-column index).

**Deployment order** (dev stack, path 2 per `CLAUDE.md`): stop `serve`/`telegram-bot`
and any running CLI → apply the migration → start the new code. Old code running
against the migrated schema would fail inserting `llm_call_logs` (NOT NULL, no default)
and would look up `openrouter/…` epochs that no longer exist. Verify row counts of
`llm_call_logs` and `labeling_runs` are unchanged, and that
`count(*) WHERE model LIKE 'openrouter/%'` is 0 afterwards.

### 10. YAML

All 11 files under `configs/agents/` lose the `openrouter/` prefix from `model_name`
(`openrouter/google/gemini-2.5-flash-lite` → `google/gemini-2.5-flash-lite`).
`AgentConfig` is unchanged; the provider concept never lives on it.

**Caveat**: the remaining string is still OpenRouter's catalog syntax (`vendor/model`),
not a provider-neutral id. Native Gemini calls the same model `gemini-2.5-flash-lite`;
Ollama has an entirely different catalog. Any future provider switch rewrites
`model_name` too — which is also why D6 costs nothing extra in invalidations.

## Clean-architecture review

- **Dependency Rule / DIP**: `commons/ai/agents` (policy: how an agent runs) depends on
  the `LlmModelProvider` abstraction in `commons/ai/llm_providers/protocols/`; the
  concrete adapters (details) depend on pydantic-ai and `OpenRouterConfig`. Composition
  roots (entry points, pywire providers) are the only place a concrete adapter is
  named — Main as the dirtiest component (ch26).
- **OCP**: a new provider is a new adapter; `BaseAgent` and the 11 agents are closed to
  that change.
- **ISP**: the port has exactly the four members `BaseAgent` consumes.
- **SRP**: provider-specific model construction/settings/cost semantics move out of
  `BaseAgent` into one class per provider (one reason to change each).
- **Deliberate deviation**: the port's signatures expose pydantic-ai types (`Model`,
  `ModelSettings`). Accepted: `BaseAgent` is itself a pydantic-ai adapter living in the
  same ring, so the port is a seam *within* the framework-adapter layer, not a boundary
  between domain and framework. Abstracting pydantic-ai away would be a different,
  much larger project.
- **Component coupling**: no cycle — `llm_providers` depends on `commons.configs` and
  pydantic-ai only; `agents` and `observability` depend on `llm_providers` (the enum),
  never the reverse.

## Testing

- `OpenRouterModelProvider` / `OllamaModelProvider` — unit tests: model class
  (`OpenRouterModel` / `OpenAIChatModel`), model name passed through verbatim,
  settings (`openrouter_usage` attached / base unchanged), `expects_cost`, `provider`,
  and that repeated `create_model` calls share one pydantic-ai provider instance.
- `BaseAgent` — existing tests swap their `OpenRouterProvider`/`OllamaProvider` doubles
  for the two adapters (or an `LlmModelProvider` double); re-verify model/settings
  built, and `expects_cost`/`model_provider` wired into `TrackedCaller`.
- `PydanticAILlmCallRecorder` / `PostgresLlmCallLogRepository` — `model_provider`
  copied and persisted (integration test against the test stack).
- `LabelingEpochMapper` — `judge_model_provider` is taken from the argument.
- `golden_set_write_repository` (integration) — two live runs with identical epoch
  fields except `judge_model_provider` get distinct ids, and each lookup returns its own.
- `golden_set_read_repository` (integration) — a non-validated labeling under a
  different `judge_model_provider` is not current; a human-validated one still wins
  regardless of provider; provenance carries `judge_model_provider`.
- Explanation API — response carries `provenance.judge_model_provider`.
- Wiring — `LlmModelProviderComponent` resolves a singleton `OpenRouterModelProvider`;
  glossary container resolves agents with the registered `LlmModelProvider`.
- Migration — manual verification per §9 (row counts, no remaining prefix,
  `information_schema` equivalence vs fresh `init.sql`).

## Risks / edge cases

- **Blast radius**: 11 agents, 7 composition roots, 4 pass-through modules, 3 wiring
  mechanisms — sized accordingly in the plan.
- **Epoch invalidation**: none at migration time — every historical run is backfilled
  to `openrouter` with its prefix stripped, matching the stripped YAML the new code
  derives. A future provider switch invalidates non-validated cached labelings (via
  both `judge_model` and `judge_model_provider`); human-validated labelings keep
  winning regardless (FR-8 precedence).
- **Deploy skew**: old code against the new schema fails loudly (see §9 deployment
  order) — acceptable for a single-user dev stack, but the order must be followed.
- **ADR 0019 superseded**: must be marked as such in the same branch, with the new ADR
  pointing to the adapter that carries its capability.
