# Package `src/guidami_ai_patente_ingestor/`

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/implement/ingestor.md`,
`plans/architecture-quiz-bank.md` (pipeline quiz bank, refactor Postgres
condiviso), `plans/ingest--data-preparation.md`,
`plans/ingest--agent-and-prompt-provider.md`,
`plans/ingest--orchestrator/04-bis-quiz-data-models.md`,
`plans/ingest--orchestrator/04-tris-quiz-mappers.md`,
`plans/ingest--orchestrator/05-knowledge-preparation-flow.md`,
`plans/ingest--orchestrator/06-quiz-preparation-flow.md`.

Pipeline/flow batch attivi:

- **corpus normativo — preparation** (flow flowstep per-source, SP05): due
  flow lineari, `build_knowledge_cleaning_flow` (`parsed` → `cleaned`) e
  `build_knowledge_enrichment_flow` (`cleaned` → `enriched`, con
  `ArticleContextualizerAgent`), eseguiti via il runner generico
  `run_preparation`. Una run per source. Sostituisce la precedente
  `DataPreparationPipeline` (rimossa). Entry point CLI non ancora wired
  (atteso in SP07).
- **corpus normativo — indexing** (flow flowstep per-source, SP03): legge `enriched`
  di UNA source → chunk → embed → `knowledge_chunks` (delete-by-source +
  insert). Eseguito una volta per source: `--source cds`, poi `--source cap`.
- **quiz bank — preparation** (flow flowstep, SP06, costruito da zero — non
  un refactor): `build_quiz_preparation_flow` (`cleaned` → `enriched`),
  enrichment Open/Closed via `QuizEnricher` Protocol +
  `QuizEnrichmentService` (primo enricher: `ImageDescriptionEnricher`, vision
  LLM con `RoadSignDescriberAgent`, dedup immagini uniche), eseguito via lo
  stesso runner `run_preparation` di SP05. Entry point CLI non ancora wired
  (atteso in SP07).
- **quiz bank — indexing** (flow flowstep SP04, mapper consolidato in
  SP04-tris): legge `enriched` quiz → mappa in `EmbeddableQuizModel` (dedup,
  ora nello step `MapToEmbeddableStep`) → embed → mappa in `QuizQuestion`
  (`QuizMapper`) → `quiz_questions` (truncate full-reload). Entry point CLI
  non ancora wired (atteso in SP07); `reset_quiz_db.py` resta disponibile.

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
                                   #   unica entità ingestor: i DTO quiz sono in models/quiz/ (SP04-bis)
  mappers/
    knowledge/
      __init__.py                         # re-esporta EnrichedArticleMapper
      enriched_article_mapper.py          # EnrichedArticleMapper.from_article_to_enriched_article(article, contexts)
                                          #   -> EnrichedArticle (SP05)
    quiz/
      __init__.py                         # re-esporta QuizMapper (unico mapper, SP04-tris)
      quiz_mapper.py                      # QuizMapper — backbone statico di tutte le transizioni 1:1:
                                          #   from_quiz_bank_item_to_enriched/from_quiz_bank_to_enriched (SP06),
                                          #   from_enriched_quiz_item_to_embeddable,
                                          #   from_embeddable_to_quiz_question (SP04-tris)
                                          #   sostituisce QuizQuestionMapper + EmbeddableQuizQuestionMapper (rimossi)
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
      quiz_bank_repository.py                # QuizBankRepository(JsonRepository[QuizBankModel])
      enriched_quiz_bank_repository.py       # EnrichedQuizBankRepository(JsonRepository[EnrichedQuizModel])
  services/
    __init__.py                   # re-esporta LayerResolver, QuizEnrichmentService
    layer_resolver.py             # LayerResolver(layers, sources).path(layer, source) -> Path
    knowledge/
      article_cleaner.py          # ArticleCleaner.clean(article) -> Article
      article_chunker.py          # ArticleChunker.chunk(enriched_article, source) -> list[KnowledgeChunk]
                                  #   (accetta EnrichedArticle, popola chunk.context)
    quiz/
      __init__.py                          # re-esporta QuizEnrichmentService (SP06)
      quiz_enrichment_service.py           # QuizEnrichmentService(enrichers).enrich(list[QuizBankModel])
                                           #   -> list[EnrichedQuizModel]: base-map + catena enricher
      enrichers/
        __init__.py                        # re-esporta QuizEnricher, ImageDescriptionEnricher
        quiz_enricher.py                   # Protocol QuizEnricher.enrich(list[EnrichedQuizModel]) -> ...
        image_description_enricher.py      # ImageDescriptionEnricher — vision LLM, dedup immagini uniche
  models/
    knowledge/
      enriched_article.py         # EnrichedArticle — articolo pulito + contexts: dict[int, str] per commi
    quiz/
      __init__.py                  # re-esporta tutti i modelli quiz (SP04-bis)
      quiz_bank.py                 # QuizBankModel, QuizBankItemModel — layer cleaned (ex QuizMainQuestion/
                                   #   QuizSubQuestion, spostati da entities/ in SP04-bis)
      enriched_quiz.py             # EnrichedQuizModel, EnrichedQuizItemModel — layer enriched
                                   #   (EnrichedQuizItemModel aggiunge image_description: str | None)
      embeddable_quiz.py           # EmbeddableQuizModel — DTO intermedio flat con embedded_text
      image_description.py        # ImageDescription(BaseModel, frozen=True) — name: str, description: str
  orchestrators/
    __init__.py                    # re-esporta build_knowledge_indexing_flow (SP03),
                                   #   build_knowledge_cleaning_flow/build_knowledge_enrichment_flow (SP05),
                                   #   build_quiz_indexing_flow (SP04), build_quiz_preparation_flow (SP06),
                                   #   run_preparation (SP05)
    context_keys.py                # Costanti chiavi FlowContext — vocabolario SP03/04/05/06 (additivo)
    knowledge_flows.py             # build_knowledge_indexing_flow(config, ..., source) -> Flow (SP03)
                                   #   build_knowledge_cleaning_flow(config, layer_resolver, source) -> Flow (SP05)
                                   #   build_knowledge_enrichment_flow(config, layer_resolver, source) -> Flow (SP05)
    quiz_flows.py                  # build_quiz_indexing_flow(config, ...) -> Flow (SP04)
                                   #   build_quiz_preparation_flow(config, layer_resolver) -> Flow (SP06)
    preparation_runner.py          # run_preparation(flow, out_path, force) -> None — runner per-source (SP05)
    steps/
      __init__.py                  # docstring package
      generic/
        __init__.py                # re-esporta EmbedStep, DbStoreStep, StoreRepository
        protocols/
          store_repository.py      # Protocol StoreRepository (truncate + bulk_insert positional-only)
        embed_step.py              # EmbedStep(Step) — assegna embedding in place, ri-scrive items_key
        db_store_step.py           # DbStoreStep(Step) — sink full-reload (truncate → bulk_insert)
      knowledge/
        __init__.py                # re-esporta i 10 step knowledge (4 indexing SP03 + 6 preparation SP05)
        load_enriched_articles_step.py  # LoadEnrichedArticlesStep — carica UNA source → ENRICHED_ARTICLES (SP03)
        chunk_articles_step.py          # ChunkArticlesStep — legge ENRICHED_ARTICLES → CHUNKS (SP03)
        embed_chunks_step.py            # EmbedChunksStep — embeddita (con filtro repealed) → CHUNKS (SP03)
        store_chunks_step.py            # StoreChunksStep — delete_source + bulk_insert (per-source sink) (SP03)
        load_parsed_articles_step.py    # LoadParsedArticlesStep — carica UNA source → PARSED_ARTICLES (SP05)
        clean_articles_step.py          # CleanArticlesStep — PARSED_ARTICLES → CLEANED_ARTICLES (SP05)
        write_cleaned_step.py           # WriteCleanedStep — sink, scrive layer "cleaned" (SP05)
        load_cleaned_articles_step.py   # LoadCleanedArticlesStep — carica layer "cleaned" → CLEANED_ARTICLES (SP05)
        contextualize_step.py           # ContextualizeStep — CLEANED_ARTICLES → ENRICHED_ARTICLES (SP05)
        write_enriched_step.py          # WriteEnrichedStep — sink, scrive layer "enriched" (SP05)
      quiz/
        __init__.py                     # re-esporta i 6 step quiz (3 indexing SP04 + 3 preparation SP06)
        load_enriched_quiz_step.py      # LoadEnrichedQuizStep — carica source quiz → ENRICHED_QUIZ (SP04, indexing)
        map_to_embeddable_step.py       # MapToEmbeddableStep — ENRICHED_QUIZ → EMBEDDABLE_QUIZ
                                        #   (flatten+dedup, migrato dal mapper in SP04-tris)
        map_to_quiz_entity_step.py      # MapToQuizEntityStep — EMBEDDABLE_QUIZ → QUIZ_ENTITIES (SP04, indexing)
        load_quiz_step.py               # LoadQuizStep — carica layer "cleaned" → CLEANED_QUIZ (SP06, preparation)
        enrich_quiz_step.py             # EnrichQuizStep — CLEANED_QUIZ → ENRICHED_QUIZ, delega QuizEnrichmentService (SP06)
        write_enriched_quiz_step.py     # WriteEnrichedQuizStep — sink, scrive layer "enriched" (SP06, preparation)
  configs/
    ingestor_config.py            # IngestorConfig (BaseSettings, frozen)
    source_config.py              # SourceConfig(dir, file) — frozen BaseModel
    pipeline_layer_config.py      # PipelineLayerConfig(input_layer, output_layer?, sources: list[str]) — frozen
  main.py                          # entry point CLI (uv run ingest-knowledge --source <cds|cap>)
  reset_db.py                      # entry point CLI (uv run reset-knowledge-db)
  reset_quiz_db.py                 # entry point CLI (uv run reset-quiz-db)
                                   # quiz_main.py e prepare_knowledge_main.py rimossi (legacy, commit
                                   #   45136a1): nessun entry point CLI per quiz/preparation flow finché
                                   #   non viene wired in SP07

configs/                            # root del progetto (non sotto src/)
  ingestor_config.yaml              # config non-secret, committata (layers/sources/pipeline selettori)
  agents/
    article_contextualizer.yaml     # AgentDefinition per ArticleContextualizer
    road_sign_describer.yaml        # AgentDefinition per RoadSignDescriber (vision)

.env.example                        # documenta le sole env var secret
                                     # (POSTGRES__USER, POSTGRES__PASSWORD)
```

