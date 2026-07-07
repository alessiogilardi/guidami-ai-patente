# Cross-Cutting Patterns

Patterns used across the codebase. All implementations live in `src/domain/` or
`src/flowstep/` and are shared between the ingestor and the future FastAPI app.

## `UseCase[T_In, T_Out]`

**Location**: `domain/use_cases/use_case.py`

Abstract base class with two type parameters that standardises the contract of stateless
components with a single operation.

- Abstract method: `execute(request: T_In) -> T_Out`
- `__call__` is marked `@final` and delegates to `execute` — every `UseCase` is directly
  callable (compatible with `ApplyStep` and `ForEach` which accept a callable).

**Adopted by**: `EmbeddingService`, `ArticleCleaner`, `ArticleChunker`, `FlattenQuiz`,
`DeduplicateQuizItems`, `ContextEnricher`, `ImageDescriptionEnricher`.

The public method of all implementations is named `execute`. This keeps the
pure/impure separation explicit: the contract does not prescribe side effects.

**`AsyncUseCase[T_In, T_Out]`** (`commons/use_cases/use_case.py`): async variant — same
structure as `UseCase` but `execute` is `async`. `__call__` is `@final async`. Added
without active consumers: establishes the contract for future async implementations
(e.g. embedding or LLM calls with `asyncio`).

## `ForEach[T, U]`

**Location**: `commons/use_cases/for_each.py`

`UseCase[list[T], list[U]]` that wraps a `Callable[[T], U]` and applies it to each element
of the input list. Accepts both `UseCase` instances (invoked via `__call__`) and static
methods (e.g. `QuizMapper.from_embeddable_to_quiz_question`).

Used in flow builders to wrap 1:1 mappers into a `list→list` callable compatible with
`ApplyStep`.

Trade-off: `fn: Callable[[T], U]` is broader than `UseCase[T, U]` — it allows passing
static methods without an additional wrapper.

## `ApplyStep` and `ApplyStep(ForEach(fn))` composition

**Location**: `src/flowstep/steps/apply_step.py` (re-exported from `flowstep`)

`ApplyStep(name, *transforms, input_key, output_key)` — generic step that chains N
`list→list` callables on a `FlowContext` value. Each transform receives the list produced
by the previous one.

The idiomatic composition pattern in flow builders:

```python
# 1:1 mapping with a UseCase or static method
ApplyStep("map_to_chunk_entity", ForEach(ArticleMapper.from_enriched_to_chunk), ...)

# Enrichment with a UseCase that is already list→list
ApplyStep("contextualize", ContextEnricher(config), ...)

# Combined: base-map then enrichment in a single step
ApplyStep("prepare", ForEach(mapper_fn), enricher_use_case, ...)

# Combined: two chained UseCase transforms (dedup then 1:1 mapping)
ApplyStep("map_to_embeddable", DeduplicateQuizItems(), ForEach(QuizMapper.from_enriched_to_embeddable), ...)
```

`ApplyStep` replaced `MapStep` (single mapper per item, 1:1 map) and `EnrichDataStep`
(chain of enrichers, list-in/list-out). The entire chain — base-map + enrichment — now
lives in a single `ApplyStep` that accepts both `ForEach(mapper)` (for 1:1 mapping) and
an enricher callable directly (for list-in/list-out operations).

**Bare function as a transform, and when to promote it to a `UseCase`**: a
transform does not have to be a `UseCase` or a class — any `list→list`
callable works, including a private module-level function. This was tried for
quiz dedup: `orchestrators/quiz_flows.py::_dedup_enriched_quiz` started as a
small, pure, single-purpose transform with no injected config, kept as a
plain function in the orchestrator instead of a `services/` class, since it
had a single call site (`ApplyStep` does not require the `UseCase` contract
for a step this narrow). Once the identical dedup key was found duplicated in
a second call site (`FlattenQuiz`, a different flow builder), that premise no
longer held: the logic was promoted to `DeduplicateQuizItems`
(`services/quiz/`), a shared, independently testable, Protocol-generic
`UseCase`, now chained as a transform in both flow builders. Rule of thumb: a
bare function is acceptable only while the logic has one call site and no
injected config — a second call site is the signal to promote it to a
`services/` class.

Domain-specific steps that survived the consolidation are those with logic that cannot be
reduced to get→callable→put: `ChunkArticlesStep` (N outputs from 1 input) and
`EmbedChunksStep` (filters on `embed_repealed`).

## `embedded_text` property convention

Intermediate DTOs that participate in embedding expose a property `embedded_text: str`
that returns the string to be embedded. This satisfies the `Embeddable` Protocol
(`commons/services/embeddings/embeddable.py`) required by `EmbeddingService`.

Examples:

- `EmbeddableChunkModel` (ingestor, knowledge): returns the chunk text, optionally
  prefixed with article title/topic context.
- `EmbeddableQuizModel` (ingestor, quiz): `embedded_text` returns `f"{topic} {text}"` —
  the question text prefixed by its topic.

**Entities** (`KnowledgeChunk`, `QuizQuestion`) do **not** expose `embedded_text`: they
are DB-write-only objects. The embedding is computed on the intermediate DTO and then
transferred to the entity before storage.

## Config loading pattern

Root configuration (`AppConfig`, `IngestorConfig`, ...) must be loaded at the **entry
point** (`cli.py`, `main.py`), never inside builders, services, or constructors.
Components receive an already-validated config object — they never load it themselves.

```python
# WRONG — config loaded inside the builder or service
class KnowledgePipelineBuilder:
    def __init__(self, config_path: str) -> None:
        self._config = IngestorConfig(_yaml_file=config_path)  # NO

# RIGHT — config loaded at the entry point, injected into the builder
# cli.py:
config = IngestorConfig(_yaml_file=args.config)
pipeline = KnowledgePipelineBuilder(config, ...).build()
```

This rule applies to all layers: orchestrators, services, repositories, clients. The only
exception is `commons`, which intentionally has no config loading — it receives already-
constructed config objects from whoever calls it.
