# Package `src/guidami_ai_patente_ingestor/`

Documents exclusively the package `src/guidami_ai_patente_ingestor/`.

Active batch pipelines/flows:

- **normative corpus — preparation** (flowstep flow per-source): two linear
  flows, `build_knowledge_cleaning_flow` (`parsed` → `cleaned`) and
  `build_knowledge_enrichment_flow` (`cleaned` → `enriched`, with
  `ArticleContextualizerAgent`), executed via the generic runner
  `run_preparation`. One run per source. Replaces the previous
  `DataPreparationPipeline` (removed). Wired via `uv run ingest prepare
  knowledge --source <cds|cap>` (SP07).
- **normative corpus — indexing** (flowstep flow per-source): reads `enriched`
  for ONE source → chunk → embed → `knowledge_chunks` (delete-by-source +
  insert). Wired via `uv run ingest index knowledge --source <cds|cap>` (SP07).
- **quiz bank — preparation** (two flowstep flows, restructured in SP09
  mirroring the knowledge topology): `build_quiz_cleaning_flow` (`parsed` → `cleaned`,
  flatten+dedup via `ApplyStep(FlattenQuiz())`) and `build_quiz_enrichment_flow`
  (`cleaned` → `enriched`, base-map + `ImageDescriptionEnricher` in a single
  `ApplyStep`), both via the same runner `run_preparation`. In SP04
  the flatten+dedup logic is moved from flowstep step to service UseCase
  (`FlattenQuiz`, `ToEmbeddableQuiz`); `EnrichDataStep`/`MapStep`/
  `EnricherProtocol` removed; all flows use `ApplyStep+ForEach`.
  Wired via `uv run ingest prepare quiz` (SP07).
- **quiz bank — indexing** (flowstep flow): reads `enriched` quiz →
  `ApplyStep(ToEmbeddableQuiz())` (dedup + mapping enriched→embeddable, flat model)
  → embed → `ApplyStep(ForEach(QuizMapper.from_embeddable_to_quiz_question))`
  → `quiz_questions` (truncate full-reload). Wired via `uv run ingest index
  quiz` (SP07).

Depends on `commons` (models, entities, `BaseAgent`, `EmbeddingClient`, `PostgresClient`,
shared configs).

## Layout

