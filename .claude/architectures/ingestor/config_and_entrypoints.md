# Ingestor — Configurazione ed entry point

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/architecture-quiz-bank.md`,
`plans/ingest--orchestrator/07-cli-and-decommission.md`.

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
  - `quiz_preparation: PipelineLayerConfig` — `input_layer: "parsed"`,
    `output_layer: "enriched"`, `sources: ["quiz"]`. **Cambiato in SP09**: in
    precedenza era `input_layer: "cleaned"` (il quiz bank partiva
    direttamente dal layer `cleaned`, senza un proprio `parsed`); SP09 ha
    introdotto un layer `parsed` esplicito per il quiz (output del parser
    PDF) e spostato il flatten+dedup nello stadio di cleaning
    (`build_quiz_cleaning_flow`), a specchio del knowledge.
  - `quiz_indexing: PipelineLayerConfig` — `input_layer: "enriched"`.
  - `agents_dir: Path = Path("configs/agents")` — directory dei file YAML
    degli agenti.
  - `quiz_images_dir: Path` — directory contenente le immagini del quiz bank
    (usata da `ImageDescriptionEnricher`).
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

## `cli.py` (SP07 — unico entry point)

Tutti i vecchi entry point (`main.py`, `reset_db.py`, `reset_quiz_db.py`)
sono stati rimossi e sostituiti dall'unico file `cli.py`. Le corrispondenti
voci `[project.scripts]` (`ingest-knowledge`, `reset-knowledge-db`,
`reset-quiz-db`) sono state sostituite dall'unico script
`ingest = "guidami_ai_patente_ingestor.cli:main"`.

### Struttura sottocomandi

```
ingest prepare knowledge --source <cds|cap> [--force]
ingest prepare quiz       [--force]
ingest index   knowledge --source <cds|cap>
ingest index   quiz
ingest reset   knowledge
ingest reset   quiz
```

### Decisioni implementate

- **`IngestorConfig` e `LayerResolver` istanziati una sola volta** in
  `main()`, prima del parsing degli argomenti. `_build_parser(config)` riceve
  il config già costruito per popolare `choices=` dai cataloghi sorgente
  (`config.knowledge_preparation.sources`, `config.knowledge_indexing.sources`,
  `config.quiz_preparation.sources`) — nessuna lista hardcoded nella CLI.
- **Argparse annidato**: `add_subparsers(dest="command")` → `"prepare"` /
  `"index"` / `"reset"`; ciascuno ha un secondo `add_subparsers(dest="entity")`
  → `"knowledge"` / `"quiz"`. `required=True` su tutti i livelli.
- **`match/case`** per il dispatch su `args.command` e `args.entity` (Python
  3.12+ structural pattern matching).
- **`prepare knowledge`** → chiama `build_knowledge_cleaning_flow` +
  `build_knowledge_enrichment_flow` (con `source` dal CLI) + `run_preparation`
  due volte (per `_CLEANED_LAYER` e per `output_layer` da config). Layer
  intermedio `"cleaned"` come costante `_CLEANED_LAYER` nel modulo.
- **`prepare quiz`** → stessa struttura a due flow; source unica letta da
  `config.quiz_preparation.sources[0]` (non esposta come argomento CLI —
  il quiz ha una sola source).
- **`index`** → costruisce `LiteLLMEmbeddingClient` + `PostgresClient` e
  chiama la factory di flow corrispondente + `flow.run()`.
- **`reset`** → costruisce `PostgresClient` + repository target (nessun flow);
  chiama `truncate()` sulla tabella giusta (`KnowledgeChunkStoreRepository` o
  `QuizQuestionStoreRepository`).

### `_build_parser(config)`

Funzione privata (non classe): costruisce e ritorna il parser argparse. Riceve
`config: IngestorConfig` per leggere i cataloghi sorgenti senza liste
hardcoded.

### Funzioni di dispatch private

- `_run_prepare(config, layer_resolver, args)` — gestisce `prepare`
- `_run_index(config, layer_resolver, args)` — gestisce `index`
- `_run_reset(config, args)` — gestisce `reset`

Ciascuna usa `match args.entity` per selezionare il ramo corretto.

## Logging

- Nessun componente dedicato (niente `LoggingConfig`/`LoggingService` in
  `commons`) — scelta deliberata per evitare overengineering, si usa
  direttamente lo stdlib `logging`.
- `cli.py:main()` chiama `logging.basicConfig(level=logging.INFO,
  format="%(asctime)s %(levelname)s %(name)s: %(message)s")`.
- Step del knowledge flow (`chunk_articles_step.py`, `embed_chunks_step.py`,
  `store_chunks_step.py`): log `info` in `execute()` con conteggio
  articoli/chunk e source della run. `EmbeddingService` logga ogni batch
  (`embedding batch {n}/{total} ({k} items)`).
- `cli.py`: log `info` al completamento di ogni operazione `index` (es.
  `"knowledge indexing completed for source 'cds'"`).
- `image_description_enricher.py`: `logger.warning` per ogni immagine
  non trovata su disco o per ogni fallimento di `describe`.
- **Convenzione**: i messaggi di log sono in inglese, per coerenza con
  eventuali strumenti di log aggregation/osservabilità.
