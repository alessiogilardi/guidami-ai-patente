# Ingestor — Data preparation

See [config_and_entrypoints.md](config_and_entrypoints.md) for `IngestorConfig`,
`LayerResolver` and the CLI entry points, [generic_steps.md](generic_steps.md)
for shared `context_keys` and building blocks (`ApplyStep`, `LoadJsonStep`,
`WriteJsonStep`, `EmbedStep`, `DbStoreStep`), [quiz_pipelines.md](quiz_pipelines.md)
for the quiz model chain and the detail of `QuizMapper`/`services/quiz/`.

Two areas of offline, idempotent preparation that precede the indexing
pipelines/flows. They produce the `enriched` artefacts that indexing reads from.

- **normative corpus (knowledge)**: rebuilt in SP05 as **two linear flowstep
  Flows per-source** (`clean`, `enrich`) + generic runner `run_preparation`.
  Replaces the previous `DataPreparationPipeline` (removed).
- **quiz bank**: built **from scratch** in SP06 as a single Flow
  (`cleaned` → `enriched`), then **restructured in SP09** to mirror the
  knowledge topology: today there are **two linear flowstep Flows**
  (`build_quiz_cleaning_flow`: `parsed` → `cleaned`, with flatten+dedup via
  `ApplyStep(FlattenQuiz())`; `build_quiz_enrichment_flow`: `cleaned` →
  `enriched`), both via the generic runner `run_preparation`. In SP04
  all steps use `ApplyStep`+`ForEach`/`UseCase` instead of `MapStep`/
  `EnrichDataStep` (removed).

## Topology

```
parsed ──[knowledge_cleaning flow: Load→Apply(ForEach(clean))→Write]───▶ cleaned ──[knowledge_enrichment flow: Load→Apply(ForEach(map)+ContextEnricher)→Write]──▶ enriched ──[knowledge_indexing flow]──▶ DB
parsed ──[quiz_cleaning flow: Load→Apply(FlattenQuiz)→Write]───────────▶ cleaned ──[quiz_enrichment flow: Load→Apply(ForEach(base-map)+ImageDescEnricher+NormRefEnricher)→Write]──▶ enriched ──[quiz_indexing flow]────▶ DB
```

From SP09 the quiz bank has the **same three-layer topology** as the knowledge
(`parsed` → `cleaned` → `enriched`), no longer a single input layer: the `parsed`
layer (direct output of the PDF parser, nested structure) is distinct from the
`cleaned` layer (flat, one row per sub-question, produced by the flatten+dedup
of the `FlattenQuiz` UseCase, wrapped by `ApplyStep`).

LLM enrichment (expensive, offline) is separate from indexing (re-runnable at
zero cost on `enriched`). Knowledge and quiz preparation are idempotent at
**file level**: they skip if the output of the respective layer already exists;
a `force` flag (applied by the caller via `run_preparation`) forces regeneration.
For the quiz, this is a known and accepted limitation: adding a new enricher
requires regenerating the entire file (including vision calls, the most expensive
ones) — a per-enricher checkpoint is deferred until truly needed.

## Knowledge preparation (SP05) — two per-source Flows + generic runner

**Per-source** pattern (consistent with SP03/04, already documented): one run per
source, `source` injected into `Load*`/`Write*` steps at factory time. **No**
`SOURCE` key in `FlowContext` and no loop over sources inside the flow/runner —
the loop, if needed, is the caller's responsibility (CLI, expected in SP07).

### `orchestrators/knowledge_flows.py` — two flow factories

```python
def build_knowledge_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    source: str,
    validate: bool = False,
) -> Flow
```
Chain: `LoadJsonStep("load_parsed_articles", model_class=ParsedArticleModel)` →
`ApplyStep("clean_articles", ForEach(ArticleCleaner()))` →
`WriteJsonStep("write_cleaned", model_class=ParsedArticleModel)`. Layers: input =
`config.knowledge_preparation.input_layer` (`"parsed"`), output = module-private
constant `_CLEANED_LAYER = "cleaned"`. The previous dedicated steps
`LoadParsedArticlesStep`/`CleanArticlesStep`/`WriteCleanedStep` no longer exist:
replaced by generic `LoadJsonStep`/`ApplyStep`/`WriteJsonStep` (the `MapStep`
used previously was removed in SP04 and replaced by `ApplyStep +
ForEach`).

