# Ingestor — Configuration and entry points

## `IngestorConfig`

- (`pydantic_settings.BaseSettings`, `frozen=True`) — "two-level config" pattern:
  committed YAML (non-secret) + env/`.env` (secrets only). See
  `Configuration (two-level config)` below for details.
- Hard-coded paths (`cds_parsed_path`, `cds_cleaned_path`, `cap_*`,
  `quiz_bank_path`) have been **removed** and replaced by the configurable
  layer model. Current fields:
  - `layers: dict[str, Path]` — layer name → root directory mapping. In the YAML:
    `parsed: data/parsed`, `cleaned: data/cleaned`, `enriched: data/enriched`.
  - `sources: dict[str, SourceConfig]` — source name →
    `SourceConfig(dir: str, file: str)`. In the YAML: `cds`, `cap`, `quiz`
    with their respective directories and JSON file names.
  - `knowledge_preparation: PipelineLayerConfig` — `input_layer: "parsed"`,
    `output_layer: "enriched"`.
  - `knowledge_indexing: PipelineLayerConfig` — `input_layer: "enriched"`.
  - `quiz_preparation: PipelineLayerConfig` — `input_layer: "parsed"`,
    `output_layer: "enriched"`, `sources: ["quiz"]`. **Changed in SP09**: previously
    `input_layer: "cleaned"` (the quiz bank started directly from the `cleaned`
    layer, without its own `parsed`); SP09 introduced an explicit `parsed` layer
    for the quiz (output of the PDF parser) and moved the flatten+dedup to the
    cleaning stage (`build_quiz_cleaning_flow`), mirroring the knowledge topology.
  - `quiz_indexing: PipelineLayerConfig` — `input_layer: "enriched"`.
  - `agents_dir: Path = Path("configs/agents")` — directory containing agent
    YAML files.
  - `quiz_images_dir: Path` — directory containing quiz bank images
    (used by `ImageDescriptionEnricher`).
  - `embedding_batch_size: int = 64`
  - `embedding: EmbeddingConfig = EmbeddingConfig()` (default from `commons`)
  - `postgres: PostgresConnectionConfig` (required)
  - `embed_repealed: bool = False`
  - `knowledge_chunks_table: str = "knowledge_chunks"`
  - `quiz_questions_table: str = "quiz_questions"`

## `LayerResolver`

- Domain service in `services/layer_resolver.py` (not a Pydantic config:
  receives injected dependencies and exposes behaviour). Built by the entry
  point from `IngestorConfig.layers` + `IngestorConfig.sources`.
- `path(layer: str, source: str) -> Path` =
  `layers[layer] / sources[source].dir / sources[source].file`.
- Instantiated at the entry point from `IngestorConfig` and injected into
  builders (config at entry point only — unchanged architectural rule).
- Adding a new source or a new layer is purely declarative in the YAML,
  with no code changes.

## Configuration (two-level config)

- **Committed, non-secret YAML** — `configs/ingestor_config.yaml` (project
  root, outside `src/`): `layers`, `sources`, pipeline selectors
  (`knowledge_preparation`, `knowledge_indexing`, `quiz_preparation`,
  `quiz_indexing`), `agents_dir`, `quiz_images_dir`, `embedding_batch_size`,
  `embedding` (`model_name: openrouter/openai/text-embedding-3-small`,
  `vector_dim: 1536`), the non-secret `postgres` fields (`host`, `port`,
  `dbname`), `knowledge_chunks_table`, `quiz_questions_table`,
  `embed_repealed`. The `configs/` folder at the root also contains the
  `agents/` subdirectory with one YAML file per agent. It is designed as
  a container for all non-sensitive project configuration.
- **Env / `.env`, secrets only** — `.env.example` (root) documents the only
  required variables: `POSTGRES__USER`, `POSTGRES__PASSWORD` (double
  underscore = `env_nested_delimiter`, populates `postgres.user` /
  `postgres.password`; renamed from `VECTOR_STORE__USER`/`PASSWORD`),
  `OPENROUTER_API_KEY` (optional — required only when using
  `LiteLLMEmbeddingClient` instead of the local client; read by litellm
  from the environment, not from `IngestorConfig`). Never commit a real `.env`.
- **`IngestorConfig.model_config`**: `SettingsConfigDict(frozen=True,
  env_nested_delimiter="__", env_file=".env",
  yaml_file="configs/ingestor_config.yaml")`.
