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
against the app, resolved through the shared `api_client` fixture (see
below) rather than building its own `AppConfig`/`TestClient` — this is the
project's first use of `TestClient` and establishes the pattern for future
`guidami_ai_patente/` endpoint tests: consume `api_client`, never call
`create_app` directly from a test.

**At most one `AppConfig` per pytest session (spec 0012 constraint,
ADR 0023).** `tests/conftest.py` enforces this mechanically, not just by
convention, via three session-scoped fixtures:
- `app_config` — the *only* `AppConfig` the whole session may construct,
  built from `postgres_test_config` (below) plus
  `quiz_images_dir=Path(__file__).parent.parent / "data" / "quiz-images"`.
- `api_client` — `TestClient(create_app(app_config))`, entered as a context
  manager so the app's lifespan runs exactly once for the session (not once
  per test).
- `_reset_pywire_container` (autouse) — calls
  `get_default_container().clear_instances()` at session teardown, dropping
  cached singletons (notably the pooled `PostgresClient` inside
  `PostgresClientProvider`) so they don't outlive the session and stall the
  ephemeral Postgres stack's teardown.

The mechanism, not just the intent: `create_app` (`api/app.py::_register_config`)
registers `config` on pywire's process-wide default container via
`container.register_instance(config, as_type=AppConfig)`, which raises
`pywire.exceptions.RegistrationError` if a *different* `AppConfig` instance
is already registered — re-registering the *same* object (identity check,
`is`) is tolerated, so a second `create_app(app_config)` call with the
session's own fixture is a no-op, but any test that tried to build a second,
independent `AppConfig` and pass it to `create_app` would fail loudly. This
is what makes "one `AppConfig` per session" a hard error instead of a
silent misconfiguration — see ADR 0023 and `.claude/rules/pywire-di.md`.
`tests/guidami_ai_patente/api/test_container_registration.py` covers all
three cases: same-instance resolution, tolerated re-registration of the
same object, and the `RegistrationError` on a genuinely different one.
`flowstep` is an external git dependency (not part of this repo's `src/`
or `tests/`), so it has no local test mirror here — see
`docs/second-brain/architecture.md`.

No `__init__.py` in any test directory — see
`.claude/rules/code-conventions.md` for the rule and rationale.

**`tests/conftest.py` is the root-level fixture registry for the suite**,
holding every fixture shared broadly enough to be worth global visibility. It
defines `RecordingProgressReporter`, a test double for the `ProgressReporter`
protocol that records every call `(method_name, args)` in order (with a
`count(method)` helper), and the `progress_recorder` fixture that hands out a
fresh instance per test.

**First exception (spec 0012 Task 9): `tests/guidami_ai_patente_ingestor/cli/
commands/conftest.py`**, scoped to that one directory's tests — the fixtures
only make sense for `reset knowledge`'s integration tests (seeding the
golden-set tables and asserting on the validated-labeling guard), so they'd be
dead weight on every other test module if hoisted to the root registry. It
defines `ingestor_test_config` (`IngestorConfig.load(postgres=
postgres_test_config)`), and two labeling-chain seed fixtures built on it —
`seeded_labeling` and `seeded_validated_labeling` — each inserting one
article → comma → quiz question → labeling run → `quiz_labelings` row (the
validated variant sets `validated_at`/`validated_by`, satisfying the
`quiz_labelings_validation_complete` CHECK), truncating the same
`_GOLDEN_SET_TABLES` tuple as `tests/labeling/repositories/
test_golden_set_schema.py`'s fixture before and after. A local, directory-
scoped `conftest.py` is the right call whenever a fixture's only sensible
callers already live under one `tests/<pkg>/.../` subtree — prefer the root
registry by default, but don't force a fixture upward past the tests that
actually need it.

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
- `app_config`/`api_client`/`_reset_pywire_container` — the session-scoped,
  one-`AppConfig` fixtures for `src/guidami_ai_patente/` (the FastAPI app),
  described above.
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

