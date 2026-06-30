# Ingestor — Pipeline corpus normativo (CdS + CAP)

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/implement/ingestor.md`, `plans/ingest--data-preparation.md`,
`plans/ingest--orchestrator/05-knowledge-preparation-flow.md`.

Questo documento copre l'**indexing** (`enriched` → chunk → embed → DB, SP03).
Vedi [data_preparation.md](data_preparation.md) per la **preparation**
(`parsed` → `cleaned` → `enriched`, ricostruita su due flow flowstep per-source
in SP05: `build_knowledge_cleaning_flow`, `build_knowledge_enrichment_flow`,
`run_preparation`, building block generici `LoadJsonStep`/`MapStep`/`WriteJsonStep`/
`EnrichDataStep` + `ContextEnricher` domain-specific, `ArticleMapper`).
Vedi [config_and_entrypoints.md](config_and_entrypoints.md) per `IngestorConfig`,
`LayerResolver` e gli entry point CLI.

## Decisioni implementate

### `repositories/` — struttura `db/` + `json/`

- Il package `repositories/` è suddiviso in due sub-package per tipo di
  storage:
  - `db/` — Postgres (psycopg v3): `KnowledgeChunkStoreRepository`,
    `QuizQuestionStoreRepository`.
  - `json/` — file system JSON: `ArticleRepository`,
    `EnrichedArticleRepository`, `QuizBankRepository`,
    `EnrichedQuizBankRepository`.
- Il `__init__.py` top-level re-esporta tutti e 6 i repository: i caller
  (orchestrators, test, entry point) importano da
  `guidami_ai_patente_ingestor.repositories` senza conoscere la suddivisione
  interna — zero breaking change rispetto alla struttura flat precedente.

### `repositories/json/_json_repository.py` — `JsonRepository[T: BaseModel]`

- Classe base generica (Python 3.12 native generics) per tutti i repository
  JSON. Prefisso `_` → privata al sub-package, non re-esportata da nessun
  `__init__.py`.
- `__init__`: ispeziona `__orig_bases__` della classe concreta per dedurre
  il tipo Pydantic `T` (es. `ParsedArticleModel` da `ArticleRepository(JsonRepository[ParsedArticleModel])`);
  lancia `TypeError` se il tipo non viene trovato.
- `load(path: Path) -> list[T]`: legge JSON e valida ogni elemento con
  `T.model_validate()`.
- `write(items: list[T], path: Path) -> None`: crea le directory mancanti
  (`mkdir(parents=True, exist_ok=True)`), serializza con
  `json.dumps(..., ensure_ascii=False, indent=2)`.
- Le quattro sottoclassi (`ArticleRepository`, `EnrichedArticleRepository`,
  `QuizBankRepository`, `EnrichedQuizBankRepository`) non aggiungono né
  `__init__` né metodi: ereditano tutto dalla base.

### `repositories/json/` — `ArticleRepository`

- Estende `JsonRepository[ParsedArticleModel]`; eredita `load` e `write` senza
  aggiungere codice. Il caller importa da `guidami_ai_patente_ingestor.repositories`
  (top-level `__init__.py`), non dal sub-package interno.
- Nessun parametro `source`: il `source` ("cds"/"cap") è noto al chiamante
  e passato direttamente ad `ArticleChunker.chunk`.

### `services/knowledge/article_cleaner.py` — `ArticleCleaner`

- Servizio puro (`clean(article: ParsedArticleModel) -> ParsedArticleModel`), nessun I/O, nessuna
  config iniettata. Ritorna una copia (`article.model_copy(update={...})`)
  con `title`, `text`, `paragraphs` puliti dal markup normattiva.
- **Titolo** (`_clean_title`): rimuove le parentesi superflue che avvolgono
  il titolo (`"(Titolo)."` / `"(Titolo)"` → `"Titolo"`); gestisce anche il
  caso in cui la chiusura manchi per un difetto upstream dello scraper.
- **Testo articolo** (`_clean_text`): rimuove il markup inline
  `((...))` via `_INLINE_MARKUP_PATTERN = re.compile(r"\(\((.*?)\)\)",
  re.DOTALL)`, mantenendo il testo interno. Se dopo la sostituzione resta
  markup non bilanciato (`"(("` o `"))"` ancora presenti — segno che un
  titolo è finito nel campo `text`), il testo viene **scartato** (diventa
  `""`).
- **Commi** (`_clean_paragraphs`): normalizza l'array `paragraphs` gestendo
  i casi limite osservati sui dati reali CdS/CAP:
  - marcatori standalone `"(("`/`"))"` che avvolgono range di commi già
    numerati → scartati senza perdere i commi interni;
  - riferimenti a note a margine come `"((171))"` → scartati (diventano
    rumore residuo dopo la rimozione dell'ordinale, stringa vuota non
    appesa);
  - commi interamente avvolti in `((...))` → markup rimosso, comma
    mantenuto;
  - commi con elenco a)/b)/c)/d) spalmati su più elementi dell'array →
    fusi in un unico comma (buffer accumulato fino al marcatore di
    chiusura `"))"`);
  - numerazione ordinale dei commi (es. `"1. "`, `"10-bis. "`, anche senza
    punto dopo l'ordinale) rimossa via
    `_ORDINAL_PREFIX_PATTERN = re.compile(r"^(\d+(?:-\w+)?\.?)\s*")` (il
    token ordinale è catturato nel gruppo 1, riusato per il controllo di
    duplicazione sotto);
  - markup inline multiplo all'interno dello stesso comma gestito dalla
    stessa `_INLINE_MARKUP_PATTERN.sub`.
  - **ordinale duplicato nel dato sorgente** (difetto upstream, es.
    `"2. 2. Nell'archivio nazionale..."` nell'art. 226 CdS): dopo aver
    rimosso il primo ordinale, se il resto inizia con lo stesso identico
    token ordinale (`duplicate.group(1) == match.group(1)`, confronto per
    identità esatta del token, non solo "è un numero"), viene rimosso anche
    quello. Questo evita di scartare per errore commi che iniziano
    legittimamente con un numero diverso dall'ordinale (es.
    `"2. 5 milioni di euro..."`, dove `"5"` ≠ `"2."` e quindi resta).
  - `_append_cleaned` è l'unico punto che applica markup-stripping +
    rimozione ordinale + rimozione ordinale duplicato + filtro "remainder
    vuoto" prima di appendere a `merged`.


### `services/knowledge/article_chunker.py` — `ArticleChunker`

Implementa `UseCase[EnrichedArticleModel, list[EmbeddableChunkModel]]`.

- `source` iniettata nel costruttore (`ArticleChunker(source: str)`): non viene
  più passata per chiamata. Questo permette di usare `chunker.execute` come
  funzione callable in `MapStep` senza adattatori.
- `execute(enriched_article: EnrichedArticleModel) -> list[EmbeddableChunkModel]`:
  `comma_index=0` generato da `article.text` **solo `if article.text:`**
  (testo non vuoto dopo cleaning); `comma_index=i+1` per ogni `paragraphs[i]`.
  Usa `ArticleMapper.from_enriched_to_embeddable_chunk(model, source, comma_index, raw_text)`
  per costruire ogni `EmbeddableChunkModel` invece di istanziare il modello inline.
- Popola `chunk.context = enriched_article.contexts.get(comma_index, "")`.
  Se `contexts` è `{}` (articolo non arricchito o abrogato), `context`
  resta `""`.
- `is_repealed = article.repealed OR "ABROGAT" in raw_text.upper()` —
  substring match, scatta anche su forme come "abrogat**e**"/"abrogat**a**"
  (non solo "COMMA ABROGATO"), confermato su dati reali (CdS art. 231) e
  accettato così com'è.

### `models/knowledge/embeddable_chunk.py` — `EmbeddableChunkModel`

- DTO intermedio per il calcolo dell'embedding di un chunk, speculare a
  `KnowledgeChunk` (stessi campi) ma con `embedded_text: str` property —
  separato dall'entità DB per disaccoppiare il testo da embeddare dalla
  scrittura su Postgres.
- `embedded_text`: `"\n".join(part for part in [article_title, context, chunk_text] if part)` —
  concatena titolo, contesto (se presente) e testo del chunk, scartando le
  parti vuote. Se `context` è vuoto, il risultato è `"article_title\nchunk_text"`.
- `embedding: list[float] | None = None` — valorizzato in place da
  `EmbedChunksStep`; `None` per i chunk repealed esclusi dall'embed.
- Soddisfa il protocollo `Embeddable` (ha `embedded_text`) e `Embedded`
  (ha `embedding`): entrambi usati da `EmbeddingService`.
- Prodotto da `ArticleChunker.chunk(enriched_article, source)`; convertito in
  `KnowledgeChunk` (entità DB-only, senza `embedded_text`) da
  `ArticleMapper.from_embeddable_chunk_to_knowledge_chunk`.

### `orchestrators/steps/knowledge/` — step di dominio knowledge (SP03)

Tre step flowstep domain-specific per il knowledge indexing. Vivono in
`orchestrators/steps/knowledge/`, mai in `services/` (la dipendenza va verso
`commons.flowstep`, non il contrario). Il flow è **per-source**: un'esecuzione
per source (`cds`, poi `cap`), source iniettata nei singoli step.

Il quarto step del flow indexing (`MapStep("map_to_chunk_entity",
ArticleMapper.from_embeddable_chunk_to_knowledge_chunk)`) è il generico
`MapStep` — non vive in `steps/knowledge/` ma in `steps/generic/`.
Gli step di preparation (cleaning/enrichment) non esistono più come classi
dedicate in questo package: sostituiti dai generici `LoadJsonStep`/`MapStep`/
`WriteJsonStep`/`EnrichDataStep` — vedi [data_preparation.md](data_preparation.md).

- **`ChunkArticlesStep`**: iniettato `ArticleChunker(source)` già costruito con
  la source (la source è nel costruttore del chunker, non più un parametro
  separato di `ChunkArticlesStep`). `execute`: legge `ENRICHED_ARTICLES`,
  chiama `chunker.execute(article)` per ogni articolo, appiattisce. Nessun
  filtro repealed — i chunk repealed sono nell'output come `EmbeddableChunkModel`.
  `required={ENRICHED_ARTICLES}`, `produced={EMBEDDABLE_CHUNKS}`.
- **`EmbedChunksStep`**: iniettati `EmbeddingService` (SP01) e `embed_repealed: bool`.
  `execute`: se `embed_repealed=False`, filtra i chunk non-repealed
  (`to_embed = [c for c in chunks if not c.is_repealed]`) → li embeddita in
  place → ri-scrive `EMBEDDABLE_CHUNKS` con la lista **intera** (repealed inclusi, con
  `embedding=None`). Composizione pura, nessuna ereditarietà da `EmbedStep`.
  `required={EMBEDDABLE_CHUNKS}`, `produced={EMBEDDABLE_CHUNKS}` (WARNING benigno FlowValidator:
  "Produced key overwrites an already available key" — non ERROR, non blocca
  `build(validate=True)`).
- **`MapStep("map_to_chunk_entity")`** (generico, non domain-specific): converte
  `list[EmbeddableChunkModel]` → `list[KnowledgeChunk]` via
  `ArticleMapper.from_embeddable_chunk_to_knowledge_chunk`.
  `required={EMBEDDABLE_CHUNKS}`, `produced={CHUNK_ENTITIES}`.
- **`StoreChunksStep`** (domain-specific, non il generico `DbStoreStep`):
  iniettati `KnowledgeChunkStoreRepository` e `source: str`. `execute`: legge
  `CHUNK_ENTITIES`, chiama `repository.delete_source(source)` poi
  `repository.bulk_insert(chunks)`. Full-reload della **sola source corrente**:
  le altre source nella tabella restano intatte. `required={CHUNK_ENTITIES}`,
  `produced=set()` (step terminale/sink).

### `orchestrators/knowledge_flows.py` — flow factory (SP03)

```python
def build_knowledge_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    source: str,
    validate: bool = False,
) -> Flow
```

Mappatura step (5 step): `LoadJsonStep("load_enriched_articles", model_class=EnrichedArticleModel)` →
`ChunkArticlesStep` → `EmbedChunksStep` →
`MapStep("map_to_chunk_entity", ArticleMapper.from_embeddable_chunk_to_knowledge_chunk)` →
`StoreChunksStep`. Il flow è prodotto da
`FlowBuilder("knowledge_indexing").add_step(...).build(validate=validate)`.
Re-esportato da `orchestrators/__init__.py` come `build_knowledge_indexing_flow`.

**Decisioni:**
- `source` ricevuta come parametro esplicito; validata contro
  `config.knowledge_indexing.sources` → `ValueError` se non riconosciuta.
  Poi narrowing a `Literal["cds","cap"]` con `cast` al confine (per `ChunkArticlesStep`).
- `input_layer` letto da `config.knowledge_indexing.input_layer`.
- Collega `main.py` direttamente (non più `IndexingPipeline` legacy).
- Il `MapStep("map_to_chunk_entity")` è interposizione obbligatoria tra
  `EmbedChunksStep` e `StoreChunksStep`: `KnowledgeChunk` è ora DB-write-only
  (nessuna property `embedded_text`), e `EmbeddableChunkModel` (che ha
  `embedded_text`) non è direttamente accettato dal repository.
- `StoreChunksStep` usato al posto del generico `DbStoreStep` perché la
  strategia di store è delete-by-source (non TRUNCATE): con il per-source,
  la seconda run su una source diversa non può azzerare la tabella intera.

### `configs/pipeline_layer_config.py` — campo `sources` (SP03)

Aggiunto `sources: list[str] = Field(default_factory=list)` a
`PipelineLayerConfig`. Valorizzato in `IngestorConfig` e nel YAML:

| Pipeline | `sources` |
|---|---|
| `knowledge_preparation` | `["cds", "cap"]` |
| `knowledge_indexing` | `["cds", "cap"]` |
| `quiz_preparation` | `["quiz"]` |
| `quiz_indexing` | `["quiz"]` |

Fonte unica del selettore source: la factory legge
`config.knowledge_indexing.sources` invece di hardcodare `["cds","cap"]`.

### `repositories/db/_bulk_insert_store_repository.py` — `BulkInsertStoreRepository[T]` (base condivisa, estratta dal refactor)

- Classe base generica (Python 3.12 native generics, `ABC`) che fattorizza
  `truncate()` + `bulk_insert(items)` + costruzione della query
  `INSERT INTO {table} ({columns}) VALUES ({placeholders})` — logica
  identica che prima era duplicata in `KnowledgeChunkStoreRepository` e
  `QuizQuestionStoreRepository`. Prefisso `_` → privata al sub-package
  `repositories/db/`, non re-esportata da nessun `__init__.py`.
- `__init__(client, table_name, columns: Sequence[str], row_mapper: Callable[[T], Sequence[object]])`:
  inietta client, tabella, colonne target e la funzione che mappa un item del
  dominio (`KnowledgeChunk`/`QuizQuestion`) in una riga DB (tupla posizionale,
  stesso ordine di `columns`). `ValueError` se `columns` è vuoto.
- `bulk_insert`: ritorna immediatamente (`return`) se la lista è vuota;
  altrimenti `client.execute_many(query, [row_mapper(item) for item in items])`.
- `_to_db_row(item: T) -> tuple[object, ...]` è un `@staticmethod @abstractmethod`:
  ogni sottoclasse implementa solo il mapping item→riga, passato come
  `row_mapper` al costruttore della base — nessun'altra differenza tra le due
  sottoclassi concrete.
- Le due sottoclassi (`KnowledgeChunkStoreRepository`, `QuizQuestionStoreRepository`)
  passano `columns`/`row_mapper` specifici al `super().__init__` e aggiungono
  solo i metodi che **non** sono condivisi (`delete_source` per il knowledge).

### `repositories/db/` — `KnowledgeChunkStoreRepository`

- Estende `BulkInsertStoreRepository[KnowledgeChunk]`. Repository di scrittura
  iniettato con un `PostgresClient` generico e il nome tabella
  (`config.knowledge_chunks_table`). Vive in `repositories/db/` (storage
  Postgres), re-esportato da `repositories/__init__.py`.
- Due modalità di reset, distinte per scope:
  - `delete_source(source: str)` — cancella solo i chunk della source indicata
    (`DELETE FROM {table} WHERE source = %s`), via `PostgresClient.execute`.
    Usato da `StoreChunksStep` nel flow per-source: le altre source restano
    intatte. Unico metodo proprio, non condiviso dalla base.
  - `truncate()` — svuota l'intera tabella (`TRUNCATE TABLE`), ereditato dalla
    base. Usato da `reset-knowledge-db` per il wipe totale pre-reimport
    completo.
- `bulk_insert(chunks: list[KnowledgeChunk])` — ereditato dalla base; colonne
  `source, article_number, article_title, comma_index, chunk_text, context,
  is_repealed, source_url, embedding`, mappate riga per riga da
  `_to_db_row` (override `@staticmethod`).
- Vincolo architetturale: con il per-source NON si può usare `truncate` nel
  flow di indexing — la seconda run su source diversa cancellerebbe la prima.
  La colonna `source` e l'unique `(source, article_number, comma_index)` sullo
  schema DB sono la precondizione che rende il delete-by-source sicuro e
  idempotente.