```python
def build_knowledge_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    source: str,
    validate: bool = False,
) -> Flow
```
Chain: `LoadJsonStep("load_cleaned_articles", model_class=ParsedArticleModel,
output_key=CLEANED_ARTICLES)` →
`ApplyStep("enrich", ForEach(ArticleMapper.from_parsed_to_enriched), ContextEnricher(agent))` →
`WriteJsonStep("write_enriched", model_class=EnrichedArticleModel)`.
Layers: input = `_CLEANED_LAYER`, output = `config.knowledge_preparation.output_layer`
(`"enriched"`); raises `ValueError` if `output_layer` is not configured. Instantiates
the agent via `ArticleContextualizerAgent.from_yaml("article_contextualizer",
config.agents_dir)` and injects it into `ContextEnricher`. In SP04 the previous
`MapStep + EnrichDataStep` (two separate steps) was unified into a single
`ApplyStep` with chain `[ForEach(ArticleMapper.from_parsed_to_enriched),
ContextEnricher(agent)]`.

**Decisions:**
- Both factories validate `source` against
  `config.knowledge_preparation.sources` → `ValueError(f"Unknown source
  '{source}'. ...")` if not recognised (same pattern as
  `build_knowledge_indexing_flow`, SP03).
- **No dependency on `embedding_client`/`postgres_client`**: the preparation
  stage does not embed or store, unlike indexing.
- **Intermediate layer `"cleaned"` as a module-private constant**, not a
  new field of `PipelineLayerConfig`: `knowledge_preparation` exposes only
  `input_layer`/`output_layer`, which is insufficient for a two-stage flow with
  an intermediate layer. This avoids adding a configuration field for a value
  that never varies today.
- The two flows are **linear and pure**: no idempotency/skip logic inside them —
  that lives in the runner.

### `orchestrators/preparation_runner.py` — `run_preparation`

```python
def run_preparation(flow: Flow, out_path: Path, force: bool) -> None:
    if out_path.exists() and not force:
        logger.info(f"{out_path} already exists, skipping")
        return
    flow.run()
```

- **Single-source helper**: encapsulates only the idempotent skip. No loop
  over sources, no injection of `source` into `FlowContext` (the `source`
  is already fixed in the steps at factory time).
- Receives `out_path` already resolved by the caller (typically via
  `LayerResolver.path(layer, source)`), so the same runner serves both
  the `clean` flow (out = `cleaned` layer) and the `enrich` flow (out =
  `enriched` layer), and for SP06 also the quiz preparation flow.
- **Shared with SP06** (quiz preparation flow, implemented): no
  knowledge-domain-specific logic inside.

### `orchestrators/steps/knowledge/` — knowledge preparation steps (updated)

All knowledge preparation steps are replaced by the generic
`LoadJsonStep`/`ApplyStep`/`WriteJsonStep` (see above) —
**no dedicated step class** remains in `steps/knowledge/` for preparation
(the package hosts only the three indexing steps: `ChunkArticlesStep`,
`EmbedChunksStep`, `StoreChunksStep`).

`ContextualizeStep` had already been removed. The previous separate `MapStep +
EnrichDataStep` were unified into a single `ApplyStep` in SP04.

### `services/knowledge/enrichers/context_enricher.py` — `ContextEnricher`

- Domain-specific enricher for per-clause LLM contextualization.
  Implements `UseCase[list[EnrichedArticleModel], list[EnrichedArticleModel]]`
  (previously satisfied `EnricherProtocol` structurally; now explicitly extends
  `UseCase`). Callable directly via `UseCase.__call__`.
- `execute(request: list[EnrichedArticleModel]) -> list[EnrichedArticleModel]`:
  calls `_contextualize(article)` for each item and returns new instances
  (immutability via `model_copy`).
