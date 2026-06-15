# Piano di implementazione — `commons/`

Riferimento: [architecture-index.md](../architecture-index.md),
[architecture-ingestor.md](../architecture-ingestor.md),
[tech-stack.md](../tech-stack.md),
[architecture-code-layout.md](../architecture-code-layout.md).

## Scope

Componenti condivisi tra `guidami_ai_patente_ingestor` e l'app FastAPI:
modelli del vector store, client embedding/DB, config. `commons` non dipende
da nessuno degli altri due package.

## Ordine di build (bottom-up, ogni step verificabile da solo)

### 1. Docker compose + `db/init.sql` — ✅ fatto

- `db/init.sql` (a livello di `src/`): `CREATE EXTENSION vector;` + `CREATE
  TABLE knowledge_chunks (...)` come da schema in
  [architecture-ingestor.md](../architecture-ingestor.md), `VECTOR(384)` come
  default — da correggere al punto 2 se la verifica empirica dà un valore
  diverso.
- `docker/docker-compose.yml` (modulo dedicato, a livello di `src/`): servizio
  `postgres` (`pgvector/pgvector:pg16`), volume persistente
  `postgres_data`, porta configurabile, variabili `POSTGRES_USER/PASSWORD/DB`
  da `docker/.env` (vedi `docker/.env.example`, copiato e già gitignorato).
  Mount di `../db/init.sql` in `/docker-entrypoint-initdb.d/`.
- **Verifica eseguita**: `docker compose up -d` da `docker/`, poi `docker
  compose exec postgres psql -U guidami -d guidami_ai_patente -c '\dx' -c '\d
  knowledge_chunks'` — estensione `vector` 0.8.2 e tabella con le colonne
  attese confermate.

### 2. `configs/embedding_config.py` + `clients/embedding_client.py` — ✅ fatto

- `EmbeddingConfig` (Pydantic): nome modello (default
  `intfloat/multilingual-e5-small`), dimensione vettore (`384`), prefissi
  `query:`/`passage:`.
- `EmbeddingClient`: interfaccia astratta con metodi `embed_query(text) ->
  list[float]` e `embed_passages(texts: list[str]) -> list[list[float]]`
  (batch).
- `E5SmallEmbeddingClient`: implementazione locale via
  `sentence-transformers`, applica i prefissi configurati, normalizza i
  vettori (`normalize_embeddings=True`, coerente con `vector_cosine_ops`).
- **Verifica eseguita (chiude punto 4 apertura di architecture-ingestor.md)**:
  test di integrazione (`tests/commons/clients/test_embedding_client.py`,
  marcato `@pytest.mark.integration`) che embedda query e passaggi e
  controlla `len(vector) == 384` — confermato, nessuna modifica a
  `db/init.sql` necessaria.
- Aggiunte dipendenze esplicite `sentence-transformers` (embedding locale,
  vedi tech-stack.md) e `pydantic` (usata direttamente in `commons`).

### 3. `models/knowledge/` — ✅ fatto

- `KnowledgeChunk` (Pydantic): riga della tabella `knowledge_chunks` —
  `source: Literal["cds", "cap"]`, `article_number`, `article_title`,
  `comma_index`, `chunk_text`, `is_repealed`, `source_url`,
  `embedding: list[float] | None` (None prima dell'embedding).
- `RetrievalResult` (Pydantic): `chunk: KnowledgeChunk`, `score: float` — per
  risultati di similarity search.
- Test: `tests/commons/models/test_knowledge_chunk.py` — validazione default
  `embedding=None` e wrapping in `RetrievalResult`.

### 4. `configs/vector_store_config.py` + `clients/vector_store_client.py` — ✅ fatto

- `VectorStoreConfig` (Pydantic, `frozen=True`): nome tabella (default
  `knowledge_chunks`). **Modifica rispetto al piano originale**: niente
  `database_url` opaco — campi di connessione espliciti (`host`, `port`,
  `user`, `password: SecretStr`, `dbname`, `sslmode`), passati dal chiamante,
  non letti da env all'interno di `commons` (vedi `architecture-ingestor.md`
  e `.claude/architectures/commons.md` per i dettagli).
- `VectorStoreClient`: wrapper `psycopg` (v3) + `pgvector` adapter
  (`register_vector`), context manager (`with`). Metodi implementati:
  - `truncate()`
  - `bulk_insert(chunks: list[KnowledgeChunk])`
  - `similarity_search(embedding: list[float], top_k: int, source: str |
    None = None) -> list[RetrievalResult]` (usa `<=>`, **non** filtra
    `is_repealed` — lasciato al chiamante, vedi `KnowledgeRepository` futuro)
  - Nota implementativa: i parametri vettoriali nelle query richiedono il
    cast esplicito `%s::vector` (senza, psycopg adatta `list[float]` ad
    `array` e Postgres non trova l'operatore `<=>` per quel tipo).
- **Verifica eseguita**: `tests/commons/clients/test_vector_store_client.py`,
  marcato `@pytest.mark.integration`, contro il Postgres del compose —
  bulk insert + similarity search ordinata, filtro per `source`, truncate.

## File layout (da architecture-code-layout.md)

```
commons/
  __init__.py
  models/
    __init__.py
    knowledge/
      __init__.py
      knowledge_chunk.py
      retrieval_result.py
  clients/
    __init__.py
    embedding_client.py
    vector_store_client.py
  configs/
    __init__.py
    embedding_config.py
    vector_store_config.py
```

## Punti confermati durante l'implementazione

- Dimensione embedding reale: **384**, confermata (vedi step 2). Nessuna
  modifica a `db/init.sql`/`EmbeddingConfig` necessaria.
- Immagine Docker: `pgvector/pgvector:pg16`.
- `similarity_search` non filtra `is_repealed` — lasciato al chiamante
  (`KnowledgeRepository` nell'app, non bloccante per l'ingestor).

## Stato

Completato (step 1-4). `commons/` pronto come dipendenza per
[ingestor.md](ingestor.md).
