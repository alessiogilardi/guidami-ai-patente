# Package `src/guidami_ai_patente_ingestor/`

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/implement/ingestor.md`,
`plans/architecture-quiz-bank.md` (pipeline quiz bank, refactor Postgres
condiviso), `plans/ingest--data-preparation.md`,
`plans/ingest--agent-and-prompt-provider.md`.

Pipeline batch attive:

- **corpus normativo — preparation** (`DataPreparationPipeline`): cleaning +
  enrichment LLM con `ArticleContextualizerAgent` → layer `enriched`;
- **corpus normativo — indexing** (flow flowstep per-source): legge `enriched`
  di UNA source → chunk → embed → `knowledge_chunks` (delete-by-source +
  insert). Eseguito una volta per source: `--source cds`, poi `--source cap`.
- **quiz bank — preparation** (`QuizDataPreparationPipeline`): vision LLM
  per immagini uniche con `RoadSignDescriberAgent` → layer `enriched`.
- **quiz bank — indexing** (flow flowstep SP04): legge `enriched` quiz →
  mappa in `EmbeddableQuizQuestion` (dedup) → embed → mappa in `QuizQuestion`
  → `quiz_questions` (truncate full-reload). Entry point CLI non ancora
  wired (atteso in SP07); `reset_quiz_db.py` resta disponibile.

Dipende da `commons` (modelli, entità, `BaseAgent`, `EmbeddingClient`, `PostgresClient`,
config condivise).

## Layout

```
src/guidami_ai_patente_ingestor/
  agents/
    __init__.py                        # re-esporta ArticleContextualizerAgent, RoadSignDescriberAgent
    article_contextualizer_agent.py    # ArticleContextualizerAgent(BaseAgent[dict[int,str]])
    road_sign_describer_agent.py       # RoadSignDescriberAgent(BaseAgent[ImageDescription])
  entities/
    article.py                     # Article — mappa 1:1 il JSON parsed (number, title, text,
                                   #   paragraphs, url, scraped_at, repealed)
    quiz_bank.py                   # QuizMainQuestion, QuizSubQuestion — layer parsed
  mappers/
    quiz/
      quiz_question_mapper.py             # QuizQuestionMapper.map(enriched_main_questions)
                                          #   -> list[EmbeddableQuizQuestion]
      embeddable_quiz_question_mapper.py  # EmbeddableQuizQuestionMapper.to_entity(EmbeddableQuizQuestion)
                                          #   -> QuizQuestion (scarta image_description)
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
      quiz_bank_repository.py                # QuizBankRepository(JsonRepository[QuizMainQuestion])
      enriched_quiz_bank_repository.py       # EnrichedQuizBankRepository(JsonRepository[EnrichedQuizMainQuestion])
  services/
    layer_resolver.py             # LayerResolver(layers, sources).path(layer, source) -> Path
    knowledge/
      article_cleaner.py          # ArticleCleaner.clean(article) -> Article
      article_chunker.py          # ArticleChunker.chunk(enriched_article, source) -> list[KnowledgeChunk]
                                  #   (accetta EnrichedArticle, popola chunk.context)
  models/
    knowledge/
      enriched_article.py         # EnrichedArticle — articolo pulito + contexts: dict[int, str] per commi
    quiz/
      embeddable_quiz_question.py # EmbeddableQuizQuestion — DTO intermedio con embedded_text
      enriched_quiz_bank.py       # EnrichedQuizMainQuestion, EnrichedQuizSubQuestion — layer enriched
                                  #   (EnrichedQuizSubQuestion aggiunge image_description: str | None)
      image_description.py        # ImageDescription(BaseModel, frozen=True) — name: str, description: str
  orchestrators/
    __init__.py                    # re-esporta build_knowledge_indexing_flow (SP03), build_quiz_indexing_flow (SP04)
    context_keys.py                # Costanti chiavi FlowContext — vocabolario SP03/04 (additivo)
    knowledge_flows.py             # build_knowledge_indexing_flow(config, ..., source) -> Flow (SP03)
    quiz_flows.py                  # build_quiz_indexing_flow(config, ...) -> Flow (SP04)
    steps/
      __init__.py                  # docstring package
      generic/
        __init__.py                # re-esporta EmbedStep, DbStoreStep, StoreRepository
        protocols/
          store_repository.py      # Protocol StoreRepository (truncate + bulk_insert positional-only)
        embed_step.py              # EmbedStep(Step) — assegna embedding in place, ri-scrive items_key
        db_store_step.py           # DbStoreStep(Step) — sink full-reload (truncate → bulk_insert)
      knowledge/
        __init__.py                # re-esporta i 4 step knowledge
        load_enriched_articles_step.py  # LoadEnrichedArticlesStep — carica UNA source → ENRICHED_ARTICLES
        chunk_articles_step.py          # ChunkArticlesStep — legge ENRICHED_ARTICLES → CHUNKS
        embed_chunks_step.py            # EmbedChunksStep — embeddita (con filtro repealed) → CHUNKS
        store_chunks_step.py            # StoreChunksStep — delete_source + bulk_insert (per-source sink)
      quiz/
        __init__.py                     # re-esporta LoadEnrichedQuizStep, MapToEmbeddableStep, MapToQuizEntityStep
        load_enriched_quiz_step.py      # LoadEnrichedQuizStep — carica source quiz → ENRICHED_QUIZ
        map_to_embeddable_step.py       # MapToEmbeddableStep — ENRICHED_QUIZ → EMBEDDABLE_QUIZ (dedup)
        map_to_quiz_entity_step.py      # MapToQuizEntityStep — EMBEDDABLE_QUIZ → QUIZ_ENTITIES
    knowledge_preparation/
      data_preparation_pipeline.py          # DataPreparationPipeline (clean → contextualize → enriched)
      data_preparation_pipeline_builder.py  # DataPreparationPipelineBuilder
    quiz_preparation/
      quiz_data_preparation_pipeline.py          # QuizDataPreparationPipeline (dedup → describe → enriched)
      quiz_data_preparation_pipeline_builder.py  # QuizDataPreparationPipelineBuilder
  configs/
    ingestor_config.py            # IngestorConfig (BaseSettings, frozen)
    source_config.py              # SourceConfig(dir, file) — frozen BaseModel
    pipeline_layer_config.py      # PipelineLayerConfig(input_layer, output_layer?, sources: list[str]) — frozen
  main.py                          # entry point CLI (uv run ingest-knowledge --source <cds|cap>)
  reset_db.py                      # entry point CLI (uv run reset-knowledge-db)
  reset_quiz_db.py                 # entry point CLI (uv run reset-quiz-db)
  prepare_knowledge_main.py        # entry point CLI (uv run prepare-knowledge, --force)

