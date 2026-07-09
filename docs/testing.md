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

## Tools

- **pytest** + **pytest-asyncio** (`asyncio_mode = "auto"`) — no
  `pytest-cov`, `pytest-mock`, or `faker`; no coverage tooling configured.
- Run commands: `uv run pytest`, `uv run pytest tests/path/to/test_file.py::test_name`.
- Adjacent quality gates: `ruff` (line-length 99, py312, Google docstring
  convention, tests exempted from docstring rules) and `pyright`
  (`include = ["src"]` only — **`tests/` is not type-checked by pyright**).
- A PostToolUse hook (`.claude/settings.json`) runs `ruff` autofix then
  `pyright` automatically on every `Edit`/`Write` touching a `*.py` file.

## Conventions

`tests/` mirrors `src/` 1:1 for every package that has tests:
`tests/commons/` ~ `src/commons/`, `tests/domain/` ~ `src/domain/`,
`tests/flowstep/` ~ `src/flowstep/`, `tests/guidami_ai_patente_ingestor/`
~ `src/guidami_ai_patente_ingestor/` (subfolder structure matches,
including `orchestrators/steps/{generic,knowledge}` and
`services/{knowledge,quiz}/enrichers`). No tests yet for `src/parsers/`,
`src/scrapers/`, or the empty `src/guidami_ai_patente/` scaffold.

No `__init__.py` in any test directory — see
`.claude/rules/code-conventions.md` for the rule and rationale.

**There is no `conftest.py` anywhere in the project.**
`tests/guidami_ai_patente_ingestor/fixtures/` is not pytest fixtures —
it holds static JSON sample files (`cds_sample.json`, `cap_sample.json`,
`quiz_bank_sample.json`) used as real input data by tests such as
`test_article_cleaner.py` and `test_article_chunker.py`. Don't go looking
for a `conftest.py`-based fixture registry; this directory is the fixture
mechanism in this project.

Naming: `test_*.py`, generally one test file per source file/class (e.g.
`test_article_chunker.py` for `article_chunker.py`).

*Last updated: 2026-07-09 — verified against commit `8ca395d`.*
