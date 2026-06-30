# Package `src/guidami_ai_patente_ingestor/`

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/implement/ingestor.md`,
`plans/architecture-quiz-bank.md` (pipeline quiz bank, refactor Postgres
condiviso), `plans/ingest--data-preparation.md`,
`plans/ingest--agent-and-prompt-provider.md`,
`plans/ingest--orchestrator/04-bis-quiz-data-models.md`,
`plans/ingest--orchestrator/04-tris-quiz-mappers.md`,
`plans/ingest--orchestrator/05-knowledge-preparation-flow.md`,
`plans/ingest--orchestrator/06-quiz-preparation-flow.md`,
`plans/ingest--orchestrator/07-cli-and-decommission.md`,
`plans/ingest--orchestrator/08-generic-map-to-step.md`,
`plans/ingest--orchestrator/09-quiz-flatten-at-preparation.md`.

Pipeline/flow batch attivi:

- **corpus normativo — preparation** (flow flowstep per-source): due flow
  lineari, `build_knowledge_cleaning_flow` (`parsed` → `cleaned`) e
  `build_knowledge_enrichment_flow` (`cleaned` → `enriched`, con
  `ArticleContextualizerAgent`), eseguiti via il runner generico
  `run_preparation`. Una run per source. Sostituisce la precedente
  `DataPreparationPipeline` (rimossa). Wired via `uv run ingest prepare
  knowledge --source <cds|cap>` (SP07).
- **corpus normativo — indexing** (flow flowstep per-source): legge `enriched`
  di UNA source → chunk → embed → `knowledge_chunks` (delete-by-source +
  insert). Wired via `uv run ingest index knowledge --source <cds|cap>` (SP07).
- **quiz bank — preparation** (due flow flowstep, ristrutturati in SP09 a
  specchio del knowledge): `build_quiz_cleaning_flow` (`parsed` → `cleaned`,
  flatten+dedup via `ApplyStep(FlattenQuiz())`) e `build_quiz_enrichment_flow`
  (`cleaned` → `enriched`, base-map + `ImageDescriptionEnricher` in unico
  `ApplyStep`), entrambi via lo stesso runner `run_preparation`. In SP04
  la logica di flatten+dedup è spostata da step flowstep a service UseCase
  (`FlattenQuiz`, `ToEmbeddableQuiz`); `EnrichDataStep`/`MapStep`/
  `EnricherProtocol` eliminati; tutti i flow usano `ApplyStep+ForEach`.
  Wired via `uv run ingest prepare quiz` (SP07).
- **quiz bank — indexing** (flow flowstep): legge `enriched` quiz →
  `ApplyStep(ToEmbeddableQuiz())` (dedup + mapping enriched→embeddable, modello
  flat) → embed → `ApplyStep(ForEach(QuizMapper.from_embeddable_to_quiz_question))`
  → `quiz_questions` (truncate full-reload). Wired via `uv run ingest index
  quiz` (SP07).

Dipende da `commons` (modelli, entità, `BaseAgent`, `EmbeddingClient`, `PostgresClient`,
config condivise).

## Layout

```
src/guidami_ai_patente_ingestor/
  agents/
    __init__.py                        # re-esporta ArticleContextualizerAgent, RoadSignDescriberAgent
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
    __init__.py                           # re-esporta ArticleMapper, QuizMapper
    article_mapper.py                     # ArticleMapper — trasformazioni 1:1 pipeline knowledge (3 metodi):
                                          #   from_parsed_to_enriched(ParsedArticleModel) -> EnrichedArticleModel
                                          #   from_enriched_to_embeddable_chunk(model, source, comma_index, raw_text) -> EmbeddableChunkModel
                                          #   from_embeddable_chunk_to_knowledge_chunk(EmbeddableChunkModel) -> KnowledgeChunk
    quiz_mapper.py                        # QuizMapper — backbone statico di tutte le transizioni 1:1:
                                          #   from_parsed_to_cleaned, from_cleaned_to_enriched,
                                          #   from_enriched_to_embeddable(item) (1 arg, rinominato SP03),
                                          #   from_embeddable_to_quiz_question
    agents/
      __init__.py                         # re-esporta ArticleContextualizerMapper, RoadSignDescriberMapper
      article_contextualizer_mapper.py    # ArticleContextualizerMapper — domain↔DTO:
                                          #   from_enriched_article_to_request(EnrichedArticleModel) -> ArticleContextualizerRequest
                                          #   from_response_to_enriched_article(EnrichedArticleModel, ArticleContextualizerResponse) -> EnrichedArticleModel
      road_sign_describer_mapper.py       # RoadSignDescriberMapper — domain↔DTO:
                                          #   from_enriched_quiz_to_request(EnrichedQuizModel) -> RoadSignDescriberRequest
                                          #   from_response_to_enriched_quiz(EnrichedQuizModel, RoadSignDescriberResponse) -> EnrichedQuizModel
  repositories/
    __init__.py                              # re-esporta tutti e 6 i repository (surface pubblica invariata)
    db/
      __init__.py                            # re-esporta KnowledgeChunkStoreRepository, QuizQuestionStoreRepository
      knowledge_chunk_store_repository.py    # KnowledgeChunkStoreRepository
                                             #   delete_source(source) + truncate() + bulk_insert(chunks)
      quiz_question_store_repository.py      # QuizQuestionStoreRepository (truncate + bulk insert)
    json/
      __init__.py                            # re-esporta ArticleRepository, EnrichedArticleRepository, QuizBankRepository, EnrichedQuizBankRepository
      _json_repository.py                    # JsonRepository[T: BaseModel] — base generica (privata al sub-package)
      article_repository.py                  # ArticleRepository(JsonRepository[Article])
      enriched_article_repository.py         # EnrichedArticleRepository(JsonRepository[EnrichedArticle])
      quiz_bank_repository.py                # QuizBankRepository(JsonRepository[ParsedQuizModel])
      enriched_quiz_bank_repository.py       # EnrichedQuizBankRepository(JsonRepository[EnrichedQuizModel])
                                             #   (non più usati direttamente dai flow di preparation, che usano
                                             #   LoadJsonStep/WriteJsonStep con model_class esplicito)
  services/
    __init__.py                   # re-esporta LayerResolver
    layer_resolver.py             # LayerResolver(layers, sources).path(layer, source) -> Path
    knowledge/
      article_cleaner.py          # ArticleCleaner(UseCase[ParsedArticleModel, ParsedArticleModel])
                                  #   .execute(article) -> ParsedArticleModel
      article_chunker.py          # ArticleChunker(UseCase[EnrichedArticleModel, list[EmbeddableChunkModel]])
                                  #   source iniettata nel costruttore; .execute(article) -> list[EmbeddableChunkModel]
                                  #   usa ArticleMapper.from_enriched_to_embeddable_chunk
      enrichers/
        __init__.py               # re-esporta ContextEnricher
        context_enricher.py       # ContextEnricher — per-comma LLM contextualization via ArticleContextualizerAgent;
                                  #   soddisfa EnricherProtocol[EnrichedArticleModel, EnrichedArticleModel];
                                  #   fallimento isolato → contexts={} + warning, non abort
    quiz/
      __init__.py                          # re-esporta ImageDescriptionEnricher
      flatten_quiz.py                      # FlattenQuiz(UseCase[list[ParsedQuizModel], list[CleanedQuizModel]])
                                           #   flatten+dedup parsed→cleaned (SP02; ex FlattenQuizStep)
      to_embeddable_quiz.py                # ToEmbeddableQuiz(UseCase[list[EnrichedQuizModel], list[EmbeddableQuizModel]])
                                           #   dedup+mapping enriched→embeddable (SP03; ex MapToEmbeddableStep)
                                           # quiz_enrichment_service.py RIMOSSO (QuizEnrichmentService,
                                           #   sostituito da ApplyStep+UseCase in SP04)
      enrichers/
        __init__.py                        # re-esporta ImageDescriptionEnricher
                                           # quiz_enricher.py RIMOSSO (Protocol QuizEnricher, alias ridondante)
        image_description_enricher.py      # ImageDescriptionEnricher(UseCase[list[EnrichedQuizModel], list[EnrichedQuizModel]])
                                           #   vision LLM, dedup su (image, topic, text); execute() ex enrich()
  models/
    knowledge/
      __init__.py                  # re-esporta ParsedArticleModel, EnrichedArticleModel, EmbeddableChunkModel
      parsed_article.py            # ParsedArticleModel — JSON parsed/cleaned (number, title, text,
                                   #   paragraphs, url, scraped_at, repealed)
      enriched_article.py          # EnrichedArticleModel — articolo pulito + contexts: dict[int, str] per commi
      embeddable_chunk.py          # EmbeddableChunkModel — DTO intermedio chunk + embedded_text property
                                   #   (article_title\ncontext\nchunk_text); embedding: list[float]|None
    quiz/
      __init__.py                  # re-esporta tutti i modelli quiz
      parsed_quiz.py               # ParsedQuizModel, ParsedQuizItemModel — layer parsed, nested
                                   #   (output diretto del parser PDF; SP09)
      cleaned_quiz.py               # CleanedQuizModel — layer cleaned, flat, autocontenuto (SP09)
      enriched_quiz.py             # EnrichedQuizModel — layer enriched, flat
                                   #   (aggiunge image_description: str | None)
      embeddable_quiz.py           # EmbeddableQuizModel — DTO intermedio flat con embedded_text
      image_description.py        # ImageDescription(BaseModel, frozen=True) — name: str, description: str
  orchestrators/
    __init__.py                    # re-esporta build_knowledge_indexing_flow,
                                   #   build_knowledge_cleaning_flow/build_knowledge_enrichment_flow,
                                   #   build_quiz_indexing_flow, build_quiz_cleaning_flow/build_quiz_enrichment_flow,
                                   #   run_preparation
    context_keys.py                # Costanti chiavi FlowContext — vocabolario condiviso (additivo)
    knowledge_flows.py             # build_knowledge_indexing_flow(config, ..., source) -> Flow
                                   #   build_knowledge_cleaning_flow(config, layer_resolver, source) -> Flow
                                   #   build_knowledge_enrichment_flow(config, layer_resolver, source) -> Flow
    quiz_flows.py                  # build_quiz_indexing_flow(config, ...) -> Flow
                                   #   build_quiz_cleaning_flow(config, layer_resolver) -> Flow (SP09)
                                   #   build_quiz_enrichment_flow(config, layer_resolver) -> Flow
                                   #   (sostituisce il precedente build_quiz_preparation_flow, rimosso)
    preparation_runner.py          # run_preparation(flow, out_path, force) -> None — runner per-source
    steps/
      __init__.py                  # docstring package
      generic/
        __init__.py                # re-esporta DbStoreStep, EmbedStep, LoadJsonStep, StoreRepository, WriteJsonStep
                                   # MapStep RIMOSSO (SP04); EnrichDataStep RIMOSSO (SP04)
        protocols/
          store_repository.py      # Protocol StoreRepository (truncate + bulk_insert positional-only)
                                   # enricher_protocol.py RIMOSSO (SP04)
        embed_step.py              # EmbedStep(Step) — assegna embedding in place, ri-scrive items_key
        db_store_step.py           # DbStoreStep(Step) — sink full-reload (truncate → bulk_insert)
        load_json_step.py          # LoadJsonStep(Step) — load(layer, source) → put(output_key, list[model_class])
        write_json_step.py         # WriteJsonStep(Step) — get(input_key) → write(layer, source)
      knowledge/                   # solo step domain-specific non generificabili (tutti indexing)
        __init__.py
        chunk_articles_step.py         # ChunkArticlesStep — ENRICHED_ARTICLES → EMBEDDABLE_CHUNKS (indexing)
        embed_chunks_step.py           # EmbedChunksStep — embed con filtro repealed (indexing)
        store_chunks_step.py           # StoreChunksStep — delete_source + bulk_insert (indexing)
                                       # ContextualizeStep RIMOSSO; MapStep/EnrichDataStep RIMOSSI (SP04)
                                       # preparation usa ApplyStep(ForEach+ContextEnricher)
      quiz/                        # package vuoto (SP04)
        __init__.py                    # __all__ = []
                                       # FlattenQuizStep RIMOSSO → FlattenQuiz in services/quiz/ (SP02)
                                       # MapToEmbeddableStep RIMOSSO → ToEmbeddableQuiz in services/quiz/ (SP03)
  configs/
    ingestor_config.py            # IngestorConfig (BaseSettings, frozen)
    source_config.py              # SourceConfig(dir, file) — frozen BaseModel
    pipeline_layer_config.py      # PipelineLayerConfig(input_layer, output_layer?, sources: list[str]) — frozen
  cli.py                           # unico entry point `ingest` (SP07)
                                   #   ingest prepare knowledge --source <cds|cap> [--force]
                                   #   ingest prepare quiz [--force]
                                   #   ingest index knowledge --source <cds|cap>
                                   #   ingest index quiz
                                   #   ingest reset knowledge
                                   #   ingest reset quiz
                                   # main.py, reset_db.py, reset_quiz_db.py rimossi (SP07)
                                   # quiz_main.py, prepare_knowledge_main.py già rimossi in precedenza (legacy)

