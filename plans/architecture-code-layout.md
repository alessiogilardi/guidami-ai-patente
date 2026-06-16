# Organizzazione del codice

Riferimento: [architecture-index.md](architecture-index.md),
[architecture-ingestor.md](architecture-ingestor.md),
[architecture-quiz-bank.md](architecture-quiz-bank.md).

## Pacchetti

Tre pacchetti sotto `src/`, in continuità con la struttura attuale (un solo
`pyproject.toml`, più package top-level — come già per `scrapers`/`parsers`).
Dipendenza a senso unico: `ingestor` e app dipendono da `common`, `common` non
dipende da nessuno dei due.

```
src/
  commons/
  guidami_ai_patente_ingestor/
  guidami_ai_patente/             # app FastAPI (pacchetto esistente)
```

## `commons/`

Componenti condivisi tra ingestion e applicativo: tutto ciò che riguarda
l'accesso al vector store e gli embedding, dato che entrambi i servizi devono
concordare su schema/dimensione/modello.

```
commons/
  entities/
    knowledge/
      knowledge_chunk.py      # KnowledgeChunk (riga della tabella knowledge_chunks)
    quiz/
      quiz_question.py         # QuizQuestion (riga della tabella quiz_questions)
  models/
    knowledge/
      retrieval_result.py     # RetrievalResult (chunk + score, per query di similarity)
  clients/
    embedding_client.py        # EmbeddingClient: interfaccia + LiteLLMEmbeddingClient (litellm/OpenRouter)
    postgres_client.py         # PostgresClient: generico e table-agnostic (connect/execute/fetch/copy,
                                # registrazione adapter pgvector)
  configs/
    embedding_config.py            # nome modello, dimensione vettore, prefissi query/passage
    postgres_connection_config.py  # unico config di connessione (host/port/user/password/dbname/sslmode)
```

`knowledge_chunks` e `quiz_questions` vivono nello stesso Postgres con le
stesse credenziali: un solo `PostgresConnectionConfig` top-level per servizio
(env `POSTGRES__USER`/`POSTGRES__PASSWORD`, rinominate da
`VECTOR_STORE__USER`/`PASSWORD`). `VectorStoreClient`/`VectorStoreConfig` e
l'ipotetico `QuizStoreClient`/`QuizStoreConfig` (client/config legati a una
singola tabella) sono **eliminati** a favore di `PostgresClient` generico +
nomi tabella iniettati nei repository, vedi
[architecture-quiz-bank.md](architecture-quiz-bank.md), decisioni 7-8.

## `guidami_ai_patente_ingestor/`

Pipeline batch di indicizzazione del corpus normativo (CdS + CAP).

```
guidami_ai_patente_ingestor/
  orchestrators/
    knowledge_indexing/
      indexing_pipeline.py          # IndexingPipeline: load -> chunk -> embed -> store
      indexing_pipeline_builder.py  # IndexingPipelineBuilder
    quiz_indexing/
      quiz_indexing_pipeline.py          # QuizIndexingPipeline: load -> map -> store (truncate + bulk insert)
      quiz_indexing_pipeline_builder.py  # QuizIndexingPipelineBuilder
  repositories/
    quiz_question_repository.py        # QuizQuestionRepository.load(path) -> list[QuizQuestion]
                                        # (flatten domande madri -> sotto-domande, denormalizza question_id/topic,
                                        #  dedup dei duplicati esatti)
    quiz_question_store_repository.py  # QuizQuestionStoreRepository: truncate + bulk insert su quiz_questions
                                        # (PostgresClient + table_name da config)
    knowledge_chunk_store_repository.py  # KnowledgeChunkStoreRepository: truncate + bulk_insert su knowledge_chunks
                                          # (PostgresClient + table_name da config, sostituisce VectorStoreClient)
  services/
    knowledge/
      article_loader.py              # ArticleLoader: legge cds/cap JSON -> entità Article
      article_chunker.py              # ArticleChunker: Article -> KnowledgeChunk (pulizia markup, is_repealed)
  configs/
    ingestor_config.py                # path JSON sorgente + PostgresConnectionConfig + nomi tabella + aggrega configs di common
  main.py                              # entry point CLI (uv run ingest-knowledge)
  quiz_main.py                         # entry point CLI (uv run ingest-quiz)
  reset_quiz_db.py                     # entry point CLI (uv run reset-quiz-db), analogo a reset_db.py
```

`quiz_indexing` non ha uno step di cleaning/embedding: il JSON del quiz bank
non ha markup da pulire, quindi `QuizIndexingPipeline` è load → map → store.
Entrambe le pipeline usano lo stesso full reload (truncate + bulk insert):
`KnowledgeChunkStoreRepository` su `knowledge_chunks`,
`QuizQuestionStoreRepository` su `quiz_questions` (vedi
[architecture-quiz-bank.md](architecture-quiz-bank.md), decisioni 2-3 e 8).

## `guidami_ai_patente/` (app FastAPI)

Applicativo che serve il quiz bot. Le route FastAPI restano controller sottili:
nessuna logica di business, solo validazione input/output e chiamata agli
orchestrator.

```
guidami_ai_patente/
  api/
    main.py                  # FastAPI app factory
    routers/
      quiz_router.py          # endpoint quiz (prossima domanda, check risposta)
      chat_router.py          # endpoint chat (spiegazione, follow-up)
    schemas/
      quiz_schemas.py          # Pydantic request/response (DTO API, separati dai models di dominio)
      chat_schemas.py
  orchestrators/
    quiz_chat/
      quiz_chat_pipeline.py
      quiz_chat_pipeline_builder.py
  services/
    quiz/
      answer_checker.py        # AnswerChecker (deterministico)
      explanation_service.py   # ExplanationService (retrieval + prompt + Groq)
      chat_service.py           # ChatService (history + RAG per follow-up)
  repositories/
    quiz_repository.py          # QuizRepository: letture on-demand su quiz_questions
                                 # (PostgresClient + table_name da config)
    knowledge_repository.py     # KnowledgeRepository: similarity_search su knowledge_chunks
                                 # (PostgresClient + table_name da config)
    session_repository.py       # interfaccia astratta + InMemorySessionRepository
  clients/
    groq_client.py               # wrapper Groq API
  models/
    quiz/                         # AnswerCheckResult, ExplanationResult (QuizQuestion arriva da commons.entities.quiz)
    chat/                         # ChatMessage, ChatSession
  configs/
    app_config.py                 # AppConfig: Groq API key, sessione, PostgresConnectionConfig + nomi tabella,
                                   # aggrega configs di common
  main.py                          # entry point (uvicorn)
```

## Punti aperti

1. **Singolo `pyproject.toml` vs uv workspace**: la struttura sopra mantiene un
   solo progetto/pyproject con più package — coerente con l'attuale
   `scrapers`/`parsers`. Un uv workspace con `pyproject.toml` indipendenti per
   `ingestor` e app darebbe dipendenze e versioning separati (es. l'app non
   avrebbe bisogno delle dipendenze di scraping), utile se in futuro i due
   servizi vanno deployati come immagini Docker realmente indipendenti. Da
   valutare quando si arriva alla containerizzazione.
2. **`schemas/` vs `models/` nell'app**: separazione tra DTO API (Pydantic per
   FastAPI) e modelli di dominio condivisi — se la conversione risultasse
   1:1 senza valore aggiunto, valutare se semplificare evitando un mapper
   inutile.

## Stato

Layout proposto, da discutere prima dell'implementazione.