```
src/guidami_ai_patente_ingestor/
  agents/
    __init__.py                        # re-exports ArticleContextualizerAgent, RoadSignDescriberAgent
    article_contextualizer_agent.py    # ArticleContextualizerAgent(BaseAgent[ArticleContextualizerRequest, ArticleContextualizerResponse])
    road_sign_describer_agent.py       # RoadSignDescriberAgent(BaseAgent[RoadSignDescriberRequest, RoadSignDescriberResponse])
    dto/
      __init__.py
      article_contextualizer/
        __init__.py
        request.py           # ArticleContextualizerRequest(BaseModel) — title, text, paragraphs: str
        response.py          # ArticleContextualizerResponse(BaseModel) — contexts: dict[int, str]
      road_sign_describer/
        __init__.py
        request.py           # RoadSignDescriberRequest(BaseModel) — topic, text
        response.py          # RoadSignDescriberResponse(BaseModel) — name, description
  mappers/
    __init__.py                           # re-exports ArticleMapper, QuizMapper
    article_mapper.py                     # ArticleMapper — 1:1 transformations for the knowledge pipeline (3 methods):
                                          #   from_parsed_to_enriched(ParsedArticleModel) -> EnrichedArticleModel
                                          #   from_enriched_to_embeddable_chunk(model, source, comma_index, raw_text) -> EmbeddableChunkModel
                                          #   from_embeddable_chunk_to_knowledge_chunk(EmbeddableChunkModel) -> KnowledgeChunk
    quiz_mapper.py                        # QuizMapper — static backbone for all 1:1 transitions:
                                          #   from_parsed_to_cleaned, from_cleaned_to_enriched,
                                          #   from_enriched_to_embeddable(item) (1 arg, renamed in SP03),
                                          #   from_embeddable_to_quiz_question
    agents/
      __init__.py                         # re-exports ArticleContextualizerMapper, RoadSignDescriberMapper
      article_contextualizer_mapper.py    # ArticleContextualizerMapper — domain↔DTO:
                                          #   from_enriched_article_to_request(EnrichedArticleModel) -> ArticleContextualizerRequest
                                          #   from_response_to_enriched_article(EnrichedArticleModel, ArticleContextualizerResponse) -> EnrichedArticleModel
      road_sign_describer_mapper.py       # RoadSignDescriberMapper — domain↔DTO:
                                          #   from_enriched_quiz_to_request(EnrichedQuizModel) -> RoadSignDescriberRequest
                                          #   from_response_to_enriched_quiz(EnrichedQuizModel, RoadSignDescriberResponse) -> EnrichedQuizModel
  repositories/
    __init__.py                              # re-exports all 6 repositories (unchanged public surface)
    db/
      __init__.py                            # re-exports KnowledgeChunkStoreRepository, QuizQuestionStoreRepository
      knowledge_chunk_store_repository.py    # KnowledgeChunkStoreRepository
                                             #   delete_source(source) + truncate() + bulk_insert(chunks)
      quiz_question_store_repository.py      # QuizQuestionStoreRepository (truncate + bulk insert)
    json/
      __init__.py                            # re-exports ArticleRepository, EnrichedArticleRepository, QuizBankRepository, EnrichedQuizBankRepository
      _json_repository.py                    # JsonRepository[T: BaseModel] — generic base (private to the sub-package)
      article_repository.py                  # ArticleRepository(JsonRepository[Article])
      enriched_article_repository.py         # EnrichedArticleRepository(JsonRepository[EnrichedArticle])
      quiz_bank_repository.py                # QuizBankRepository(JsonRepository[ParsedQuizModel])
      enriched_quiz_bank_repository.py       # EnrichedQuizBankRepository(JsonRepository[EnrichedQuizModel])
                                             #   (no longer used directly by preparation flows, which use
                                             #   LoadJsonStep/WriteJsonStep with explicit model_class)
  services/
    __init__.py                   # re-exports LayerResolver
    layer_resolver.py             # LayerResolver(layers, sources).path(layer, source) -> Path
    knowledge/
      article_cleaner.py          # ArticleCleaner(UseCase[ParsedArticleModel, ParsedArticleModel])
                                  #   .execute(article) -> ParsedArticleModel
      article_chunker.py          # ArticleChunker(UseCase[EnrichedArticleModel, list[EmbeddableChunkModel]])
                                  #   source injected in constructor; .execute(article) -> list[EmbeddableChunkModel]
                                  #   uses ArticleMapper.from_enriched_to_embeddable_chunk
      enrichers/
        __init__.py               # re-exports ContextEnricher
        context_enricher.py       # ContextEnricher — per-clause LLM contextualization via ArticleContextualizerAgent;
                                  #   satisfies EnricherProtocol[EnrichedArticleModel, EnrichedArticleModel];
                                  #   isolated failure → contexts={} + warning, no abort
    quiz/
      __init__.py                          # re-exports ImageDescriptionEnricher
      flatten_quiz.py                      # FlattenQuiz(UseCase[list[ParsedQuizModel], list[CleanedQuizModel]])
                                           #   flatten+dedup parsed→cleaned (SP02; ex FlattenQuizStep)
      to_embeddable_quiz.py                # ToEmbeddableQuiz(UseCase[list[EnrichedQuizModel], list[EmbeddableQuizModel]])
                                           #   dedup+mapping enriched→embeddable (SP03; ex MapToEmbeddableStep)
                                           # quiz_enrichment_service.py REMOVED (QuizEnrichmentService,
                                           #   replaced by ApplyStep+UseCase in SP04)
      enrichers/
        __init__.py                        # re-exports ImageDescriptionEnricher
                                           # quiz_enricher.py REMOVED (Protocol QuizEnricher, redundant alias)
        image_description_enricher.py      # ImageDescriptionEnricher(UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]])
                                           #   vision LLM, dedup on (image, topic, text); execute() ex enrich()
  models/
    knowledge/
      __init__.py                  # re-exports ParsedArticleModel, EnrichedArticleModel, EmbeddableChunkModel
      parsed_article.py            # ParsedArticleModel — parsed/cleaned JSON (number, title, text,
                                   #   paragraphs, url, scraped_at, repealed)
      enriched_article.py          # EnrichedArticleModel — cleaned article + contexts: dict[int, str] per clause
      embeddable_chunk.py          # EmbeddableChunkModel — intermediate chunk DTO + embedded_text property
                                   #   (article_title\ncontext\nchunk_text); embedding: list[float]|None
    quiz/
      __init__.py                  # re-exports all quiz models
      parsed_quiz.py               # ParsedQuizModel, ParsedQuizItemModel — parsed layer, nested
                                   #   (direct output of the PDF parser; SP09)
      cleaned_quiz.py               # CleanedQuizModel — cleaned layer, flat, self-contained (SP09)
      enriched_quiz.py             # EnrichedQuizModel — enriched layer, flat
                                   #   (adds image_description: str | None)
      embeddable_quiz.py           # EmbeddableQuizModel — intermediate flat DTO with embedded_text
      image_description.py        # ImageDescription(BaseModel, frozen=True) — name: str, description: str
  orchestrators/
    __init__.py                    # re-exports build_knowledge_indexing_flow,
                                   #   build_knowledge_cleaning_flow/build_knowledge_enrichment_flow,
                                   #   build_quiz_indexing_flow, build_quiz_cleaning_flow/build_quiz_enrichment_flow,
                                   #   run_preparation
    context_keys.py                # FlowContext key constants — shared vocabulary (additive)
    knowledge_flows.py             # build_knowledge_indexing_flow(config, ..., source) -> Flow
                                   #   build_knowledge_cleaning_flow(config, layer_resolver, source) -> Flow
                                   #   build_knowledge_enrichment_flow(config, layer_resolver, source) -> Flow
    quiz_flows.py                  # build_quiz_indexing_flow(config, ...) -> Flow
                                   #   build_quiz_cleaning_flow(config, layer_resolver) -> Flow (SP09)
                                   #   build_quiz_enrichment_flow(config, layer_resolver) -> Flow
                                   #   (replaces the previous build_quiz_preparation_flow, removed)
    preparation_runner.py          # run_preparation(flow, out_path, force) -> None — per-source runner
    steps/
      __init__.py                  # package docstring
      generic/
        __init__.py                # re-exports DbStoreStep, EmbedStep, LoadJsonStep, StoreRepository, WriteJsonStep
                                   # MapStep REMOVED (SP04); EnrichDataStep REMOVED (SP04)
        protocols/
          store_repository.py      # Protocol StoreRepository (truncate + bulk_insert positional-only)
                                   # enricher_protocol.py REMOVED (SP04)
        embed_step.py              # EmbedStep(Step) — assigns embedding in place, rewrites items_key
        db_store_step.py           # DbStoreStep(Step) — full-reload sink (truncate → bulk_insert)
        load_json_step.py          # LoadJsonStep(Step) — load(layer, source) → put(output_key, list[model_class])
        write_json_step.py         # WriteJsonStep(Step) — get(input_key) → write(layer, source)
      knowledge/                   # domain-specific steps only (all indexing)
        __init__.py
        chunk_articles_step.py         # ChunkArticlesStep — ENRICHED_ARTICLES → EMBEDDABLE_CHUNKS (indexing)
        embed_chunks_step.py           # EmbedChunksStep — embed with repealed filter (indexing)
        store_chunks_step.py           # StoreChunksStep — delete_source + bulk_insert (indexing)
                                       # ContextualizeStep REMOVED; MapStep/EnrichDataStep REMOVED (SP04)
                                       # preparation uses ApplyStep(ForEach+ContextEnricher)
      quiz/                        # empty package (SP04)
        __init__.py                    # __all__ = []
                                       # FlattenQuizStep REMOVED → FlattenQuiz in services/quiz/ (SP02)
                                       # MapToEmbeddableStep REMOVED → ToEmbeddableQuiz in services/quiz/ (SP03)
  configs/
    ingestor_config.py            # IngestorConfig (BaseSettings, frozen)
    source_config.py              # SourceConfig(dir, file) — frozen BaseModel
    pipeline_layer_config.py      # PipelineLayerConfig(input_layer, output_layer?, sources: list[str]) — frozen
  cli.py                           # single entry point `ingest` (SP07)
                                   #   ingest prepare knowledge --source <cds|cap> [--force]
                                   #   ingest prepare quiz [--force]
                                   #   ingest index knowledge --source <cds|cap>
                                   #   ingest index quiz
                                   #   ingest reset knowledge
                                   #   ingest reset quiz
                                   # main.py, reset_db.py, reset_quiz_db.py removed (SP07)
                                   # quiz_main.py, prepare_knowledge_main.py already removed earlier (legacy)

configs/                            # project root (not under src/)
  ingestor_config.yaml              # non-secret config, committed (layers/sources/pipeline selectors)
  agents/
    article_contextualizer.yaml     # AgentDefinition for ArticleContextualizer
    road_sign_describer.yaml        # AgentDefinition for RoadSignDescriber (vision)

.env.example                        # documents only the secret env vars
                                     # (POSTGRES__USER, POSTGRES__PASSWORD)
```

