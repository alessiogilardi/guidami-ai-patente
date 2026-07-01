# Ingestor — Normative corpus pipeline (CdS + CAP)

This document covers **indexing** (`enriched` → chunk → embed → DB, SP03).
See [data_preparation.md](data_preparation.md) for **preparation**
(`parsed` → `cleaned` → `enriched`, rebuilt on two per-source flowstep flows
in SP05: `build_knowledge_cleaning_flow`, `build_knowledge_enrichment_flow`,
`run_preparation`, `ApplyStep`+`ForEach` + `ContextEnricher` (UseCase, SP01),
`ArticleMapper`).
See [config_and_entrypoints.md](config_and_entrypoints.md) for `IngestorConfig`,
`LayerResolver` and the CLI entry points.

## Implemented decisions

### `repositories/` — `db/` + `json/` structure

- The `repositories/` package is divided into two sub-packages by storage type:
  - `db/` — Postgres (psycopg v3): `KnowledgeChunkStoreRepository`,
    `QuizQuestionStoreRepository`.
  - `json/` — filesystem JSON: `ArticleRepository`,
    `EnrichedArticleRepository`, `QuizBankRepository`,
    `EnrichedQuizBankRepository`.
- The top-level `__init__.py` re-exports all 6 repositories: callers
  (orchestrators, tests, entry points) import from
  `guidami_ai_patente_ingestor.repositories` without knowing the internal
  subdivision — zero breaking change from the previous flat structure.

### `repositories/json/_json_repository.py` — `JsonRepository[T: BaseModel]`

- Generic base class (Python 3.12 native generics) for all JSON repositories.
  `_` prefix → private to the sub-package, not re-exported from any `__init__.py`.
- `__init__`: inspects `__orig_bases__` of the concrete class to infer
  the Pydantic type `T` (e.g. `ParsedArticleModel` from `ArticleRepository(JsonRepository[ParsedArticleModel])`);
  raises `TypeError` if the type is not found.
- `load(path: Path) -> list[T]`: reads JSON and validates each element with
  `T.model_validate()`.
- `write(items: list[T], path: Path) -> None`: creates missing directories
  (`mkdir(parents=True, exist_ok=True)`), serialises with
  `json.dumps(..., ensure_ascii=False, indent=2)`.
- The four subclasses (`ArticleRepository`, `EnrichedArticleRepository`,
  `QuizBankRepository`, `EnrichedQuizBankRepository`) add neither
  `__init__` nor methods: they inherit everything from the base.

### `repositories/json/` — `ArticleRepository`

- Extends `JsonRepository[ParsedArticleModel]`; inherits `load` and `write` without
  adding code. The caller imports from `guidami_ai_patente_ingestor.repositories`
  (top-level `__init__.py`), not from the internal sub-package.
- No `source` parameter: the `source` ("cds"/"cap") is known to the caller
  and passed directly to `ArticleChunker.chunk`.

### `services/knowledge/article_cleaner.py` — `ArticleCleaner`

- Pure service (`clean(article: ParsedArticleModel) -> ParsedArticleModel`), no I/O, no
  injected config. Returns a copy (`article.model_copy(update={...})`)
  with `title`, `text`, `paragraphs` cleaned of normattiva markup.
- **Title** (`_clean_title`): removes superfluous parentheses wrapping
  the title (`"(Title)."` / `"(Title)"` → `"Title"`); also handles the
  case where the closing parenthesis is missing due to an upstream scraper defect.
- **Article text** (`_clean_text`): removes inline markup
  `((...))` via `_INLINE_MARKUP_PATTERN = re.compile(r"\(\((.*?)\)\)",
  re.DOTALL)`, preserving the inner text. If after substitution unbalanced
  markup remains (`"(("` or `"))"` still present — sign that a title ended
  up in the `text` field), the text is **discarded** (becomes `""`).
