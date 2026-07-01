# Ingestor — Generic Steps and Context Keys

Domain-agnostic orchestration glue in `orchestrators/steps/generic/` and the
shared key vocabulary in `context_keys.py`. These components sit between the
[flowstep framework](../../flowstep/_index.md) and the concrete
repositories/services/mappers. No domain logic.

## Layout

```
src/guidami_ai_patente_ingestor/orchestrators/
  context_keys.py                # FlowContext key constants (no magic strings)
  steps/
    generic/
      __init__.py                # re-exports DbStoreStep, EmbedStep, LoadJsonStep,
                                 #   StoreRepository, WriteJsonStep
      protocols/
        store_repository.py      # Protocol StoreRepository
                                 # enricher_protocol.py REMOVED (EnricherProtocol removed in SP04)
      embed_step.py              # class EmbedStep(Step)
      db_store_step.py           # class DbStoreStep(Step)
      load_json_step.py          # class LoadJsonStep(Step)
      write_json_step.py         # class WriteJsonStep(Step)
                                 # map_step.py REMOVED (MapStep replaced by ApplyStep+ForEach in SP04)
                                 # enrich_data_step.py REMOVED (EnrichDataStep removed in SP04)
```

## `context_keys.py` — key vocabulary

Constants used by both pipelines (knowledge, quiz), indexing and preparation.
Consumers access as `context_keys.EMBEDDABLE_CHUNKS` via submodule import
(`from guidami_ai_patente_ingestor.orchestrators import context_keys`).

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

Key design constraints:

- `ARTICLES_BY_SOURCE` (as `dict[str, list[...]]`) does not exist: the design
  is per-source (one run per source), so article keys are always flat lists for
  ONE source only.
- No `SOURCE` key: the source is injected into `Load*`/`Write*` steps at
  factory time, never passed through `FlowContext`.
- `IMAGE_DESCRIPTIONS` is not a context key: it stays as internal state of
  `ImageDescriptionEnricher` (dict built and consumed inside `enrich()`).

## Implemented Decisions

- **Placement in `orchestrators/steps/generic/`**: steps import `flowstep.Step`
  (top-level package — orchestration glue). They belong to `orchestrators/`, not
  `services/` (SRP + dependency direction).
- **`StoreRepository` Protocol with positional-only `bulk_insert`**: the `/`
  parameter decouples the contract from the concrete argument names (`chunks`/
  `questions`) used by `KnowledgeChunkStoreRepository` and
  `QuizQuestionStoreRepository`. `list[Any]` (gradual typing) is satisfied by
  both concrete types. Structural conformance — no explicit inheritance required.
- **`EmbedStep`: `required == produced == {items_key}`**: the step reads and
  rewrites the same key (in-place mutation + `context.put`). `FlowValidator`
  emits a benign WARNING "Produced key overwrites an already available key" — not
  an ERROR and does not block `build(validate=True)` (SP03/04).
- **`DbStoreStep`: `produced == set()`**: terminal sink, produces no new keys.
  Guaranteed order: `truncate()` → `bulk_insert(items)`.
- **`super().__init__(name)` required** in both steps: `Step.name` reads
  `self._name` initialised by the base constructor (concrete ABC, not mixed in).
- **`StoreRepository` next to `DbStoreStep`**: if `DbStoreStep` were promoted to
  `flowstep/steps/` in the future, the Protocol would go with it — `flowstep`
  cannot import from the ingestor (zero domain dependencies).
- **`cast(list[Embedded], context.get(...))` and `cast(list[Any], ...)`**: used
  at `FlowContext.get(key)` boundaries (which returns `Any`) to signal the
  expected type explicitly.
- **`zip(strict=True)` in `EmbedStep`**: defensive guard — raises `ValueError`
  if `EmbeddingService` returned a different number of vectors than items (explicit
  contract, even though `EmbeddingService` guarantees 1:1 alignment).
- **Generic `LoadJsonStep`/`WriteJsonStep`**: get→delegate→put steps for JSON
  load and write. Parameterised with `model_class`/`layer`/`source`/`output_key`
  or `input_key`. Reused identically by knowledge and quiz flows. Previous
  domain-specific steps (`LoadParsedArticlesStep`, `WriteCleanedStep`, etc.) were
  removed because they were pure get→delegate→put with no own logic.
- **`MapStep`/`EnrichDataStep`/`EnricherProtocol` removed in SP04**: superseded
  by `ApplyStep` in the flowstep package. See
  [flowstep/_index.md](../../flowstep/_index.md) for the unification decision.

## Testing

All tests in `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/` —
no `integration` marker (no external dependencies):

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

**Removed** (deleted steps): `test_map_step.py` (MapStep removed in SP04),
`test_enrich_data_step.py` (EnrichDataStep removed in SP04).
