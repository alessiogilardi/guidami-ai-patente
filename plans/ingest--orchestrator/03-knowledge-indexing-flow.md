# SP03 — Flow knowledge indexing

> **Stato: ✅ COMPLETATO** (2026-06-22).
>
> **File creati:**
> - `src/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/__init__.py`
> - `src/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/load_enriched_articles_step.py`
> - `src/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/chunk_articles_step.py`
> - `src/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/embed_chunks_step.py`
> - `src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py`
> - `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/__init__.py`
> - `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_load_enriched_articles_step.py`
> - `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_chunk_articles_step.py`
> - `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_embed_chunks_step.py`
> - `tests/guidami_ai_patente_ingestor/orchestrators/test_knowledge_flows.py`
>
> **File modificati:**
> - `src/guidami_ai_patente_ingestor/orchestrators/context_keys.py` (aggiunto `ARTICLES_BY_SOURCE`)
> - `src/guidami_ai_patente_ingestor/orchestrators/__init__.py` (re-export `build_knowledge_indexing_flow`)
> - `src/guidami_ai_patente_ingestor/configs/pipeline_layer_config.py` (aggiunto `sources: list[str]`)
> - `src/guidami_ai_patente_ingestor/configs/ingestor_config.py` (valorizzato `sources` per tutte le pipeline)
> - `configs/ingestor_config.yaml` (aggiunto campo `sources` per tutte le pipeline)
>
> **Verifiche verdi:** 22 test unit passati (+ 1 integration deselezionato per Postgres assente),
> pyright 0 errori, ruff clean sui file SP03. `IndexingPipeline`/builder non rimossi.
> `ENRICHED_ARTICLES` mantenuta. `EmbedStep` generico non toccato.

## Scopo singolo
Ricostruire l'indicizzazione del corpus normativo come **Flow flowstep**: corpus `enriched`
(cds+cap) → chunk → embed (solo non-repealed) → `knowledge_chunks`. Sostituisce
`IndexingPipeline` + builder.

## Dipende da
SP02 (`DbStoreStep`, `context_keys`) e SP01 (`EmbeddingService`). **Non** usa l'`EmbedStep`
generico: il knowledge ha un embedding con filtro repealed di dominio → step dedicato
(`EmbedChunksStep`, vedi sotto). L'`EmbedStep` generico resta usato dal solo quiz (SP04).

## Mappatura Flow
`LoadEnrichedArticlesStep` → `ChunkArticlesStep` → `EmbedChunksStep` → `DbStoreStep(items_key=CHUNKS)`

Chiave context **unica** `CHUNKS` per tutta la catena dopo il chunking. Niente seconda chiave per
il sottoinsieme da embeddare: il filtro repealed è un dettaglio **interno** a `EmbedChunksStep`
(esattamente come `_filter_chunks` era interno a `_assign_embeddings` nel baseline).

## Comportamento da preservare (vincolante)
Baseline (`indexing_pipeline.py:72-89`): il filtro repealed agisce **solo sull'embedding**, non
sullo store. Con `embed_repealed=False` i chunk repealed vengono **comunque inseriti** in
`knowledge_chunks`, con `embedding=NULL`; solo i non-repealed ricevono il vettore.
`EmbedChunksStep` muta gli item **in place** e `DbStoreStep` legge la lista intera → i repealed
restano a `None`. (Il retrieval a valle filtrerà `embedding IS NOT NULL` — fuori scope qui.)

## Stato attuale (riferimento)
`orchestrators/knowledge_indexing/indexing_pipeline.py`:
- `run()` carica cds+cap via `EnrichedArticleRepository.load(layer_resolver.path(input_layer, src))`;
- `_chunk_articles` delega `ArticleChunker.chunk(article, source)` e appiattisce;
- `_assign_embeddings`: filtro repealed locale (`_filter_chunks`, salvo `config.embed_repealed`) →
  embedding in batch assegnato **in place**; lo store usa la lista **non** filtrata → repealed
  con `embedding=NULL`;
- poi truncate + bulk_insert.

## Componenti

### Nuovi (step di dominio) — `orchestrators/steps/knowledge/`
- **`LoadEnrichedArticlesStep`**:
  iniettati `EnrichedArticleRepository`, `LayerResolver`, `input_layer: str`, `sources: list[str]`
  (es. `["cds","cap"]`). `execute`: per ogni source carica → `put(ARTICLES_BY_SOURCE,
  dict[str, list[EnrichedArticle]])`. `required=set()`, `produced={ARTICLES_BY_SOURCE}`.
  *(`SOURCE` non serve qui: l'indexing carica tutte le source in un colpo, niente runner —
  coerente con SP07 `index → flow.run()` senza runner.)*
