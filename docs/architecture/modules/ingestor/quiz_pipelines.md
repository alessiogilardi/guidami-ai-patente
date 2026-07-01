# Ingestor — Quiz bank pipeline

See [data_preparation.md](data_preparation.md) for the two quiz
preparation flows (`build_quiz_cleaning_flow`, `build_quiz_enrichment_flow`) that
produce the `cleaned`/`enriched` layers consumed here.
See [config_and_entrypoints.md](config_and_entrypoints.md) for `IngestorConfig`,
`LayerResolver` and the CLI entry points.

## Quiz model chain (4 stages, one model per layer, all flat)

```text
parsed (layer "parsed", nested — direct output of the PDF parser)
   ParsedQuizModel ─┬─ sub_questions: list[ParsedQuizItemModel]
        │ flatten + dedup → FlattenQuiz.execute(items)
        │                   (per item: QuizMapper.from_parsed_to_cleaned)
        ▼
cleaned (layer "cleaned", flat — one row per sub-question, self-contained)
   CleanedQuizModel
        │ ApplyStep("enrich"):
        │   ForEach(QuizMapper.from_cleaned_to_enriched) base-map flat→flat
        │   + ImageDescriptionEnricher.execute() populates image_description
        ▼
enriched (layer "enriched", flat)
   EnrichedQuizModel   (+ image_description)
        │ to embeddable → ToEmbeddableQuiz().execute(items)
        │                 (indexing side: dedup + QuizMapper.from_enriched_to_embeddable)
        ▼
embeddable (flat)
   EmbeddableQuizModel   (image_description, embedding, embedded_text)
        │ embed (EmbedStep) → embedding populated
        │ to_entity → QuizMapper.from_embeddable_to_quiz_question (via ForEach)
        ▼
db row (flat)
   QuizQuestion   [entity, commons/entities/quiz — unchanged]
```

`*Model` = non-persisted intermediate (`models/quiz/`); `QuizQuestion` (no
suffix) = DB row (`commons/entities/quiz/`).

**SP09 decision — flatten+dedup moved to preparation**: flatten (nested
→ flat) and dedup on sub-questions historically happened at the indexing stage.
SP09 moved them **upstream**, to the cleaning stage: from `cleaned` onwards
(`cleaned`, `enriched`, `embeddable`) the quiz bank is **already flat**,
one row per sub-question, self-contained (`question_id`/`topic`
denormalised on each row). The SP04 refactor then moved the flatten+dedup logic
**from a flowstep step** (`FlattenQuizStep`) to a **domain service**
(`FlattenQuiz`), and analogously the enriched→embeddable mapping logic
from `MapToEmbeddableStep` to `ToEmbeddableQuiz`. The two services are then wrapped
by `ApplyStep` in the flow factories — no breakage to the flowstep interface.

## Implemented decisions

### `models/quiz/` — one model per layer (renamed in SP09)

- `parsed_quiz.py` — `ParsedQuizModel`/`ParsedQuizItemModel`: parent question +
  sub-questions, nested structure as-is from the PDF parser JSON (layer
  `parsed`). Ex `QuizBankModel`/`QuizBankItemModel`.
- `cleaned_quiz.py` — `CleanedQuizModel`: one sub-question per row, flat,
  self-contained (`question_id`, `topic`, `number`, `text`, `correct_answer`,
  `image`). Output of `FlattenQuiz.execute` (layer `cleaned`).
- `enriched_quiz.py` — `EnrichedQuizModel`: same fields as `CleanedQuizModel`
  + `image_description: str | None`. Output of the enrichment flow (layer
  `enriched`).
- `embeddable_quiz.py` — `EmbeddableQuizModel`: DTO for computing
  the embedding (indexing side), `embedded_text` property = `f"{topic}
  {text}"` + `f" {image_description}"` if present.
- `image_description.py` — `ImageDescription(BaseModel, frozen=True)`:
  `name: str`, `description: str`.

`question_id` is a numeric string in the source JSON, but Pydantic v2 coerces
it to `int` (lax coercion) — the `quiz_questions.question_id INTEGER` column is
therefore correct without manual conversions.

