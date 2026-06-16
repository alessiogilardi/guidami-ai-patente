# Ingestor — Pipeline corpus normativo (CdS + CAP)

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/implement/ingestor.md`.

Vedi [config_and_entrypoints.md](config_and_entrypoints.md) per `IngestorConfig`
e gli entry point CLI.

## Decisioni implementate

### `repositories/` — `ArticleRepository`

- Unico componente di data-access per `Article` da/verso JSON:
  `load(path: Path) -> list[Article]` e
  `write(articles: list[Article], path: Path) -> None`.
- Sostituisce il precedente `ArticleLoader` (che era in
  `services/knowledge` ed era solo lettura) — ora lettura e scrittura sono
  nello stesso componente perché operano sullo stesso formato (JSON di
  `Article`). `write` crea le directory mancanti (`mkdir(parents=True,
  exist_ok=True)`) e serializza con `ensure_ascii=False, indent=2`.
- Nessun parametro `source`: il `source` ("cds"/"cap") è noto al chiamante
  e passato direttamente ad `ArticleChunker.chunk`.

### `services/knowledge/article_cleaner.py` — `ArticleCleaner`

- Servizio puro (`clean(article: Article) -> Article`), nessun I/O, nessuna
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

### `orchestrators/knowledge_cleaning/` — `CleaningPipeline` + `CleaningPipelineBuilder`

- **`CleaningPipeline.run()`**: per ciascuna source (cds, cap) chiama
  `_clean_source(parsed_path, cleaned_path, source)`:
  1. se `cleaned_path.exists()` → log `info` e skip (pipeline
     **idempotente**, nessuna ri-pulizia di dati già processati);
  2. altrimenti `ArticleRepository.load(parsed_path)` →
     `ArticleCleaner.clean(article)` per ciascun articolo →
     `ArticleRepository.write(cleaned_articles, cleaned_path)`, con log
     `info` del conteggio.
  - Dipendenze iniettate via costruttore: `ArticleRepository`,
    `ArticleCleaner`, `IngestorConfig`.
- **`CleaningPipelineBuilder`**: valida che `cds_parsed_path` e
  `cap_parsed_path` esistano, stesso pattern di
  `IndexingPipelineBuilder._validate_source_paths` —
  `FileNotFoundError` aggregato su entrambi i path mancanti (report
  completo, non solo il primo).
  - Setter fluent `with_article_repository`, `with_article_cleaner`
    (ritornano `Self`); `build()` usa controlli espliciti `is not None`
    per scegliere tra dipendenza assegnata e default.

### `services/knowledge/article_chunker.py` — `ArticleChunker`

- **Non pulisce più i dati**: rimossi `_MARKUP_PATTERN`/`_clean`. Opera
  solo su `Article` già puliti da `ArticleCleaner` (precondizione: input
  letto da `data/cleaned/`).
- `chunk(article, source) -> list[KnowledgeChunk]`: `comma_index=0`
  generato da `article.text` **solo `if article.text:`** (testo non vuoto
  dopo cleaning); `comma_index=i+1` per ogni `paragraphs[i]`.
- `is_repealed = article.repealed OR "ABROGAT" in raw_text.upper()` —
  substring match, scatta anche su forme come "abrogat**e**"/"abrogat**a**"
  (non solo "COMMA ABROGATO"), confermato su dati reali (CdS art. 231) e
  accettato così com'è.

### `orchestrators/knowledge_indexing/` — `IndexingPipeline` + `IndexingPipelineBuilder`

- Rinominato `article_loader`/`with_article_loader` →
  `article_repository`/`with_article_repository` (usa `ArticleRepository`
  da `repositories/`).
- **`IndexingPipeline.run()`** — layout flat, step sequenziali senza
  nidificazione:
  1. due chiamate separate `ArticleRepository.load()`
     (`config.cds_cleaned_path`, `config.cap_cleaned_path`) — legge da
     `data/cleaned/`, non più da `data/parsed/`; load completato prima di
     iniziare il chunking;
  2. `_chunk_articles` (helper privato) per cds e cap separatamente, poi
     concatenazione dei chunk;
  3. `_assign_embeddings` (helper privato): chiama prima `_filter_chunks`
     che, se `config.embed_repealed` è `False`, esclude i chunk con
     `is_repealed=True` dalla lista prima di procedere. Poi batch di
     `config.embedding_batch_size`, `EmbeddingClient.embed_passages(
     [chunk.embedded_text for chunk in batch])` (il testo embeddato è
     `f"{article_title} {chunk_text}"`, titolo prefissato) e assegnazione di
     `chunk.embedding` in place (campo mutabile). Ogni chiamata è una
     richiesta API a pagamento (OpenRouter) — il costo è limitato al
     re-ingest del corpus (operazione offline, non query utente);
  4. `KnowledgeChunkStoreRepository.truncate()` poi `bulk_insert(chunks)`
     (full reload).
  - Dipendenze iniettate via costruttore: `ArticleRepository`,
    `ArticleChunker`, `EmbeddingClient` (ABC, `commons`),
    `KnowledgeChunkStoreRepository`, `IngestorConfig`.
- **`IndexingPipelineBuilder`**: valida l'esistenza di `cds_cleaned_path`/
  `cap_cleaned_path` (non più `cds_path`/`cap_path`) con `FileNotFoundError`
  fail-fast **prima** di istanziare il client di embedding o `PostgresClient`
  (apre connessione Postgres). `_validate_source_paths` aggrega tutti i path
  mancanti in un unico `FileNotFoundError` (report completo, non solo il
  primo). Nessuna classe di eccezioni dedicata — `FileNotFoundError` con
  messaggio chiaro, coerente con KISS a questa scala.
  - Setter fluent `with_article_repository`, `with_article_chunker`,
    `with_embedding_client`, `with_knowledge_chunk_store_repository`
    (ritornano `Self`) per assegnare ogni dipendenza concreta prima di
    `build()`. Il default di `embedding_client` è
    `LiteLLMEmbeddingClient(config.embedding)` (cloud, `text-embedding-3-small`
    via OpenRouter); il default di `knowledge_chunk_store_repository` è
    `KnowledgeChunkStoreRepository(PostgresClient(config.postgres),
    config.knowledge_chunks_table)`. `build()` usa controlli espliciti
    `is not None` (non `or`) per scegliere tra dipendenza assegnata e
    default, per evitare problemi di truthiness se in futuro una di queste
    classi implementasse `__bool__`.

### `repositories/` — `KnowledgeChunkStoreRepository`

- Sostituisce l'uso diretto di `VectorStoreClient` (rimosso, vedi
  `commons.md`): repository di scrittura full-reload, iniettato con un
  `PostgresClient` generico e il nome tabella
  (`config.knowledge_chunks_table`).
- `truncate()` + `bulk_insert(chunks: list[KnowledgeChunk])` — colonne
  `source, article_number, article_title, comma_index, chunk_text,
  is_repealed, source_url, embedding`.
- Costruisce la query con `psycopg.sql.SQL(...).format(table=
  sql.Identifier(table_name))` e `client.execute_many(query, params_seq)`;
  `bulk_insert` ritorna immediatamente (`return`) se la lista è vuota.
