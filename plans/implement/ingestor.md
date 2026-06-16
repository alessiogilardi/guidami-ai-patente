# Piano di implementazione — `guidami_ai_patente_ingestor/`

Riferimento: [architecture-index.md](../architecture-index.md),
[architecture-ingestor.md](../architecture-ingestor.md),
[architecture-code-layout.md](../architecture-code-layout.md),
[commons.md](commons.md) (dipendenza).

## Scope

Pipeline batch che legge `data/processed/cds/codice_della_strada.json` e
`data/processed/cap/codice_rca.json`, li trasforma in `KnowledgeChunk` (da
`commons`), calcola gli embedding e popola `knowledge_chunks` (full reload).

## Entità

- `Article` (entity, in `entities/` o `models/` del package ingestor):
  `number: str`, `title: str`, `text: str`, `paragraphs: list[str]`,
  `url: str`, `scraped_at: str`, `repealed: bool` — mappa 1:1 il JSON
  sorgente.

## Ordine di build / TDD (dal basso, ogni pezzo testabile isolatamente)

### 1. `services/knowledge/article_loader.py` — `ArticleLoader` — ✅ fatto

- `load(path: Path) -> list[Article]`: legge il JSON e mappa in `Article`.
  **Modifica rispetto al piano originale**: rimosso il parametro `source`,
  non utilizzato da `Article` (il `source` è noto al chiamante e viene
  passato direttamente a `ArticleChunker.chunk`, vedi step 2).
- Test: `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_loader.py`,
  fixture in `tests/guidami_ai_patente_ingestor/fixtures/` (`cds_sample.json`:
  articoli 1, 2, 94-bis, 231; `cap_sample.json`: articolo 118 — copiati dai
  dati reali) → verifica mapping corretto dei campi.

### 2. `services/knowledge/article_chunker.py` — `ArticleChunker` — ✅ fatto

Pezzo a più alto valore di test isolato: logica pura, nessun I/O.

- `chunk(article: Article, source: Literal["cds", "cap"]) ->
  list[KnowledgeChunk]`.
- Regole (da architecture-ingestor.md, decisioni 1-3):
  1. Rimuove markup `((...))` via regex da `text` e da ogni `paragraph`
     prima di costruire `chunk_text`.
  2. Genera `comma_index=0` da `article.text` **solo se** `text.strip()` non
     è vuoto dopo la pulizia del markup.
  3. Per ogni `paragraphs[i]`, genera `comma_index=i+1`.
  4. `is_repealed` per ogni chunk = `article.repealed OR "ABROGAT" in
     paragraph.upper()` (check sul testo originale, prima o dopo pulizia
     markup è equivalente perché "ABROGATO" non è dentro `((...))` di norma —
     verificare sul dato reale).
  5. `source_url = article.url`, `article_number = article.number`,
     `article_title = article.title`.

#### Casi limite — fixture usate nei test (dati reali, non sintetici)

| Caso | Fixture | Comportamento atteso |
|---|---|---|
| Articolo normale | CdS art. 1 (`text` non vuoto + `paragraphs`) | chunk 0 da `text`, chunk 1..n da `paragraphs`, markup `((...))` rimosso |
| `text=""` | CAP art. 118 (interamente abrogato) | nessun chunk con `comma_index=0`, si parte da `comma_index=1` |
| Comma "ABROGAT..." in articolo attivo | CdS art. 231 (`repealed=false`, commi 1-2 contengono "abrogat...", comma 3 no) | commi 1-2 → `is_repealed=true`, comma 3 → `is_repealed=false` |
| Articolo interamente abrogato | CdS art. 2 (`repealed: true`, 10 paragraphs) | **tutti** i chunk dell'articolo hanno `is_repealed=true` |
| Numerazione non numerica + markup multiplo | CdS art. `94-bis` | `article_number` resta stringa `"94-bis"`, markup `((da € 543 a € 2.170))` e `((163))` rimossi mantenendo il contenuto |

- **Nota implementativa**: il check `"ABROGAT" in raw_text.upper()` è una
  substring match e scatta anche su forme come "abrogat**e**"/"abrogat**a**",
  non solo su "COMMA ABROGATO" — confermato sui dati reali (CdS art. 231).
  Comportamento accettato così com'è, coerente con la decisione 3 di
  architecture-ingestor.md.
- Fixture: `tests/guidami_ai_patente_ingestor/fixtures/cds_sample.json`
  (articoli 1, 2, 94-bis, 231) e `cap_sample.json` (articolo 118).
- Test: `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_chunker.py`
  — assert su `comma_index`, `is_repealed`, assenza di `((`/`))` in
  `chunk_text`.

### 3. `orchestrators/knowledge_indexing/indexing_pipeline.py` —
   `IndexingPipeline` — ✅ fatto

- Dipendenze iniettate: `ArticleLoader`, `ArticleChunker`, `EmbeddingClient`,
  `VectorStoreClient` (da `commons`), `IngestorConfig`.
- `run() -> None`, layout **flat** (ogni passaggio una riga sequenziale, senza
  nidificazione):
  1. `load`: due chiamate separate ad `ArticleLoader.load(...)`, una per
     `cds_path` e una per `cap_path` — step di load completato prima di
     iniziare il chunking.
  2. `chunk`: per ciascun set di articoli, helper privato `_chunk_articles`
     chiama `ArticleChunker.chunk(article, source)` per ogni articolo →
     `list[KnowledgeChunk]` (senza `embedding`); i due risultati (`cds`,
     `cap`) vengono concatenati.
  3. `embed`: helper privato `_assign_embeddings` itera i chunk a batch di
     `config.embedding_batch_size`, chiama `EmbeddingClient.embed_passages([c.chunk_text
     for c in batch])` e assegna `chunk.embedding` in place (campo mutabile,
     non frozen).
  4. `load`: `VectorStoreClient.truncate()` poi `bulk_insert(chunks)`.
