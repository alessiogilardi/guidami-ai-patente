# Package `src/guidami_ai_patente_ingestor/`

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/architecture-code-layout.md`, `plans/implement/ingestor.md`,
`plans/architecture-quiz-bank.md` (pipeline quiz bank, refactor Postgres
condiviso).

Due pipeline batch indipendenti, entrambe full-reload su Postgres:

- **corpus normativo (CdS + CAP)**: pulizia (`CleaningPipeline`) e
  indicizzazione (`IndexingPipeline`) in `knowledge_chunks` (embedding
  incluso);
- **quiz bank**: `QuizIndexingPipeline`, load + map (flatten/dedup) +
  full-reload di `quiz_questions` (nessun embedding).

Dipende da `commons` (modelli, `EmbeddingClient`, `PostgresClient`, config
condivise).

## Layout

```
src/guidami_ai_patente_ingestor/
  entities/
    article.py                    # Article — mappa 1:1 il JSON sorgente (number, title, text,
                                   # paragraphs, url, scraped_at, repealed)
    quiz_bank.py                   # QuizMainQuestion, QuizSubQuestion — mappano 1:1 il JSON sorgente
  repositories/
    article_repository.py         # ArticleRepository.load(path) -> list[Article]
                                   # ArticleRepository.write(articles, path) -> None
    knowledge_chunk_store_repository.py  # KnowledgeChunkStoreRepository (truncate + bulk insert)
    quiz_bank_repository.py        # QuizBankRepository.load(path) -> list[QuizMainQuestion]
    quiz_question_store_repository.py    # QuizQuestionStoreRepository (truncate + bulk insert)
  services/
    knowledge/
      article_cleaner.py          # ArticleCleaner.clean(article) -> Article
      article_chunker.py          # ArticleChunker.chunk(article, source) -> list[KnowledgeChunk]
    quiz/
      quiz_question_mapper.py     # QuizQuestionMapper.map(main_questions) -> list[QuizQuestion]
  orchestrators/
    knowledge_cleaning/
      cleaning_pipeline.py          # CleaningPipeline
      cleaning_pipeline_builder.py  # CleaningPipelineBuilder
    knowledge_indexing/
      indexing_pipeline.py          # IndexingPipeline
      indexing_pipeline_builder.py  # IndexingPipelineBuilder
    quiz_indexing/
      quiz_indexing_pipeline.py          # QuizIndexingPipeline
      quiz_indexing_pipeline_builder.py  # QuizIndexingPipelineBuilder
  configs/
    ingestor_config.py            # IngestorConfig (BaseSettings, frozen)
  main.py                          # entry point CLI (uv run ingest-knowledge)
  reset_db.py                      # entry point CLI (uv run reset-knowledge-db)
  quiz_main.py                     # entry point CLI (uv run ingest-quiz)
  reset_quiz_db.py                 # entry point CLI (uv run reset-quiz-db)

configs/                            # root del progetto (non sotto src/)
  ingestor_config.yaml              # config non-secret, committata

.env.example                        # documenta le sole env var secret
                                     # (POSTGRES__USER, POSTGRES__PASSWORD)