**Third-party exception-hierarchy canary** (`tests/commons/clients/
test_postgres_client_integration.py::test_pool_failures_are_catchable_as_
psycopg_errors`, spec 0012, D12): a plain (non-integration) unit test
asserting `issubclass(psycopg_pool.PoolTimeout, psycopg.Error)` and the same
for `PoolClosed` — not behaviour of this project's own code, but a pin on an
upstream library invariant `status.py`/`prepare.py` both rely on when they
catch broad `psycopg.Error` to report "database unreachable". If a future
`psycopg_pool` release ever stops `PoolTimeout` subclassing `psycopg.Error`,
this test fails immediately at that dependency bump instead of the
regression only surfacing as an uncaught traceback the next time a caller
hits an exhausted pool. Same file also has
`test_an_unreachable_database_fails_at_construction_not_at_first_query`
(integration-marked, D3): asserts `PostgresClient(dead_config)` itself
raises `psycopg.Error`, not a later `.fetch()` call.

**Import-boundary test via `ast`** (`tests/retrieval_evaluation/test_entry_points.py::
test_the_labeler_imports_no_private_ingestor_module`, spec 0011 phase 2): parses
every `.py` file under a package's source tree with `ast`, collects every
`ImportFrom`/`Import` module path, and asserts none crosses a declared boundary
(here: no path both starts with `guidami_ai_patente_ingestor` and contains a
dotted segment beginning with `_`) — a structural convention (FR-12) enforced as a
regular unit test, no real imports executed, no fixture needed. Reusable pattern
for any future "package X must not reach into package Y's private internals" rule.
Reused by `tests/labeling/test_module_boundary.py` (spec 0012, quiz-flow-api-phase1
plan Task 5): same `_imported_modules(source_text) -> list[str]` helper, four
assertions guarding `src/labeling/`'s dependency edges both ways — it imports
nothing from `retrieval_evaluation` (AD-12), nothing from `pywire` (ADR 0015),
nothing from `guidami_ai_patente` (the FastAPI app) — plus one guarding the
opposite direction, that `src/domain/` imports nothing from `labeling` (D13),
since `labeling/` legitimately imports `domain/` and nothing else prevents the
edge from silently inverting.

*Last updated: 2026-08-06 — verified against commit `91028b2`; documented the
isolated ephemeral Postgres test stack (`docker/docker-compose.test.yml`) and
the `_postgres_test_stack`/`postgres_test_config` fixtures that replaced
per-file hardcoded dev-database connections in integration tests.*

*Last updated: 2026-08-17 — verified against commit `b3ca8b30` (working tree ahead of it,
uncommitted, on `feat/backend`); added `tests/guidami_ai_patente/api/routers/test_health.py`,
the first test for `src/guidami_ai_patente/` and the project's first use of FastAPI's
`TestClient`, covering the `pywire.fastapi.wire()`-based DI added to `GET /health`
(see `docs/architecture.md` and `adr/0016-pywire-native-fastapi-wiring.md`).*

*Last updated: 2026-08-21 — verified against commit `e4977a94` (working tree ahead:
spec 0011 phase 2, T-11); documented the `ast`-based import-boundary test convention,
introduced for `retrieval_evaluation`'s "no private-module import from the ingestor" rule.*

*Last updated: 2026-08-25 — verified against commit `7005ad3f` (working tree ahead: spec
0012, quiz-flow-api-phase1 plan Task 5). Noted `tests/labeling/test_module_boundary.py`'s
reuse of the `ast`-based import-boundary convention: four assertions guarding
`labeling/`'s edges (no `retrieval_evaluation`, no `pywire`, no `guidami_ai_patente`) plus
one guarding `domain/` never importing back from `labeling/`.*

