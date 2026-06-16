# Package `src/commons/`

Riferimento progettazione: `plans/architecture-code-layout.md`,
`plans/implement/commons.md`, `plans/architecture-quiz-bank.md` (decisioni
7-8, refactor Postgres condiviso).

Componenti condivisi tra `guidami_ai_patente_ingestor` e l'app FastAPI (non
ancora avviata). `commons` non dipende da nessuno dei due.

## Layout

```
src/commons/
  entities/
    knowledge/
      knowledge_chunk.py   # KnowledgeChunk — riga di knowledge_chunks
    quiz/
      quiz_question.py     # QuizQuestion — riga di quiz_questions
  models/
    knowledge/
      retrieval_result.py  # RetrievalResult — chunk + score (similarity search)
  clients/
    embeddings/
      __init__.py                                  # re-esporta EmbeddingClient, LiteLLMEmbeddingClient,
                                                   # SentenceTransformerEmbeddingClient
      embedding_client.py                          # EmbeddingClient (interfaccia ABC)
      litellm_embedding_client.py                  # LiteLLMEmbeddingClient (cloud, OpenRouter)
      sentence_transformer_embedding_client.py     # SentenceTransformerEmbeddingClient (locale, bge-m3)
    __init__.py            # re-esporta tutti i client pubblici
    postgres_client.py     # PostgresClient — wrapper psycopg generico, table-agnostic
  configs/
    embedding_config.py          # EmbeddingConfig (frozen)
    postgres_connection_config.py # PostgresConnectionConfig (frozen)
```

## Decisioni implementate