- `_contextualize(article)`: delegates domain↔DTO translation to
  `ArticleContextualizerMapper`:
  1. `mapper.from_enriched_article_to_request(article)` → `ArticleContextualizerRequest`
  2. `agent.run_sync(request)` → `ArticleContextualizerResponse`
  3. `mapper.from_response_to_enriched_article(article, response)` → new `EnrichedArticleModel`
  On exception: `logger.warning` + returns the original article with
  `contexts={}`, without interrupting the batch (same failure tolerance as
  `ImageDescriptionEnricher`).
- Injects `ArticleContextualizerAgent` and `ArticleContextualizerMapper` in the constructor.
- Lives in `services/knowledge/enrichers/` — not in `orchestrators/steps/knowledge/`
  (no dependency on `flowstep`).

The generic `LoadJsonStep`/`WriteJsonStep` steps receive `layer_resolver`/
layer/`source` in the constructor and resolve the path via
`layer_resolver.path(layer, source)` — they never read `source` from `FlowContext`.

### `mappers/` — `ArticleMapper` (flat, no longer in a `knowledge/` sub-package)

- **`ArticleMapper`** now lives directly in `mappers/article_mapper.py`
  (no longer in `mappers/knowledge/`). Static, backbone of the 1:1
  transformations for the knowledge pipeline. Re-exported from `mappers/__init__.py`.
  Three methods:
  - `from_parsed_to_enriched(article: ParsedArticleModel) -> EnrichedArticleModel`:
    copies common fields, sets `contexts={}` (populated by `ContextEnricher`).
    Used via `ForEach(ArticleMapper.from_parsed_to_enriched)` in the enrichment flow.
  - `from_enriched_to_embeddable_chunk(model: EnrichedArticleModel, source: str,
    comma_index: int, raw_text: str) -> EmbeddableChunkModel`:
    builds an `EmbeddableChunkModel` for a single clause. Used by
    `ArticleChunker.execute`.
  - `from_embeddable_chunk_to_knowledge_chunk(model: EmbeddableChunkModel) -> KnowledgeChunk`:
    copies all fields (including `embedding`) into `KnowledgeChunk` (DB-only entity).
    Used via `ForEach(ArticleMapper.from_embeddable_chunk_to_knowledge_chunk)`
    in the indexing flow (`ApplyStep("map_to_chunk_entity")`).

### `mappers/agents/` — `ArticleContextualizerMapper`, `RoadSignDescriberMapper`, and `NormReferenceDescriberMapper`

Architectural principle: domain↔DTO translation is the mapper's responsibility,
not the enricher's or the agent's. They live in `mappers/agents/`, re-exported
from `mappers/agents/__init__.py`.

- **`ArticleContextualizerMapper`** (`mappers/agents/article_contextualizer_mapper.py`):
  - `from_enriched_article_to_request(article: EnrichedArticleModel) -> ArticleContextualizerRequest`:
    builds the agent input DTO from the article's fields
    (`title`, `text`, `paragraphs` formatted as string `"Comma {i}: ..."`)
  - `from_response_to_enriched_article(article: EnrichedArticleModel,
    response: ArticleContextualizerResponse) -> EnrichedArticleModel`:
    applies `model_copy(update={"contexts": response.contexts})` — immutable.

- **`RoadSignDescriberMapper`** (`mappers/agents/road_sign_describer_mapper.py`):
  - `from_enriched_quiz_to_request(item: EnrichedQuizModel) -> RoadSignDescriberRequest`:
    builds the agent input DTO (`topic`, `text`) from the quiz model.
  - `from_response_to_enriched_quiz(item: EnrichedQuizModel,
    response: RoadSignDescriberResponse) -> EnrichedQuizModel`:
    applies `model_copy(update={"image_description": f"{response.name}. {response.description}"})`.