```

## Convenzione directory dati

Pipeline a tre stadi su disco:

- `data/raw/<source>/` — HTML grezzo dello scraper (non toccato da questo
  package).
- `data/parsed/<source>/...json` — JSON grezzo prodotto dallo scraper
  (rinominato da `data/processed/`), markup normattiva ancora presente.
- `data/cleaned/<source>/...json` — JSON pulito da `ArticleCleaner`, pronto
  per il chunking. Output di `CleaningPipeline`, input di `IndexingPipeline`.

Struttura mirror per source: `data/cleaned/cds/codice_della_strada.json`,
`data/cleaned/cap/codice_rca.json` (stessi nomi file di `data/parsed/`).

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
  3. `_assign_embeddings` (helper privato): batch di
     `config.embedding_batch_size`, `EmbeddingClient.embed_passages()` e
     assegnazione di `chunk.embedding` in place (campo mutabile). Ogni
     chiamata è una richiesta API a pagamento (OpenRouter) — il costo è
     limitato al re-ingest del corpus (operazione offline, non query utente);
  4. `KnowledgeChunkStoreRepository.truncate()` poi `bulk_insert(chunks)`
     (full reload).
  - Dipendenze iniettate via costruttore: `ArticleRepository`,
    `ArticleChunker`, `EmbeddingClient` (ABC, `commons`),
    `KnowledgeChunkStoreRepository`, `IngestorConfig`.
- **`IndexingPipelineBuilder`**: valida l'esistenza di `cds_cleaned_path`/
  `cap_cleaned_path` (non più `cds_path`/`cap_path`) con `FileNotFoundError`
  fail-fast **prima** di istanziare `LiteLLMEmbeddingClient` o `PostgresClient`
  (apre connessione Postgres). `_validate_source_paths` aggrega tutti i path
  mancanti in un unico `FileNotFoundError` (report completo, non solo il
  primo). Nessuna classe di eccezioni dedicata — `FileNotFoundError` con
  messaggio chiaro, coerente con KISS a questa scala.
  - Setter fluent `with_article_repository`, `with_article_chunker`,
    `with_embedding_client`, `with_knowledge_chunk_store_repository`
    (ritornano `Self`) per assegnare ogni dipendenza concreta prima di
    `build()`. Il default di `embedding_client` è
    `LiteLLMEmbeddingClient(config.embedding)`; il default di
    `knowledge_chunk_store_repository` è
    `KnowledgeChunkStoreRepository(PostgresClient(config.postgres),
    config.knowledge_chunks_table)`. `build()` usa controlli espliciti
    `is not None` (non `or`) per scegliere tra dipendenza assegnata e
    default, per evitare problemi di truthiness se in futuro una di queste
    classi implementasse `__bool__`.

### `repositories/` — `KnowledgeChunkStoreRepository` / `QuizQuestionStoreRepository`

- Sostituiscono l'uso diretto di `VectorStoreClient` (rimosso, vedi
  `commons.md`): entrambi sono repository di scrittura full-reload,
  iniettati con un `PostgresClient` generico e il nome tabella
  (`config.knowledge_chunks_table` / `config.quiz_questions_table`).
- **`KnowledgeChunkStoreRepository`**: `truncate()` +
  `bulk_insert(chunks: list[KnowledgeChunk])` — colonne `source,
  article_number, article_title, comma_index, chunk_text, is_repealed,
  source_url, embedding`.
- **`QuizQuestionStoreRepository`**: `truncate()` +
  `bulk_insert(questions: list[QuizQuestion])` — colonne `number,
  question_id, topic, text, correct_answer, image_filename`.
- Entrambi costruiscono la query con `psycopg.sql.SQL(...).format(table=
  sql.Identifier(table_name))` e `client.execute_many(query, params_seq)`;
  `bulk_insert` ritorna immediatamente (`return`) se la lista è vuota.

### `entities/quiz_bank.py` — `QuizMainQuestion` / `QuizSubQuestion`

- Mappano 1:1 il JSON sorgente `data/parsed/quiz-patente-ab/quiz-patente-ab.json`
  (715 domande madri, 7106 sotto-domande): `QuizMainQuestion` (`question_id:
  int`, `topic: str`, `sub_questions: list[QuizSubQuestion]`),
  `QuizSubQuestion` (`number: str`, `text: str`, `correct_answer: bool`,
  `image: str | None = None`).
- `question_id` è una stringa numerica nel JSON, ma Pydantic v2 la coercise a
  `int` (coercizione lax) — la colonna `quiz_questions.question_id INTEGER`
  è quindi corretta senza conversioni manuali.

### `repositories/quiz_bank_repository.py` — `QuizBankRepository`

- `load(path: Path) -> list[QuizMainQuestion]`: legge il JSON e valida ogni
  elemento con `QuizMainQuestion.model_validate`. Nessuna dipendenza/config
  iniettata — stesso ruolo di `ArticleRepository` per il quiz bank, ma solo
  lettura (non c'è uno stadio "cleaned" per il quiz bank).

### `services/quiz/quiz_question_mapper.py` — `QuizQuestionMapper`

- `map(main_questions: list[QuizMainQuestion]) -> list[QuizQuestion]`:
  appiattisce ogni `sub_questions` in una `QuizQuestion`, denormalizzando
  `question_id`/`topic` dalla domanda madre.
- `image_filename = PurePosixPath(image).name if image is not None else
  None` — salva solo il nome file (non il path repo-relative stantio della
  fonte), risolvendo l'incoerenza `data/processed` vs `data/parsed` osservata
  nei dati senza dipendere da un refactor del parser (decisione 4 del piano).
- **Dedup duplicati esatti**: chiave `(text.strip(), correct_answer, image)`
  in un `set`; ogni duplicato scartato genera
  `logger.warning(f"skipping duplicate sub-question {number} (question_id=...)")`.
  Verificato su dati reali: 8 duplicati esatti su 7106 sotto-domande → 7098
  righe mappate.

### `orchestrators/quiz_indexing/` — `QuizIndexingPipeline` + `QuizIndexingPipelineBuilder`

- **`QuizIndexingPipeline.run()`** — tre step lineari, nessuno step di
  cleaning/embedding (il JSON del quiz bank non ha markup da pulire, le righe
  non hanno vettori):
  1. `QuizBankRepository.load(config.quiz_bank_path)`;
  2. `QuizQuestionMapper.map(main_questions)`;
  3. `QuizQuestionStoreRepository.truncate()` poi `bulk_insert(questions)`
     (full reload, stessa strategia di `IndexingPipeline`).
  - Dipendenze iniettate via costruttore: `QuizBankRepository`,
    `QuizQuestionMapper`, `QuizQuestionStoreRepository`, `IngestorConfig`.
- **`QuizIndexingPipelineBuilder`**: valida l'esistenza di
  `config.quiz_bank_path` con `FileNotFoundError` fail-fast prima di
  istanziare `PostgresClient`. Setter fluent `with_quiz_bank_repository`,
  `with_quiz_question_mapper`, `with_quiz_question_store_repository`
  (ritornano `Self`); `build()` usa controlli espliciti `is not None`,
  stesso pattern di `IndexingPipelineBuilder`. Default di
  `quiz_question_store_repository`:
  `QuizQuestionStoreRepository(PostgresClient(config.postgres),
  config.quiz_questions_table)`.

### `IngestorConfig`

- (`pydantic_settings.BaseSettings`, `frozen=True`) — pattern "config a due
  livelli": YAML committato (non-secret) + env/`.env` (solo secrets). Vedi
  `Configurazione (config a due livelli)` sotto per i dettagli; campi:
  - `cds_parsed_path: Path = Path("data/parsed/cds/codice_della_strada.json")`
  - `cds_cleaned_path: Path = Path("data/cleaned/cds/codice_della_strada.json")`
  - `cap_parsed_path: Path = Path("data/parsed/cap/codice_rca.json")`
  - `cap_cleaned_path: Path = Path("data/cleaned/cap/codice_rca.json")` —
    **non** `codice_assicurazioni_private.json` (610 articoli, codice
    completo); `codice_rca.json` contiene i 96 articoli rilevanti per
    RCA/patente.
  - `quiz_bank_path: Path = Path("data/parsed/quiz-patente-ab/quiz-patente-ab.json")`
  - `embedding_batch_size: int = 64`
  - `embedding: EmbeddingConfig = EmbeddingConfig()` (default `commons`)
  - `postgres: PostgresConnectionConfig` (obbligatorio, nessun default —
    `user`/`password` arrivano da env, il resto dal YAML)
  - `knowledge_chunks_table: str = "knowledge_chunks"`
  - `quiz_questions_table: str = "quiz_questions"`
- Il vecchio campo `vector_store: VectorStoreConfig` è stato sostituito da
  `postgres: PostgresConnectionConfig` (senza `table_name`, vedi
  `commons.md`) + i due campi `*_table` separati, iniettati nei rispettivi
  repository di scrittura (decisione 7 del piano quiz-bank).
  `configs/ingestor_config.yaml` aggiornato di conseguenza.

### Configurazione (config a due livelli)

- **YAML committato, non-secret** — `configs/ingestor_config.yaml` (root del
  progetto, fuori da `src/`): `cds_parsed_path`, `cds_cleaned_path`,
  `cap_parsed_path`, `cap_cleaned_path`, `quiz_bank_path`,
  `embedding_batch_size`, `embedding` (model_name `openrouter/openai/text-embedding-3-small`,
  `vector_dim=1536`, nessun prefisso), i campi non-secret di `postgres`
  (`host`, `port`, `dbname`), e `knowledge_chunks_table`/`quiz_questions_table`. La cartella `configs/`
  alla root è pensata come contenitore anche per le future configurazioni non
  sensibili (es. futuro `app_config.yaml` per l'app FastAPI).
- **Env / `.env`, solo secrets** — `.env.example` (root) documenta le sole
  variabili richieste: `POSTGRES__USER`, `POSTGRES__PASSWORD` (doppio
  underscore = `env_nested_delimiter`, popola `postgres.user` /
  `postgres.password`; rinominate da `VECTOR_STORE__USER`/`PASSWORD`),
  `OPENROUTER_API_KEY` (letta da litellm dall'ambiente, non da
  `IngestorConfig`). Mai committare un `.env` reale.
- **`IngestorConfig.model_config`**: `SettingsConfigDict(frozen=True,
  env_nested_delimiter="__", env_file=".env",
  yaml_file="configs/ingestor_config.yaml")`.
- **`settings_customise_sources`** override: precedenza
  `init_settings > env_settings > dotenv_settings >
  YamlConfigSettingsSource`. I secrets da env/`.env` hanno priorità sul YAML,
  che fornisce tutti i valori non sensibili con merge profondo dei campi
  annidati di `postgres` (es. `host`/`port`/`dbname` dal YAML, `user`/
  `password` da env, uniti nello stesso `PostgresConnectionConfig`).
- Questo pattern è pensato per essere riusato dal futuro `AppConfig`
  dell'app FastAPI (stessa cartella `configs/`, stesso schema
  `PostgresConnectionConfig`, stessi nomi tabella).
- **`commons/` resta privo di dipendenze `pydantic-settings`/env-loading** —
  `PostgresConnectionConfig` è un DTO puro popolato dal chiamante; solo
  `guidami_ai_patente_ingestor` (e in futuro l'app) dipendono da
  `pydantic-settings[yaml]`.

### `main.py`

- `config = IngestorConfig()` — `# pyright: ignore[reportCallIssue]` con
  commento, perché pyright non sa che i campi richiesti sono popolati a
  runtime da env/`.env`/YAML. Config caricata solo qui (entry point).
