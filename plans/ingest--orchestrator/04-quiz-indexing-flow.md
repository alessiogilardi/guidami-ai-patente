# SP04 — Flow quiz indexing

> **Status: ✅ COMPLETED** (2026-06-22). Flow quiz indexing implemented on flowstep
> (`orchestrators/quiz_flows.py` + `orchestrators/steps/quiz/`), `build_quiz_indexing_flow`
> re-exported. Reuses the generic steps `EmbedStep`/`DbStoreStep` (SP02). **Unit** tests green
> (integration e2e not implemented — see note below), architectural doc synchronized.

> ⚠️ **Code tweaked by SP04-bis (behavior-preserving refactor).** The models/mappers described in
> this plan were renamed/moved by [04-bis](https://www.google.com/search?q=04-bis-quiz-data-models.md):
> `EnrichedQuizMainQuestion`→`EnrichedQuizModel`, the two mappers `QuizQuestionMapper`/
> `EmbeddableQuizQuestionMapper`→ single `QuizMapper`, and the flatten+dedup migrated from the mapper to
> `MapToEmbeddableStep`. This plan documents the original state (2026-06-22); for current names,
> refer to SP04-bis. **Implemented parts touched by 04-bis**: `LoadEnrichedQuizStep`,
> `MapToEmbeddableStep`, `MapToQuizEntityStep`, the quiz mappers, and the quiz models.

> ℹ️ **Integration state note.** The e2e integration test (`quiz_questions` count 7098) declared in the
> criteria below was **not** implemented: `test_quiz_flows.py` is only unit (mock) and
> `data/enriched/quiz-patente-ab/` does not exist yet (it will be produced by SP06). The 7098 e2e verification is therefore
> postponed to the SP07 gate, after SP06 generates the enriched output.

## Single Purpose

Reconstruct the indexing of the quiz bank as a **Flow flowstep**: `enriched` quiz bank →
embeddable → embed → entity → `quiz_questions`. Replaces `QuizIndexingPipeline` + builder
(**already removed** in SP03, see note below).

## Depends on

SP02 (`EmbedStep`, `DbStoreStep`, `context_keys`) ✅ completed. SP03 ✅ completed — it is the
concrete **reference pattern** to mirror (`orchestrators/knowledge_flows.py` +
`orchestrators/steps/knowledge/`).

> ⚠️ **Post-SP03 Status (2026-06-22)**: the commit `🔥 Remove legacy indexing pipelines and orphan tests` has **already removed** `orchestrators/quiz_indexing/` (pipeline + builder), `quiz_main.py`, and the
> related orphan tests. Therefore:
> * there is no longer a `QuizIndexingPipeline` to "replace": SP04 builds the flow **from scratch**;
> * the logic to port is **not** in a pipeline, but lives entirely in the **mappers** already present
> (`mappers/quiz/quiz_question_mapper.py`, `mappers/quiz/embeddable_quiz_question_mapper.py`);
> * `reset_quiz_db.py` remains (reset entry point, out of scope for SP04, CLI cutover in SP07).
> 
> 

## Flow Mapping

`LoadEnrichedQuizStep` → `MapToEmbeddableStep` → `EmbedStep(items_key=EMBEDDABLE_QUIZ)` →
`MapToQuizEntityStep` → `DbStoreStep(items_key=QUIZ_ENTITIES)`

Keys chain: `ENRICHED_QUIZ` → `EMBEDDABLE_QUIZ` → (`EmbedStep` mutates in place on `EMBEDDABLE_QUIZ`)
→ `QUIZ_ENTITIES`. All three keys **already exist** in `orchestrators/context_keys.py` (SP02):
no changes to `context_keys.py`.

## Logic to Preserve (reference: existing mappers)

The end-to-end logic of the old pipeline is currently encapsulated in the already tested static mappers:

* loading: `EnrichedQuizBankRepository.load(path)` → `list[EnrichedQuizMainQuestion]`;
* `QuizQuestionMapper.from_enriched_quiz_main_questions_to_embeddable_quiz_questions(main)`
→ flattens the sub-questions **and deduplicates** (8 exact duplicates → 7098 rows). The dedup is
**inside the mapper** and happens **before** the embed → duplicates are not embedded;
* batch embed (→ generic `EmbedStep` + `EmbeddingService`, SP01/SP02);
* `EmbeddableQuizQuestionMapper.to_entity(eq)` for each item → `QuizQuestion`;
* full-reload store (→ `DbStoreStep`).

`EmbeddableQuizQuestion` satisfies the `Embedded` protocol (writable field `embedding` + property
`embedded_text = f"{topic} {text}"`, with image description if present) → the generic `EmbedStep`
is applicable without adaptations.

## Components

### New (thin domain steps) — `orchestrators/steps/quiz/`

> Placement consistent with SP03: domain steps live in `orchestrators/steps/<domain>/`,
> never in `services/` (the Step imports `commons.flowstep.Step`, it is orchestration glue).

* **`LoadEnrichedQuizStep`**: injected `EnrichedQuizBankRepository`, `LayerResolver`,
`input_layer: str`, **`source: str`**. `execute`: `path = layer_resolver.path(input_layer, source)`
→ `repository.load(path)` → `put(ENRICHED_QUIZ, list[EnrichedQuizMainQuestion])`.
`required=set()`, `produced={ENRICHED_QUIZ}`.
* ⚠️ **Inject `source`, do not hardcode `"quiz"**`: identical to `LoadEnrichedArticlesStep` (SP03),
which receives `source` in the constructor. The factory derives it from `config.quiz_indexing.sources[0]`
(= `"quiz"`). No magic string in the step.


* **`MapToEmbeddableStep`**: delegates `QuizQuestionMapper.from_enriched_quiz_main_questions_to_embeddable_quiz_questions`.
`required={ENRICHED_QUIZ}`, `produced={EMBEDDABLE_QUIZ}`.
* **`MapToQuizEntityStep`**: delegates `EmbeddableQuizQuestionMapper.to_entity` (list-comprehension on the items).
`required={EMBEDDABLE_QUIZ}`, `produced={QUIZ_ENTITIES}`.

The mappers already exist (`mappers/quiz/`, re-exported from `__init__.py`) → the steps are pure
adapters (`get → call static mapper → put`), no new service.

### Store: generic `DbStoreStep` (truncate), **not** a delete-by-source step

⚠️ **Intentional divergence from SP03**: the knowledge indexing uses the dedicated step `StoreChunksStep`
(delete-by-source + insert) because it is **per-source** and a `truncate` would delete the other sources.
The **quiz has only one source** (`"quiz"`), so the `truncate` of the entire `quiz_questions` table is
correct and SP04 uses the **generic `DbStoreStep**` of SP02 (truncate + bulk_insert), without creating
any `StoreQuizStep`. `QuizQuestionStoreRepository` structurally satisfies the `StoreRepository`
Protocol (it has `truncate()` + `bulk_insert(...)`). This is the only point where SP04 does **not** follow SP03, and
it is a deliberate choice.

### New (flow factory) — `orchestrators/quiz_flows.py`

Mirror of `knowledge_flows.py`. **Exact** signature (aligned with `build_knowledge_indexing_flow`,
but **without** the `source` parameter: the quiz source is unique and derived from config):

```python
def build_quiz_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    validate: bool = False,
) -> Flow:
    ...

```

Body:

* `indexing_config = config.quiz_indexing`; `source = indexing_config.sources[0]` (= `"quiz"`);
* `LoadEnrichedQuizStep("load_enriched_quiz", EnrichedQuizBankRepository(), layer_resolver, indexing_config.input_layer, source)`;
* `MapToEmbeddableStep("map_to_embeddable")`;
* `EmbedStep("embed_quiz", EmbeddingService(embedding_client, config.embedding_batch_size), context_keys.EMBEDDABLE_QUIZ)`;
* `MapToQuizEntityStep("map_to_quiz_entity")`;
* `DbStoreStep("store_quiz", QuizQuestionStoreRepository(postgres_client, config.quiz_questions_table), context_keys.QUIZ_ENTITIES)`;
* `FlowBuilder("quiz_indexing").add_step(...)....build(validate=validate)`.

> * **Every `Step` requires `name**` as the first positional argument (SP02 signature
> `Step.__init__(self, name)`): the factory must pass it.
> * `EmbedStep` has `required == produced == {EMBEDDABLE_QUIZ}` → with `validate=True` the
> `FlowValidator` emits the **benign WARNING** *"Produced key overwrites an already available
> key"* on `EMBEDDABLE_QUIZ` (severity WARNING, **not** ERROR → `build` succeeds). Expected, as in SP03.
> 
> 

### Modified

* `orchestrators/steps/quiz/__init__.py` (NEW package — re-export of the three domain steps).
* `orchestrators/__init__.py`: add the re-export of `build_quiz_indexing_flow` next to
`build_knowledge_indexing_flow` (**additive** intervention; SP03 already created the file).
* **No** modifications to `context_keys.py` (the 3 quiz keys are already there) nor to `quiz_main.py`
(no longer exists).

## TDD

* `MapToEmbeddableStep` / `MapToQuizEntityStep`: correct delegation to the mapper (fake/spy) and keys contract
(`{ENRICHED_QUIZ}→{EMBEDDABLE_QUIZ}`, `{EMBEDDABLE_QUIZ}→{QUIZ_ENTITIES}`).
* `LoadEnrichedQuizStep`: loads from the path resolved by `LayerResolver.path(input_layer, source)`
(fake repo + resolver); `required=set()`, `produced={ENRICHED_QUIZ}`; verifies that it uses the injected `source`
(not a hardcoded constant).
* Flow factory: `build(validate=True)` does not raise (only benign WARNING "overwrites" on
`EMBEDDABLE_QUIZ`); `required_input_keys == set()` (the load does not require external inputs);
produced/required keys correctly concatenated along the chain.
* Integration (`@pytest.mark.integration`): complete flow on Postgres → `quiz_questions` count ==
**7098** (known constant post-dedup; there is no longer an old pipeline to compare with).

## Done criteria

* Green quiz indexing flow (unit + integration), chain
`ENRICHED_QUIZ→EMBEDDABLE_QUIZ→QUIZ_ENTITIES`.
* Store via generic `DbStoreStep` (truncate full-reload), **no** delete-by-source step
(single source) — deliberate divergence from SP03 documented.
* `build_quiz_indexing_flow` re-exported from `orchestrators/__init__.py`; steps re-exported from
`orchestrators/steps/quiz/__init__.py`.
* Generic `EmbedStep`/`DbStoreStep` (SP02) reused without modifications; `context_keys.py` untouched.
* Green ruff/pyright. CLI cutover (single entry point) and removal of `reset_quiz_db.py` remain for SP07.