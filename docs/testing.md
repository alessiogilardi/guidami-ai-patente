# Testing

## Strategy

Two test types: plain unit tests (the large majority) and
`@pytest.mark.integration` tests that require real external services
(Postgres via Docker Compose, or local model downloads for the
sentence-transformers embedding client). Integration tests are a small,
deliberate minority layered on top of a unit-heavy suite that relies on
mocking/fakes for collaborators (LLM agents, clients).

Default `pytest` invocation excludes integration tests
(`addopts = "-m 'not integration'"`), matching the "Run tests" command in
`CLAUDE.md`. Run them explicitly when touching Postgres-backed
repositories or embedding clients.

**Postgres integration tests never touch the dev database.** They run
against a fully isolated, ephemeral stack defined in
`docker/docker-compose.test.yml` — its own container, its own port
(5433, vs. 5432 for the dev stack in `docker/docker-compose.yml`), and a
`tmpfs` data directory that is never persisted to disk. This exists
because every Postgres-backed integration test fixture used to hardcode
`host="localhost", port=5432, dbname="guidami_ai_patente"` — the exact
connection details of the dev stack's bind-mounted volume — and truncated
real tables in setup/teardown; running the suite against a populated dev
database destroyed real ingested data. See "Conventions" below for the
fixtures that start/stop the isolated stack automatically.

## Tools

- **pytest** + **pytest-asyncio** (`asyncio_mode = "auto"`) — no
  `pytest-cov`, `pytest-mock`, or `faker`; no coverage tooling configured.
- Run commands: `uv run pytest`, `uv run pytest tests/path/to/test_file.py::test_name`.
- Adjacent quality gates: `ruff` (line-length 99, py312, Google docstring
  convention, tests exempted from docstring rules; rule set `E,F,I,G,D,UP`
  plus `SIM` simplify and `C901` cyclomatic complexity with
  `max-complexity = 10`, `src/scrapers/**` and `src/parsers/**` exempted
  from `C901` as script entry points) and `pyright`
  (`include = ["src"]` only — **`tests/` is not type-checked by pyright**).
- A PostToolUse hook (`.claude/settings.json`) runs `ruff` autofix then
  `pyright` automatically on every `Edit`/`Write` touching a `*.py` file.

## Conventions

`tests/` mirrors `src/` 1:1 for every package that has tests:
`tests/commons/` ~ `src/commons/`, `tests/domain/` ~ `src/domain/`,
`tests/guidami_ai_patente_ingestor/` ~ `src/guidami_ai_patente_ingestor/`
(subfolder structure matches, including
`orchestrators/steps/{generic,knowledge}` and
`services/{knowledge,quiz}/enrichers`), `tests/parsers/` ~ `src/parsers/`.
`tests/parsers/test_questions_pdf.py` unit-tests `_get_headers_with_y` in
isolation via a small local fake page object exposing only
`extract_words()` (the one pdfplumber method the function calls) — the
PDF-parsing entry point `main_questions` itself is not tested (would
require a real PDF plus `fitz`/`pdfplumber`/image extraction).
`tests/scrapers/test_normattiva.py` follows the same precedent: it
unit-tests `_parse_article` (and the private helpers it delegates to —
`_extract_comma_number_and_text`, `_split_leading_title`/
`_split_into_comma_segments`/`_validate_contiguous_numbering` for the
Regolamento's single-block `art-just-text-akn` body since spec 0003 Phase 1,
plus, since spec 0004 T-6's `C901` complexity split, the five smaller
orchestration steps `_parse_article` itself now delegates to —
`_extract_numero_and_titolo`, `_build_commi_from_comma_divs`,
`_apply_pre_comma_block`, `_detect_article_repeal`,
`_apply_just_text_akn_body` — exercised only indirectly, through
`_parse_article`'s existing characterization tests, not with dedicated unit
tests of their own) against small, hand-built HTML fixtures using the real
Normattiva CSS class names (`art-comma-div-akn`, `comma-num-akn`,
`art_text_in_comma`, `art-just-text-akn`, `article-heading-akn`,
`article-pre-comma-text-akn`), not real scraped pages. Spec 0004 T-4 added
direct network-free coverage of `main()` (`RunArtifactWriter` wiring, the
`--dry-run` no-I/O path) and of the extracted `_process_article` (each of
the three skip categories plus the success path), each via a mocked
`httpx.Client`/`RunArtifactWriter` — the former `main_cds`/`main_cap`/
`main_reg` per-law entry points this section used to call out as untested no
longer exist (spec 0004 T-5 replaced them with one `cli_main`, itself
covered by `test_cli_main_dispatches_to_main_with_resolved_source`/
`test_cli_main_dry_run_flag_forwarded` via a monkeypatched `main`).
`tests/guidami_ai_patente/api/routers/test_health.py` is the first test for
`src/guidami_ai_patente/`: FastAPI's `TestClient` (`fastapi.testclient`)
against an app built by `create_app(AppConfig(...))` with an inline,
non-Docker `PostgresConnectionConfig` — the route under test never opens a
DB connection, so no fixture from `_postgres_test_stack` is needed. This is
the project's first use of `TestClient` and establishes the pattern for
future `guidami_ai_patente/` endpoint tests.
`flowstep` is an external git dependency (not part of this repo's `src/`
or `tests/`), so it has no local test mirror here — see
`docs/architecture.md`.