- **`ChunkArticlesStep`**: delega `ArticleChunker.chunk(article, source)` e appiattisce.
  **Solo chunking, nessun filtro repealed.** Itera le coppie `(source, articles)` del dict.
  `required={ARTICLES_BY_SOURCE}`, `produced={CHUNKS}`.
  - Nota tipi: le chiavi del dict sono `str`, ma `ArticleChunker.chunk` vincola
    `source: Literal["cds","cap"]` → cast/narrowing esplicito al confine
    (`cast(Literal["cds","cap"], source)` o validazione contro un set noto).
- **`EmbedChunksStep`**: iniettati `EmbeddingService` (SP01) e `embed_repealed: bool`.
  `required={CHUNKS}`, `produced={CHUNKS}`. `execute`:
  ```python
  chunks = cast(list[KnowledgeChunk], context.get(context_keys.CHUNKS))
  to_embed = chunks if self._embed_repealed else [c for c in chunks if not c.is_repealed]
  vectors = self._embedding_service.embed(to_embed)
  for chunk, vector in zip(to_embed, vectors, strict=True):
      chunk.embedding = vector
  context.put(context_keys.CHUNKS, chunks)
  ```
  - **Composizione pura**, niente ereditarietà da `EmbedStep`: si accettano le ~3 righe del
    loop di assegnazione duplicate (decisione: no Template Method, no helper condiviso,
    `EmbedStep`/SP02 intatti).
  - Domain-specific (conosce `is_repealed`) → vive in `steps/knowledge/`, mai in `services/`.
  - `produced={CHUNKS}` ri-dichiara una chiave già disponibile → `FlowValidator` emette il
    WARNING benigno *"Produced key overwrites an already available key"* (non ERROR, non blocca
    `build(validate=True)`).

### Nuovi (flow factory) — `orchestrators/knowledge_flows.py`
- `build_knowledge_indexing_flow(config, layer_resolver, embedding_client, postgres_client, ...) -> Flow`:
  istanzia gli step concreti +
  `EmbedChunksStep("embed_chunks", EmbeddingService(embedding_client, config.embedding_batch_size), config.embed_repealed)` +
  `DbStoreStep("store_chunks", KnowledgeChunkStoreRepository(...), context_keys.CHUNKS)` e
  `FlowBuilder("knowledge_indexing").add_step(...).build(validate=True)`.
  - `input_layer` letto da `config.knowledge_indexing.input_layer` (già esistente).
  - `sources`: **introdotto in `IngestorConfig`** (decisione presa). Oggi è hardcoded `"cds"/"cap"`
    in `run()`; va spostato in config come fonte unica, condivisa con prep (SP05) e CLI (SP07).
    - Stato attuale config: esiste già `IngestorConfig.sources: dict[str, SourceConfig]` (catalogo
      dir/file con chiavi `cds`/`cap`/`quiz` **mischiate**) e `knowledge_indexing: PipelineLayerConfig`
      (oggi solo `input_layer`/`output_layer`).
    - Intervento: aggiungere `sources: list[str]` a `PipelineLayerConfig` (selettore dei source
      key di **quella** pipeline → indicizza il catalogo `IngestorConfig.sources`). Default:
      `knowledge_indexing` → `["cds","cap"]`. La factory passa `config.knowledge_indexing.sources`
      a `LoadEnrichedArticlesStep`.
    - ⚠️ **Modifica config condivisa**: `PipelineLayerConfig` è usata anche da
      `knowledge_preparation`/`quiz_preparation`/`quiz_indexing` → il campo va valorizzato anche lì
      (knowledge_* = `["cds","cap"]`, quiz_* = `["quiz"]`). Coordinare con SP04/SP05.
  - **Ogni `Step` richiede `name`** come primo argomento posizionale (firma SP02
    `Step.__init__(self, name)`): le factory devono passarlo (era omesso nelle bozze precedenti).

### Modificati (context keys) — `src/guidami_ai_patente_ingestor/orchestrators/context_keys.py`
⚠️ **File reale da modificare** (creato da SP02, già committato). Intervento **solo additivo**
sul blocco *Knowledge indexing*:
- **Aggiungere** `ARTICLES_BY_SOURCE = "articles_by_source"`: il knowledge indexing usa un dict
  per-source — non una lista piatta — perché la `source` serve per-articolo a `ArticleChunker.chunk`.