configs/                            # root del progetto (non sotto src/)
  ingestor_config.yaml              # config non-secret, committata (layers/sources/pipeline selettori)
  agents/
    article_contextualizer.yaml     # AgentDefinition per ArticleContextualizer
    road_sign_describer.yaml        # AgentDefinition per RoadSignDescriber (vision)

.env.example                        # documenta le sole env var secret
                                     # (POSTGRES__USER, POSTGRES__PASSWORD)
```

## Convenzione directory dati

Pipeline/flow a quattro layer su disco, risolti da `LayerResolver`. Dal SP09
sia il corpus normativo sia il quiz bank seguono la **stessa topologia a tre
stadi** (`parsed` → `cleaned` → `enriched`):

- `data/raw/<source>/` — HTML grezzo dello scraper (non toccato da questo
  package).
- `data/parsed/<source>/...json` — JSON grezzo prodotto dallo scraper/parser,
  markup/struttura ancora grezza. Input del flow `build_knowledge_cleaning_flow`
  (corpus) o `build_quiz_cleaning_flow` (quiz, layer introdotto in SP09: prima
  il quiz partiva direttamente da `cleaned`).
- `data/cleaned/<source>/...json` — (layer `cleaned`). Per il corpus
  normativo: output del flow `build_knowledge_cleaning_flow` (sink
  `WriteJsonStep`), input del flow `build_knowledge_enrichment_flow`
  (`LoadJsonStep`). Il layer `"cleaned"` è una costante privata in
  `knowledge_flows.py`/`quiz_flows.py` (`_CLEANED_LAYER`), non un campo di
  `PipelineLayerConfig`. Per il quiz bank (SP09): output del flow
  `build_quiz_cleaning_flow` (flatten+dedup di `FlattenQuiz` UseCase, una riga
  flat per sotto-domanda), input del flow `build_quiz_enrichment_flow`.
- `data/enriched/<source>/...json` — (layer `enriched`) output del flow di
  enrichment (corpus o quiz); input dei flow di indexing. Self-contained:
  articolo pulito + `contexts` per i commi (corpus), o sotto-domanda flat +
  `image_description` (quiz).

Risoluzione path: `LayerResolver.path(layer, source)` =
`layers[layer] / sources[source].dir / sources[source].file`.

## Dettaglio per area

- [data_preparation.md](data_preparation.md) — preparation: corpus normativo
  su due flow flowstep per-source (`build_knowledge_cleaning_flow`,
  `build_knowledge_enrichment_flow`, `run_preparation`, `ApplyStep`+`ForEach` +
  `ContextEnricher` domain-specific, `ArticleMapper`); quiz bank su due flow
  analoghi (`build_quiz_cleaning_flow` con `ApplyStep(FlattenQuiz())`,
  `build_quiz_enrichment_flow` con `ApplyStep(ForEach+ImageDescriptionEnricher)`).
  Più `ArticleContextualizerAgent`, `RoadSignDescriberAgent`,
  `EnrichedArticleRepository`, `EnrichedQuizBankRepository`.
- [knowledge_pipelines.md](knowledge_pipelines.md) — corpus normativo (CdS + CAP):
  catena modelli `ParsedArticleModel`/`EnrichedArticleModel`/`EmbeddableChunkModel`
  (un modello per layer, `EmbeddableChunkModel` ha `embedded_text`),
  `ArticleMapper` consolidato, `ArticleCleaner`, `ArticleChunker`,
  flow per-source (`build_knowledge_indexing_flow`, 5 step con `ApplyStep`
  tra `EmbedChunksStep` e `StoreChunksStep`), `KnowledgeChunkStoreRepository`
  (con `delete_source`).
- [quiz_pipelines.md](quiz_pipelines.md) — quiz bank: catena modelli
  `ParsedQuizModel`/`CleanedQuizModel`/`EnrichedQuizModel`/`EmbeddableQuizModel`
  (un modello per layer, SP09), `QuizMapper` consolidato (metodo
  `from_enriched_to_embeddable` rinominato da SP03, 1 argomento),
  `QuizQuestionStoreRepository`; service `FlattenQuiz` e `ToEmbeddableQuiz`
  (UseCase, ex step flowstep, SP02/SP03); flow indexing quiz con
  `ApplyStep(ToEmbeddableQuiz())` e `ApplyStep(ForEach(...))` (SP04);
  flow preparation quiz: `ApplyStep(FlattenQuiz())` (cleaning) +
  `ApplyStep(ForEach+ImageDescriptionEnricher)` (enrichment, 3 step, SP04);
  `ImageDescriptionEnricher` ora implementa `UseCase` (ex `EnricherProtocol`).
- [config_and_entrypoints.md](config_and_entrypoints.md) — `IngestorConfig`, `LayerResolver`,
  pattern config a due livelli, unico entry point `cli.py` (SP07, sottocomandi `ingest prepare
  / index / reset`), convenzioni di logging.
- [flowstep_toolkit.md](flowstep_toolkit.md) — `flowstep` package top-level
  (SP00b) con `ApplyStep` in `src/flowstep/steps/`; step generici ingestor:
  `EmbedStep`, `DbStoreStep`, `LoadJsonStep`, `WriteJsonStep`, `StoreRepository`
  Protocol; `context_keys`; `MapStep`/`EnrichDataStep`/`EnricherProtocol`
  rimossi in SP04.
- [tests.md](tests.md) — elenco completo dei test con file e comportamenti verificati.