*Last updated: 2026-08-25 — verified against commit `b6e34f4d` (working tree ahead:
spec 0012 Task 9, FR-17/AD-28); `tests/guidami_ai_patente_ingestor/cli/commands/
conftest.py` is the suite's first non-root `conftest.py` — corrected the prior
"there is no other `conftest.py`" claim and documented why a directory-scoped one
was the right call here (fixtures only meaningful to `reset knowledge`'s tests).*

*Last updated: 2026-08-25 — verified against commit `c77de38a` (quiz-flow-api-phase1
plan Task 11); documented the third-party exception-hierarchy canary test in
`test_postgres_client_integration.py` (D12) alongside the existing fail-fast-at-
construction test (D3).*

**`object.__new__` container bypass for a pure-unit `@service`/`@repository`/`@client`
test** (`tests/guidami_ai_patente/services/test_explanation_status_service.py`, spec
0012, quiz-flow-api-phase2 plan Task 8): `service = object.__new__(ExplanationStatusService)`
constructs the instance without running pywire's instrumented `__init__` (which would
resolve the real, container-managed singletons — Postgres, the labeling stack), then the
test assigns lightweight `@dataclass` doubles directly onto the `Autowired` field names
(`service.golden_set = _GoldenSetDouble(...)`, etc., each `# type: ignore[assignment]`
since pyright sees the real `Autowired[T]` annotation). Works whenever the class under
test declares its collaborators as bare `Autowired[T]` fields with **no constructor body
of its own** — true for `ExplanationStatusService`/`HealthCheckService`
(`services/`) and `QuizQuestionRepository`/`GoldenSetReadRepository` (`repositories/`),
but **not** for a class like `LabelingStackProvider`/`PostgresClientProvider`
(`clients/`) or `AgentConfigRepository` (`repositories/`), whose `__init__` does real
work (loading a YAML file, building a pooled client) that pywire's DI is what triggers —
bypassing it with `object.__new__` there would skip that work entirely, not just the
container resolution. For a zero-body class, the class's "construction" *is* setting
those fields, so `object.__new__` plus manual assignment reproduces it exactly, with no
Docker/Postgres and no pywire container involved at all. Reach for the heavier
`api_client`/`app_config`
fixtures (above) instead when the test needs the real DI graph or a live HTTP round trip;
reach for this bypass when it only needs one class's own logic isolated from its
collaborators.

*Last updated: 2026-08-26 — verified against commit `f9d436de` (working tree ahead:
quiz-flow-api-phase2 plan Task 8); documented the `object.__new__` container-bypass
pattern for pure-unit tests of `Autowired`-only pywire classes, introduced by
`ExplanationStatusService`'s test.*

*Last updated: 2026-08-26 — verified against commit `ff0b188e` (working tree ahead:
quiz-flow-api-phase2 plan Task 2); documented the session-scoped `app_config`/
`api_client`/`_reset_pywire_container` fixtures that make "one `AppConfig` per
pytest session" a hard error via `create_app`'s `register_instance` call (ADR 0023),
replacing the prior per-test `create_app(AppConfig(...))` pattern in
`test_health.py`; noted the new `test_container_registration.py` coverage.*

*Last updated: 2026-09-02 — verified against commit `8d8443e5` (working tree ahead:
uncommitted, on `feat/quiz-flow-api-phase1`). `pywire` 0.7.0 -> 0.8.0 removed
`pywire.fastapi.wire()`, leaving `pywire_lifespan` as the only way to bind a container
to a FastAPI app (ADR 0028) — which makes a **testing constraint** out of what used to be
a style choice: `TestClient(app)` binds `app.state.pywire_container` **only** when used
as a context manager, because that is what runs the lifespan. Without the `with`, every
`Autowired[T]` route parameter resolves against the module-level default container
instead, silently — no error, possibly a different instance than the test set up. Any
test exercising an endpoint must therefore go through `tests/conftest.py::api_client`
(`with TestClient(create_app(...)) as client`, session-scoped) rather than constructing
its own `TestClient`. `wire()` had no such hazard: it bound eagerly at call time. The
`object.__new__` container-bypass pattern for pure-unit tests of `Autowired`-only classes
(2026-08-26 entry above) is unaffected — it never touches the app or its lifespan.*

*Last updated: 2026-09-18 — verified against commit `68575993` (spec 0016, bot user
authorization & answer history). Documented the FK-truncate fixture-list convention
(every existing fixture truncating a table `quiz_answers` now FK-references had to add
it to its tuple) and the new function-scoped `registered_headers` fixture
(`tests/conftest.py`) that truncates/seeds a `registered = true` `users` row (bracketed
truncate before and after, same pattern every other integration fixture in that file
uses) and yields the `X-Telegram-User-Id` header gated-endpoint tests attach to their
`api_client` calls.*