## Data directory convention

Pipeline/flow with four on-disk layers, resolved by `LayerResolver`. From SP09
both the normative corpus and the quiz bank follow the **same three-stage topology**
(`parsed` → `cleaned` → `enriched`):

- `data/raw/<source>/` — raw HTML from the scraper (not touched by this
  package).
- `data/parsed/<source>/...json` — raw JSON produced by the scraper/parser,
  markup/structure still raw. Input of the `build_knowledge_cleaning_flow`
  (corpus) or `build_quiz_cleaning_flow` (quiz, layer introduced in SP09: before
  this the quiz started directly from `cleaned`).
- `data/cleaned/<source>/...json` — (`cleaned` layer). For the normative
  corpus: output of `build_knowledge_cleaning_flow` (`WriteJsonStep` sink),
  input of `build_knowledge_enrichment_flow` (`LoadJsonStep`). The `"cleaned"`
  layer is a private constant in `knowledge_flows.py`/`quiz_flows.py`
  (`_CLEANED_LAYER`), not a field of `PipelineLayerConfig`. For the quiz bank
  (SP09): output of `build_quiz_cleaning_flow` (flatten+dedup by `FlattenQuiz`
  UseCase, one flat row per sub-question), input of `build_quiz_enrichment_flow`.
- `data/enriched/<source>/...json` — (`enriched` layer) output of the
  enrichment flow (corpus or quiz); input of the indexing flows. Self-contained:
  cleaned article + `contexts` per clause (corpus), or flat sub-question +
  `image_description` (quiz).