- Esegue in sequenza:
  1. `CleaningPipeline.run()` (`CleaningPipelineBuilder(config)
     .with_article_repository(ArticleRepository())
     .with_article_cleaner(ArticleCleaner()).build()`) — skip automatico per
     source già pulite;
  2. `IndexingPipeline.run()` (`IndexingPipelineBuilder(config)
     .with_article_repository(ArticleRepository())
     .with_article_chunker(ArticleChunker())
     .with_embedding_client(LiteLLMEmbeddingClient(config.embedding))
     .with_knowledge_chunk_store_repository(KnowledgeChunkStoreRepository(
       PostgresClient(config.postgres), config.knowledge_chunks_table))
     .build()`).
- `ArticleRepository()` viene istanziata due volte (una per pipeline) — è
  un componente stateless e senza config iniettata, condiviso/equivalente
  tra `CleaningPipelineBuilder` e `IndexingPipelineBuilder`; nessuna
  necessità di condividere la stessa istanza.
- Wiring delle dipendenze concrete esplicito tramite i `with_*` dei
  builder — visibile a colpo d'occhio nell'entry point, coerente con
  "explicit over implicit". I default interni dei builder restano comunque
  disponibili per chi costruisce le pipeline con override parziali (es. nei
  test).
- Script registrato: `ingest-knowledge = "guidami_ai_patente_ingestor.main:main"`.