## Convenzione directory dati

Pipeline/flow a quattro layer su disco, risolti da `LayerResolver`:

- `data/raw/<source>/` — HTML grezzo dello scraper (non toccato da questo
  package).
- `data/parsed/<source>/...json` — JSON grezzo prodotto dallo scraper, markup
  normattiva ancora presente. Input del flow `build_knowledge_cleaning_flow`
  (corpus, SP05). Per il quiz non esiste un layer `parsed` distinto da
  `cleaned` (vedi sotto).
- `data/cleaned/<source>/...json` — (layer `cleaned`). Per il corpus
  normativo, ricostruito da SP05 come **stadio esplicito su disco**: output
  del flow `build_knowledge_cleaning_flow` (sink `WriteCleanedStep`), input
  del flow `build_knowledge_enrichment_flow` (`LoadCleanedArticlesStep`). Il
  layer `"cleaned"` è una costante privata in `knowledge_flows.py`
  (`_CLEANED_LAYER`), non un campo di `PipelineLayerConfig`. Per il quiz
  bank, `data/cleaned/quiz-patente-ab/quiz-patente-ab.json` è l'**input**
  diretto del flow `build_quiz_preparation_flow` (`LoadQuizStep`, SP06): non
  c'è uno stadio "clean" separato per il quiz, il layer `cleaned` è già il
  punto di partenza.
