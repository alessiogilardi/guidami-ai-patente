# Ingestor — Configurazione ed entry point

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/architecture-quiz-bank.md`.

## `IngestorConfig`

- (`pydantic_settings.BaseSettings`, `frozen=True`) — pattern "config a due
  livelli": YAML committato (non-secret) + env/`.env` (solo secrets). Vedi
  `Configurazione (config a due livelli)` sotto per i dettagli.
- I path hard-coded (`cds_parsed_path`, `cds_cleaned_path`, `cap_*`,
  `quiz_bank_path`) sono stati **rimossi** e sostituiti dal modello a layer
  configurabile. Campi attuali:
  - `layers: dict[str, Path]` — mappa nome-layer → directory radice. Nel YAML:
    `parsed: data/parsed`, `cleaned: data/cleaned`, `enriched: data/enriched`.
  - `sources: dict[str, SourceConfig]` — mappa nome-source →
    `SourceConfig(dir: str, file: str)`. Nel YAML: `cds`, `cap`, `quiz`
    con le rispettive directory e nome file JSON.
  - `knowledge_preparation: PipelineLayerConfig` — `input_layer: "parsed"`,
    `output_layer: "enriched"`.
  - `knowledge_indexing: PipelineLayerConfig` — `input_layer: "enriched"`.
  - `quiz_preparation: PipelineLayerConfig` — `input_layer: "cleaned"` (il
    file del quiz bank vive in `data/cleaned/`, non in `data/parsed/` —
    **deviazione dal piano**, che prevedeva `parsed`; adattato ai dati reali
    su disco). `output_layer: "enriched"`.
  - `quiz_indexing: PipelineLayerConfig` — `input_layer: "enriched"`.
  - `agents_dir: Path = Path("configs/agents")` — directory dei file YAML
    degli agenti.
  - `quiz_images_dir: Path` — directory contenente le immagini del quiz bank
    (usata da `ImageDescriptionEnricher`, SP06).
  - `embedding_batch_size: int = 64`
  - `embedding: EmbeddingConfig = EmbeddingConfig()` (default `commons`)
  - `postgres: PostgresConnectionConfig` (obbligatorio)
  - `embed_repealed: bool = False`
  - `knowledge_chunks_table: str = "knowledge_chunks"`
  - `quiz_questions_table: str = "quiz_questions"`

## `LayerResolver`

- Servizio di dominio in `services/layer_resolver.py` (non una configurazione
  Pydantic: riceve dipendenze iniettate e espone comportamento). Costruito
  dall'entry point a partire da `IngestorConfig.layers` + `IngestorConfig.sources`.
- `path(layer: str, source: str) -> Path` =
  `layers[layer] / sources[source].dir / sources[source].file`.
- Istanziato all'entry point da `IngestorConfig` e iniettato nei builder
  (config solo all'entry point, regola architetturale invariata).
- Aggiungere una nuova source o un nuovo layer è puramente dichiarativo nel
  YAML, senza modifiche al codice.

## Configurazione (config a due livelli)

- **YAML committato, non-secret** — `configs/ingestor_config.yaml` (root del
  progetto, fuori da `src/`): `layers`, `sources`, selettori per pipeline
  (`knowledge_preparation`, `knowledge_indexing`, `quiz_preparation`,
  `quiz_indexing`), `agents_dir`, `quiz_images_dir`, `embedding_batch_size`,
  `embedding` (`model_name: openrouter/openai/text-embedding-3-small`,
  `vector_dim: 1536`), i campi non-secret di `postgres` (`host`, `port`,
  `dbname`), `knowledge_chunks_table`, `quiz_questions_table`,
  `embed_repealed`. La cartella `configs/` alla root contiene anche la
  sottodirectory `agents/` con un file YAML per agente. È pensata come
  contenitore per tutte le configurazioni non sensibili del progetto.
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

- `config = IngestorConfig()` — `# pyright: ignore[reportCallIssue]`. Config
  caricata solo qui (entry point). Argomento CLI `--source` **obbligatorio**:
  la source da indicizzare (es. `cds`, `cap`). Esegue l'indexing per-source
  leggendo dal layer `enriched`.
- Flusso:
  1. `argparse.ArgumentParser` — `--source` required.
  2. `config = IngestorConfig()`, `layer_resolver = LayerResolver(...)`.
  3. `build_knowledge_indexing_flow(config, layer_resolver, LiteLLMEmbeddingClient(...),
     PostgresClient(...), source=args.source)` — la factory valida `source`
     contro `config.knowledge_indexing.sources` e assembla il flow.
  4. `flow.run()`.
- Script registrato: `ingest-knowledge = "guidami_ai_patente_ingestor.main:main"`.
- Usage: `uv run ingest-knowledge --source cds`, poi `uv run ingest-knowledge --source cap`.

## `prepare_knowledge_main.py`

- Entry point CLI (`uv run prepare-knowledge`). Argomento opzionale `--force`
  (default `False`): se passato, forza la rigenerazione degli artefatti
  `enriched` anche se esistono.
- Instanzia `config = IngestorConfig()`, `layer_resolver = LayerResolver(...)`,
  `Agent("article_contextualizer", config.agents_dir)`, poi esegue
  `DataPreparationPipeline.run(force=...)` via
  `DataPreparationPipelineBuilder(config, layer_resolver).build()`.
- Script registrato: `prepare-knowledge = "guidami_ai_patente_ingestor.prepare_knowledge_main:main"`.

## `reset_db.py`

- Entry point separato (`uv run reset-knowledge-db`,
  `reset-knowledge-db = "guidami_ai_patente_ingestor.reset_db:main"`) per
  svuotare **l'intera** tabella `knowledge_chunks` (tutte le source) in vista
  di un full reload da zero, senza rieseguire il flow di indexing.
- Stesso pattern di `main.py`: `logging.basicConfig(...)`,
  `config = IngestorConfig()` caricata come unico entry point, `logger =
  logging.getLogger(__name__)` a livello di modulo.
- Istanzia `PostgresClient(config.postgres)` come context manager,
  `KnowledgeChunkStoreRepository(client, config.knowledge_chunks_table)
  .truncate()`; log `info` di completamento ("knowledge_chunks table
  truncated").

## `quiz_main.py`

**Rimosso** (decommissioning SP03-bis). Lo script `ingest-quiz` e la voce
`[project.scripts]` corrispondente non esistono più. Il flow di quiz indexing
sarà reintrodotto come flow flowstep (SP04) quando implementato.

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
- Entry point attivi (`main.py`, `prepare_knowledge_main.py`,
  `reset_db.py`, `reset_quiz_db.py`) chiamano
  `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")`
  all'inizio di `main()`.
- `data_preparation_pipeline.py`: log `info` per source skippata (artefatto
  enriched già presente), log `info` per source processata (n articoli
  descritti), `logger.warning` per immagine non trovata su disco.
- Step del knowledge flow (`load_enriched_articles_step.py`,
  `chunk_articles_step.py`, `embed_chunks_step.py`, `store_chunks_step.py`):
  log `info` in `execute()` con conteggio articoli/chunk e source della run.
  `EmbeddingService` logga ogni batch (`embedding batch {n}/{total} ({k} items)`).
- `quiz_question_mapper.py`: `logger.warning` per ogni sotto-domanda scartata
  come duplicato esatto.
- **Convenzione**: i messaggi di log sono in inglese, per coerenza con
  eventuali strumenti di log aggregation/osservabilità.
