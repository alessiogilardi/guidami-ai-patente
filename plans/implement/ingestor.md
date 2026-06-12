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
   `IndexingPipeline`

- Dipendenze iniettate: `ArticleLoader`, `ArticleChunker`, `EmbeddingClient`,
  `VectorStoreClient` (da `commons`), `IngestorConfig`.
- `run() -> None`:
  1. `load`: `ArticleLoader.load(...)` per `cds` e `cap`.
  2. `chunk`: `ArticleChunker.chunk(article, source)` per ogni articolo →
     `list[KnowledgeChunk]` (senza `embedding`).
  3. `embed`: `EmbeddingClient.embed_passages([c.chunk_text for c in
     chunks])` in batch (size configurabile), assegna `chunk.embedding`.
  4. `load`: `VectorStoreClient.truncate()` poi `bulk_insert(chunks)`.
- Test: integrazione contro Postgres del compose (richiede `commons` step 4
  e 1 completati) — verifica conteggio righe finale == numero chunk generati
  dall'`ArticleChunker` sui dati reali (o su un sottoinsieme).

### 4. `orchestrators/knowledge_indexing/indexing_pipeline_builder.py` —
   `IndexingPipelineBuilder`

- Valida `IngestorConfig`, istanzia le dipendenze concrete (`E5SmallEmbeddingClient`,
  `VectorStoreClient`, `ArticleLoader`, `ArticleChunker`) e assembla `IndexingPipeline`.

### 5. `configs/ingestor_config.py` — `IngestorConfig`

- Path ai JSON sorgente (`cds_path`, `cap_path`, default da
  `data/processed/...`), batch size embedding, aggrega `EmbeddingConfig` e
  `VectorStoreConfig` di `commons`.

### 6. `main.py` + script CLI

- `main()`: carica `IngestorConfig` (da env/yaml), costruisce pipeline via
  `IndexingPipelineBuilder`, chiama `run()`.
- Registra `ingest-knowledge = "guidami_ai_patente_ingestor.main:main"` in
  `[project.scripts]`.

## File layout (da architecture-code-layout.md)

```
guidami_ai_patente_ingestor/
  __init__.py
  orchestrators/
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

Step 1-2 completati (`Article`, `ArticleLoader`, `ArticleChunker`, con test su
fixture reali). `ruff check` e `pyright` su `src/guidami_ai_patente_ingestor`
e relativi test puliti. Prossimo step: 3 (`IndexingPipeline`).