configs/                            # root del progetto (non sotto src/)
  ingestor_config.yaml              # config non-secret, committata (layers/sources/pipeline selettori)
  agents/
    article_contextualizer.yaml     # AgentDefinition per ArticleContextualizer
    road_sign_describer.yaml        # AgentDefinition per RoadSignDescriber (vision)

.env.example                        # documenta le sole env var secret
                                     # (POSTGRES__USER, POSTGRES__PASSWORD)
```

## Convenzione directory dati

Pipeline a quattro layer su disco, risolti da `LayerResolver`:

- `data/raw/<source>/` — HTML grezzo dello scraper (non toccato da questo
  package).
- `data/parsed/<source>/...json` — JSON grezzo prodotto dallo scraper, markup
  normattiva ancora presente. Input di `DataPreparationPipeline` e
  `QuizDataPreparationPipeline`.
- `data/cleaned/<source>/...json` — (layer `cleaned`) non più scritto come
  stadio esplicito: `ArticleCleaner` ora è un intermedio in-memory dentro
  `DataPreparationPipeline`. Il layer `cleaned` rimane nella configurazione
  `layers` ma non è prodotto come artefatto disco.
- `data/enriched/<source>/...json` — (layer `enriched`) output delle pipeline
  di preparation; input di `IndexingPipeline` e `QuizIndexingPipeline`.
  Self-contained: articolo pulito + `contexts` per i commi (corpus), o quiz
  bank + `image_description` per le sotto-domande (quiz).

Risoluzione path: `LayerResolver.path(layer, source)` =
`layers[layer] / sources[source].dir / sources[source].file`.

## Dettaglio per area

- [data_preparation.md](data_preparation.md) — pipeline di preparation (LLM offline):
  `DataPreparationPipeline`, `QuizDataPreparationPipeline`, `ArticleContextualizerAgent`,
  `RoadSignDescriberAgent`, `EnrichedArticleRepository`, `EnrichedQuizBankRepository`.
- [knowledge_pipelines.md](knowledge_pipelines.md) — corpus normativo (CdS + CAP):
  `ArticleRepository`, `ArticleCleaner`, `ArticleChunker`, flow per-source
  (`build_knowledge_indexing_flow`, step knowledge, `StoreChunksStep`),
  `KnowledgeChunkStoreRepository` (con `delete_source`).
- [quiz_pipelines.md](quiz_pipelines.md) — quiz bank: `QuizMainQuestion`/`QuizSubQuestion`,
  `QuizBankRepository`, `QuizQuestionMapper`, `EmbeddableQuizQuestionMapper`,
  `QuizQuestionStoreRepository`; flow indexing quiz (SP04): step
  `LoadEnrichedQuizStep`, `MapToEmbeddableStep`, `MapToQuizEntityStep`,
  factory `build_quiz_indexing_flow` (truncate full-reload, `EmbedStep`
  generico riusato, cutover CLI pendente in SP07).
- [config_and_entrypoints.md](config_and_entrypoints.md) — `IngestorConfig`, `LayerResolver`,
  pattern config a due livelli, entry point CLI (incl. `--source` di `ingest-knowledge`),
  convenzioni di logging.
- [flowstep_toolkit.md](flowstep_toolkit.md) — step generici flowstep (SP02):
  `EmbedStep`, `DbStoreStep`, `StoreRepository` Protocol, `context_keys`.
- [tests.md](tests.md) — elenco completo dei test con file e comportamenti verificati.
