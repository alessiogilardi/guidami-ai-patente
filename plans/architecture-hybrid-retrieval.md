# Hybrid Search — retrieval ibrido (pgvector + FTS, fusione RRF)

Riferimenti: [architecture-index.md](architecture-index.md),
[architecture-ingestor.md](architecture-ingestor.md) (sezione "Possibili
estensioni future"), [architecture-code-layout.md](architecture-code-layout.md),
[tech-stack.md](tech-stack.md).

## Contesto e motivazione

Il retrieval del corpus normativo (CdS + CAP) alimenta `ExplanationService`:
data una domanda del quiz, recupera i chunk più rilevanti da `knowledge_chunks`
per costruire il prompt all'LLM. La sola ricerca vettoriale (semantica) **perde
i match esatti** che nel testo legale contano quanto la similarity: numeri di
articolo (`Art. 142`), termini tecnici (`catadiottro`), espressioni precise
(`spia blu`). L'embedding tende a "diluire" questi token in favore del senso
generale.

L'**hybrid search** combina due recuperi complementari, tutto dentro Postgres:

- **Dense / semantico**: `pgvector`, distanza coseno tra embedding (`<=>`).
- **Sparse / lessicale**: Full-Text Search nativo di Postgres
  (`to_tsvector('italian', …)` + `@@`), match esatto sui token.
- **Fusione**: **Reciprocal Rank Fusion (RRF)** in SQL — normalizza e combina
  i ranking dei due recuperi in un'unica classifica.

Risultato atteso: massima precisione di recupero (termini specifici trovati
esattamente) mantenendo la comprensione semantica, **senza infrastruttura
aggiuntiva** (un solo Postgres, nessun vector DB esterno, nessun framework
RAG — coerente con la scelta `psycopg` diretto / no-SQLAlchemy del progetto).

## Stato di partenza (verificato nel codice)

- `knowledge_chunks` esiste (`db/init.sql`) con `embedding VECTOR(384)`;
  ingestion (load → chunk → embed → store) **già implementata**. Nessun indice
  vettoriale (seq scan su ~1500-2000 righe è istantaneo).
- **Il retrieval non esiste ancora**: `KnowledgeRepository` è solo *pianificato*
  in [architecture-code-layout.md](architecture-code-layout.md) sotto
  `guidami_ai_patente/` (app FastAPI non ancora avviata). **L'hybrid search è la
  prima implementazione del layer di recupero** — non si sostituisce a una
  `similarity_search` esistente.
- Esistono già e si riusano: `EmbeddingClient.embed_query()` (prefisso e5
  `query: `, embedding normalizzato → coseno), `PostgresClient` (psycopg +
  adapter `pgvector` registrato, `fetch()`), `RetrievalResult` (chunk + score),
  `KnowledgeChunk`.

## Decisioni

### 1. Scope: end-to-end (schema + retrieval)

Il piano copre sia l'abilitazione di schema (colonna `tsvector` + indice GIN)
sia la logica di recupero (`KnowledgeRepository.hybrid_search`). La schema da
sola non porta valore senza la query che la usa.

### 2. Colonna `tsvector` GENERATED + indice GIN

```sql
-- in CREATE TABLE knowledge_chunks (db/init.sql):
chunk_tsv  tsvector GENERATED ALWAYS AS (to_tsvector('italian', chunk_text)) STORED

-- + indice:
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_tsv
    ON knowledge_chunks USING GIN (chunk_tsv);
```

- **Colonna generata `STORED`**: si popola automaticamente da `chunk_text` a
  ogni insert — **zero modifiche al codice di ingestion** e nessun campo nuovo
  in `KnowledgeChunk`/`bulk_insert`.
- **Configurazione `'italian'`**: stemming + stopword italiane. Numeri (`142`)
  e termini tecnici (`catadiottro`) diventano lessemi cercabili.
- Indice **GIN** (non GiST): corpus statico, letture frequenti, build una tantum.

### 3. Migrazione via `db/init.sql` + reset (no Alembic)

Coerente con il meccanismo attuale (`db/init.sql` montato in
`/docker-entrypoint-initdb.d/`, gira solo a creazione volume; nessuna migration
history). Si modifica `init.sql`, poi:

```bash
uv run reset-knowledge-db   # drop/ricrea (vedi reset_db.py)
uv run ingest-knowledge     # full reload, pochi secondi
```

Il full reload è già la filosofia dell'ingestion (decisione in
architecture-ingestor.md), quindi nessun nuovo concetto operativo. Alembic
resta non giustificato a questa scala.