- **`EmbeddingConfig`** (`BaseModel`, `frozen=True`): campi `model_name`
  (default `"BAAI/bge-m3"`), `vector_dim: int = 1024`, `dimensions: int |
  None = None` (Matryoshka opzionale — ignorato dal client locale, passato
  all'API se si usa `LiteLLMEmbeddingClient`), `timeout: float = 30.0`,
  `num_retries: int = 3`. I campi cloud rimangono per compatibilità A/B con
  `LiteLLMEmbeddingClient`.
- **`SentenceTransformerEmbeddingClient`**: implementazione locale via
  libreria **sentence-transformers**. Carica il modello con
  `SentenceTransformer(config.model_name)` al momento della costruzione
  (import a livello di modulo). Costruttore: `config: EmbeddingConfig`,
  `query_prefix: str = ""`, `passage_prefix: str = ""` — prefissi vuoti per
  default (stile bge-m3); passare prefissi espliciti per modelli asimmetrici
  come `intfloat/multilingual-e5-*`. `normalize_embeddings=True` sempre in
  entrambi i metodi. Sostituisce `E5SmallEmbeddingClient` (rimosso).
- **`LiteLLMEmbeddingClient`**: implementazione cloud via libreria
  **litellm**, instradato su **OpenRouter** (endpoint embeddings
  OpenAI-compatible). Riceve in costruzione un `EmbeddingConfig`; chiama
  `litellm.embedding(model=..., input=texts, ...)` passando `timeout`,
  `num_retries` e opzionalmente `dimensions`. La risposta viene ordinata per
  `data[i]["index"]` per garantire l'allineamento input↔output
  indipendentemente dall'ordine restituito dall'API. L'API key
  `OPENROUTER_API_KEY` è letta da litellm dall'ambiente (`.env`), senza
  lettura esplicita nel codice. Rimane disponibile come alternativa cloud per
  A/B di qualità.
- **`EmbeddingClient` (ABC)**: interfaccia `embed_query(text: str) ->
  list[float]` / `embed_passages(texts: list[str]) -> list[list[float]]`
  invariata — l'implementazione concreta è sostituibile senza cambiare i
  chiamanti (Dependency Inversion). Entrambe le implementazioni
  (`SentenceTransformerEmbeddingClient`, `LiteLLMEmbeddingClient`) sono
  esportate da `commons.clients`.
- **`PostgresConnectionConfig`** (`BaseModel`, `frozen=True`): sostituisce
  `VectorStoreConfig` (rimosso). Resta `BaseModel`, non `BaseSettings` —
  `commons` non legge env, i valori arrivano dal chiamante (il caricamento
  config resta a `main.py` dei rispettivi servizi, vedi
  `rules/python/architecture.md`). Campi: `host`, `port: int = 5432`, `user`,
  `password: SecretStr`, `dbname`, `sslmode: str | None = None`. **Nessun
  campo `table_name`**: il nome tabella è un dettaglio del repository che usa
  il client (decisione 7 del piano quiz-bank), non della connessione — un
  unico `PostgresConnectionConfig` è condiviso tra `knowledge_chunks` e
  `quiz_questions` (stesso Postgres, stesse credenziali).
- **`PostgresClient`**: wrapper `psycopg` v3 generico e **table-agnostic**
  con adapter `pgvector` registrato (`register_vector`), usabile come context
  manager (`__enter__`/`__exit__` chiude la connessione, più `close()`
  esplicito). Sostituisce `VectorStoreClient` (rimosso, incluso
  `similarity_search` — nessun consumer attuale). La connessione è costruita
  con `psycopg.conninfo.make_conninfo(host=..., port=..., user=...,
  password=config.password.get_secret_value(), dbname=...,
  sslmode=config.sslmode)` seguito da `psycopg.connect(conninfo,
  autocommit=True)` — `make_conninfo` filtra automaticamente `sslmode=None`.
  Metodi:
  - `truncate(table_name: str)` — `TRUNCATE TABLE {table}` con
    `sql.Identifier` (nome tabella passato dal chiamante, non dalla config);
  - `execute_many(query: sql.Composed, params_seq: Sequence[Sequence[object]])`
    — `cursor.executemany`, usato per i bulk insert dei repository;
  - `fetch(query: sql.Composed, params: Sequence[object] | None = None) ->
    list[tuple]` — `cursor.execute` + `fetchall`, pensato per le letture
    on-demand del futuro `QuizRepository`/`KnowledgeRepository` lato app.
  - I parametri vettoriali richiedono cast esplicito `%s::vector` nelle query
    (psycopg altrimenti adatta `list[float]` ad `array`, incompatibile con
    `<=>`).
- **`KnowledgeChunk`** (Pydantic, `commons/entities/knowledge/`): `source:
  Literal["cds", "cap"]`, `embedding: list[float] | None = None` (None prima
  dell'embedding).
- **`QuizQuestion`** (Pydantic, `BaseModel`, `commons/entities/quiz/`): riga
  di `quiz_questions` — `number: str`, `question_id: int`, `topic: str`,
  `text: str`, `correct_answer: bool`, `image_filename: str | None = None`,
  `embedding: list[float] | None = None` (None prima dell'embedding, stesso
  pattern di `KnowledgeChunk`).
- **`entities/` vs `models/`**: `KnowledgeChunk` e `QuizQuestion` sono entità
  di dominio (righe di tabella), spostate da `commons/models/` a
  `commons/entities/` per coerenza con `rules/python/architecture.md`
  (`models/` = DTO/value object, `entities/` = entità di dominio).
  `commons/models/knowledge/` ora esporta solo `RetrievalResult`, che
  importa `KnowledgeChunk` da `commons.entities.knowledge` (import assoluto,
  attraversa il confine di package). `commons/models/quiz/` è stato rimosso
  interamente (conteneva solo `QuizQuestion`).

## Test

- `tests/commons/clients/test_embedding_client.py` — test offline con mock di
  `litellm.embedding`: verifica costruzione risposta, ordinamento per `index`,
  separazione `embed_query`/`embed_passages`. Test `@pytest.mark.integration`
  (skippato senza `OPENROUTER_API_KEY`) verifica `len(vector) == 1536` contro
  l'API reale. Test per `SentenceTransformerEmbeddingClient`: `embed_query` e
  `embed_passages` con prefissi vuoti (bge-m3) e con prefissi espliciti
  (e5-style); verifica `len(vector) == config.vector_dim`.
- `tests/commons/clients/test_postgres_client.py` — contro il Postgres del
  compose (no marker `integration`): `truncate`, `execute_many`/`fetch` su
  `knowledge_chunks` (bulk insert + lettura ordinata).
- `tests/commons/entities/knowledge/test_knowledge_chunk.py` — default
  `embedding=None`.
- `tests/commons/models/knowledge/test_retrieval_result.py` — wrapping di
  `KnowledgeChunk` in `RetrievalResult` con `score`.