**FK-truncate fixture lists must grow with the schema.** Every integration-test fixture
that truncates a set of tables between tests (e.g. `bank`/`cached_question`/
`live_question`/`bank_with_image` in `tests/guidami_ai_patente/api/routers/
test_quiz_questions.py` and its siblings in `test_quiz_images.py`/
`test_quiz_explanation.py`) names its tables as an explicit tuple passed to
`PostgresClient.truncate(*table_names)` — required, not just convenient, since Postgres
refuses to `TRUNCATE` a table another live table's FK references unless the referencing
table is named in the same statement (`database.md`'s `PostgresClient.truncate()`
paragraph). When `quiz_answers` gained an FK into `quiz_questions` (spec 0016), every
one of these fixtures had to add `"quiz_answers"` to its tuple — otherwise the fixture's
own teardown/setup `TRUNCATE` fails with `psycopg.errors.FeatureNotSupported`,
independent of and unrelated to whatever the test itself is checking. Adding a new table
with a live FK into an already-truncated table is therefore not purely additive: search
`tests/` for that referenced table's existing truncate-fixture tuples and widen them in
the same change, or every integration test touching that fixture breaks for a reason
that has nothing to do with the change being made.

`tests/conftest.py` gained a `registered_headers` fixture (spec 0016) — the
`{"X-Telegram-User-Id": ...}` header dict every gated-endpoint integration test now
attaches to its `api_client` calls, after seeding the corresponding `users` row with
`registered = true`. An unregistered/absent header is what the auth-gate tests
(`tests/guidami_ai_patente/api/dependencies/test_user_identity.py`,
`tests/guidami_ai_patente/api/test_exception_handlers.py`) exercise instead.

**Closed gap (2026-09-21): every truncate list now names `quiz_answers`.** The paragraph
above lists the fixtures widened for spec 0016 at the time, but twelve more test files
(under `tests/commons/repositories/db/`, `tests/guidami_ai_patente/`,
`tests/guidami_ai_patente_ingestor/` — including `cli/commands/conftest.py`, which
`test_reset.py` seeds through — and `tests/labeling/repositories/`) still truncated
`quiz_questions` without it, so a full `uv run pytest -m "integration or not integration"`
ended with 1 failure and 70 errors (`FeatureNotSupported … Truncate "quiz_answers"`) on this
branch, independent of the change under test. All twelve now name `quiz_answers`, and the
full run is green (1198 passed, 2 skipped). All of them reach Postgres only through
`postgres_test_config` — directly, via `api_client`/`app_config`, or via
`ingestor_test_config` — i.e. the ephemeral stack on port 5433, never the dev database.
When a new FK lands, grep `tests/` for every `truncate(` list that names the referenced
table, not just the fixtures of the tests you are editing.

*Last updated: 2026-09-21 — verified against commit `61c290f1`. Recorded the gap above; the
summary work itself added integration tests to
`tests/guidami_ai_patente/repositories/test_quiz_answer_repository.py` and
`tests/guidami_ai_patente/api/routers/test_quiz_answers.py` whose fixtures do truncate
`quiz_answers`, and plain unit tests for the bot's `messages.summary_message`.*

*Last updated: 2026-09-21 — verified against commit `d9c44f28`. Replaced the "known gap"
note with its resolution: twelve test files widened their `truncate` lists with
`quiz_answers`; full run 1198 passed, 2 skipped, dev database row counts unchanged before
and after the run.*

**A fetched `vector` column round-trips as `numpy.ndarray`, not a plain `list`.**
`commons/clients/postgres_client.py` registers `pgvector.psycopg.register_vector` on every
connection, so `PostgresClient.fetch(...)` on a query selecting a `vector` column returns
rows containing a `numpy.ndarray`. Comparing two such rows directly with Python's tuple/list
`==` (e.g. `assert before == after` in an integration test asserting an UPDATE didn't touch
an unrelated vector column) raises `ValueError: The truth value of an array with more than
one element is ambiguous` — numpy's own `==` elementwise-overrides comparison, and the outer
tuple/list equality can't reduce that back to one bool. Normalize the vector field to a
plain `list()` before comparing (`[(term, definition, list(embedding)) for term, definition,
embedding in rows]`); see `tests/glossary/repositories/test_glossary_term_update_repository.py`
(`_normalized_rows`, spec 0019).

