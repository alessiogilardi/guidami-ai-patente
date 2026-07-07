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
        │ ApplyStep("flatten_quiz"):
        │   FlattenQuiz.execute(items) unnest + map (per item: QuizMapper.from_parsed_to_cleaned)
        │   + DeduplicateQuizItems.execute(items) dedup on triple
        ▼
cleaned (layer "cleaned", flat — one row per sub-question, self-contained)
   CleanedQuizModel
        │ ApplyStep("enrich"):
        │   ForEach(QuizMapper.from_cleaned_to_enriched) base-map flat→flat
        │   + ImageDescriptionEnricher.execute() populates image_description
        ▼
enriched (layer "enriched", flat)
   EnrichedQuizModel   (+ image_description, quiz_metadata)
        │ ApplyStep("map_to_embeddable"):
        │   DeduplicateQuizItems.execute(items) dedup on triple
        │   + ForEach(QuizMapper.from_enriched_to_embeddable) mapping flat→flat
        ▼
embeddable (flat)
   EmbeddableQuizModel   (image_description, quiz_metadata, embedding, embedded_text)
        │ embed (EmbedQuizMetadata) → embedding populated from quiz_metadata.embedded_text
        │   (items with quiz_metadata is None pass through, embedding stays None)
        │ to_entity → QuizMapper.from_embeddable_to_quiz_question (via ForEach)
        ▼
db row (flat)
   QuizQuestion   [entity, domain/entities/quiz]