- **`NormReferenceDescriberMapper`** (`mappers/agents/norm_reference_describer_mapper.py`):
  - `from_enriched_quiz_to_request(item: EnrichedQuizModel) -> NormReferenceDescriberRequest`:
    builds the agent input DTO (`topic`, `text`, `correct_answer`, `image_description`)
    from the quiz model (called after `ImageDescriptionEnricher`, so
    `image_description` may already be populated).
  - `from_response_to_enriched_quiz(item: EnrichedQuizModel,
    response: NormReferenceDescriberResponse) -> EnrichedQuizModel`:
    converts `NormReferenceDescriberResponse` → `QuizMetadata` at the boundary
    and applies `model_copy(update={"quiz_metadata": quiz_metadata})` — immutable.
    `NormReferenceDescriberResponse` and `QuizMetadata` are intentionally separate
    models (independent lifecycle: agent response vs. domain model).


### `context_keys.py` — keys added by SP05

**Additive** extension: `PARSED_ARTICLES = "parsed_articles"` (input of the
`clean` flow), `CLEANED_ARTICLES = "cleaned_articles"` (output of `clean` /
input of `enrich`). Reuses `ENRICHED_ARTICLES` (already defined by SP02/03, now
also produced by the `enrich` flow, not only consumed by indexing). No
`SOURCE` key: the source never passes through the context, it is fixed at the
factory. See [generic_steps.md](generic_steps.md) for the complete vocabulary.

### What has NOT (yet) changed

- No CLI entry point cutover: `prepare_knowledge_main.py` (with the old
  `DataPreparationPipeline`) had already been removed in SP03-bis; a new
  entry point invoking `build_knowledge_cleaning_flow` +
  `build_knowledge_enrichment_flow` + `run_preparation` **does not yet exist**
  — expected in SP07.
- No removal of remaining legacy pipelines: out of scope for SP05.

### Ingestor models for the quiz bank (one model per layer, renamed in SP09)

`ParsedQuizModel`/`ParsedQuizItemModel` (layer `parsed`, nested),
`CleanedQuizModel` (layer `cleaned`, flat) and `EnrichedQuizModel` (layer
`enriched`, flat) live in `guidami_ai_patente_ingestor/models/quiz/` — not
in `entities/` (they are non-persisted DTOs, not DB rows). `EnrichedQuizModel`
adds `image_description: str | None` and `quiz_metadata: QuizMetadata | None`
compared to `CleanedQuizModel`.
Full detail of the model chain and the consolidated `QuizMapper` in
[quiz_pipelines.md](quiz_pipelines.md).

### `repositories/enriched_article_repository.py` — `EnrichedArticleRepository`

- `load(path: Path) -> list[EnrichedArticle]` and
  `write(articles: list[EnrichedArticle], path: Path) -> None` — same pattern
  as `ArticleRepository`, but operates on the `EnrichedArticle` type (from `commons`).
- `write` creates missing directories and serialises with `ensure_ascii=False, indent=2`.

### `repositories/json/enriched_quiz_bank_repository.py` — `EnrichedQuizBankRepository`

- `load(path: Path) -> list[EnrichedQuizModel]` and
  `write(questions: list[EnrichedQuizModel], path: Path) -> None`.
- Same pattern as the existing JSON repositories (`JsonRepository[T]` generic).

### `agents/article_contextualizer_agent.py` — `ArticleContextualizerAgent`

Subclass of `BaseAgent[ArticleContextualizerRequest, ArticleContextualizerResponse]`
(`commons/agents/`). Replaces the previous `ArticleContextualizer` service (removed).

- The agent has **no** domain↔DTO translation logic: it receives and returns
  typed DTOs (`ArticleContextualizerRequest` / `ArticleContextualizerResponse`).
  Translation to/from `EnrichedArticleModel` is the responsibility of
  `ArticleContextualizerMapper` (see `mappers/agents/` section above).
- YAML prompt (`configs/agents/article_contextualizer.yaml`): variables
  `$title`, `$text`, `$paragraphs` (match the request fields).
- `from_yaml(name, agents_dir, output_type=None) -> Self`: factory that fixes
  `output_type=ArticleContextualizerResponse`.
- Structured output is handled by PydanticAI via `output_type`; no need to
  parse JSON manually or validate the raw response.

### `agents/road_sign_describer_agent.py` — `RoadSignDescriberAgent`