- **Clauses** (`_clean_paragraphs`): normalises the `paragraphs` array handling
  edge cases observed on real CdS/CAP data:
  - standalone markers `"(("` / `"))"` wrapping ranges of already-numbered
    clauses → discarded without losing the inner clauses;
  - margin note references such as `"((171))"` → discarded (become
    residual noise after ordinal removal, empty string not appended);
  - clauses entirely wrapped in `((...))` → markup removed, clause kept;
  - clauses with a)/b)/c)/d) lists spread across multiple array elements →
    merged into a single clause (buffer accumulated until the closing `"))"` marker);
  - clause ordinal numbering (e.g. `"1. "`, `"10-bis. "`, also without
    a period after the ordinal) removed via
    `_ORDINAL_PREFIX_PATTERN = re.compile(r"^(\d+(?:-\w+)?\.?)\s*")` (the
    ordinal token is captured in group 1, reused for the duplication check below);
  - inline multiple markup within the same clause handled by the same
    `_INLINE_MARKUP_PATTERN.sub`.
  - **duplicated ordinal in source data** (upstream defect, e.g.
    `"2. 2. Nell'archivio nazionale..."` in art. 226 CdS): after removing
    the first ordinal, if the remainder begins with the same exact ordinal token
    (`duplicate.group(1) == match.group(1)`, exact token identity comparison,
    not just "is a number"), it is also removed. This avoids incorrectly
    discarding clauses that legitimately start with a number different from
    the ordinal (e.g. `"2. 5 milioni di euro..."`, where `"5"` ≠ `"2."` and
    therefore stays).
  - `_append_cleaned` is the single point that applies markup-stripping +
    ordinal removal + duplicate ordinal removal + "empty remainder" filter
    before appending to `merged`.


### `services/knowledge/article_chunker.py` — `ArticleChunker`

Implements `UseCase[EnrichedArticleModel, list[EmbeddableChunkModel]]`.

- `source` injected in the constructor (`ArticleChunker(source: str)`): no
  longer passed per call. This allows using `chunker.execute` as a
  callable in `ForEach` (or `ApplyStep`) without adapters.
- `execute(enriched_article: EnrichedArticleModel) -> list[EmbeddableChunkModel]`:
  `comma_index=0` generated from `article.text` **only `if article.text:`**
  (non-empty text after cleaning); `comma_index=i+1` for each `paragraphs[i]`.
  Uses `ArticleMapper.from_enriched_to_embeddable_chunk(model, source, comma_index, raw_text)`
  to build each `EmbeddableChunkModel` instead of instantiating the model inline.
- Populates `chunk.context = enriched_article.contexts.get(comma_index, "")`.
  If `contexts` is `{}` (article not enriched or repealed), `context`
  remains `""`.
- `is_repealed = article.repealed OR "ABROGAT" in raw_text.upper()` —
  substring match, also triggers on forms like "abrogat**e**"/"abrogat**a**"
  (not only "COMMA ABROGATO"), confirmed on real data (CdS art. 231) and
  accepted as-is.

### `models/knowledge/embeddable_chunk.py` — `EmbeddableChunkModel`

- Intermediate DTO for computing the embedding of a chunk, mirroring
  `KnowledgeChunk` (same fields) but with an `embedded_text: str` property —
  separated from the DB entity to decouple the text to embed from the
  Postgres write.
- `embedded_text`: `"\n".join(part for part in [article_title, context, chunk_text] if part)` —
  concatenates title, context (if present) and chunk text, discarding empty parts.
  If `context` is empty, the result is `"article_title\nchunk_text"`.
- `embedding: list[float] | None = None` — populated in place by
  `EmbedChunksStep`; `None` for repealed chunks excluded from embedding.
- Satisfies the `Embeddable` protocol (has `embedded_text`) and `Embedded`
  (has `embedding`): both used by `EmbeddingService`.
- Produced by `ArticleChunker.chunk(enriched_article, source)`; converted to
  `KnowledgeChunk` (DB-only entity, without `embedded_text`) by
  `ArticleMapper.from_embeddable_chunk_to_knowledge_chunk`.

### `orchestrators/steps/knowledge/` — knowledge domain steps (SP03)

