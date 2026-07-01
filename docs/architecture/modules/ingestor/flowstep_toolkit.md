# Ingestor — Generic flowstep steps and ApplyStep (SP02, extended by SP08-bis, enrichment refactor, SP00b/SP04)

**`flowstep` is now a top-level package** (`src/flowstep/`, sibling of `commons/` and
the ingestor — moved from `src/commons/flowstep/` in SP00b). Zero dependencies on
`commons` or the domain. Exposes `Flow`, `Step`, `FlowBuilder`, `FlowContext`,
`FlowValidator`, exceptions + **`ApplyStep`** (new, in `src/flowstep/steps/`).

The **domain-agnostic** steps in `orchestrators/steps/generic/` are orchestration
glue between `flowstep` and the concrete repositories/services/mappers. No
domain logic.

## Layout

```
src/flowstep/                    # Top-level package (moved from commons/flowstep/ in SP00b)
  __init__.py                    # re-exports Flow, Step, FlowBuilder, FlowContext, ApplyStep,
                                 #   FlowValidator, FlowValidationError, FlowValidationReport,
                                 #   StepValidationResult, ValidationSeverity, FlowExecutionError
  core/                          # Flow, Step, FlowContext — unchanged
  builder/                       # FlowBuilder — unchanged
  validation/                    # FlowValidator, report, exceptions — unchanged
  steps/
    __init__.py                  # re-exports ApplyStep
    apply_step.py                # class ApplyStep(Step) — chains N list→list callables on a context key

src/guidami_ai_patente_ingestor/orchestrators/
  context_keys.py                # FlowContext key constants (no magic strings)
  preparation_runner.py          # run_preparation(flow, out_path, force) — generic runner (SP05)
  steps/
    __init__.py                  # docstring
    generic/
      __init__.py                # re-exports DbStoreStep, EmbedStep, LoadJsonStep,
                                 #   StoreRepository, WriteJsonStep
      protocols/
        store_repository.py      # Protocol StoreRepository
                                 # enricher_protocol.py REMOVED (EnricherProtocol removed in SP04)
      embed_step.py              # class EmbedStep
      db_store_step.py           # class DbStoreStep
      load_json_step.py          # class LoadJsonStep
      write_json_step.py         # class WriteJsonStep
                                 # map_step.py REMOVED (MapStep replaced by ApplyStep+ForEach)
                                 # enrich_data_step.py REMOVED (EnrichDataStep removed)
    knowledge/                   # domain-specific knowledge steps (indexing only)
      __init__.py
      chunk_articles_step.py     # ChunkArticlesStep (indexing)
      embed_chunks_step.py       # EmbedChunksStep (indexing, embed_repealed filter)
      store_chunks_step.py       # StoreChunksStep (indexing, delete-by-source)
                                 # ContextualizeStep REMOVED (preparation uses generic ApplySteps)
    quiz/                        # empty package — no remaining quiz domain-specific steps
      __init__.py                # __all__ = []
                                 # FlattenQuizStep REMOVED → logic moved to services/quiz/flatten_quiz.py
                                 # MapToEmbeddableStep REMOVED → logic moved to services/quiz/to_embeddable_quiz.py
```

**`ApplyStep`** (`src/flowstep/steps/apply_step.py`, re-exported from `flowstep`):
generic step that applies N `list→list` callables in a chain to a value from the
`FlowContext`. Constructor signature: `ApplyStep(name, *transforms, input_key,
output_key)`. Each transform receives the list produced by the previous one. Replaces
`MapStep` (a single mapper per item, 1:1 map) and `EnrichDataStep` (chain of
list-in/list-out enrichers): now the entire chain — base-map + enrichment —
lives in a single `ApplyStep` that accepts both `ForEach(mapper)` (for 1:1 mapping)
and an enricher callable directly (for list-in/list-out operations).

**Decision — unification of MapStep+EnrichDataStep into ApplyStep**: removed
steps: `map_step.py`, `enrich_data_step.py`, `enricher_protocol.py` (generic
Protocol), `flatten_quiz_step.py`, `map_to_embeddable_step.py`. Stateful logic
(flatten+dedup) moved to `services/quiz/` (`FlattenQuiz`,
`ToEmbeddableQuiz`) — see [quiz_pipelines.md](quiz_pipelines.md). Accepted
trade-off: `*transforms: Callable[[list[Any]], list[Any]]` uses `Any` to
express heterogeneous chains (not expressible in Python 3.12 without losing
type information on mixed chains). The surviving domain-specific steps are
those with logic irreducible to get→callable→put: `ChunkArticlesStep` (N
outputs from 1 input) and `EmbedChunksStep` (`embed_repealed` filter).

## `context_keys.py` — key vocabulary

Constants used by both pipelines (knowledge, quiz), indexing and preparation:

| Constant | Value | Used by |
|---|---|---|
| `ENRICHED_ARTICLES` | `"enriched_articles"` | indexing input + enrich flow output — flat list, one source |
| `PARSED_ARTICLES` | `"parsed_articles"` | `clean` flow input: `list[ParsedArticleModel]` from `parsed` layer |
| `CLEANED_ARTICLES` | `"cleaned_articles"` | `clean` flow output / `enrich` flow input: cleaned `list[ParsedArticleModel]` |
| `EMBEDDABLE_CHUNKS` | `"embeddable_chunks"` | chunker output → embed: `list[EmbeddableChunkModel]` |
| `CHUNK_ENTITIES` | `"chunk_entities"` | map output → store: `list[KnowledgeChunk]` |
| `ENRICHED_QUIZ` | `"enriched_quiz"` | indexing input + enrichment flow output — enriched quiz bank (flat from SP09) |
| `EMBEDDABLE_QUIZ` | `"embeddable_quiz"` | intermediate models → embed |
| `QUIZ_ENTITIES` | `"quiz_entities"` | final entities → store |
| `PARSED_QUIZ` | `"parsed_quiz"` | cleaning flow input: `list[ParsedQuizModel]` (nested) from `parsed` layer (SP09) |
| `CLEANED_QUIZ` | `"cleaned_quiz"` | cleaning flow output / enrichment flow input: `list[CleanedQuizModel]` flat (SP09) |