```

`*Model` = non-persisted intermediate (`models/quiz/`); `QuizQuestion` (no
suffix) = DB row (`domain/entities/quiz/`).

**SP09 decision — flatten+dedup moved to preparation**: flatten (nested
→ flat) and dedup on sub-questions historically happened at the indexing stage.
SP09 moved them **upstream**, to the cleaning stage: from `cleaned` onwards
(`cleaned`, `enriched`, `embeddable`) the quiz bank is **already flat**,
one row per sub-question, self-contained (`question_id`/`topic`
denormalised on each row). The SP04 refactor then moved the flatten+dedup logic
**from a flowstep step** (`FlattenQuizStep`) to a **domain service**
(`FlattenQuiz`), and analogously the enriched→embeddable mapping logic
from `MapToEmbeddableStep` to a service `ToEmbeddableQuiz`, wrapped by
`ApplyStep` in the flow factories — no breakage to the flowstep interface.

**Later decision — dedup promoted to a shared `services/quiz/` class**:
`ToEmbeddableQuiz` (dedup + mapping in one `UseCase`) was removed and split
into two transforms chained in the same `ApplyStep("map_to_embeddable", ...)`:
dedup, then `ForEach(QuizMapper.from_enriched_to_embeddable)`. The dedup
transform first lived as `_dedup_enriched_quiz`, a private module-level
function in `orchestrators/quiz_flows.py` (single call site, no injected
config). Once `FlattenQuiz` gained the identical dedup rule as a *second* call
site (`build_quiz_cleaning_flow`, parsed→cleaned), the logic was promoted to
`DeduplicateQuizItems` in `services/quiz/` — a generic, Protocol-typed,
independently testable `UseCase` shared by both flow builders. See
"`DeduplicateQuizItems` — dedup promoted to a shared service" below for the
full rationale.

## Implemented decisions

### `models/quiz/` — one model per layer (renamed in SP09)

- `parsed_quiz.py` — `ParsedQuizModel`/`ParsedQuizItemModel`: parent question +
  sub-questions, nested structure as-is from the PDF parser JSON (layer
  `parsed`). Ex `QuizBankModel`/`QuizBankItemModel`.
- `cleaned_quiz.py` — `CleanedQuizModel`: one sub-question per row, flat,
  self-contained (`question_id`, `topic`, `number`, `text`, `correct_answer`,
  `image`). Output of `FlattenQuiz.execute` (layer `cleaned`).
- `enriched_quiz.py` — `EnrichedQuizModel`: same fields as `CleanedQuizModel`
  + `image_description: str | None` + `quiz_metadata: QuizMetadata | None`.
  Output of the enrichment flow (layer `enriched`). The base-map
  (`from_cleaned_to_enriched`) leaves both enrichment fields `None`; each
  enricher populates its own field via `model_copy`.
- `embeddable_quiz.py` — `EmbeddableQuizModel`: DTO for computing
  the embedding (indexing side), `embedded_text` property delegates to
  `self.quiz_metadata.embedded_text` (only ever read on items where
  `EmbedQuizMetadata` has already filtered `quiz_metadata is not None`).
  `QuizMetadata` itself satisfies `Embeddable` via duck typing, exposing
  `embedded_text = "\n".join(vector_search_queries)` — the semantic vector
  is computed from the LLM-generated metadata, not from the raw quiz text.
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
| `from_embeddable_to_quiz_question` | `(model: EmbeddableQuizModel) -> QuizQuestion` | drops `image_description`, carries `quiz_metadata` and `embedding` to entity |

**Decisions:**

- **Accepted SRP trade-off**: a single class for all transitions changes for
  more reasons (weaker than the "one class per transformation" rule), but makes
  the chain readable in a single place. Mitigation: static, small, pure methods.
- **`flatten+dedup` NOT in the mapper**: it is not a 1:1 mapping but
  a collection operation → lives in `FlattenQuiz` (unnest+map,
  parsed→cleaned, SP09/SP02) and `DeduplicateQuizItems` (dedup, shared by
  both the cleaning and indexing flows, `services/quiz/`), not in
  `QuizMapper`.
- **Enrichment and Open/Closed**: the base-map (`from_cleaned_to_enriched`)
  produces `EnrichedQuizModel` with enrichment fields set to `None`; enrichers
  populate them via `model_copy`. Adding an agent does not modify the base-map
  signature.

### `orchestrators/steps/quiz/` — package removed

The package existed as an empty placeholder (`__all__ = []`) after all its
step classes were removed, and has now been deleted entirely along with its
test directory. All the quiz domain logic previously hosted there has moved
to `services/quiz/` and to the flow builders themselves (see below); flow
builders use `ApplyStep` to wrap those services — including
`DeduplicateQuizItems`, now a `services/quiz/` class rather than a bare
orchestrator function (see "`DeduplicateQuizItems` — dedup promoted to a
shared service" below).

**Removed steps (SP04):**
- `FlattenQuizStep` → logic moved to `services/quiz/flatten_quiz.py::FlattenQuiz`
- `MapToEmbeddableStep` → logic moved to `services/quiz/to_embeddable_quiz.py::ToEmbeddableQuiz`
  (that service was itself later removed — see "`DeduplicateQuizItems` —
  dedup promoted to a shared service" below)
- `LoadQuizStep`, `EnrichQuizStep`, `WriteEnrichedQuizStep` — removed
  earlier, replaced by generic `LoadJsonStep`/`WriteJsonStep`.

### `services/quiz/` — domain services for the quiz bank

```
services/quiz/
├── __init__.py                          # re-exports DeduplicateQuizItems, EmbedQuizMetadata, ImageDescriptionEnricher
├── deduplicate_quiz_items.py            # DeduplicateQuizItems[T: _QuizItemLike](UseCase[list[T], list[T]])
├── flatten_quiz.py                      # FlattenQuiz(UseCase[list[ParsedQuizModel], list[CleanedQuizModel]])
├── embed_quiz_metadata.py               # EmbedQuizMetadata(UseCase[list[EmbeddableQuizModel], list[EmbeddableQuizModel]])
└── enrichers/
    ├── __init__.py                      # re-exports ImageDescriptionEnricher, NormReferenceEnricher
    ├── image_description_enricher.py    # ImageDescriptionEnricher(UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]])
    └── norm_reference_enricher.py       # NormReferenceEnricher(UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]])