Three domain-specific flowstep steps for knowledge indexing. They live in
`orchestrators/steps/knowledge/`, never in `services/` (dependency goes toward
`flowstep` top-level, not the other way). The flow is **per-source**: one execution
per source (`cds`, then `cap`), source injected into individual steps.

The fourth step of the indexing flow is
`ApplyStep("map_to_chunk_entity", ForEach(ArticleMapper.from_embeddable_chunk_to_knowledge_chunk))`
— lives in `knowledge_flows.py` (not in `steps/knowledge/`).
Preparation steps (cleaning/enrichment) no longer exist as dedicated classes
in this package: replaced by generic `LoadJsonStep`/`ApplyStep`/`WriteJsonStep`
— see [data_preparation.md](data_preparation.md).

- **`ChunkArticlesStep`**: injected with `ArticleChunker(source)` already built with
  the source (source is in the chunker's constructor, no longer a separate
  parameter of `ChunkArticlesStep`). `execute`: reads `ENRICHED_ARTICLES`,
  calls `chunker.execute(article)` for each article, flattens. No repealed
  filter — repealed chunks are in the output as `EmbeddableChunkModel`.
  `required={ENRICHED_ARTICLES}`, `produced={EMBEDDABLE_CHUNKS}`.
- **`EmbedChunksStep`**: injected with `EmbeddingService` (SP01) and `embed_repealed: bool`.
  `execute`: if `embed_repealed=False`, filters non-repealed chunks
  (`to_embed = [c for c in chunks if not c.is_repealed]`) → embeds them
  in place → rewrites `EMBEDDABLE_CHUNKS` with the **full** list (repealed included,
  with `embedding=None`). Pure composition, no inheritance from `EmbedStep`.
  `required={EMBEDDABLE_CHUNKS}`, `produced={EMBEDDABLE_CHUNKS}` (benign FlowValidator
  WARNING: "Produced key overwrites an already available key" — not ERROR, does not
  block `build(validate=True)`).
- **`ApplyStep("map_to_chunk_entity", ForEach(ArticleMapper.from_embeddable_chunk_to_knowledge_chunk))`**:
  converts `list[EmbeddableChunkModel]` → `list[KnowledgeChunk]` via
  `ForEach` + static mapper. `required={EMBEDDABLE_CHUNKS}`,
  `produced={CHUNK_ENTITIES}`. Not a dedicated step class: it is an
  `ApplyStep` configured inline in the flow builder.
- **`StoreChunksStep`** (domain-specific, not the generic `DbStoreStep`):
  injected with `KnowledgeChunkStoreRepository` and `source: str`. `execute`: reads
  `CHUNK_ENTITIES`, calls `repository.delete_source(source)` then
  `repository.bulk_insert(chunks)`. Full-reload of the **current source only**:
  other sources in the table remain intact. `required={CHUNK_ENTITIES}`,
  `produced=set()` (terminal/sink step).

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

Step mapping (5 steps): `LoadJsonStep("load_enriched_articles", model_class=EnrichedArticleModel)` →
`ChunkArticlesStep` → `EmbedChunksStep` →
`ApplyStep("map_to_chunk_entity", ForEach(ArticleMapper.from_embeddable_chunk_to_knowledge_chunk))` →
`StoreChunksStep`. The flow is produced by
`FlowBuilder("knowledge_indexing").add_step(...).build(validate=validate)`.
Re-exported from `orchestrators/__init__.py` as `build_knowledge_indexing_flow`.

**Decisions:**
- `source` received as an explicit parameter; validated against
  `config.knowledge_indexing.sources` → `ValueError` if not recognised.
  Then narrowed to `Literal["cds","cap"]` with `cast` at the boundary (for `ChunkArticlesStep`).
- `input_layer` read from `config.knowledge_indexing.input_layer`.
- Connects `main.py` directly (no longer the legacy `IndexingPipeline`).
- The `ApplyStep("map_to_chunk_entity", ForEach(ArticleMapper.from_embeddable_chunk_to_knowledge_chunk))`
  is a mandatory interposition between `EmbedChunksStep` and `StoreChunksStep`:
  `KnowledgeChunk` is DB-write-only (no `embedded_text` property), and
  `EmbeddableChunkModel` (which has `embedded_text`) is not directly
  accepted by the repository.