No `__init__.py` in any test directory — see
`.claude/rules/code-conventions.md` for the rule and rationale.

**`tests/conftest.py` is the single, root-level fixture registry for the
suite** — there is no other `conftest.py` anywhere else in the project. It
defines `RecordingProgressReporter`, a test double for the `ProgressReporter`
protocol that records every call `(method_name, args)` in order (with a
`count(method)` helper), and the `progress_recorder` fixture that hands out a
fresh instance per test.

It also defines the two fixtures every Postgres-backed integration test
relies on for isolation, both session-scoped:
- `_postgres_test_stack` — starts the isolated test stack
  (`docker compose -f docker/docker-compose.test.yml -p guidami-ai-patente-test
  up -d --wait`) the first time a collected test requests it, and tears it
  down (`down -v`) once at the end of the session. Never invoked directly by
  test modules.
- `postgres_test_config` — depends on `_postgres_test_stack` and returns the
  `PostgresConnectionConfig` for the isolated stack (port 5433). Carries a
  defensive `assert config.port != 5432` against ever pointing back at the
  dev database. Every per-module `client` fixture that opens a real
  `PostgresClient` (e.g.
  `tests/guidami_ai_patente_ingestor/repositories/test_article_store_repository.py`)
  requests this fixture rather than building its own
  `PostgresConnectionConfig`.
`tests/guidami_ai_patente_ingestor/fixtures/` is a separate mechanism, not
pytest fixtures — it holds static JSON sample files (`cds_sample.json`,
`cap_sample.json`, `quiz_bank_sample.json`) used as real input data by
`test_json_repository.py`'s `ParsedArticleModel` field-mapping tests.

`test_article_cleaner.py` constructs its `ParsedArticleModel` instances
inline rather than via the shared JSON fixtures (spec 0001 T-5/T-6): once
`ParsedArticleModel` moved to a `commas: list[ParsedComma]` shape, its input
no longer matched the fixture files' original shape closely enough to be
worth sharing. `test_json_repository.py`'s parametrized round-trip test
(`ROUND_TRIP_CASES`) covers `CleanedArticleModel` inline instead (spec 0001
T-15, after `EnrichedArticleModel` was deleted).

Naming: `test_*.py`, generally one test file per source file/class (e.g.
`test_article_cleaner.py` for `article_cleaner.py`).

*Last updated: 2026-08-06 — verified against commit `91028b2`; documented the
isolated ephemeral Postgres test stack (`docker/docker-compose.test.yml`) and
the `_postgres_test_stack`/`postgres_test_config` fixtures that replaced
per-file hardcoded dev-database connections in integration tests.*

*Last updated: 2026-08-17 — verified against commit `b3ca8b30` (working tree ahead of it,
uncommitted, on `feat/backend`); added `tests/guidami_ai_patente/api/routers/test_health.py`,
the first test for `src/guidami_ai_patente/` and the project's first use of FastAPI's
`TestClient`, covering the `pywire.fastapi.wire()`-based DI added to `GET /health`
(see `docs/architecture.md` and `adr/0016-pywire-native-fastapi-wiring.md`).*