- **NON rimuovere `ENRICHED_ARTICLES`**: SP03 non la consuma (usa `ARTICLES_BY_SOURCE`), ma la
  chiave è **usata da SP05** — il flow di enrichment la produce in `ContextualizeStep` e la
  consuma in `WriteEnrichedStep` (`05-knowledge-preparation-flow.md`). Rimuoverla romperebbe SP05.
- **Non** serve `EMBEDDABLE_CHUNKS`: chiave unica `CHUNKS`.

Diff concreto del blocco (solo aggiunta):
```diff
 # --- Knowledge indexing (SP03) ---
 ENRICHED_ARTICLES = "enriched_articles"    # input enrich (SP05) — NON rimuovere
+ARTICLES_BY_SOURCE = "articles_by_source"  # input indexing: dict[str, list[EnrichedArticle]] per source
 CHUNKS = "chunks"                          # output del chunker → embed (solo non-repealed) → store
```
> ⚠️ **Edit condiviso (annotazione per i piani successivi)**: `context_keys.py` è modificato
> anche da **SP05** (aggiunge `PARSED_ARTICLES`/`CLEANED_ARTICLES`, riusa `ENRICHED_ARTICLES`) e
> **SP06** (`IMAGE_DESCRIPTIONS`). Tutti gli interventi sono additivi → coordinare il merge, non
> rimuovere chiavi altrui.
> Le chiavi del blocco *Quiz indexing* (`ENRICHED_QUIZ`, `EMBEDDABLE_QUIZ`, `QUIZ_ENTITIES`)
> restano invariate (le usa SP04).

### Modificati (re-export)
- `orchestrators/steps/knowledge/__init__.py` (re-export `LoadEnrichedArticlesStep`,
  `ChunkArticlesStep`, `EmbedChunksStep`) + `orchestrators/__init__.py` (re-export
  `build_knowledge_indexing_flow`).
- ⚠️ **Conflitto di merge con SP05**: `knowledge_flows.py`, `steps/knowledge/__init__.py`,
  `orchestrators/__init__.py` e `context_keys.py` sono toccati anche da SP05 (parallelo nel DAG).
  Coordinare: chi merga per primo crea lo scheletro dei file/package condivisi.

### Invariati
- `main.py` (entry point legacy): **lasciato com'è** fino a SP07 (cutover atomico). Niente
  ripuntamento anticipato al nuovo flow (la validazione e2e si fa via test di integrazione).

## TDD
- `ChunkArticlesStep`: dato `ARTICLES_BY_SOURCE` con due source (fake), produce i chunk di tutte;
  **nessun filtro** (i repealed sono presenti nell'output); contratto `{ARTICLES_BY_SOURCE}→{CHUNKS}`.
- `EmbedChunksStep`:
  - `embed_repealed=False`: i chunk repealed restano con `embedding=None` ma **presenti** in
    `CHUNKS`; i non-repealed hanno il vettore atteso.
  - `embed_repealed=True`: tutti embeddati.
  - contratto chiavi `{CHUNKS}→{CHUNKS}`.
- `LoadEnrichedArticlesStep`: carica tutte le source configurate (fake repo) → dict per source;
  `required=set()`, `produced={ARTICLES_BY_SOURCE}`.
- Flow factory: `build(validate=True)` non solleva (solo WARNING benigno "overwrites" su `CHUNKS`
  da `EmbedChunksStep`); `required_input_keys == set()` (il load non richiede input esterni).
- Integration (`@pytest.mark.integration`): flow completo su Postgres →
  - conteggio righe `knowledge_chunks` == baseline pre-refactor (tutti i chunk, repealed inclusi);
  - chunk repealed con `embedding IS NULL`, non-repealed con vettore valorizzato.

## Done criteria
- Flow knowledge indexing eseguibile e verde (unit + integration), chiave unica `CHUNKS`.
- Comportamento repealed identico al baseline (storati con `embedding=NULL`, solo i non-repealed
  embeddati).
- `context_keys` esteso con `ARTICLES_BY_SOURCE` (additivo); `ENRICHED_ARTICLES` **mantenuta**
  (la usa SP05).
- `EmbedStep` generico **non** usato dal knowledge (resta per il quiz, SP04); `EmbedStep`/SP02 intatti.
- `IndexingPipeline`/builder **non ancora rimossi** (rimozione in SP07).