**A `--dry-run` subprocess test can't isolate itself with `monkeypatch.chdir(tmp_path)`
when the entry point's config needs a real `configs/*.yaml`/`.env` from cwd.** A CLI whose
root config (e.g. `GlossaryConfig`) is constructed unconditionally before the `--dry-run`
branch — because even the dry-run print needs config values — will fail that construction
first if the subprocess's cwd is an isolated, empty `tmp_path` with no `configs/*.yaml`/
`.env` to source required fields from (a `ValidationError`, not the intended dry-run exit).
Verify the "no filesystem write" guarantee a different way instead: run the subprocess from
the real project root, and snapshot the real `logs/` directory's run-prefixed subdirectories
(`RunArtifactWriter.build_run_dir`'s naming convention, e.g. `build_glossary_*`) before and
after, asserting no new one appeared — the log directory is only ever created past the
dry-run's early return, so the guarantee is verified without touching the config's own I/O
requirements. See `tests/glossary/test_main.py`/`tests/glossary/test_translate_main.py`
(spec 0019). Passing `tmp_path` as a fixture parameter but never wiring it into
`subprocess.run(..., cwd=...)` produces a *silently* vacuous assertion (it compiles, it
passes, it verifies nothing) rather than the loud `ValidationError` above — a sharper trap,
since nothing fails to flag the gap.

*Last updated: 2026-09-25 — verified against commit `3c418a5d` (spec 0019, `src/glossary/`
package). Documented two testing gotchas the `glossary/` package's pywire-wired,
Postgres/vector-backed, subprocess-tested shape surfaced for the first time in this repo:
the numpy `vector`-column comparison trap and the `--dry-run` subprocess cwd-isolation trap.
The existing `object.__new__` container-bypass pattern (2026-08-26 entry above) needed no
change — `glossary/`'s services follow it correctly (bare `Autowired` field names,
zero-constructor-body classes), confirmed against `pywire/container.py`'s actual
`_inject_fields` behavior (plain `setattr(instance, name, value)`, never underscore-prefixed).*

**A module-level `os.environ.get(...)` constant runs before any fixture, including a
session-scoped `autouse` one meant to protect it.** `tests/conftest.py`'s
`_open_router_environment` fixture pins `OPENROUTER_API_KEY` to a dummy value for the whole
session — but that pin applies at test *setup* time, which is always after pytest finishes
*collecting* every test module. A real-key gate written as a bare module-level assignment
(`_REAL_KEY = os.environ.get("OPENROUTER_API_KEY", "")`, evaluated once, at import time,
during collection) captures whatever the ambient environment held *before* the session
fixture ever ran — the fixture's later pin has no effect on an already-evaluated constant.
`tests/glossary/test_extraction_spike.py` shipped with exactly this shape and, under one
specific invocation (`rtk proxy uv run pytest -m integration`, this project's raw/unfiltered
CLI proxy mode — see `RTK.md`), the ambient environment genuinely did carry a real
`OPENROUTER_API_KEY` at collection time, which the session fixture's dummy value never
overrode: the "requires a real key" spike ran for real and made a billed call, despite the
suite's own protection existing specifically to prevent that. Root-caused rather than papered
over: the fix is not a stronger `skipif` string check (any check computed at collection time
has the identical hole) but reading the gate fresh, inside the test body, at call time, after
the session fixture has already run — and, for a genuinely destructive/billable real-API-call
test, requiring a *second*, independent opt-in env var (`GLOSSARY_SPIKE_LIVE=1`) on top of a
real key, so no single leaked variable alone can trigger it. Any future real-API-call
integration test in this repo should follow this shape, not the module-constant one.

*Last updated: 2026-09-25 — verified against commit (pending final review fix, same session).
Documented the module-level-env-capture-races-ahead-of-fixtures trap after it caused a real,
unintended, billed OpenRouter call during this plan's own finishing-branch verification —
fixed in `test_extraction_spike.py` with a call-time, two-condition gate.*
