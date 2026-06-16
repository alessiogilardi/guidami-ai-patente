# Migrazione embedder del corpus → bge-m3 (locale, 1024)

Riferimento: [architecture-index.md](architecture-index.md),
[architecture-ingestor.md](architecture-ingestor.md),
[tech-stack.md](tech-stack.md). Prerequisito di
[ingest--llm-as-judge.md](ingest--llm-as-judge.md) e del retrieval ibrido
([architecture-hybrid-retrieval.md](architecture-hybrid-retrieval.md)).

## Obiettivo

Adottare **`BAAI/bge-m3` locale (1024 dim)** come **unico** embedder del progetto,
usato sia per l'indicizzazione offline del corpus normativo sia per il retrieval a
runtime. Sostituisce l'attuale default (cloud `text-embedding-3-small`, 1536).
Richiede il **cambio dimensione della colonna `VECTOR(N)`** (1536 → 1024) e un
**re-embedding completo del corpus**.

## Perché bge-m3 locale

- Qualità multilingue/italiano **paragonabile a `text-embedding-3-small`** su
  retrieval, ma **gratis** e **senza API key né latenza di rete a runtime**.
- Gira via `sentence-transformers` (stack già in dipendenze) — nessuna nuova
  infrastruttura.
- **Vincolo di coerenza**: query e chunk devono vivere nello stesso spazio
  vettoriale → un solo embedder per offline e runtime. A runtime serve comunque
  **solo per i follow-up liberi**: la spiegazione iniziale di un quiz mappato è una
  JOIN sul mapping precomputato (vedi [ingest--llm-as-judge.md](ingest--llm-as-judge.md)).
- `LiteLLMEmbeddingClient` (OpenRouter) **resta** come alternativa intercambiabile
  per eventuale A/B di qualità — l'astrazione `EmbeddingClient` è già in place.

## Stato di partenza (riconciliato col codice)

> Verificato sul codice il 2026-06-16; il piano originale era disallineato su più
> punti (corretti qui sotto).

- `EmbeddingConfig` (`src/commons/configs/embedding_config.py`): è un `BaseModel`
  con `model_name="openrouter/openai/text-embedding-3-small"`, `vector_dim=1536`,
  più campi cloud (`dimensions`, `timeout`, `num_retries`). Docstring: "embedder
  cloud".
- Client esistenti (`src/commons/clients/embeddings/`):
  - `E5SmallEmbeddingClient` — sentence-transformers, **già parametrizzato** sui
    prefissi (`query_prefix="query: "`, `passage_prefix="passage: "`), con import
    lazy di `sentence_transformers` e messaggio "uv add sentence-transformers".
  - `LiteLLMEmbeddingClient` — cloud via litellm.
- `db/init.sql`: `knowledge_chunks.embedding` è **`VECTOR(1536)`** (non 384 come
  diceva il piano). `quiz_questions` ha **già `UNIQUE(number)`** (prerequisito del
  llm-as-judge soddisfatto).
- **Default in uso = cloud**: sia `main.py` (`ingest-knowledge`, riga 42) sia il
  fallback di `IndexingPipelineBuilder` istanziano `LiteLLMEmbeddingClient`.
- `pyproject.toml`: `sentence-transformers>=5.5.1` e `litellm` sono **già
  dipendenze non opzionali**; il marker pytest `integration` **esiste già**.
- Scripts presenti: `ingest-knowledge`, `reset-knowledge-db` (solo TRUNCATE di
  `knowledge_chunks`), `ingest-quiz`, `reset-quiz-db`.

### Cosa resta davvero da fare

1. `EmbeddingConfig` default → `BAAI/bge-m3` / 1024 (+ docstring).
2. Generalizzare il client locale (rinomina + default prefissi vuoti + rimozione
   import lazy ora ridondante).
3. Spostare il **default** dell'embedder da cloud a locale (`main.py` +
   `IndexingPipelineBuilder`).
4. Portare la colonna `embedding` a `VECTOR(1024)` (init.sql + recreate volume).
5. Reset completo del DB + re-ingestion di articoli **e** quiz.
6. Embedding **offline** dei quiz: colonna `quiz_questions.embedding VECTOR(1024)` +
   step di embedding nella pipeline `ingest-quiz` (così il giudice non embedda a
   runtime).

## Modifiche

### 1. Config (`src/commons/configs/embedding_config.py`)
- `model_name="BAAI/bge-m3"`, `vector_dim=1024`.
- Aggiornare la docstring: la config ora descrive l'**embedder di default locale**;
  i campi cloud (`dimensions`, `timeout`, `num_retries`) restano per l'alternativa
  `LiteLLMEmbeddingClient` ma sono **ignorati** dal client locale.