### 4. Fusione RRF in SQL puro (una sola query)

RRF: per ogni documento, `score = Σ 1 / (k + rank_i)` su ciascun recuperatore in
cui compare; `k` costante di smorzamento (default **60**, valore canonico). Una
sola query con due CTE evita doppio round-trip e tiene la logica vicino ai dati,
coerente con `psycopg` diretto. La query è interrogata via `PostgresClient.fetch`.

```sql
WITH dense AS (
    SELECT id,
           ROW_NUMBER() OVER (ORDER BY embedding <=> %(query_embedding)s::vector) AS rank
    FROM knowledge_chunks
    WHERE NOT is_repealed
    ORDER BY embedding <=> %(query_embedding)s::vector
    LIMIT %(candidate_pool)s
),
sparse AS (
    SELECT id,
           ROW_NUMBER() OVER (
               ORDER BY ts_rank(chunk_tsv, websearch_to_tsquery('italian', %(query_text)s)) DESC
           ) AS rank
    FROM knowledge_chunks
    WHERE NOT is_repealed
      AND chunk_tsv @@ websearch_to_tsquery('italian', %(query_text)s)
    ORDER BY ts_rank(chunk_tsv, websearch_to_tsquery('italian', %(query_text)s)) DESC
    LIMIT %(candidate_pool)s
)
SELECT c.source, c.article_number, c.article_title, c.comma_index,
       c.chunk_text, c.is_repealed, c.source_url,
       COALESCE(1.0 / (%(rrf_k)s + dense.rank),  0.0)
     + COALESCE(1.0 / (%(rrf_k)s + sparse.rank), 0.0) AS rrf_score
FROM dense
FULL OUTER JOIN sparse USING (id)
JOIN knowledge_chunks c ON c.id = COALESCE(dense.id, sparse.id)
ORDER BY rrf_score DESC
LIMIT %(top_k)s;
```

Note:
- **`FULL OUTER JOIN`**: un chunk trovato da un solo recuperatore concorre
  comunque (`COALESCE(..., 0.0)` sul ramo mancante).
- **`websearch_to_tsquery`**: robusto a input utente arbitrario (non solleva su
  sintassi), supporta frasi tra virgolette. Preferito a `plainto_tsquery`.
- **`WHERE NOT is_repealed`** su entrambi i rami: non si recuperano/citano norme
  abrogate (default; eventuale `include_repealed` rinviabile se servisse).
- **`embedding <=> …`**: coseno (embedding e5 normalizzati). `query_embedding`
  passato come parametro grazie all'adapter `pgvector` già registrato nel
  `PostgresClient`.
- **`rrf_score` non è una similarity in [0,1]**: è un punteggio di fusione, utile
  solo per ordinare. I chiamanti non devono applicarci soglie tipo cosine.

### 5. `KnowledgeRepository.hybrid_search` — dove e come

Nel layer app (prima pietra di `guidami_ai_patente/`), come da
[architecture-code-layout.md](architecture-code-layout.md):
`guidami_ai_patente/repositories/knowledge_repository.py`.

```python
class KnowledgeRepository:
    def __init__(self, client: PostgresClient, table_name: str,
                 config: HybridSearchConfig) -> None: ...

    def hybrid_search(
        self, query_text: str, query_embedding: Sequence[float], top_k: int | None = None
    ) -> list[RetrievalResult]: ...
```