Subclass of `BaseAgent[RoadSignDescriberRequest, RoadSignDescriberResponse]`
(`commons/agents/`). Replaces the previous `RoadSignDescriber` service (removed).

- The agent receives `RoadSignDescriberRequest(topic, text)` as typed input;
  images are still passed separately via the `images` parameter (they do not
  enter the DTO). Translation to/from `EnrichedQuizModel` is the responsibility
  of `RoadSignDescriberMapper`.
- YAML prompt (`configs/agents/road_sign_describer.yaml`): variables `$topic`,
  `$text` (match the request fields).
- `from_yaml(name, agents_dir, output_type=None) -> Self`: factory that fixes
  `output_type=RoadSignDescriberResponse`.
- `RoadSignDescriberResponse(BaseModel, frozen=True)` — `name: str`, `description: str`
  — lives in `agents/dto/road_sign_describer/`. `ImageDescription` (previous DTO
  with the same fields in `models/quiz/`) is now replaced by this response DTO;
  the two models share the same structure but are conceptually distinct
  (agent response vs. domain model).

### `agents/norm_reference_describer_agent.py` — `NormReferenceDescriberAgent`

Subclass of `BaseAgent[NormReferenceDescriberRequest, NormReferenceDescriberResponse]`
(`commons/agents/`). Text-only (no images) — same structural pattern as
`RoadSignDescriberAgent` but no `images` parameter.

- Receives `NormReferenceDescriberRequest(topic, text, correct_answer,
  image_description)` as typed input. Translation to/from `EnrichedQuizModel`
  is the responsibility of `NormReferenceDescriberMapper`.
- YAML prompt (`configs/agents/norm_reference_describer.yaml`): model
  `openrouter/google/gemini-2.5-flash-lite`; variables `$topic`, `$text`,
  `$correct_answer`, `$image_description`.
- `from_yaml(name, agents_dir, output_type=None) -> Self`: factory that fixes
  `output_type=NormReferenceDescriberResponse`.
- `NormReferenceDescriberResponse(BaseModel, frozen=True)` — fields
  `core_concepts: list[str]`, `entities: list[str]`, `exact_keywords: list[str]`,
  `vector_search_queries: list[str]`, `rule_explanation: str` — lives in
  `agents/dto/norm_reference_describer/`.

## Quiz preparation — two Flows (SP09) + generic runner, enrichment refactored on generic building blocks

> **History**: introduced in SP06 as a single Flow (`cleaned` → `enriched`,
> greenfield — before SP06 no quiz preparation pipeline existed).
> **SP09** restructured it into two Flows mirroring the knowledge topology
> (`parsed` → `cleaned` → `enriched`), moving flatten+dedup into the new
> cleaning stage. The current refactor (see
> [quiz_pipelines.md](quiz_pipelines.md)) then replaced the quiz-specific
> enrichment steps/services (`EnrichQuizStep`, `QuizEnrichmentService`,
> `Protocol QuizEnricher` — all removed) with the generic building blocks
> `MapStep`/`EnrichDataStep` already used elsewhere.

Two flows in `orchestrators/quiz_flows.py`:

```python
def build_quiz_cleaning_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```
Chain: `LoadJsonStep("load_parsed_quiz", model_class=ParsedQuizModel)` →
`ApplyStep("flatten_quiz", FlattenQuiz())` →
`WriteJsonStep("write_cleaned_quiz", model_class=CleanedQuizModel)`. Keys
`PARSED_QUIZ` → `CLEANED_QUIZ`. SP04 moved the logic from `FlattenQuizStep`
(flowstep step) to `FlattenQuiz` (service UseCase).

```python
def build_quiz_enrichment_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    validate: bool = False,
) -> Flow
```
Chain: `LoadJsonStep("load_cleaned_quiz", model_class=CleanedQuizModel)` →
`ApplyStep("enrich", ForEach(QuizMapper.from_cleaned_to_enriched), ImageDescriptionEnricher(...), NormReferenceEnricher(...))` →
`WriteJsonStep("write_enriched_quiz", model_class=EnrichedQuizModel)`.
Keys `CLEANED_QUIZ` → `ENRICHED_QUIZ`. SP04 unified the previous
`MapStep + EnrichDataStep` into a single `ApplyStep`; `NormReferenceEnricher`
was added after `ImageDescriptionEnricher` — Open/Closed: zero changes to
existing steps or enrichers.