- Il profilo cloud A/B si ottiene istanziando una `EmbeddingConfig` con override
  (`model_name="openrouter/openai/text-embedding-3-small"`, `vector_dim=1536`) —
  config unica condivisa, nessuna classe separata.

### 2. Client locale: generalizzazione (decisione presa)
Rinominare `E5SmallEmbeddingClient` → **`SentenceTransformerEmbeddingClient`**
(`sentence_transformer_embedding_client.py`):
- `__init__(self, config, query_prefix: str = "", passage_prefix: str = "")` —
  default **vuoti** (bge-m3 non usa prefissi). e5 resta raggiungibile passando
  `query_prefix="query: "`, `passage_prefix="passage: "`.
- `normalize_embeddings=True`, output 1024 dim per bge-m3.
- **Rimuovere l'import lazy + ImportError**: `sentence-transformers` è dipendenza
  fissa, quindi `from sentence_transformers import SentenceTransformer` diventa un
  import normale a livello di modulo.
- Aggiornare `src/commons/clients/embeddings/__init__.py` e
  `src/commons/clients/__init__.py`: esportare `SentenceTransformerEmbeddingClient`,
  rimuovere `E5SmallEmbeddingClient` dall'API pubblica.
- Nessuna classe `BgeM3EmbeddingClient` dedicata né classe `e5` residua.

### 3. Default dell'embedder: da cloud a locale
- `main.py` (`ingest-knowledge`): sostituire
  `LiteLLMEmbeddingClient(config.embedding)` con
  `SentenceTransformerEmbeddingClient(config.embedding)`; aggiornare l'import.
- `IndexingPipelineBuilder`: il fallback di default in `build()` e la docstring di
  `with_embedding_client` passano a `SentenceTransformerEmbeddingClient`.
- `LiteLLMEmbeddingClient` resta importabile e iniettabile via
  `with_embedding_client(...)` per A/B, ma non è più il default.

### 4. Schema DB (`db/init.sql`)
- `embedding VECTOR(1536)` → **`VECTOR(1024)`**.
- `init.sql` gira **solo alla creazione del volume**: per applicarlo al DB esistente
  si **ricrea il volume** (vedi sezione "Reset completo"). Niente `ALTER TABLE` né
  DDL duplicato in Python.

### 5. Dipendenze
- Nessuna aggiunta: `sentence-transformers` e `litellm` sono già presenti. Il peso
  del modello bge-m3 (~2 GB) viene scaricato al primo uso e messo in cache da
  HuggingFace.

### 6. Embedding dei quiz **offline** (precompute per il giudice)
Oggi `ingest-quiz` fa solo load → map → store (nessun embedding) e lo stadio
*retrieve* del giudice (vedi [ingest--llm-as-judge.md](ingest--llm-as-judge.md))
chiamerebbe `embed_query(text)` **per ogni domanda a tempo di giudizio**. Spostiamo
quel calcolo **offline**, dentro la pipeline del quiz bank: ogni riga
`quiz_questions` nasce già con il suo embedding, così il giudice non carica il
modello né embedda nulla a runtime.

**Decisione — estendere `QuizIndexingPipeline`** (non un comando separato di
backfill): un solo comando `uv run ingest-quiz` produce righe complete (testo +
embedding), stesso pattern del corpus (`chunk → embed → store`). Un backfill
separato (`ingest-quiz-embeddings`) aggiungerebbe un orchestrator e un secondo
passaggio sul DB senza vantaggi: scartato.

Modifiche:
- **Schema** (`db/init.sql`): aggiungere `embedding VECTOR(1024)` a `quiz_questions`
  (nullable: la colonna è sempre popolata dalla pipeline, ma nullable evita vincoli
  rigidi e mantiene il truncate+insert semplice). Indice vettoriale **non
  necessario**: le query top-k del giudice sono su `knowledge_chunks`, non su
  `quiz_questions` — qui l'embedding è solo un valore precomputato da leggere.
- **Entità** (`commons/entities/quiz/quiz_question.py`): aggiungere
  `embedding: list[float] | None = None`.
- **Pipeline** (`QuizIndexingPipeline`): nuovo step `_assign_embeddings` tra `map` e
  `store`, identico a quello di `IndexingPipeline` (batch da
  `config.embedding_batch_size`, `embed_passages([q.text for q in batch])`).
- **Builder** (`QuizIndexingPipelineBuilder`): iniettare un `EmbeddingClient`
  (`with_embedding_client`, default `SentenceTransformerEmbeddingClient`), come fa
  `IndexingPipelineBuilder`.