### `reset_db.py`

- Entry point separato (`uv run reset-knowledge-db`,
  `reset-knowledge-db = "guidami_ai_patente_ingestor.reset_db:main"`) per
  svuotare la tabella `knowledge_chunks` in vista di un full reload, senza
  rieseguire `CleaningPipeline`/`IndexingPipeline`.
- Stesso pattern di `main.py`: `logging.basicConfig(...)`,
  `config = IngestorConfig()` caricata come unico entry point, `logger =
  logging.getLogger(__name__)` a livello di modulo.
- Istanzia `PostgresClient(config.postgres)` come context manager,
  `KnowledgeChunkStoreRepository(client, config.knowledge_chunks_table)
  .truncate()`; log `info` di completamento ("knowledge_chunks table
  truncated").

### `quiz_main.py`

- Entry point CLI (`uv run ingest-quiz`,
  `ingest-quiz = "guidami_ai_patente_ingestor.quiz_main:main"`). Stesso
  pattern di `main.py`: `logging.basicConfig(...)`, `config =
  IngestorConfig()` (`# pyright: ignore[reportCallIssue]`), `logger =
  logging.getLogger(__name__)` a livello di modulo.
- Esegue `QuizIndexingPipeline.run()` da
  `QuizIndexingPipelineBuilder(config).build()` (nessun `with_*` esplicito —
  i default del builder bastano), con log `info` "starting quiz indexing
  pipeline" / "quiz indexing pipeline completed".
- Pipeline separata da `main.py` (decisione 8 del piano quiz-bank): step
  diversi (chunk+embed vs map+dedup), eseguibili indipendentemente, pur
  condividendo la strategia di store (truncate + insert).

### `reset_quiz_db.py`

- Entry point separato (`uv run reset-quiz-db`,
  `reset-quiz-db = "guidami_ai_patente_ingestor.reset_quiz_db:main"`) per
  svuotare `quiz_questions` senza rieseguire `QuizIndexingPipeline`. Stesso
  pattern di `reset_db.py`: `PostgresClient(config.postgres)` come context
  manager, `QuizQuestionStoreRepository(client,
  config.quiz_questions_table).truncate()`; log `info` ("quiz_questions
  table truncated").

### Logging

- Nessun componente dedicato (niente `LoggingConfig`/`LoggingService` in
  `commons`) — scelta deliberata per evitare overengineering, si usa
  direttamente lo stdlib `logging`.
- `main.py` (composition root) chiama
  `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")`
  all'inizio di `main()`, prima di qualsiasi altro log; `logger =
  logging.getLogger(__name__)` a livello di modulo, con log `info` di
  inizio/fine di entrambe le pipeline ("starting cleaning pipeline" /
  "cleaning pipeline completed", "starting indexing pipeline" / "indexing
  pipeline completed").
- `cleaning_pipeline.py`: `logger = logging.getLogger(__name__)` a livello
  di modulo; log `info` per source skippata
  (`"{source}: {cleaned_path} already exists, skipping cleaning"`) o
  pulita (`"{source}: cleaned {n} articles -> {cleaned_path}"`).
- `indexing_pipeline.py`: `logger = logging.getLogger(__name__)` a livello
  di modulo, log `info` in `run()`:
  - dopo il load: conteggio articoli CdS/CAP caricati;
  - dopo il chunking: conteggio chunk CdS/CAP/totali;
  - in `_assign_embeddings`: una riga per batch (`embedding batch
    {n}/{total} ({size} chunks)`);
  - prima di `truncate()`: numero di chunk da inserire;
  - dopo `bulk_insert()`: completamento.
- `quiz_indexing_pipeline.py`: `logger = logging.getLogger(__name__)` a
  livello di modulo, log `info` in `run()` per ciascuno dei tre step (numero
  di domande madri caricate, numero di righe mappate, numero di righe da
  inserire prima del truncate, completamento dopo `bulk_insert`).
  `quiz_question_mapper.py`: `logger.warning` per ogni sotto-domanda
  scartata come duplicato esatto.
- **Convenzione**: i messaggi di log sono in inglese (a differenza di
  docstring/commenti, in italiano), per coerenza con eventuali strumenti di
  log aggregation/osservabilità.

## Test

- `tests/guidami_ai_patente_ingestor/repositories/test_article_repository.py` —
  `load`/`write` round-trip su fixture reali.
- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_cleaner.py` —
  su fixture reali (`tests/.../fixtures/cds_sample.json`, `cap_sample.json`,
  copiate da dati reali CdS/CAP): rimozione markup inline da `text` e
  `paragraphs`, rimozione ordinali, markup inline a metà comma, marcatori
  standalone scartati senza perdere commi, titolo avvolto in parentesi
  spogliato, comma interamente avvolto con riferimento a nota scartato.
  `test_duplicated_ordinal_prefix_is_fully_stripped` (fixture art. 226 in
  `cds_sample.json`) verifica che l'ordinale duplicato (`"2. 2. Nell'archivio
  nazionale..."`) sia rimosso completamente.
- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_chunker.py` —
  casi limite: articolo interamente abrogato, `text=""`, comma singolarmente
  abrogato, numerazione non numerica con markup multiplo (su `Article` già
  puliti).
- `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_cleaning/test_cleaning_pipeline.py` —
  unit con `Mock(spec=ArticleRepository)`: pulizia di entrambe le source
  quando nessun output esiste, skip per source con `cleaned_path` già
  presente.
- `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_cleaning/test_cleaning_pipeline_builder.py` —
  path `*_parsed_path` mancanti → `FileNotFoundError` aggregato.
- `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_indexing/test_indexing_pipeline.py` —
  unit, nessun I/O reale: batching degli embedding, ordine
  `truncate()`→`bulk_insert()`, load di entrambe le fonti (`*_cleaned_path`)
  completato prima del chunking.
- `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_indexing/test_indexing_pipeline_builder.py` —
  path `*_cleaned_path` mancanti → `FileNotFoundError` senza istanziare
  `LiteLLMEmbeddingClient`/`PostgresClient`.
- `tests/guidami_ai_patente_ingestor/configs/test_ingestor_config.py` —
  default path (`*_parsed_path`/`*_cleaned_path`/`quiz_bank_path`), default
  dei nomi tabella (`knowledge_chunks_table`/`quiz_questions_table`),
  `postgres: PostgresConnectionConfig` obbligatorio (`ValidationError` se
  assente con `_env_file=None`), immutabilità (`frozen=True`).
- `tests/guidami_ai_patente_ingestor/repositories/test_quiz_bank_repository.py` —
  `load` su fixture reale (`tests/.../fixtures/quiz_bank_sample.json`):
  mappatura in `QuizMainQuestion`/`QuizSubQuestion`.
- `tests/guidami_ai_patente_ingestor/services/quiz/test_quiz_question_mapper.py` —
  denormalizzazione `question_id`/`topic`, estrazione `image_filename` da
  path repo-relative (`PurePosixPath(...).name`), `image_filename=None` se
  assente, dedup su `(text.strip(), correct_answer, image)` (mantiene righe
  con stesso testo ma immagine o `correct_answer` diversi).
- `tests/guidami_ai_patente_ingestor/orchestrators/quiz_indexing/test_quiz_indexing_pipeline.py` —
  unit con `Mock(spec=...)` per repository/mapper: ordine
  load→map→truncate→bulk_insert.
- `tests/guidami_ai_patente_ingestor/orchestrators/quiz_indexing/test_quiz_indexing_pipeline_builder.py` —
  `quiz_bank_path` mancante → `FileNotFoundError` senza istanziare
  `PostgresClient`.
- `tests/guidami_ai_patente_ingestor/repositories/test_quiz_question_store_repository.py` —
  contro il Postgres del compose (no marker `integration`): `truncate` +
  `bulk_insert` su `quiz_questions`, fixture `client` analoga a
  `test_postgres_client.py`.
- `tests/commons/clients/test_postgres_client.py` — aggiornato per
  `PostgresConnectionConfig` (host/port/user/password/dbname/sslmode) al
  posto di `VectorStoreConfig`/`database_url`; nessuna assert su
  `similarity_search` (rimosso).
- **Non ancora implementato**: test di integrazione end-to-end contro
  Postgres + modello reali con marker `@pytest.mark.integration` dedicato
  (i test Postgres attuali girano contro il compose locale ma non sono
  marcati).