- **Il repository riceve sia `query_text` (per l'FTS) sia `query_embedding`
  (per il dense)**; non dipende da `EmbeddingClient`. L'embedding della query è
  responsabilità del chiamante (`ExplanationService`, che già "embed della
  domanda → retrieval" nel flusso runtime di architecture-index.md). Mantiene il
  repository come puro data-access e testabile senza caricare il modello.
- Mappa ogni riga del `fetch` in `RetrievalResult(chunk=KnowledgeChunk(...),
  score=rrf_score)`, preservando l'ordine restituito da SQL.

### 6. Config RRF minimale

`guidami_ai_patente/configs/` — `HybridSearchConfig(BaseModel, frozen=True)`:

```python
rrf_k: int = 60            # costante di smorzamento RRF
candidate_pool: int = 50   # candidati per recuperatore prima della fusione
top_k: int = 5             # risultati finali restituiti al servizio
```

Aggregata in `AppConfig` (entry point dell'app). Niente over-engineering
(coerente con la linea KISS del progetto): tre interi con default ragionevoli.

## Componenti da creare/modificare

| File | Azione |
|---|---|
| `db/init.sql` | + colonna `chunk_tsv` GENERATED in `knowledge_chunks` + indice GIN |
| `guidami_ai_patente/repositories/knowledge_repository.py` | nuovo — `KnowledgeRepository.hybrid_search` |
| `guidami_ai_patente/configs/` | nuovo — `HybridSearchConfig` (+ aggregazione in `AppConfig`) |
| `commons/models/knowledge/retrieval_result.py` | riuso invariato (`RetrievalResult`) |

Riuso senza modifiche: `EmbeddingClient.embed_query`, `PostgresClient.fetch`,
`KnowledgeChunk`.

## Ordine di build / TDD

1. **Schema** — aggiorna `db/init.sql`; verifica via `\d knowledge_chunks` che
   `chunk_tsv` e l'indice GIN esistano dopo `reset-knowledge-db` +
   `ingest-knowledge`.
2. **`HybridSearchConfig`** — config frozen + test default/immutabilità.
3. **`KnowledgeRepository.hybrid_search`** (TDD):
   - **Unit** (`PostgresClient.fetch` mockato, righe finte): verifica il mapping
     riga → `RetrievalResult`, la preservazione dell'ordine, e che i parametri
     (`query_embedding`, `query_text`, `rrf_k`, `candidate_pool`, `top_k`)
     siano passati correttamente. La *semantica* SQL **non** è testabile in
     unit.
   - **Integration** (`@pytest.mark.integration`, Postgres+pgvector reale con
     corpus seedato): caso che distingue hybrid da vettoriale puro — una query
     con termine esatto (es. `catadiottro` o `Art. 142`) deve recuperare il
     chunk giusto che la sola similarity mancherebbe. È **il** test di
     comportamento reale dell'RRF (coerente con i test di integrazione rinviati
     in [implement/ingestor.md](implement/ingestor.md)).

> Nota TDD (regola utente): la logica vive in SQL e non è testabile a priori in
> unit puro; gli unit test coprono il glue Python, l'integration test copre il
> comportamento RRF. Questa è l'alternativa proposta dove il TDD "test-first
> sull'implementazione" è impraticabile.

## Verifica end-to-end

1. `uv run reset-knowledge-db && uv run ingest-knowledge` → DB ripopolato con
   `chunk_tsv` valorizzato.
2. Ispezione: `psql … -c '\d knowledge_chunks'` mostra colonna + indice GIN.
3. `uv run pytest -m integration tests/.../test_knowledge_repository.py`.
4. Spot-check manuale in `psql` con la query RRF su un caso a termine esatto,
   confrontando il ranking con il solo ramo `dense`.

## Possibili estensioni future

- **Indice vettoriale HNSW** (`vector_cosine_ops`) sul ramo dense, se il corpus
  crescesse di ordini di grandezza (oggi non serve).
- **Pesi per recuperatore** nell'RRF (es. dare più peso allo sparse sulle query
  con numeri di articolo) — da valutare solo con dati di qualità reali.
- **`include_repealed`** opzionale, se emergesse il bisogno di citare norme
  abrogate per contesto storico.

## Stato

Progettazione completata e concordata. **Non ancora implementato** (dipende
dall'avvio del package `guidami_ai_patente/`, oggi non iniziato). L'abilitazione
di schema (punto 2-3) è applicabile in qualsiasi momento senza re-embedding.
