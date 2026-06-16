# Ingestion del corpus normativo (CdS + CAP) — vector store

Riferimento: [architecture-index.md](architecture-index.md),
[tech-stack.md](tech-stack.md).

## Dati sorgente

- `data/processed/cds/codice_della_strada.json` — 266 articoli
- `data/processed/cap/codice_rca.json` — 96 articoli
- Ogni articolo: `number`, `title`, `text` (eventuale comma introduttivo), `paragraphs`
  (lista di commi), `url`, `scraped_at`, `repealed` (bool, a livello di articolo)
- 29 articoli CdS e 4 CAP interamente abrogati (`repealed: true`)
- 44 singoli commi marcati testualmente "ABROGATO" dentro articoli altrimenti attivi
- Numerazione articoli non sempre numerica (es. `94-bis`, `198-bis`)

## Schema tabella vettoriale

```sql
CREATE TABLE knowledge_chunks (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,        -- 'cds' | 'cap'
    article_number  TEXT NOT NULL,        -- '141', '94-bis' (testo, non numerico)
    article_title   TEXT NOT NULL,
    comma_index     INT NOT NULL,         -- 0 = `text`/comma introduttivo, 1..n = paragraphs
    chunk_text      TEXT NOT NULL,        -- testo pulito usato per embedding e citazione
    is_repealed     BOOLEAN NOT NULL DEFAULT FALSE,  -- a livello di articolo O di singolo comma
    source_url      TEXT NOT NULL,
    embedding       VECTOR(1536),         -- openrouter/openai/text-embedding-3-small (vedi punto 4)
    UNIQUE (source, article_number, comma_index)
);
```

Indice vettoriale: nessuno per ora (sequential scan su ~1500-2000 righe è
istantaneo). Se il corpus crescesse di ordini di grandezza, valutare HNSW con
`vector_cosine_ops`.

## Decisioni

1. **Markup `((...))`**: rimosso in fase di chunking (regex) prima di
   embedding/storage — il testo normattiva usa doppie parentesi per segnalare
   modifiche normative, non semanticamente utile per retrieval/citazione.

2. **Comma 0 (`text`)**: generato solo se `text` non è vuoto. Articoli con
   `text=""` (es. CAP art. 118) partono direttamente da `comma_index=1`.

3. **Commi singolarmente abrogati**: rilevati con check testuale
   (`"ABROGAT" in paragraph.upper()`), impostano `is_repealed=true` sul singolo
   chunk anche se l'articolo non è interamente abrogato. `is_repealed` finale di
   un chunk = `article.repealed OR comma_abrogato_rilevato`.

4. **Dimensione embedding**: `1536`, fissata da
   `openrouter/openai/text-embedding-3-small` (via litellm/OpenRouter). Cambio di
   modello richiede `ALTER TABLE`/nuova tabella + re-ingestion completa, vedi
   [tech-stack.md](tech-stack.md).

5. **Metrica di distanza**: cosine (`vector_cosine_ops`, operatore `<=>`),
   scale-invariant: i vettori OpenAI sono già unit-norm, nessuna normalizzazione
   manuale necessaria.

6. **Client DB**: `psycopg` (v3) + libreria Python `pgvector` (adapter
   numpy↔vector), tramite `PostgresClient` generico e table-agnostic in
   `commons/clients/postgres_client.py` (condiviso con `quiz_questions`, vedi
   [architecture-quiz-bank.md](architecture-quiz-bank.md), decisione 8) +
   `KnowledgeChunkStoreRepository` nell'ingestor per truncate/bulk insert su
   `knowledge_chunks`. Niente SQLAlchemy — overhead non giustificato per
   poche tabelle a questa scala.

7. **Gestione schema**: `db/init.sql` montato in
   `/docker-entrypoint-initdb.d/` del container Postgres, eseguito automaticamente
   alla creazione del volume. Niente Alembic per ora (no migration history
   complessa con una sola tabella).

8. **Trigger ingestion**: CLI script registrato in `[project.scripts]`
   (es. `uv run ingest-knowledge`), seguendo la convenzione di
   `scrape-codice`/`parse-domande`. Config a due livelli: YAML committato
   (non-secret, `configs/ingestor_config.yaml`) + env/`.env` per le sole
   credenziali DB (`POSTGRES__USER`/`POSTGRES__PASSWORD`, rinominate da
   `VECTOR_STORE__USER`/`PASSWORD` — vedi
   [architecture-quiz-bank.md](architecture-quiz-bank.md), decisione 7),
   caricati da `IngestorConfig` (`pydantic_settings.BaseSettings`) a livello
   di entry point — vedi `.claude/architectures/ingestor.md` per i dettagli
   implementati finora.

## Flusso di ingestion

```
orchestrators/knowledge_indexing/indexing_pipeline.py

1. Load: legge cds/codice_della_strada.json + cap/codice_rca.json
2. Chunk: per ogni articolo, genera 0..n chunk (text + paragraphs),
          pulisce markup, calcola is_repealed (articolo OR comma)
3. Embed: batch embedding via litellm / OpenRouter (batch size
          configurabile)
4. Load: truncate + bulk insert in knowledge_chunks
```

**Full reload** (truncate + bulk insert) invece di upsert incrementale: a questa
scala (pochi secondi di embedding + insert), la semplicità di "drop & rebuild"
supera il vantaggio di un upsert incrementale, ed evita bug di sincronizzazione
se un articolo viene rimosso dalla fonte. Re-eseguibile a ogni re-scrape.

## Possibili estensioni future

**Hybrid search (full-text + semantico, fusione RRF)**: per testo legale i match
esatti su numeri di articolo/termini tecnici contano quanto la similarity
semantica — una colonna `tsvector` generata (`to_tsvector('italian', chunk_text)`)
con indice GIN, combinata con l'embedding via Reciprocal Rank Fusion, potrebbe
migliorare il retrieval. Rimandata perché:
- a questa scala (~1500-2000 righe) non serve per le performance
- è una modifica alla logica di `KnowledgeRepository`/retrieval, non
  all'ingestion
- **non richiede re-ingestion**: colonna generata e indici si aggiungono via
  `ALTER TABLE`/`CREATE INDEX` in qualsiasi momento, senza dipendere dal modello
  di embedding

Da valutare dopo aver validato la qualità del retrieval semantico puro con
text-embedding-3-small sui casi reali. **Progettazione di dettaglio**:
[architecture-hybrid-retrieval.md](architecture-hybrid-retrieval.md).

## Stato

**Implementato**: pipeline `knowledge_indexing` (load/chunk/embed/store) e
schema `knowledge_chunks` in `db/init.sql`. Decisioni 6-8 (client/config
Postgres condivisi con `quiz_questions`, `PostgresClient` generico +
`KnowledgeChunkStoreRepository`, comando `uv run ingest-knowledge`) aggiornate
e implementate insieme al refactor descritto in
[architecture-quiz-bank.md](architecture-quiz-bank.md) (decisioni 7-8).
Hybrid search (sezione "Possibili estensioni future") non implementato,
rimandato come da nota.