- **`settings_customise_sources`** override: precedence
  `init_settings > env_settings > dotenv_settings >
  YamlConfigSettingsSource`. Secrets from env/`.env` take priority over the
  YAML, which provides all non-sensitive values with deep merge of nested
  `postgres` fields (e.g. `host`/`port`/`dbname` from YAML, `user`/
  `password` from env, merged into the same `PostgresConnectionConfig`).
- This pattern is designed to be reused by the future FastAPI app's `AppConfig`
  (same `configs/` folder, same `PostgresConnectionConfig` schema, same table
  names).
- **`commons/` remains free of `pydantic-settings`/env-loading dependencies** —
  `PostgresConnectionConfig` is a pure DTO populated by the caller; only
  `guidami_ai_patente_ingestor` (and the future app) depend on
  `pydantic-settings[yaml]`.

## `cli.py` (SP07 — single entry point)

All the old entry points (`main.py`, `reset_db.py`, `reset_quiz_db.py`)
have been removed and replaced by the single `cli.py` file. The corresponding
`[project.scripts]` entries (`ingest-knowledge`, `reset-knowledge-db`,
`reset-quiz-db`) have been replaced by the single script
`ingest = "guidami_ai_patente_ingestor.cli:main"`.

### Subcommand structure

```
ingest prepare knowledge --source <cds|cap> [--force]
ingest prepare quiz       [--force]
ingest index   knowledge --source <cds|cap>
ingest index   quiz
ingest reset   knowledge
ingest reset   quiz
```

### Implemented decisions

- **`IngestorConfig` and `LayerResolver` instantiated once** in
  `main()`, before argument parsing. `_build_parser(config)` receives
  the already-built config to populate `choices=` from the source catalogs
  (`config.knowledge_preparation.sources`, `config.knowledge_indexing.sources`,
  `config.quiz_preparation.sources`) — no hardcoded lists in the CLI.
- **Nested argparse**: `add_subparsers(dest="command")` → `"prepare"` /
  `"index"` / `"reset"`; each has a second `add_subparsers(dest="entity")`
  → `"knowledge"` / `"quiz"`. `required=True` on all levels.
- **`match/case`** for dispatch on `args.command` and `args.entity` (Python
  3.12+ structural pattern matching).
- **`prepare knowledge`** → calls `build_knowledge_cleaning_flow` +
  `build_knowledge_enrichment_flow` (with `source` from the CLI) + `run_preparation`
  twice (for `_CLEANED_LAYER` and for `output_layer` from config). Intermediate
  layer `"cleaned"` as a module-private constant `_CLEANED_LAYER`.
- **`prepare quiz`** → same two-flow structure; single source read from
  `config.quiz_preparation.sources[0]` (not exposed as a CLI argument —
  the quiz has a single source).
- **`index`** → builds `LiteLLMEmbeddingClient` + `PostgresClient` and
  calls the corresponding flow factory + `flow.run()`.
- **`reset`** → builds `PostgresClient` + target repository (no flow);
  calls `truncate()` on the correct table (`KnowledgeChunkStoreRepository` or
  `QuizQuestionStoreRepository`).

### `_build_parser(config)`

Private function (not a class): builds and returns the argparse parser. Receives
`config: IngestorConfig` to read source catalogs without hardcoded lists.

### Private dispatch functions

- `_run_prepare(config, layer_resolver, args)` — handles `prepare`
- `_run_index(config, layer_resolver, args)` — handles `index`
- `_run_reset(config, args)` — handles `reset`

Each uses `match args.entity` to select the correct branch.

## Logging

- No dedicated component (no `LoggingConfig`/`LoggingService` in
  `commons`) — deliberate choice to avoid over-engineering; uses
  stdlib `logging` directly.
- `cli.py:main()` calls `logging.basicConfig(level=logging.INFO,
  format="%(asctime)s %(levelname)s %(name)s: %(message)s")`.
- Knowledge flow steps (`chunk_articles_step.py`, `embed_chunks_step.py`,
  `store_chunks_step.py`): `info` log in `execute()` with article/chunk
  count and source of the run. `EmbeddingService` logs each batch
  (`embedding batch {n}/{total} ({k} items)`).
- `cli.py`: `info` log on completion of each `index` operation (e.g.
  `"knowledge indexing completed for source 'cds'"`).
- `image_description_enricher.py`: `logger.warning` for every image
  not found on disk or for every `describe` failure.
- **Convention**: log messages are in English, for consistency with
  any log aggregation/observability tooling.
