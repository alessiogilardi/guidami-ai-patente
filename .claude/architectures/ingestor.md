# Package `src/guidami_ai_patente_ingestor/`

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/architecture-code-layout.md`, `plans/implement/ingestor.md`.

Pipeline batch di indicizzazione del corpus normativo (CdS + CAP) in
`knowledge_chunks`. Dipende da `commons` (modelli, client embedding/vector
store, config condivise).

## Layout

```
src/guidami_ai_patente_ingestor/
  entities/
    article.py                    # Article — mappa 1:1 il JSON sorgente (number, title, text,
                                   # paragraphs, url, scraped_at, repealed)
  services/
    knowledge/
      article_loader.py           # ArticleLoader.load(path) -> list[Article]
      article_chunker.py          # ArticleChunker.chunk(article, source) -> list[KnowledgeChunk]
  orchestrators/
    knowledge_indexing/
      indexing_pipeline.py          # IndexingPipeline
      indexing_pipeline_builder.py  # IndexingPipelineBuilder
  configs/
    ingestor_config.py            # IngestorConfig (frozen)
  main.py                          # entry point CLI (uv run ingest-knowledge)
```

## Decisioni implementate

- **`ArticleLoader.load(path: Path) -> list[Article]`**: nessun parametro
  `source` (diverso dal piano originale) — il `source` ("cds"/"cap") è noto al
  chiamante e passato direttamente ad `ArticleChunker.chunk`.

- **`ArticleChunker.chunk(article, source) -> list[KnowledgeChunk]`**: logica
  pura, nessun I/O, nessuna config iniettata.
  - rimuove il markup `((...))` di normattiva via regex
    (`_MARKUP_PATTERN = re.compile(r"\(\((.*?)\)\)", re.DOTALL)`), mantenendo
    il testo interno;
  - `comma_index=0` generato da `article.text` solo se non vuoto dopo pulizia
    markup; `comma_index=i+1` per ogni `paragraphs[i]`;
  - `is_repealed = article.repealed OR "ABROGAT" in raw_text.upper()` —
    substring match, scatta anche su forme come "abrogat**e**"/"abrogat**a**"
    (non solo "COMMA ABROGATO"), confermato su dati reali (CdS art. 231) e
    accettato così com'è.

- **`IndexingPipeline.run()`** — layout flat, step sequenziali senza
  nidificazione:
  1. due chiamate separate `ArticleLoader.load()` (`cds_path`, `cap_path`) —
     load completato prima di iniziare il chunking;
  2. `_chunk_articles` (helper privato) per cds e cap separatamente, poi
     concatenazione dei chunk;
  3. `_assign_embeddings` (helper privato): batch di
     `config.embedding_batch_size`, `EmbeddingClient.embed_passages()` e
     assegnazione di `chunk.embedding` in place (campo mutabile);
  4. `VectorStoreClient.truncate()` poi `bulk_insert(chunks)` (full reload).
  - Dipendenze iniettate via costruttore: `ArticleLoader`, `ArticleChunker`,
    `EmbeddingClient` (ABC, `commons`), `VectorStoreClient` (`commons`),
    `IngestorConfig`.

- **`IndexingPipelineBuilder`**: valida l'esistenza di `cds_path`/`cap_path`
  con `FileNotFoundError` fail-fast **prima** di istanziare
  `E5SmallEmbeddingClient` (carica il modello sentence-transformers) o
  `VectorStoreClient` (apre connessione Postgres). `_validate_source_paths`
  aggrega tutti i path mancanti in un unico `FileNotFoundError` (report
  completo, non solo il primo). Nessuna classe di eccezioni dedicata —
  `FileNotFoundError` con messaggio chiaro, coerente con KISS a questa scala.
  - Setter fluent `with_article_loader`, `with_article_chunker`,
    `with_embedding_client`, `with_vector_store_client` (ritornano `Self`)
    per assegnare ogni dipendenza concreta prima di `build()`. `build()` usa
    controlli espliciti `is not None` (non `or`) per scegliere tra
    dipendenza assegnata e default, per evitare problemi di truthiness se in
    futuro una di queste classi implementasse `__bool__`.
  - `main.py` (composition root) chiama tutti e quattro i `with_*`
    esplicitamente — wiring delle dipendenze concrete visibile a colpo
    d'occhio nell'entry point, coerente con "explicit over implicit". I
    default interni del builder restano comunque disponibili per chi
    costruisce la pipeline con override parziali (es. nei test).

- **`IngestorConfig`** (Pydantic `BaseModel`, `frozen=True`):
  - `cds_path: Path = Path("data/processed/cds/codice_della_strada.json")`
  - `cap_path: Path = Path("data/processed/cap/codice_rca.json")` — **non**
    `codice_assicurazioni_private.json` (610 articoli, codice completo);
    `codice_rca.json` contiene i 96 articoli rilevanti per RCA/patente.
  - `embedding_batch_size: int = 64`
  - `embedding: EmbeddingConfig = EmbeddingConfig()` (default `commons`)
  - `vector_store: VectorStoreConfig` (obbligatorio, `database_url` richiesto
    senza default)

- **`main.py`**: legge `DATABASE_URL` da `os.environ` direttamente — nessuna
  dipendenza `pydantic-settings` introdotta (per un'unica env var è la
  soluzione più semplice; da rivalutare se in futuro nascerà un `AppConfig`
  condiviso più ampio con l'app). Config caricata solo qui (entry point).
  Wiring delle dipendenze concrete (`ArticleLoader`, `ArticleChunker`,
  `E5SmallEmbeddingClient`, `VectorStoreClient`) esplicito tramite i `with_*`
  del builder (vedi sopra). Script registrato:
  `ingest-knowledge = "guidami_ai_patente_ingestor.main:main"`.

- **`repositories/`**: non presente nell'ingestor — `IndexingPipeline` scrive
  solo `truncate()` + `bulk_insert()` su `VectorStoreClient` (nessuna logica
  di query da nascondere). `KnowledgeRepository` è previsto solo per l'app
  FastAPI (vedi `plans/architecture-code-layout.md`).

- **Logging**: nessun componente dedicato (niente `LoggingConfig`/
  `LoggingService` in `commons`) — scelta deliberata per evitare
  overengineering, si usa direttamente lo stdlib `logging`.
  - `main.py` (composition root) chiama
    `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")`
    all'inizio di `main()`, prima di qualsiasi altro log; `logger =
    logging.getLogger(__name__)` a livello di modulo, con log `info` di
    inizio/fine pipeline ("starting indexing pipeline" / "indexing pipeline
    completed").
  - `indexing_pipeline.py`: `logger = logging.getLogger(__name__)` a livello
    di modulo, log `info` in `run()`:
    - dopo il load: conteggio articoli CdS/CAP caricati;
    - dopo il chunking: conteggio chunk CdS/CAP/totali;
    - in `_assign_embeddings`: una riga per batch (`embedding batch
      {n}/{total} ({size} chunks)`);
    - prima di `truncate()`: numero di chunk da inserire;
    - dopo `bulk_insert()`: completamento.
  - **Convenzione**: i messaggi di log sono in inglese (a differenza di
    docstring/commenti, in italiano), per coerenza con eventuali strumenti di
    log aggregation/osservabilità.

## Test

- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_loader.py`,
  `test_article_chunker.py` — su fixture reali (`tests/.../fixtures/cds_sample.json`,
  `cap_sample.json`, copiate da dati reali CdS/CAP, casi limite: articolo
  interamente abrogato, `text=""`, comma singolarmente abrogato, numerazione
  non numerica con markup multiplo).
- `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_indexing/test_indexing_pipeline.py` —
  unit, nessun I/O reale: batching degli embedding, ordine
  `truncate()`→`bulk_insert()`, load di entrambe le fonti completato prima del
  chunking.
- `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_indexing/test_indexing_pipeline_builder.py` —
  path sorgente mancanti → `FileNotFoundError` senza istanziare
  `E5SmallEmbeddingClient`/`VectorStoreClient`.
- `tests/guidami_ai_patente_ingestor/configs/test_ingestor_config.py` —
  default path, `vector_store` obbligatorio, immutabilità (`frozen=True`).
- **Non ancora implementato**: test di integrazione end-to-end contro
  Postgres + modello reali (da marcare `@pytest.mark.integration`).