```

**`FlattenQuiz`** (`services/quiz/flatten_quiz.py`, SP02): implements
`UseCase[list[ParsedQuizModel], list[CleanedQuizModel]]`. `execute`: unnests
`ParsedQuizModel.sub_questions` into `(sub_q, main_q)` pairs and maps each pair
via `QuizMapper.from_parsed_to_cleaned(sub_q, main_q)`. Responsibility:
nested→flat unnest + map only — it does **not** deduplicate; dedup is a
separate transform (`DeduplicateQuizItems`) chained after it in
`build_quiz_cleaning_flow`. Does not depend on flowstep.

**`DeduplicateQuizItems` — dedup promoted to a shared service**
(`services/quiz/deduplicate_quiz_items.py`): implements
`class DeduplicateQuizItems[T: _QuizItemLike](UseCase[list[T], list[T]])`,
generic over a structural `Protocol` (`_QuizItemLike`: `text: str`,
`correct_answer: bool`, `image: str | None`, `number: str`) satisfied by both
`CleanedQuizModel` and `EnrichedQuizModel` with no subclassing or model
changes. `execute` deduplicates via `deduplicate()` (from `commons.utils`)
keyed on `(text.strip(), correct_answer, image)`, logging
`"skipping duplicate quiz item %s"` for each discarded item.

Replaces the SP03 `ToEmbeddableQuiz` service (dedup + enriched→embeddable
mapping in one `UseCase`, since removed) and the interim
`_dedup_enriched_quiz` — a private, module-level function that briefly lived
in `orchestrators/quiz_flows.py`. Both `build_quiz_indexing_flow` and
`build_quiz_cleaning_flow` chain `DeduplicateQuizItems()` as a separate
transform in their respective `ApplyStep`s:

- `build_quiz_cleaning_flow`'s `"flatten_quiz"` step: `FlattenQuiz()` (unnest +
  map) then `DeduplicateQuizItems()`.
- `build_quiz_indexing_flow`'s `"map_to_embeddable"` step: `DeduplicateQuizItems()`
  then `ForEach(QuizMapper.from_enriched_to_embeddable)`.

**Decision reversal — why a bare function first, then a class**: when the
dedup logic was extracted from `ToEmbeddableQuiz`, it had a single call site
(`build_quiz_indexing_flow`) and no injected config, so it was kept as
`_dedup_enriched_quiz`, a small pure module-level function in the orchestrator
— promoting it to a `services/` class felt like unnecessary ceremony for one
caller (mirroring how `ApplyStep` already accepts bare callables, not just
`UseCase`s, as transforms). That premise stopped holding once the exact same
dedup key `(text.strip(), correct_answer, image)` was found duplicated inside
`FlattenQuiz` — a second, independent call site in `build_quiz_cleaning_flow`.
With the logic genuinely shared across two flow builders, it was promoted to
`DeduplicateQuizItems`, a shared, independently unit-tested `services/quiz/`
class, generic over `_QuizItemLike` so it works for both flat quiz models
without duplication. Tested directly in
`tests/guidami_ai_patente_ingestor/services/quiz/test_deduplicate_quiz_items.py`
(see [tests.md](tests.md)).

**`ImageDescriptionEnricher`** now implements
`UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]]` (previously only
satisfied `EnricherProtocol` structurally). `execute` (ex `enrich`): same
logic as before — dedup on key `(image, topic, text)`, one vision call
per unique image, skip + warning on missing file or exception.

**`NormReferenceEnricher`** (`services/quiz/enrichers/norm_reference_enricher.py`):
implements `UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]]`. Text-only
(no vision calls); same structural pattern as `ImageDescriptionEnricher`.
`__init__(agent: NormReferenceDescriberAgent, mapper: NormReferenceDescriberMapper)`.
**Dedup key**: `(topic, text, correct_answer, image_filename)` (4-field tuple) —
one LLM call per unique sub-question. Called after `ImageDescriptionEnricher` in
`ApplyStep("enrich")`, so `image_description` is already available for the prompt.
Agent error → `logger.warning` + `quiz_metadata` remains `None` (does not interrupt
the batch — same failure tolerance as `ImageDescriptionEnricher`).

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
  RoadSignDescriberAgent, file_reader: FileReaderInterface)`. Implements `UseCase[list[EnrichedQuizModel],
  list[EnrichedQuizModel]]`; callable via `__call__` (no explicit `Protocol`
  inheritance). `execute(request: list[EnrichedQuizModel])
  -> list[EnrichedQuizModel]`:
  1. collects the **unique** `(image, topic, text)` keys via `deduplicate()` (from
     `commons.utils`) applied to a pre-filter generator `(q for q in questions if
     q.image is not None)`; `cast(str, q.image)` inside the loop resolves pyright's
     `str | None` narrowing; one vision call per unique context;
  2. for each unique image: `self._file_reader.exists_or_raise(image)` — if it
     raises `FileNotFoundError` or `PermissionError` (path-traversal, raised by
     `BaseFileSystemClient._resolve_path` — see
     [commons/overview.md](../commons/overview.md)) → `logger.warning` + skip,
     both handled the same way; if `describe()` raises → `logger.warning`
     (with `exc_info=True`) + skip; otherwise formats
     `f"{desc.name}. {desc.description}"`. The image name passed through is a
     bare relative path (no `images_dir / image` join) — resolved by the
     `file_reader`'s own base directory;
  3. returns new `EnrichedQuizModel` instances (via list comprehension with
     `RoadSignDescriberMapper.from_response_to_enriched_quiz`, no in-place
     mutation) with `image_description` populated for each sub-question whose
     key is in the dict (remains `None` if absent or skipped).

