# Ingestor — Configurazione ed entry point

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/architecture-quiz-bank.md`.

## `IngestorConfig`

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
  - `embed_repealed: bool = False` — se `False` (default e valore in YAML),
    i chunk con `is_repealed=True` vengono esclusi dall'embedding in
    `IndexingPipeline._filter_chunks`; impostare a `True` per indicizzare
    anche gli articoli abrogati.
  - `knowledge_chunks_table: str = "knowledge_chunks"`
  - `quiz_questions_table: str = "quiz_questions"`
- Il vecchio campo `vector_store: VectorStoreConfig` è stato sostituito da
  `postgres: PostgresConnectionConfig` (senza `table_name`, vedi
  `commons.md`) + i due campi `*_table` separati, iniettati nei rispettivi
  repository di scrittura (decisione 7 del piano quiz-bank).
  `configs/ingestor_config.yaml` aggiornato di conseguenza.

## Configurazione (config a due livelli)

- **YAML committato, non-secret** — `configs/ingestor_config.yaml` (root del
  progetto, fuori da `src/`): `cds_parsed_path`, `cds_cleaned_path`,
  `cap_parsed_path`, `cap_cleaned_path`, `quiz_bank_path`,
  `embedding_batch_size`, `embedding` (`model_name:
  openrouter/openai/text-embedding-3-small`, `vector_dim: 1536`), i campi
  non-secret di `postgres` (`host`, `port`, `dbname`), e
  `knowledge_chunks_table`/`quiz_questions_table`. La cartella `configs/` alla
  root è pensata come contenitore anche per le future configurazioni non
  sensibili (es. futuro `app_config.yaml` per l'app FastAPI).
- **Env / `.env`, solo secrets** — `.env.example` (root) documenta le sole
  variabili richieste: `POSTGRES__USER`, `POSTGRES__PASSWORD` (doppio
  underscore = `env_nested_delimiter`, popola `postgres.user` /
  `postgres.password`; rinominate da `VECTOR_STORE__USER`/`PASSWORD`),
  `OPENROUTER_API_KEY` (opzionale — necessaria solo se si usa
  `LiteLLMEmbeddingClient` al posto del client locale; letta da litellm
  dall'ambiente, non da `IngestorConfig`). Mai committare un `.env` reale.
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

## `main.py`

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

## `reset_db.py`

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

## `quiz_main.py`

- Entry point CLI (`uv run ingest-quiz`,
  `ingest-quiz = "guidami_ai_patente_ingestor.quiz_main:main"`). Stesso
  pattern di `main.py`: `logging.basicConfig(...)`, `config =
  IngestorConfig()` (`# pyright: ignore[reportCallIssue]`), `logger =
  logging.getLogger(__name__)` a livello di modulo.
- Esegue `QuizIndexingPipeline.run()` da
  `QuizIndexingPipelineBuilder(config)
  .with_embedding_client(LiteLLMEmbeddingClient(config.embedding))
  .build()` — l'embedding client è passato esplicitamente, coerente con il
  pattern di `main.py` (wiring visibile nell'entry point). Log `info`
  "starting quiz indexing pipeline" / "quiz indexing pipeline completed".
- Pipeline separata da `main.py` (decisione 8 del piano quiz-bank): step
  diversi (corpus: load+chunk+embed vs quiz: load+map+embed), eseguibili
  indipendentemente, pur condividendo la strategia di store (truncate +
  insert) e lo stesso embedder (`text-embedding-3-small` via
  `LiteLLMEmbeddingClient`).

## `reset_quiz_db.py`

- Entry point separato (`uv run reset-quiz-db`,
  `reset-quiz-db = "guidami_ai_patente_ingestor.reset_quiz_db:main"`) per
  svuotare `quiz_questions` senza rieseguire `QuizIndexingPipeline`. Stesso
  pattern di `reset_db.py`: `PostgresClient(config.postgres)` come context
  manager, `QuizQuestionStoreRepository(client,
  config.quiz_questions_table).truncate()`; log `info` ("quiz_questions
  table truncated").

## Logging

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
  livello di modulo, log `info` in `run()` per ciascuno dei quattro step
  (numero di domande madri caricate, numero di righe mappate, in
  `_assign_embeddings` una riga per batch `embedding batch {n}/{total}
  ({size} questions)`, numero di righe da inserire prima del truncate,
  completamento dopo `bulk_insert`).
  `quiz_question_mapper.py`: `logger.warning` per ogni sotto-domanda
  scartata come duplicato esatto.
- **Convenzione**: i messaggi di log sono in inglese (a differenza di
  docstring/commenti, in italiano), per coerenza con eventuali strumenti di
  log aggregation/osservabilità.
