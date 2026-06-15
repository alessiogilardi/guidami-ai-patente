# Organizzazione del codice

Riferimento: [architecture-index.md](architecture-index.md),
[architecture-ingestor.md](architecture-ingestor.md).

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
  models/
    knowledge/
      knowledge_chunk.py      # KnowledgeChunk (riga della tabella knowledge_chunks)
      retrieval_result.py     # RetrievalResult (chunk + score, per query di similarity)
  clients/
    embedding_client.py        # EmbeddingClient: interfaccia + impl e5-small (sentence-transformers)
    vector_store_client.py     # VectorStoreClient: wrapper pgvector (psycopg)
  configs/
    embedding_config.py         # nome modello, dimensione vettore, prefissi query/passage
    vector_store_config.py      # campi di connessione espliciti (host/port/user/password/dbname/sslmode), nome tabella
```

## `guidami_ai_patente_ingestor/`

Pipeline batch di indicizzazione del corpus normativo (CdS + CAP).

```
guidami_ai_patente_ingestor/
  orchestrators/
    knowledge_indexing/
      indexing_pipeline.py          # IndexingPipeline: load -> chunk -> embed -> load
      indexing_pipeline_builder.py  # IndexingPipelineBuilder
  services/
    knowledge/
      article_loader.py              # ArticleLoader: legge cds/cap JSON -> entità Article
      article_chunker.py              # ArticleChunker: Article -> KnowledgeChunk (pulizia markup, is_repealed)
  configs/
    ingestor_config.py                # path JSON sorgente + aggrega configs di common
  main.py                              # entry point CLI (uv run ingest-knowledge)
```

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
    quiz_repository.py          # QuizRepository (JSON statico in memoria)
    knowledge_repository.py     # KnowledgeRepository (query su VectorStoreClient di common)
    session_repository.py       # interfaccia astratta + InMemorySessionRepository
  clients/
    groq_client.py               # wrapper Groq API
  models/
    quiz/                         # QuizQuestion, AnswerCheckResult, ExplanationResult
    chat/                         # ChatMessage, ChatSession
  configs/
    app_config.py                 # AppConfig: Groq API key, sessione, aggrega configs di common
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