Path resolution: `LayerResolver.path(layer, source)` =
`layers[layer] / sources[source].dir / sources[source].file`.

## Detail by area

- [data_preparation.md](data_preparation.md) — preparation: normative corpus
  on two flowstep flows per-source (`build_knowledge_cleaning_flow`,
  `build_knowledge_enrichment_flow`, `run_preparation`, `ApplyStep`+`ForEach` +
  `ContextEnricher` domain-specific, `ArticleMapper`); quiz bank on two analogous
  flows (`build_quiz_cleaning_flow` with `ApplyStep(FlattenQuiz())`,
  `build_quiz_enrichment_flow` with `ApplyStep(ForEach+ImageDescriptionEnricher)`).
  Plus `ArticleContextualizerAgent`, `RoadSignDescriberAgent`,
  `EnrichedArticleRepository`, `EnrichedQuizBankRepository`.
- [knowledge_pipelines.md](knowledge_pipelines.md) — normative corpus (CdS + CAP):
  model chain `ParsedArticleModel`/`EnrichedArticleModel`/`EmbeddableChunkModel`
  (one model per layer, `EmbeddableChunkModel` has `embedded_text`),
  consolidated `ArticleMapper`, `ArticleCleaner`, `ArticleChunker`,
  per-source flow (`build_knowledge_indexing_flow`, 5 steps with `ApplyStep`
  between `EmbedChunksStep` and `StoreChunksStep`), `KnowledgeChunkStoreRepository`
  (with `delete_source`).
- [quiz_pipelines.md](quiz_pipelines.md) — quiz bank: model chain
  `ParsedQuizModel`/`CleanedQuizModel`/`EnrichedQuizModel`/`EmbeddableQuizModel`
  (one model per layer, SP09), consolidated `QuizMapper` (method
  `from_enriched_to_embeddable` renamed in SP03, 1 argument),
  `QuizQuestionStoreRepository`; service `FlattenQuiz` and `ToEmbeddableQuiz`
  (UseCase, ex flowstep step, SP02/SP03); quiz indexing flow with
  `ApplyStep(ToEmbeddableQuiz())` and `ApplyStep(ForEach(...))` (SP04);
  quiz preparation flows: `ApplyStep(FlattenQuiz())` (cleaning) +
  `ApplyStep(ForEach+ImageDescriptionEnricher)` (enrichment, 3 steps, SP04);
  `ImageDescriptionEnricher` now implements `UseCase` (ex `EnricherProtocol`).
- [config_and_entrypoints.md](config_and_entrypoints.md) — `IngestorConfig`, `LayerResolver`,
  two-level config pattern, single entry point `cli.py` (SP07, subcommands `ingest prepare
  / index / reset`), logging conventions.
- [generic_steps.md](generic_steps.md) — generic ingestor steps in
  `orchestrators/steps/generic/`: `EmbedStep`, `DbStoreStep`, `LoadJsonStep`,
  `WriteJsonStep`, `StoreRepository` Protocol; `context_keys` vocabulary;
  `MapStep`/`EnrichDataStep`/`EnricherProtocol` removed in SP04. For the
  underlying framework see [flowstep module](../../flowstep/_index.md).
- [tests.md](tests.md) — complete list of tests with files and verified behaviours.