> **`EnrichDataStep[T]` and `EnricherProtocol` REMOVED in SP04**: they were the
> generic step (list-in/list-out enricher chain) and the related Protocol.
> Replaced by `ApplyStep` with direct callables (enrichers as `UseCase`
> callable via `__call__`). See [generic_steps.md](generic_steps.md).

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
`ApplyStep("map_to_embeddable", DeduplicateQuizItems(), ForEach(QuizMapper.from_enriched_to_embeddable))` →
`ApplyStep("embed_quiz", EmbedQuizMetadata(embedding_service))` →
`ApplyStep("map_to_quiz_entity", ForEach(QuizMapper.from_embeddable_to_quiz_question))` →
`DbStoreStep("store_quiz")`.
`map_to_embeddable` chains two transforms in the same `ApplyStep`: dedup on
`(text.strip(), correct_answer, image)` via `DeduplicateQuizItems()`
(`services/quiz/`, shared with `build_quiz_cleaning_flow` below), then 1:1
mapping via `ForEach(QuizMapper.from_enriched_to_embeddable)` — see
"`DeduplicateQuizItems` — dedup promoted to a shared service" above for the
history of this decision.

```python
def build_quiz_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```

Chain (3 steps):
`LoadJsonStep("load_parsed_quiz")` →
`ApplyStep("flatten_quiz", FlattenQuiz(), DeduplicateQuizItems())` →
`WriteJsonStep("write_cleaned_quiz")`.
Introduced in SP09; SP04 replaced `FlattenQuizStep` with
`ApplyStep(FlattenQuiz())`. `flatten_quiz` chains two transforms: unnest+map
parsed→cleaned via `FlattenQuiz()`, then dedup on
`(text.strip(), correct_answer, image)` via `DeduplicateQuizItems()` —
shared with `build_quiz_indexing_flow` above.

```python
def build_quiz_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```

Chain (current, 3 steps):
`LoadJsonStep("load_cleaned_quiz")` →
`ApplyStep("enrich", ForEach(QuizMapper.from_cleaned_to_enriched), ImageDescriptionEnricher(...), NormReferenceEnricher(...))` →
`WriteJsonStep("write_enriched_quiz")`.
The base-map (`ForEach`) and both enrichers are applied in sequence by the same
`ApplyStep`: `ImageDescriptionEnricher` runs first (populates `image_description`),
then `NormReferenceEnricher` (populates `quiz_metadata`, with `image_description`
already available for the prompt). Open/Closed: adding a further enricher
requires only inserting it into the `*transforms` list.

**Decisions:**

- **One `LocalFileSystemClient(config.quiz_images_dir)` shared by both image
  consumers**: `build_quiz_enrichment_flow` constructs
  `images_file_reader = LocalFileSystemClient(config.quiz_images_dir)` once and
  passes it both to `RoadSignDescriberAgent.from_yaml("road_sign_describer",
  agents_repository, images_file_reader)` and to
  `ImageDescriptionEnricher(describer, images_file_reader)` — mirroring the
  existing `LocalFileSystemClient(config.agents_dir)` reused for
  `agents_repository` in the same file.
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
  base-map and enrichment in a single `ApplyStep`. `ToEmbeddableQuiz` was
  itself later removed and its dedup responsibility promoted to the shared
  `DeduplicateQuizItems` service — see "`DeduplicateQuizItems` — dedup
  promoted to a shared service" above.
- **Generic `DbStoreStep` (truncate full-reload)** for indexing: the quiz
  has a single source, so `TRUNCATE TABLE quiz_questions` is correct and
  safe. Intentional divergence from `StoreChunksStep` for knowledge
  (delete-by-source), which is needed because knowledge sources (`cds`, `cap`)
  coexist in the same table.
- **`EmbedQuizMetadata` replaces the generic `EmbedStep`**
  (`services/quiz/embed_quiz_metadata.py`): `UseCase[list[EmbeddableQuizModel],
  list[EmbeddableQuizModel]]` injected with `EmbeddingService`. Filters items
  with `quiz_metadata is not None`, passes their `quiz_metadata` (an
  `Embeddable` via duck typing) to `EmbeddingService.execute`, and assigns the
  resulting vector to `item.embedding`. Items without metadata pass through
  unchanged (`embedding` stays `None` — no fallback to quiz text). If
  `EmbeddingService.execute` raises, the whole batch is skipped unchanged with
  a `logger.warning` — the flow does not stop. Wrapped by `ApplyStep`, same as
  every other quiz-domain service.
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
  correct_answer, image_filename, quiz_metadata, embedding`, mapped row by row by
  `_to_db_row` (`@staticmethod` override). `quiz_metadata` is serialised as
  `Jsonb(item.quiz_metadata.model_dump())` when present, `None` otherwise.
  No additional own methods (unlike knowledge, the quiz has a single source
  → no `delete_source`).
