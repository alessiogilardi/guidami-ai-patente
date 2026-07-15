---
status: Implemented
effort: L
---
# Ingest Cli Revamp

References:
- `src/guidami_ai_patente_ingestor/cli.py` (current monolith, to be split)
- `src/guidami_ai_patente_ingestor/orchestrators/preparation_runner.py` (idempotency semantics the status matrix mirrors)
- `src/guidami_ai_patente_ingestor/services/layer_resolver.py` (per-source path resolution)
- `.claude/rules/code-conventions.md`, `~/.claude/rules/python/architecture.md`, `.claude/rules/dependency-injection.md`

## Context and motivation

The 'ingest' CLI is a 278-line monolith exposing only bare argparse help. Turn it into a real interface: complete help, a readable 'status' command (config view + per-command executability matrix), and an opt-in online mode with Postgres reachability and per-table health checks. Simplify the code into a dedicated cli/ package.

### Affected areas

src/guidami_ai_patente_ingestor/cli.py -> new **self-contained** cli/ package holding all CLI-only components under its own layered structure: cli/{main,parser,wiring}.py, cli/commands/{prepare,index,reset,status}.py, cli/services/status/{status_inspector,table_health_checker}.py, cli/models/status/* (readiness DTOs), cli/rendering/status_renderer.py. Shared infra stays in its layer: KnowledgeChunkStoreRepository & QuizQuestionStoreRepository (via the shared BulkInsertStoreRepository base) gain a table-existence + row-count method. Also: pyproject.toml (declare rich as direct dep, keep 'ingest = guidami_ai_patente_ingestor.cli:main' working via package __init__); LayerResolver reused for per-source path resolution; tests under tests/ mirroring the cli/ tree (online ones integration-marked); docs (CLAUDE.md command table + second brain); a new .claude/rules/cli-structure.md recording the self-containment convention.

### Success criteria

'ingest --help' and 'ingest <cmd> --help' list all commands with usage; 'ingest status' renders config with secrets masked plus a per-(command x entity) matrix (eseguibile/scartato/bloccato) computed filesystem-only with no DB contact; 'ingest status --online' additionally pings Postgres and reports per-table existence and row count, reflecting index/reset readiness from DB state (reset shows rows-to-truncate); the monolith is replaced by a cli/ package with separated parsing/dispatch/wiring and the entry point still works; tests pass and online-status tests are integration-marked and skipped by default.

## Non-goals

No new CLI library (argparse stays; no typer/click). Don't touch the other scripts (scrape-codice, scrape-cap, parse-domande). Don't change prepare/index/reset pipeline behavior or idempotency - status only observes. Health check limited to table existence + row count (no schema/column drift validation). No DB contact in default status (online is opt-in). Secrets never shown in clear.

## Decisions

1. **argparse for parsing + `rich` for presentation; no typer/click** — the requested value (readable config, colored matrix, health view) is presentation, delivered by `rich` (already in the env at 15.0.0 via litellm/pydantic-ai). The parser is config-driven (`choices` from `IngestorConfig` sources), which argparse expresses naturally and typer fights (wants static Enums).
2. **The `cli/` package is self-contained: CLI-only components live under it, replicating the layered structure (`cli/services/`, `cli/models/`, `cli/rendering/`)** — `StatusInspector`, `TableHealthChecker`, and the readiness DTOs exist solely to serve the `status` command and are not used by the `prepare`/`index`/`reset` pipelines, so co-locating them keeps the feature cohesive and removable (vertical slice) instead of polluting the global `services/`/`models/` packages. The CLI is a thin controller + a `rich` renderer; readiness/health logic stays in these CLI-local services producing plain DTOs, unit-testable without `rich` or a DB. **Boundary rule**: self-contained by default; genuinely shared infrastructure stays in its own top-level layer (see Decision 3).
3. **Health read primitives (`table_exists`, `row_count`) added to the shared `BulkInsertStoreRepository` base — NOT inside `cli/`** — that base is shared infrastructure (it already does `truncate`/`bulk_insert` for the pipelines and owns `table_name` + client); the read primitives are a low-cost addition there, and a parallel read repo would only duplicate the table-name wiring for two SELECTs. This is the explicit exception to Decision 2's self-containment. Repos return primitives; the CLI-local `TableHealthChecker` assembles the `TableHealth` DTO (repo stays free of domain models).
4. **Online mode is opt-in (`--online`); the default `status` never touches the network or secrets** — DB/LLM clients are built lazily per command in `wiring.py` (not eagerly in `main` as today), so `status` and `reset` run without `OPENROUTER_API_KEY`.
5. **Matrix aggregated per (command × entity); per-source states computed underneath** — display stays compact (e.g. "1/2 runnable"); the `CommandReadiness` DTO keeps the per-source breakdown.
6. **Config view masks secrets** (`postgres.password`, `open_router_config.api_key`) — never printed in clear; a rendering test asserts the plaintext secret is absent from the output.
7. **`reset` is included in the matrix** — offline: always "available"; online: annotated with rows-to-truncate from the table health check.
8. **`index` has no `SKIP` state offline** — its output is the DB table, invisible to a filesystem-only check; offline it is `RUNNABLE` (enriched input present) or `BLOCKED` (absent). Online it stays `RUNNABLE` (re-index overwrites) and is annotated with current row count ("N rows, will be replaced").
9. **Complete help = argparse `RawDescriptionHelpFormatter` + curated epilog**, not a parallel rich help system — keeps `-h` authoritative at every nesting level and avoids drift; a test asserts every command name appears in `format_help()`.
10. **`cli.py` becomes the `cli/` package; `main` is re-exported from `cli/__init__.py`** — the entry point string `guidami_ai_patente_ingestor.cli:main` is unchanged.

## Open questions / Risks

- **`rich` version floats with its transitive parents** (litellm/pydantic-ai). Declaring it a direct dependency is correct hygiene; pin a conservative lower bound (`>=13`) to avoid surprises without fighting the resolver.
- **`table_exists` via `to_regclass('name')`** relies on `search_path` resolving the unqualified name in `public`. Acceptable for this single-schema project; revisit only if a non-default schema is introduced.
- **Rendering tests must assert substrings, not exact layout** — `rich` output formatting is not a stable contract.

## Implementation tasks

### 1. Health read primitives on the store repository base
Add `table_exists() -> bool` (via `SELECT to_regclass(%s) IS NOT NULL`) and `row_count() -> int` (`SELECT count(*) FROM {table}`) to `BulkInsertStoreRepository` (`repositories/db/_bulk_insert_store_repository.py`), reusing `PostgresClient.fetch`. Both `KnowledgeChunkStoreRepository` and `QuizQuestionStoreRepository` inherit them unchanged. Keep return types primitive — no domain DTO leaks into the repo.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- Add: `tests/guidami_ai_patente_ingestor/repositories/test_knowledge_chunk_store_repository.py::test_row_count_and_table_exists` — `@pytest.mark.integration`, real DB: existing table returns `exists=True` and the correct count; a non-existent table name returns `exists=False` without issuing a `count`.

### 2. Status DTOs (CLI-local)
Create `cli/models/status/` (frozen pydantic, one class per file, re-exported via `__init__.py`):
- `ReadinessState(str, Enum)`: `RUNNABLE`, `SKIP`, `BLOCKED`.
- `SourceReadiness`: `source: str`, `state: ReadinessState`.
- `CommandReadiness`: `command: str`, `entity: str`, `sources: list[SourceReadiness]`, with a computed summary property (counts per state) for the aggregate display.
- `TableHealth`: `table: str`, `exists: bool`, `row_count: int | None`.
- `StatusReport`: `readiness: list[CommandReadiness]`, `tables: list[TableHealth] | None`, `db_reachable: bool | None`.

Imports: relative within `cli/models/status/`; absolute when crossing package boundaries.

**Tests**:
- Add: `tests/guidami_ai_patente_ingestor/cli/models/status/test_command_readiness.py::test_summary_counts_states` — the summary property aggregates per-source states correctly (e.g. 1 SKIP + 1 RUNNABLE).

### 3. `StatusInspector` service (CLI-local, filesystem-only readiness)
Create `cli/services/status/status_inspector.py` — `StatusInspector(config: IngestorConfig, layer_resolver: LayerResolver)` with `evaluate_readiness() -> list[CommandReadiness]`. Derives the command catalog from the four `PipelineLayerConfig` fields (`knowledge_preparation`, `quiz_preparation`, `knowledge_indexing`, `quiz_indexing`) plus the two table names. Per source, using `LayerResolver.path`:
- prepare: `SKIP` if output(enriched) exists; else `BLOCKED` if input(parsed) missing; else `RUNNABLE`.
- index: `BLOCKED` if input(enriched) missing; else `RUNNABLE` (no `SKIP` offline).
- reset: always `RUNNABLE` (no source dimension; single synthetic entry per entity).
No DB, no network — pure `Path.exists()`. Imports `IngestorConfig`/`LayerResolver` absolutely (cross-boundary), the readiness DTOs relatively from `cli/models/status/`.

**Tests**:
- Add: `tests/guidami_ai_patente_ingestor/cli/services/status/test_status_inspector.py::test_prepare_states_from_filesystem` — `tmp_path` layout drives `SKIP`/`BLOCKED`/`RUNNABLE` per source.
- Add: `...::test_index_has_no_skip_offline` — enriched present → `RUNNABLE`; absent → `BLOCKED`.

### 4. `TableHealthChecker` service (CLI-local, online only)
Create `cli/services/status/table_health_checker.py` — takes the two health-capable store repositories and returns `list[TableHealth]`, calling `table_exists()`/`row_count()` and skipping the count when the table is absent (`row_count=None`). Instantiated only on `--online`.

**Tests**:
- Add: `tests/guidami_ai_patente_ingestor/cli/services/status/test_table_health_checker.py::test_assembles_table_health_from_repos` — fake repos returning primitives; absent table yields `row_count=None`. No DB.

### 5. `cli/` package — wiring, parser, command modules, main
Replace `cli.py` with the `cli/` package:
- `wiring.py`: lazy DI builders extracted from the old `cli.py` (`build_layer_resolver`, `build_open_router_provider`, `build_postgres_client`, `build_tracker`, health repos). Providers/clients built per command, not upfront.
- `parser.py`: `build_parser(config)` — existing `prepare`/`index`/`reset` subcommands plus new `status [--online]`; `RawDescriptionHelpFormatter` with a curated epilog listing every command + usage examples.
- `commands/prepare.py`, `commands/index.py`, `commands/reset.py`: the current `_run_prepare`/`_dispatch_prepare`/`_run_index`/`_run_reset` bodies, verbatim in behavior, using `wiring.py`.
- `commands/status.py`: `run_status(config, layer_resolver, args)` — builds `StatusInspector` → readiness; if `--online`, best-effort `build_postgres_client` + repos + `TableHealthChecker` (catch `psycopg.Error` → `db_reachable=False`, `tables=None`); renders via `status_renderer`. Exit code 0 always.
- `main.py`: `main()` — logging, load config, `LayerResolver`, `build_parser`, dispatch by command.
- `__init__.py`: `from .main import main` (keeps `...cli:main`).
Delete the old `cli.py`.

**Tests**:
- Add: `tests/guidami_ai_patente_ingestor/cli/commands/test_prepare.py`, `test_index.py`, `test_reset.py` — migrated from `test_cli.py`, same behavioural assertions (dispatch → correct factory/runner/repo, `--force`, degrade-without-postgres), patch targets updated to the new module paths.
- Add: `tests/guidami_ai_patente_ingestor/cli/test_parser.py::test_required_source_exits` and `::test_help_lists_all_commands` — `format_help()` contains `prepare`, `index`, `reset`, `status`.
- Add: `tests/guidami_ai_patente_ingestor/cli/commands/test_status.py::test_online_db_unreachable_degrades` — monkeypatched client builder raising `psycopg.Error` → `db_reachable is False`, no exception.
- Remove: `tests/guidami_ai_patente_ingestor/test_cli.py` — superseded by the split above.

### 6. `status_renderer` (rich presentation)
Create `cli/rendering/status_renderer.py` — `render(config, report, console)`: a config `Panel` (secrets masked to `****`/`set`/`missing`), a readiness `Table` (command, entity, aggregate state, per-source detail), and, when `report.tables` is present, a health `Table` (table, exists, rows) plus row-count annotations on `index`/`reset`; when `db_reachable is False`, a visible "Postgres unreachable" note. Reads `IngestorConfig` directly (no config DTO).

**Tests**:
- Add: `tests/guidami_ai_patente_ingestor/cli/rendering/test_status_renderer.py::test_renders_matrix_and_masks_secrets` — render to `Console(record=True)`; asserts command names + states present and that the plaintext secret value is absent from the export.

### 7. Declare `rich` as a direct dependency
Add `rich>=13` to `[project.dependencies]` in `pyproject.toml`; run `uv sync`. Entry point line `ingest = "guidami_ai_patente_ingestor.cli:main"` stays unchanged.

### 8. Documentation
Add the `ingest status [--online]` row to the command table in `CLAUDE.md`. Run the `second-brain:update` skill to reflect the new self-contained `cli/` package layout (`cli/services/status/`, `cli/models/status/`, `cli/rendering/`) in `docs/` (layout.md, architecture.md). The self-containment convention is already recorded in `.claude/rules/cli-structure.md` (created during planning) — verify it is still accurate at implementation time.
## Definition of Done

Variable block (plan-specific):

- [x] Entry point intact: `uv run python -c "from guidami_ai_patente_ingestor.cli import main"` exits 0
- [x] Monolith removed: `test ! -f src/guidami_ai_patente_ingestor/cli.py` and `test -d src/guidami_ai_patente_ingestor/cli`
- [x] Package modules present: `cli/main.py`, `cli/parser.py`, `cli/wiring.py`, `cli/commands/{prepare,index,reset,status}.py`, `cli/rendering/status_renderer.py` all exist
- [x] Status services are CLI-local: `cli/services/status/status_inspector.py` and `cli/services/status/table_health_checker.py` exist
- [x] Status DTOs are CLI-local: `cli/models/status/` exists and contains the readiness DTO files
- [x] Self-containment respected — no top-level leakage: `test ! -e src/guidami_ai_patente_ingestor/services/status` and `test ! -e src/guidami_ai_patente_ingestor/models/status`
- [x] Convention recorded: `test -f .claude/rules/cli-structure.md`
- [x] Health primitives added: `grep -q "def table_exists" src/guidami_ai_patente_ingestor/repositories/db/_bulk_insert_store_repository.py` and `grep -q "def row_count" ...`
- [x] Complete help lists every command: `uv run ingest --help` output contains `prepare`, `index`, `reset`, and `status`
- [x] Default status is offline: `uv run ingest status` exits 0 with no reachable DB / no `OPENROUTER_API_KEY` set
- [x] `--online` degrades gracefully: `uv run ingest status --online` exits 0 and shows a "Postgres unreachable" note when the DB is down
- [x] Old test module retired: `test ! -f tests/guidami_ai_patente_ingestor/test_cli.py`
- [x] Secrets never printed in clear: `test_renders_matrix_and_masks_secrets` passes
- [x] `rich` declared: `grep -q "rich" pyproject.toml`
- [x] `CLAUDE.md` command table includes an `ingest status` row: `grep -q "ingest status" CLAUDE.md`

Fixed block (same for every plan):

- [x] `uv run pytest` green (including new tests)
- [x] `uv run pyright` clean
- [x] `uv run ruff check src tests` clean
- [x] Plan updated to `status: Implemented`
