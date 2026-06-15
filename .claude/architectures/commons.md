# Package `src/commons/`

Riferimento progettazione: `plans/architecture-code-layout.md`,
`plans/implement/commons.md`.

Componenti condivisi tra `guidami_ai_patente_ingestor` (non ancora avviato) e
l'app FastAPI (non ancora avviata). `commons` non dipende da nessuno dei due.

## Layout

```
src/commons/
  models/
    knowledge/
      knowledge_chunk.py   # KnowledgeChunk — riga di knowledge_chunks
      retrieval_result.py  # RetrievalResult — chunk + score (similarity search)
  clients/
    embedding_client.py    # EmbeddingClient (interfaccia) + E5SmallEmbeddingClient
    vector_store_client.py # VectorStoreClient — wrapper psycopg + pgvector
  configs/
    embedding_config.py    # EmbeddingConfig (frozen)
    vector_store_config.py # VectorStoreConfig (frozen)
```

## Decisioni implementate

- **`EmbeddingConfig`**: default `intfloat/multilingual-e5-small`,
  `vector_dim=384`, prefissi `query: ` / `passage: ` (richiesti dal modello
  e5).
- **`E5SmallEmbeddingClient`**: implementazione locale via
  `sentence-transformers`, applica i prefissi e normalizza i vettori
  (`normalize_embeddings=True`), coerente con l'operatore
  `vector_cosine_ops` usato in `similarity_search`.
- **`VectorStoreConfig`**: resta `BaseModel` (non `BaseSettings`) — `commons`
  non legge env, i valori arrivano dal chiamante (il caricamento config resta
  a `main.py` dei rispettivi servizi, vedi `rules/python/architecture.md`).
  Campi di connessione **espliciti** (non più `database_url: str`): `host`,
  `port: int = 5432`, `user`, `password: SecretStr`, `dbname`,
  `sslmode: str | None = None`, `table_name: str = "knowledge_chunks"`. La
  decomposizione garantisce che l'autenticazione sia sempre esplicita e
  validata (niente stringa di connessione opaca).
- **`VectorStoreClient`**: wrapper `psycopg` v3 + adapter `pgvector`
  (`register_vector`), usabile come context manager. La connessione è
  costruita con `psycopg.conninfo.make_conninfo(host=..., port=..., user=...,
  password=config.password.get_secret_value(), dbname=...,
  sslmode=config.sslmode)` seguito da `psycopg.connect(conninfo,
  autocommit=True)` — `make_conninfo` filtra automaticamente `sslmode=None`,
  ed evita i problemi di typing pyright di un dict di kwargs union-typed
  passato a `connect()`. Metodi:
  - `truncate()`
  - `bulk_insert(chunks: list[KnowledgeChunk])`
  - `similarity_search(embedding, top_k, source=None) ->
    list[RetrievalResult]` — usa `<=>`, **non filtra `is_repealed`** (lasciato
    al chiamante, es. futuro `KnowledgeRepository` nell'app).
  - I parametri vettoriali richiedono cast esplicito `%s::vector` nelle query
    (psycopg altrimenti adatta `list[float]` ad `array`, incompatibile con
    `<=>`).
- **`KnowledgeChunk`** (Pydantic): `source: Literal["cds", "cap"]`,
  `embedding: list[float] | None = None` (None prima dell'embedding).

## Test

- `tests/commons/clients/test_embedding_client.py` —
  `@pytest.mark.integration`, verifica `len(vector) == 384`.
- `tests/commons/clients/test_vector_store_client.py` —
  `@pytest.mark.integration`, contro il Postgres del compose: bulk insert +
  similarity search ordinata, filtro per `source`, truncate.
- `tests/commons/models/test_knowledge_chunk.py` — default `embedding=None`,
  wrapping in `RetrievalResult`.