Both reuse **the same runner** as the knowledge
(`run_preparation(flow, out_path, force)`), invoked by the caller with
`out_path = layer_resolver.path(<layer>, "quiz")`.

Full detail of steps, Open/Closed enrichment
(`ApplyStep`/`ImageDescriptionEnricher` as `UseCase`) and factory decisions
in [quiz_pipelines.md](quiz_pipelines.md).

### Dedup and domain↔DTO translation (`ImageDescriptionEnricher`)

`ImageDescriptionEnricher` uses `RoadSignDescriberMapper` for domain↔DTO
translation, consistently with `ContextEnricher`. Flow for each sub-question
with an image:
1. `mapper.from_enriched_quiz_to_request(item)` → `RoadSignDescriberRequest`
2. `agent.run_sync(request, images=(image_path,))` → `RoadSignDescriberResponse`
3. `mapper.from_response_to_enriched_quiz(item, response)` → new `EnrichedQuizModel`

**Dedup key**: the description cache is indexed on
`(image, topic, text)` (3-field tuple). Compared to the previous version
(only `item.image`), the wider key ensures that the same image with different
topic/text receives distinct descriptions — reflecting the fact that the agent
prompt includes both `$topic` and `$text`.

Image not found on disk or agent error → `logger.warning` +
`image_description = None` (does not block enrichment of other questions).
The enricher implements `UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]]`
(previously satisfied `EnricherProtocol` structurally; now explicitly extends
`UseCase`, with `execute` instead of `enrich`).

### `NormReferenceEnricher` — text-only enricher for norm-reference metadata

`NormReferenceEnricher` uses `NormReferenceDescriberMapper` for domain↔DTO
translation, following the same pattern as `ContextEnricher` and
`ImageDescriptionEnricher`.

- **Dedup key**: `(topic, text, correct_answer, image_filename)` (4-field tuple)
  — one LLM call per unique sub-question. A sub-question may appear under
  multiple parent questions, so the key is wider than the image-dedup key to
  avoid conflating semantically distinct items.
- Called after `ImageDescriptionEnricher` in `ApplyStep("enrich")`, so
  `image_description` is already populated when the agent runs and can be
  included in the prompt via `NormReferenceDescriberRequest.image_description`.
- Agent error: `logger.warning` + `quiz_metadata` remains `None` (does not
  interrupt the batch — same failure tolerance as `ImageDescriptionEnricher`).

### What has NOT (yet) changed

- No dedicated CLI entry point for the quiz preparation/indexing flows:
  they are not yet wired to any script. `reset_quiz_db.py` remains
  available.
- `agents_dir`/agent yaml (`road_sign_describer.yaml`) unchanged.

## Tests

For tests of the knowledge preparation flow and the quiz preparation flow: steps,
mapper, flow factory, runner, enricher — see [tests.md](tests.md).

Tests remaining for shared components:

- `tests/guidami_ai_patente_ingestor/agents/test_article_contextualizer_agent.py` —
  via `agent.core_agent.override(model=TestModel(...))`: repealed article →
  returns `{}` without calling the model; prompt variables built correctly;
  `dict[int, str]` output via PydanticAI (no manual parsing).
- `tests/guidami_ai_patente_ingestor/agents/test_road_sign_describer_agent.py` —
  via `agent.core_agent.override(model=TestModel(...))`: `ImageDescription`
  output via PydanticAI; image path passed as `BinaryContent`.
- `tests/guidami_ai_patente_ingestor/repositories/test_enriched_article_repository.py` —
  `write`/`load` round-trip on `EnrichedArticleModel`.
- `tests/guidami_ai_patente_ingestor/repositories/test_enriched_quiz_bank_repository.py` —
  `write`/`load` round-trip on `EnrichedQuizModel`.