`ARTICLES_BY_SOURCE` (proposed as `dict[str, list[EnrichedArticleModel]]` for multiple
sources) **does not exist in the code**: the implemented design is per-source (one
run per source), so `ENRICHED_ARTICLES`/`PARSED_ARTICLES`/`CLEANED_ARTICLES`
are always flat lists of ONE source only. No `SOURCE` key: the source never
passes through `FlowContext`, it is injected into `Load*`/`Write*` steps at
factory time. Same principle for the quiz: `IMAGE_DESCRIPTIONS` is not a context
key — it stays as internal state of `ImageDescriptionEnricher` (dict
built and consumed inside `enrich()`), never exposed in `FlowContext`.

Consumers access as `context_keys.EMBEDDABLE_CHUNKS` — submodule import
(`from guidami_ai_patente_ingestor.orchestrators import context_keys`).
`orchestrators/__init__.py` re-exports `build_knowledge_indexing_flow`,
`build_knowledge_cleaning_flow`/`build_knowledge_enrichment_flow`,
`build_quiz_indexing_flow`, `build_quiz_cleaning_flow`/
`build_quiz_enrichment_flow` (SP09, replacing the previous
`build_quiz_preparation_flow`) and `run_preparation`.

## Implemented decisions

- **Placement in `orchestrators/steps/generic/`**: the `Step`s import
  `flowstep.Step` (top-level package — orchestration glue) — they belong
  to `orchestrators/`, not `services/` (SRP + dependency direction).
- **`StoreRepository` Protocol with positional-only `bulk_insert`**: the `/`
  parameter decouples the contract from the concrete names (`chunks`/`questions`) of
  `KnowledgeChunkStoreRepository` and `QuizQuestionStoreRepository`, which would
  otherwise break pyright's structural match. `list[Any]` (gradual typing) is
  satisfied by both `list[KnowledgeChunk]` and `list[QuizQuestion]`.
  **Structural** conformance — no explicit inheritance in concrete repos.
- **`EmbedStep`: `required == produced == {items_key}`**: the step reads and
  rewrites the same key (in-place mutation + `context.put`). `FlowValidator` will
  emit a **benign WARNING** "Produced key overwrites an already available key" — not
  an ERROR and does not block `build(validate=True)` (SP03/04).
- **`DbStoreStep`: `produced == set()`**: terminal sink, produces no new keys.
  Guaranteed order: `truncate()` → `bulk_insert(items)`.
- **`super().__init__(name)` required** in both steps: `Step.name` reads
  `self._name` initialised by the base constructor (concrete ABC, not mixed in).
- **`StoreRepository` next to `DbStoreStep`**: in the future, if `DbStoreStep` were
  promoted to `flowstep/steps/`, the Protocol would go with it — `flowstep` cannot
  import from the ingestor (zero domain dependencies).
- **`cast(list[Embedded], context.get(...))` and `cast(list[Any], ...)`**: at
  `FlowContext.get(key)` boundaries (which returns `Any`) to explicitly signal the
  expected type.
- **`zip(strict=True)` in `EmbedStep`**: defensive guard — raises `ValueError` if
  `EmbeddingService` returned a different number of vectors than items (explicit
  contract, even though `EmbeddingService` guarantees 1:1 alignment).
- **Generic `LoadJsonStep`/`WriteJsonStep`**: get→delegate→put steps for JSON load
  and write. Parameterised with `model_class`/`layer`/`source`/`output_key` or
  `input_key`. Reused identically by knowledge and quiz. The previous
  domain-specific steps (`LoadParsedArticlesStep`, `WriteCleanedStep`, etc.) were
  removed because they were pure get→delegate→put with no own logic.
- **`ApplyStep`** (in `flowstep.steps`, not in `generic/`): see section above.

## Tests

- `tests/flowstep/steps/test_apply_step.py` — `ApplyStep` with zero, one, multiple
  transforms; transforms are called in sequence, each on the previous output;
  `get_required_keys() == {input_key}`, `get_produced_keys() ==
  {output_key}`; input_key == output_key (overwrite in place) works.

`tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/` — no
`integration` marker (no external dependencies):

- `test_embed_step.py`:
  - `get_required_keys() == get_produced_keys() == {items_key}`.
  - `execute` assigns embedding in place and rewrites `items_key` in the context.
  - `ValueError` on vector/item length mismatch (`zip strict`).
- `test_db_store_step.py`:
  - `get_required_keys() == {items_key}`, `get_produced_keys() == set()`.
  - `execute` calls `truncate` then `bulk_insert` in the correct order.
- `test_store_repository.py`:
  - Static structural conformance (pyright): `_conforms` function with
    `StoreRepository` annotations on `KnowledgeChunkStoreRepository` and
    `QuizQuestionStoreRepository`. No runtime instantiation (no Postgres required).
- `test_load_json_step.py` / `test_write_json_step.py`:
  - `required`/`produced` contract per key; delegation to `layer_resolver.path(...)`
    + injected repository/model_class.

**Removed** (deleted steps): `test_map_step.py` (MapStep removed),
`test_enrich_data_step.py` (EnrichDataStep removed).