### `repositories/json/quiz_bank_repository.py` / `enriched_quiz_bank_repository.py`

- `QuizBankRepository` extends `JsonRepository[ParsedQuizModel]`,
  `EnrichedQuizBankRepository` extends `JsonRepository[EnrichedQuizModel]`.
  Both have no injected dependencies/config, inherit `load`/`write` from
  the base. Re-exported from `repositories/__init__.py`.
- The preparation `cleaning`/`enrichment` flows today use the generic `Step`s
  `LoadJsonStep`/`WriteJsonStep` with explicit `model_class`, not these
  repositories — see [data_preparation.md](data_preparation.md). The repositories
  remain used in round-trip tests.

### `mappers/quiz/quiz_mapper.py` — `QuizMapper` (consolidated)

Single static mapper hosting **all** 1:1 transitions of the quiz chain,
each as `from_X_to_Y(model, *extra) -> Z`.

| Method | Signature | Notes |
| --- | --- | --- |
| `from_parsed_to_cleaned` | `(item: ParsedQuizItemModel, parent: ParsedQuizModel) -> CleanedQuizModel` | denormalises `question_id`/`topic` from `parent` (SP09) |
| `from_cleaned_to_enriched` | `(item: CleanedQuizModel) -> EnrichedQuizModel` | base-map flat→flat, `image_description=None` (SP09) |
| `from_enriched_to_embeddable` | `(item: EnrichedQuizModel) -> EmbeddableQuizModel` | indexing side; 1 argument, flat model (renamed in SP03, ex `from_enriched_quiz_item_to_embeddable`) |
| `from_embeddable_to_quiz_question` | `(model: EmbeddableQuizModel) -> QuizQuestion` | drops `image_description`, keeps `embedding` |

**Decisions:**

- **Accepted SRP trade-off**: a single class for all transitions changes for
  more reasons (weaker than the "one class per transformation" rule), but makes
  the chain readable in a single place. Mitigation: static, small, pure methods.
- **`flatten+dedup` NOT in the mapper**: it is not a 1:1 mapping but
  a collection operation + dedup rule → lives in `FlattenQuiz`
  (preparation, parsed→cleaned, SP09/SP02) and `ToEmbeddableQuiz` (indexing,
  enriched→embeddable, SP03), not in `QuizMapper`.
- **Enrichment and Open/Closed**: the base-map (`from_cleaned_to_enriched`)
  produces `EnrichedQuizModel` with enrichment fields set to `None`; enrichers
  populate them via `model_copy`. Adding an agent does not modify the base-map
  signature.

### `orchestrators/steps/quiz/` — empty package

The `orchestrators/steps/quiz/` package no longer contains any step class
(`__all__ = []`). All the quiz domain logic previously in
`FlattenQuizStep` and `MapToEmbeddableStep` has been moved to `services/quiz/`
(see below). The flow builders use `ApplyStep` to wrap those services.

**Removed steps (SP04):**
- `FlattenQuizStep` → logic moved to `services/quiz/flatten_quiz.py::FlattenQuiz`
- `MapToEmbeddableStep` → logic moved to `services/quiz/to_embeddable_quiz.py::ToEmbeddableQuiz`
- `LoadQuizStep`, `EnrichQuizStep`, `WriteEnrichedQuizStep` — removed
  earlier, replaced by generic `LoadJsonStep`/`WriteJsonStep`.

### `services/quiz/` — domain services for the quiz bank

```
services/quiz/
├── __init__.py                          # re-exports ImageDescriptionEnricher
├── flatten_quiz.py                      # FlattenQuiz(UseCase[list[ParsedQuizModel], list[CleanedQuizModel]])
├── to_embeddable_quiz.py                # ToEmbeddableQuiz(UseCase[list[EnrichedQuizModel], list[EmbeddableQuizModel]])
└── enrichers/
    ├── __init__.py                      # re-exports ImageDescriptionEnricher
    └── image_description_enricher.py    # ImageDescriptionEnricher(UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]])
```