- **Store** (`QuizQuestionStoreRepository.bulk_insert`): aggiungere la colonna
  `embedding` alla INSERT.

**Coerenza dello spazio vettoriale**: bge-m3 **non usa prefissi** (query/passage
vuoti), quindi l'embedding del testo quiz calcolato qui in batch (`embed_passages`)
è **identico** a quello che il giudice avrebbe ottenuto con `embed_query` → stesso
spazio dei chunk del corpus, confronto cosine valido. ⚠️ Se in futuro si tornasse a
un modello con prefissi asimmetrici (es. e5), questo precompute andrebbe fatto col
**query prefix** per restare corretto.

## Reset completo del DB + re-ingestion (runbook)

Decisione: **recreate del volume Docker** (l'`init.sql` aggiornato a `VECTOR(1024)`
ri-crea lo schema da zero, senza duplicare DDL in Python). Il reset azzera **tutto**
il DB (corpus + quiz bank + eventuali mapping), quindi vanno re-ingestati sia gli
articoli sia il quiz.

```bash
# 1. Distrugge e ricrea il volume → init.sql applica lo schema a 1024 dim
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d

# 2. Re-ingestion del corpus normativo (CdS + CAP) con l'embedder locale bge-m3
uv run ingest-knowledge

# 3. Re-ingestion del quiz bank — ora calcola anche l'embedding di ogni domanda
uv run ingest-quiz
```

> `reset-knowledge-db` / `reset-quiz-db` (TRUNCATE per-tabella) **non bastano** qui:
> non cambiano la dimensione della colonna `VECTOR`. Servono solo per un full-reload
> a schema invariato; per il cambio dimensione serve il recreate del volume.

## TDD

Riscrivere `tests/commons/clients/test_embedding_client.py` per il client rinominato
(i test e5 a 384 dim vanno aggiornati al nuovo nome/contratto), mockando
`SentenceTransformer` come già si fa (modulo fittizio in `sys.modules`):

- `embed_passages` con prefissi **vuoti** (default bge-m3): nessun prefisso aggiunto
  agli input, un vettore per input, `normalize_embeddings=True` inoltrato.
- `embed_query` coerente con `embed_passages` (stesso spazio, nessun prefisso di
  default).
- Prefissi custom: passando `query_prefix="query: "` il prefisso viene applicato
  (copre il caso e5 senza una classe dedicata).
- I test di `LiteLLMEmbeddingClient` restano invariati (alternativa A/B).
- Rimuovere il test sull'`ImportError` di `sentence-transformers` (non più lazy).
- `EmbeddingConfig` di default punta a `BAAI/bge-m3` / `vector_dim == 1024`.
- Smoke d'integrazione **opt-in** (`@pytest.mark.integration`, escluso dal run di
  default per via del download/peso): carica davvero bge-m3 e verifica che
  `embed_query` ritorni un vettore di **dimensione reale 1024**.

## Verifica end-to-end

1. `docker compose down -v && up -d` → la tabella `knowledge_chunks` esiste con
   `VECTOR(1024)` (conferma: `\d knowledge_chunks` o
   `SELECT atttypmod FROM pg_attribute …`).
2. `uv run ingest-knowledge` → la tabella si ripopola senza errori di dimensione.
3. `uv run ingest-quiz` → `quiz_questions` ripopolata.
4. Controllo dimensione: `SELECT vector_dims(embedding) FROM knowledge_chunks
   LIMIT 5;` → `1024`.
5. Sanity di similarità: embeddo una query nota (es. "limiti di velocità") e
   verifico che i chunk dell'articolo pertinente compaiano in cima al top-k.

## Documenti da aggiornare a valle

- [tech-stack.md](tech-stack.md): default già descritto come bge-m3 locale (1024);
  verificare solo la coerenza dell'avviso ⚠️ sulla dimensione (oggi cita `1024`).
- [architecture-index.md](architecture-index.md): flusso runtime già aggiornato
  (embedding a runtime solo per i follow-up). Verificare assenza di riferimenti a
  "chiamata paid a OpenRouter" per la spiegazione.
- [ingest--llm-as-judge.md](ingest--llm-as-judge.md): il blocco "Prerequisito" punta
  già a questo piano.

## Stato

⬜ Non avviato. Decisioni prese: **bge-m3 locale, 1024**; client locale
**generalizzato** (`SentenceTransformerEmbeddingClient`, prefissi opzionali);
reset via **recreate del volume Docker** + re-ingestion di corpus e quiz;
**embedding dei quiz offline** dentro `ingest-quiz` (precompute per il giudice).
Implementazione in TDD. Al termine, aggiornare `.claude/architectures/` via
`architecture-doc-keeper`.