- `StoreChunksStep` used instead of the generic `DbStoreStep` because the
  store strategy is delete-by-source (not TRUNCATE): with per-source runs,
  the second run on a different source cannot wipe the entire table.

### `configs/pipeline_layer_config.py` — `sources` field (SP03)

Added `sources: list[str] = Field(default_factory=list)` to
`PipelineLayerConfig`. Populated in `IngestorConfig` and in the YAML:

| Pipeline | `sources` |
|---|---|
| `knowledge_preparation` | `["cds", "cap"]` |
| `knowledge_indexing` | `["cds", "cap"]` |
| `quiz_preparation` | `["quiz"]` |
| `quiz_indexing` | `["quiz"]` |

Single source of truth for source selection: the factory reads
`config.knowledge_indexing.sources` instead of hardcoding `["cds","cap"]`.

### `repositories/db/_bulk_insert_store_repository.py` — `BulkInsertStoreRepository[T]` (shared base, extracted during refactor)

- Generic base class (Python 3.12 native generics, `ABC`) that factors out
  `truncate()` + `bulk_insert(items)` + construction of the query
  `INSERT INTO {table} ({columns}) VALUES ({placeholders})` — logic
  that was previously duplicated in `KnowledgeChunkStoreRepository` and
  `QuizQuestionStoreRepository`. `_` prefix → private to the `repositories/db/`
  sub-package, not re-exported from any `__init__.py`.
- `__init__(client, table_name, columns: Sequence[str], row_mapper: Callable[[T], Sequence[object]])`:
  injects client, table, target columns and the function that maps a domain item
  (`KnowledgeChunk`/`QuizQuestion`) into a DB row (positional tuple,
  same order as `columns`). `ValueError` if `columns` is empty.
- `bulk_insert`: returns immediately (`return`) if the list is empty;
  otherwise `client.execute_many(query, [row_mapper(item) for item in items])`.
- `_to_db_row(item: T) -> tuple[object, ...]` is a `@staticmethod @abstractmethod`:
  each subclass implements only the item→row mapping, passed as
  `row_mapper` to the base constructor — no other difference between the two
  concrete subclasses.
- The two subclasses (`KnowledgeChunkStoreRepository`, `QuizQuestionStoreRepository`)
  pass specific `columns`/`row_mapper` to `super().__init__` and add
  only methods that are **not** shared (`delete_source` for knowledge).

### `repositories/db/` — `KnowledgeChunkStoreRepository`

- Extends `BulkInsertStoreRepository[KnowledgeChunk]`. Write-only repository
  injected with a generic `PostgresClient` and the table name
  (`config.knowledge_chunks_table`). Lives in `repositories/db/` (Postgres
  storage), re-exported from `repositories/__init__.py`.
- Two reset modes, distinct by scope:
  - `delete_source(source: str)` — deletes only the chunks for the given source
    (`DELETE FROM {table} WHERE source = %s`), via `PostgresClient.execute`.
    Used by `StoreChunksStep` in the per-source flow: other sources remain
    intact. Only own method, not shared by the base.
  - `truncate()` — empties the entire table (`TRUNCATE TABLE`), inherited from
    the base. Used by `reset-knowledge-db` for the full wipe before a complete
    re-import.
- `bulk_insert(chunks: list[KnowledgeChunk])` — inherited from the base; columns
  `source, article_number, article_title, comma_index, chunk_text, context,
  is_repealed, source_url, embedding`, mapped row by row by
  `_to_db_row` (`@staticmethod` override).
- Architectural constraint: with per-source runs `truncate` CANNOT be used in
  the indexing flow — a second run on a different source would delete the first.
  The `source` column and the unique `(source, article_number, comma_index)` on
  the DB schema are the precondition that makes delete-by-source safe and
  idempotent.