- Test: `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_indexing/test_indexing_pipeline.py`
  — unit, nessun I/O reale. Un test usa `ArticleLoader`/`ArticleChunker` reali
  sulle fixture esistenti (cds/cap sample) con `EmbeddingClient`/`VectorStoreClient`
  mockati, verifica batching degli embedding e che `truncate()` precede
  `bulk_insert()`; un secondo test mocka anche `ArticleLoader`/`ArticleChunker`
  per verificare che **entrambi** i load avvengano prima di qualsiasi chunk
  (step separati, non interlacciati).
- Test di integrazione contro Postgres reale (full pipeline con modello e DB
  veri) **rimandato**, da marcare `@pytest.mark.integration` quando
  implementato — non bloccante per questo step.

### 4. `orchestrators/knowledge_indexing/indexing_pipeline_builder.py` —
   `IndexingPipelineBuilder` — ✅ fatto

- Valida `IngestorConfig` (esistenza di `cds_path`/`cap_path`, fail-fast con
  `FileNotFoundError` **prima** di istanziare `LiteLLMEmbeddingClient` o
  `VectorStoreClient` — apre connessione Postgres), istanzia le dipendenze
  concrete (`LiteLLMEmbeddingClient`, `VectorStoreClient`, `ArticleLoader`,
  `ArticleChunker`) e assembla `IndexingPipeline`.
- Nessuna classe di eccezioni dedicata: `FileNotFoundError` con messaggio
  chiaro è sufficiente a questa scala (coerente con KISS).
- Test: `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_indexing/test_indexing_pipeline_builder.py`
  — verifica che path sorgente mancanti facciano fallire `build()` con
  `FileNotFoundError` **senza** istanziare `LiteLLMEmbeddingClient`/
  `VectorStoreClient` (mockati per fallire il test se chiamati). Il caso
  "path validi → pipeline costruita" richiederebbe `OPENROUTER_API_KEY` e
  connessione Postgres reale: rimandato a test di integrazione futuro.

### 5. `configs/ingestor_config.py` — `IngestorConfig` — ✅ fatto

- Campi: `cds_path` (default `data/processed/cds/codice_della_strada.json`),
  `cap_path` (default `data/processed/cap/codice_rca.json` — **non**
  `codice_assicurazioni_private.json`, che contiene 610 articoli del codice
  completo invece dei 96 rilevanti per RCA, vedi `architecture-ingestor.md`),
  `embedding_batch_size` (default 64), `embedding: EmbeddingConfig` (default
  `EmbeddingConfig()`), `vector_store: VectorStoreConfig` (obbligatorio, nessun
  default — `user`/`password` arrivano da env).
- **Modifica rispetto al piano originale**: `pydantic_settings.BaseSettings`
  (non `BaseModel`) con `model_config = SettingsConfigDict(frozen=True,
  env_nested_delimiter="__", env_file=".env",
  yaml_file="configs/ingestor_config.yaml")` — config a due livelli: YAML
  committato (non-secret) + env/`.env` (solo `VECTOR_STORE__USER`/
  `VECTOR_STORE__PASSWORD`). `settings_customise_sources` dà precedenza a
  env/`.env` sul YAML. Nuova dipendenza `pydantic-settings[yaml]`. Dettagli
  completi in `.claude/architectures/ingestor.md`.
- Test: `tests/guidami_ai_patente_ingestor/configs/test_ingestor_config.py` —
  default dei path, caricamento da YAML, override da env, precedenza
  env > YAML, immutabilità (`frozen=True`).

### 6. `main.py` + script CLI — ✅ fatto

- `main()`: costruisce `config = IngestorConfig()` (campi popolati a runtime
  da env/`.env`/YAML, `# pyright: ignore[reportCallIssue]`), assembla la
  pipeline via `IndexingPipelineBuilder(config).build()` e chiama `run()`.
- **Modifica rispetto al piano originale**: niente `os.environ["DATABASE_URL"]`
  — i secrets (`VECTOR_STORE__USER`/`VECTOR_STORE__PASSWORD`) e la config
  non-secret (YAML) sono caricati da `IngestorConfig` stesso (config a due
  livelli, vedi step 5), unico punto di caricamento config come da regola
  architetturale.
- Registrato `ingest-knowledge = "guidami_ai_patente_ingestor.main:main"` in
  `[project.scripts]`.

## File layout (da architecture-code-layout.md)

```
guidami_ai_patente_ingestor/
  __init__.py
  orchestrators/
    __init__.py
    knowledge_indexing/
      __init__.py
      indexing_pipeline.py
      indexing_pipeline_builder.py
  services/
    knowledge/
      __init__.py
      article_loader.py
      article_chunker.py
  entities/
    __init__.py
    article.py
  configs/
    __init__.py
    ingestor_config.py
  main.py
```

## Stato

Step 1-6 completati: `Article`, `ArticleLoader`, `ArticleChunker`,
`IndexingPipeline`, `IndexingPipelineBuilder`, `IngestorConfig`, `main.py` +
script `ingest-knowledge`. `uv run pytest tests/guidami_ai_patente_ingestor/`
(13 test) e `ruff check`/`pyright` su `src/guidami_ai_patente_ingestor` e
relativi test puliti. Resta da fare (non bloccante): test di integrazione end
to end contro Postgres + modello reali (`@pytest.mark.integration`).