**`FlattenQuiz`** (`services/quiz/flatten_quiz.py`, SP02): implements
`UseCase[list[ParsedQuizModel], list[CleanedQuizModel]]`. `execute`: iterates
`sub_questions` of each parent question, deduplicates on key `(text.strip(),
correct_answer, image)` (`logger.warning` for each discarded duplicate), for
each kept item delegates to `QuizMapper.from_parsed_to_cleaned(item, parent)`.
Responsibility: nested→flat flatten + dedup. Does not depend on flowstep.

**`ToEmbeddableQuiz`** (`services/quiz/to_embeddable_quiz.py`, SP03):
implements `UseCase[list[EnrichedQuizModel], list[EmbeddableQuizModel]]`.
`execute`: iterates the flat enriched list, deduplicates on the same triple
`(text.strip(), correct_answer, image)` (removes the 8 historical exact duplicates
→ 7098 final rows), for each kept item calls
`QuizMapper.from_enriched_to_embeddable(item)` (1 argument, flat model).
Responsibility: dedup + enriched→embeddable mapping. Does not depend on flowstep.

**`ImageDescriptionEnricher`** now implements
`UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]]` (previously only
satisfied `EnricherProtocol` structurally). `execute` (ex `enrich`): same
logic as before — dedup on key `(image, topic, text)`, one vision call
per unique image, skip + warning on missing file or exception.

**Removed**: `services/quiz/quiz_enrichment_service.py` (`QuizEnrichmentService`)
and `services/quiz/enrichers/quiz_enricher.py` (`Protocol QuizEnricher`).

**Architectural decision — enrichment evolution (two phases).** First
phase (previous refactor): removed `QuizEnrichmentService`/`EnrichQuizStep`/`Protocol
QuizEnricher` in favour of generic `MapStep` + `EnrichDataStep`. Second phase
(SP04): removed `MapStep`/`EnrichDataStep` in favour of a single `ApplyStep`
that accepts direct callables. Enrichers are now `UseCase` callables via
`__call__` — no intermediate `Protocol` needed.

**Open/Closed**: adding a future enricher = adding the callable
to the `*transforms` list of `ApplyStep("enrich")` in the factory. Zero
changes to the step, the flowstep framework or other enrichers.

- **`ImageDescriptionEnricher`** (only concrete enricher): `__init__(road_sign_describer:
  RoadSignDescriberAgent, images_dir: Path)`. Implements `UseCase[list[EnrichedQuizModel],
  list[EnrichedQuizModel]]`; callable via `__call__` (no explicit `Protocol`
  inheritance). `execute(request: list[EnrichedQuizModel])
  -> list[EnrichedQuizModel]`:
  1. collects the **unique** `(image, topic, text)` keys across the entire flat
     list (dedup on triple → one vision call per unique context);
  2. for each unique image: if the file does not exist → `logger.warning` +
     skip (no exception); if `describe()` raises → `logger.warning`
     (with `exc_info=True`) + skip; otherwise formats
     `f"{desc.name}. {desc.description}"`;
  3. returns new `EnrichedQuizModel` instances (via list comprehension with
     `RoadSignDescriberMapper.from_response_to_enriched_quiz`, no in-place
     mutation) with `image_description` populated for each sub-question whose
     key is in the dict (remains `None` if absent or skipped).

> **`EnrichDataStep[T]` and `EnricherProtocol` REMOVED in SP04**: they were the
> generic step (list-in/list-out enricher chain) and the related Protocol.
> Replaced by `ApplyStep` with direct callables (enrichers as `UseCase`
> callable via `__call__`). See [flowstep_toolkit.md](flowstep_toolkit.md).

### `orchestrators/quiz_flows.py` — quiz flow factory

```python
def build_quiz_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    validate: bool = False,
) -> Flow
```

Chain (5 steps):
`LoadJsonStep("load_enriched_quiz")` →
`ApplyStep("map_to_embeddable", ToEmbeddableQuiz())` →
`EmbedStep("embed_quiz", items_key=EMBEDDABLE_QUIZ)` →
`ApplyStep("map_to_quiz_entity", ForEach(QuizMapper.from_embeddable_to_quiz_question))` →
`DbStoreStep("store_quiz")`.

```python
def build_quiz_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```