- `data/enriched/<source>/...json` — (layer `enriched`) output del flow di
  enrichment (corpus, `WriteEnrichedStep`) o del flow di quiz preparation
  (`WriteEnrichedQuizStep`, SP06); input dei flow di indexing. Self-contained:
  articolo pulito + `contexts` per i commi (corpus), o quiz bank +
  `image_description` per le sotto-domande (quiz).

Risoluzione path: `LayerResolver.path(layer, source)` =
`layers[layer] / sources[source].dir / sources[source].file`.

## Dettaglio per area

- [data_preparation.md](data_preparation.md) — preparation: corpus normativo
  ricostruito su due flow flowstep per-source (SP05: `build_knowledge_cleaning_flow`,
  `build_knowledge_enrichment_flow`, `run_preparation`, step `Load*`/`Clean*`/
  `Write*`/`Contextualize*`, `EnrichedArticleMapper`); quiz bank costruito da
  zero su un flow flowstep (SP06: `build_quiz_preparation_flow`, step
  `LoadQuizStep`/`EnrichQuizStep`/`WriteEnrichedQuizStep`, riuso di
  `run_preparation`). Più `ArticleContextualizerAgent`,
  `RoadSignDescriberAgent`, `EnrichedArticleRepository`, `EnrichedQuizBankRepository`.
- [knowledge_pipelines.md](knowledge_pipelines.md) — corpus normativo (CdS + CAP):
  `ArticleRepository`, `ArticleCleaner`, `ArticleChunker`, flow per-source
  (`build_knowledge_indexing_flow`, step knowledge, `StoreChunksStep`),
  `KnowledgeChunkStoreRepository` (con `delete_source`).
- [quiz_pipelines.md](quiz_pipelines.md) — quiz bank: catena modelli
  `QuizBankModel`/`EnrichedQuizModel`/`EmbeddableQuizModel` (SP04-bis),
  `QuizBankRepository`, `QuizMapper` consolidato (SP04-tris),
  `QuizQuestionStoreRepository`; flow indexing quiz (SP04): step
  `LoadEnrichedQuizStep`, `MapToEmbeddableStep` (flatten+dedup), `MapToQuizEntityStep`,
  factory `build_quiz_indexing_flow` (truncate full-reload, `EmbedStep`
  generico riusato); flow preparation quiz (SP06): `services/quiz/`
  (`QuizEnricher`, `QuizEnrichmentService`, `ImageDescriptionEnricher`),
  factory `build_quiz_preparation_flow`. Cutover CLI per entrambi pendente
  in SP07.
- [config_and_entrypoints.md](config_and_entrypoints.md) — `IngestorConfig`, `LayerResolver`,
  pattern config a due livelli, entry point CLI (incl. `--source` di `ingest-knowledge`),
  convenzioni di logging.
- [flowstep_toolkit.md](flowstep_toolkit.md) — step generici flowstep (SP02):
  `EmbedStep`, `DbStoreStep`, `StoreRepository` Protocol, `context_keys`.
- [tests.md](tests.md) — elenco completo dei test con file e comportamenti verificati.
