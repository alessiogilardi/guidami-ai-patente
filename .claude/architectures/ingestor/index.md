# Package `src/guidami_ai_patente_ingestor/`

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/architecture-code-layout.md`, `plans/implement/ingestor.md`,
`plans/architecture-quiz-bank.md` (pipeline quiz bank, refactor Postgres
condiviso).

Due pipeline batch indipendenti, entrambe full-reload su Postgres:

- **corpus normativo (CdS + CAP)**: pulizia (`CleaningPipeline`) e
  indicizzazione (`IndexingPipeline`) in `knowledge_chunks` (embedding
  incluso);
- **quiz bank**: `QuizIndexingPipeline`, load + map (flatten/dedup) +
  embedding + full-reload di `quiz_questions`.

Dipende da `commons` (modelli, `EmbeddingClient`, `PostgresClient`, config
condivise).

## Layout

```
src/guidami_ai_patente_ingestor/
  entities/
    article.py                    # Article — mappa 1:1 il JSON sorgente (number, title, text,
                                   # paragraphs, url, scraped_at, repealed)
    quiz_bank.py                   # QuizMainQuestion, QuizSubQuestion — mappano 1:1 il JSON sorgente
  repositories/
    article_repository.py         # ArticleRepository.load(path) -> list[Article]
                                   # ArticleRepository.write(articles, path) -> None
    knowledge_chunk_store_repository.py  # KnowledgeChunkStoreRepository (truncate + bulk insert)
    quiz_bank_repository.py        # QuizBankRepository.load(path) -> list[QuizMainQuestion]
    quiz_question_store_repository.py    # QuizQuestionStoreRepository (truncate + bulk insert)
  services/
    knowledge/
      article_cleaner.py          # ArticleCleaner.clean(article) -> Article
      article_chunker.py          # ArticleChunker.chunk(article, source) -> list[KnowledgeChunk]
    quiz/
      quiz_question_mapper.py     # QuizQuestionMapper.map(main_questions) -> list[QuizQuestion]
  orchestrators/
    knowledge_cleaning/
      cleaning_pipeline.py          # CleaningPipeline
      cleaning_pipeline_builder.py  # CleaningPipelineBuilder
    knowledge_indexing/
      indexing_pipeline.py          # IndexingPipeline
      indexing_pipeline_builder.py  # IndexingPipelineBuilder
    quiz_indexing/
      quiz_indexing_pipeline.py          # QuizIndexingPipeline
      quiz_indexing_pipeline_builder.py  # QuizIndexingPipelineBuilder
  configs/
    ingestor_config.py            # IngestorConfig (BaseSettings, frozen)
  main.py                          # entry point CLI (uv run ingest-knowledge)
  reset_db.py                      # entry point CLI (uv run reset-knowledge-db)
  quiz_main.py                     # entry point CLI (uv run ingest-quiz)
  reset_quiz_db.py                 # entry point CLI (uv run reset-quiz-db)

configs/                            # root del progetto (non sotto src/)
  ingestor_config.yaml              # config non-secret, committata

.env.example                        # documenta le sole env var secret
                                     # (POSTGRES__USER, POSTGRES__PASSWORD)
```

## Convenzione directory dati

Pipeline a tre stadi su disco:

- `data/raw/<source>/` — HTML grezzo dello scraper (non toccato da questo
  package).
- `data/parsed/<source>/...json` — JSON grezzo prodotto dallo scraper
  (rinominato da `data/processed/`), markup normattiva ancora presente.
- `data/cleaned/<source>/...json` — JSON pulito da `ArticleCleaner`, pronto
  per il chunking. Output di `CleaningPipeline`, input di `IndexingPipeline`.

Struttura mirror per source: `data/cleaned/cds/codice_della_strada.json`,
`data/cleaned/cap/codice_rca.json` (stessi nomi file di `data/parsed/`).

## Dettaglio per area

- [knowledge_pipelines.md](knowledge_pipelines.md) — corpus normativo (CdS + CAP):
  `ArticleRepository`, `ArticleCleaner`, `ArticleChunker`, `CleaningPipeline`,
  `IndexingPipeline`, `KnowledgeChunkStoreRepository`.
- [quiz_pipelines.md](quiz_pipelines.md) — quiz bank: `QuizMainQuestion`/`QuizSubQuestion`,
  `QuizBankRepository`, `QuizQuestionMapper`, `QuizIndexingPipeline`,
  `QuizQuestionStoreRepository`.
- [config_and_entrypoints.md](config_and_entrypoints.md) — `IngestorConfig`, pattern
  config a due livelli, entry point CLI (`main.py`, `reset_db.py`, `quiz_main.py`,
  `reset_quiz_db.py`), convenzioni di logging.
- [tests.md](tests.md) — elenco completo dei test con file e comportamenti verificati.