Chain (3 steps):
`LoadJsonStep("load_parsed_quiz")` →
`ApplyStep("flatten_quiz", FlattenQuiz())` →
`WriteJsonStep("write_cleaned_quiz")`.
Introduced in SP09; SP04 replaced `FlattenQuizStep` with
`ApplyStep(FlattenQuiz())`.

```python
def build_quiz_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```

Chain (current, 3 steps):
`LoadJsonStep("load_cleaned_quiz")` →
`ApplyStep("enrich", ForEach(QuizMapper.from_cleaned_to_enriched), ImageDescriptionEnricher(...))` →
`WriteJsonStep("write_enriched_quiz")`.
The base-map (`ForEach`) and enrichment (`ImageDescriptionEnricher`) are
applied in sequence by the same `ApplyStep`, eliminating the previous
separate `MapStep` + `EnrichDataStep`.

**Decisions:**

- `source` derived from `prep.sources[0]` (`"quiz"`, single source): no
  explicit `source` parameter, unlike the knowledge flow (per-source on
  `cds`/`cap`).
- **`build_quiz_enrichment_flow` raises `ValueError`** if
  `prep.output_layer is None`, mirroring the guard in
  `build_knowledge_enrichment_flow`.
- **`build_quiz_preparation_flow` (single `cleaned`→`enriched` flow) no
  longer exists**: replaced in SP09 by two flows (`build_quiz_cleaning_flow`,
  `build_quiz_enrichment_flow`), mirroring the knowledge topology
  (`parsed`→`cleaned`→`enriched`). The quiz bank now has its own explicit
  `parsed` layer (PDF parser output) distinct from `cleaned`.
- **SP04 refactor**: `EnrichQuizStep`/`QuizEnrichmentService` already removed in
  the previous refactor; `FlattenQuizStep`/`MapToEmbeddableStep` removed in SP04
  — replaced by services (`FlattenQuiz`/`ToEmbeddableQuiz`) wrapped by
  `ApplyStep`. The enrichment flow is now 3 steps (down from 4), combining
  base-map and enrichment in a single `ApplyStep`.
- **Generic `DbStoreStep` (truncate full-reload)** for indexing: the quiz
  has a single source, so `TRUNCATE TABLE quiz_questions` is correct and
  safe. Intentional divergence from `StoreChunksStep` for knowledge
  (delete-by-source), which is needed because knowledge sources (`cds`, `cap`)
  coexist in the same table.
- **Generic `EmbedStep` reused** (with `items_key=EMBEDDABLE_QUIZ`): the quiz
  has no `embed_repealed` filter, so the generic step is sufficient without
  a dedicated `EmbedQuizStep`.
- `QuizQuestionStoreRepository` satisfies `StoreRepository` Protocol
  structurally: `DbStoreStep` can receive it without changes.

**Idempotency (preparation):** file-level via the generic runner
`run_preparation` — skip if the output of the respective layer exists, unless
`force`. **Known and accepted limitation**: adding a new enricher requires
regenerating the entire `enriched` file (re-running vision too, the most
expensive call) via `force` or by deleting the output; a per-enricher
checkpoint (incremental merge) is deferred until truly needed.

**Pending CLI cutover:** none of the quiz preparation/indexing flows are
yet wired to a dedicated CLI entry point. `reset_quiz_db.py` remains
available.

### `repositories/db/` — `QuizQuestionStoreRepository`

- Extends `BulkInsertStoreRepository[QuizQuestion]` (shared base with
  `KnowledgeChunkStoreRepository`, see
  [knowledge_pipelines.md](knowledge_pipelines.md#repositoriesdb_bulk_insert_store_repositorypy--bulkinsertstorerepositoryt-base-condivisa-estratta-dal-refactor)
  for detail). Full-reload write repository, injected with a generic
  `PostgresClient` and the table name (`config.quiz_questions_table`).
  Lives in `repositories/db/` (Postgres storage), re-exported from
  `repositories/__init__.py`.
- `truncate()` + `bulk_insert(questions: list[QuizQuestion])` — both
  inherited from the base; columns `number, question_id, topic, text,
  correct_answer, image_filename, embedding`, mapped row by row by
  `_to_db_row` (`@staticmethod` override). No additional own methods
  (unlike knowledge, the quiz has a single source → no `delete_source`).
