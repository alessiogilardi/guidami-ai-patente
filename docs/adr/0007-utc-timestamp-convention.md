# ADR 0007: UTC Timestamp Convention Across App, Logs, and DB

## Status

Proposed

## Context

An audit of date/timestamp handling across the codebase found the DB schema
already consistent — every `TIMESTAMPTZ` column is written via `now()` or an
application-supplied `datetime.now(UTC)` — but found two concrete bugs one
layer up:

- `RunArtifactWriter.build_run_dir`
  (`src/commons/observability/run_artifact_writer/run_artifact_writer.py`)
  stamped the `logs/<prefix>_<timestamp>/` directory name with naive
  `datetime.now()` (host-local time, unlabeled), while every other timestamp
  written by the same run (`manifest.json`'s `started_at`/`ended_at`, any
  `TIMESTAMPTZ` column) uses `datetime.now(UTC)`.
- The shared `LOG_FORMAT` (`%(asctime)s %(levelname)s %(name)s: %(message)s`,
  same file, consumed by `cli/logging_setup.py` and `scrapers/normattiva.py`
  via `logging.basicConfig`) left `%(asctime)s` on the stdlib default, which
  is also host-local time via `time.localtime`.

Separately, `scraped_at` — computed correctly in UTC by the scraper
(`src/scrapers/normattiva.py`, `datetime.now(UTC).isoformat()`) and carried
as a plain ISO-8601 `str` through `ParsedArticleModel` and
`CleanedArticleModel` (`src/guidami_ai_patente_ingestor/models/knowledge/`)
— was silently dropped at the DB-entity mapping boundary: `ArticleEntity`
(`src/domain/entities/knowledge/article.py`) never declared the field, and
`articles` had no column for it, so scrape provenance was computed at zero
extra cost and then discarded before persistence.

Both bugs share a root cause: the project never wrote down an explicit
timestamp convention, so "current time" calls and the log formatter drifted
from the DB-layer discipline that was already correctly UTC.

## Decision

Adopt one explicit convention, covering the whole app/log/DB timestamp
surface:

1. Every DB timestamp column is `TIMESTAMPTZ`, written via `now()` (DB-side
   defaults) or an application-supplied `datetime.now(UTC)`.
2. Every application-level "current time" call is `datetime.now(UTC)`, never
   naive `datetime.now()`.
3. `logging.Formatter.converter` is globally forced to `time.gmtime`
   (`src/commons/observability/run_artifact_writer/run_artifact_writer.py`,
   immediately after the `LOG_FORMAT` constant), so every `%(asctime)s` in
   every `run.log` — across every `Formatter` created anywhere in the
   process, including `basicConfig`'s internal one — is UTC too, matching
   the JSON/DB timestamps written by the same run.
4. The raw scraper output (`ParsedArticleModel.scraped_at`) stays an
   ISO-8601 `str` — it mirrors the on-disk scraped JSON verbatim, and JSON
   has no native datetime type. Every model downstream of the
   parsed→cleaned boundary carries `scraped_at` as a real `datetime`
   instead, so the string→datetime parse happens exactly once, as early as
   possible, rather than being repeated (or forgotten) at every consumer.
   Concretely: `CleanedArticleModel.scraped_at`
   (`src/guidami_ai_patente_ingestor/models/knowledge/cleaned_article.py`)
   is typed `datetime` — pydantic v2 auto-parses the ISO-8601 string on
   `ArticleMapper.from_parsed_to_cleaned`'s
   `CleanedArticleModel(**article.model_dump(), source=source)` construction,
   no explicit parse call needed. `ArticleEntity` gained a matching
   `scraped_at: datetime` field (`src/domain/entities/knowledge/article.py`),
   `articles` gained a matching `scraped_at TIMESTAMPTZ NOT NULL` column with
   no default (`db/init.sql`), `ArticleMapper.from_cleaned_to_article_entity`
   (`src/guidami_ai_patente_ingestor/mappers/article_mapper.py`) just copies
   the already-`datetime` value through, and `ArticleStoreRepository`
   (`src/guidami_ai_patente_ingestor/repositories/db/article_store_repository.py`)
   writes it like any other column — `psycopg` adapts Python `datetime` to
   `TIMESTAMPTZ` natively, no explicit cast needed.

   The JSON-layer write path still needs to turn that `datetime` back into a
   JSON-safe string when persisting `CleanedArticleModel` to disk (the
   `cleaned/` layer). `BaseFileRepository._serialize_item`
   (`src/commons/repositories/file_repository/_base_file_repository.py`)
   uses `item.model_dump(mode="json")` rather than the bare `model_dump()`
   default (`mode="python"`, which would leave a real `datetime` object in
   the dict and crash `json.dumps` with `TypeError: Object of type datetime
   is not JSON serializable`) — `mode="json"` recursively converts every
   field to a JSON-safe type (`datetime` → ISO-8601 string) and is a no-op
   for the plain `str`/`int`/`bool`/`list`/`Literal` fields already flowing
   through every other model this shared repository serializes.
   `_deserialize_item`'s `model_validate(raw_item)` needs no matching
   change: pydantic already parses ISO strings back into `datetime` fields
   on validation.

## Alternatives considered

- **Keep log timestamps in unlabeled local time**: no code change needed.
  Rejected — it makes correlating `run.log` lines against `manifest.json`/DB
  timestamps from the same run impossible without knowing the host's
  timezone, which defeats the point of writing structured, cross-referenced
  run artifacts in the first place.
- **Leave `scraped_at` JSON-only and drop the dead field instead of
  persisting it**: smaller diff, no schema change. Rejected — the value is
  already computed at zero extra cost by the scraper; persisting it is
  cheaper than re-deriving scrape provenance later, and the entity-design
  rule in `.claude/rules/code-conventions.md` only exempts *DB-generated*
  columns (`id`, `created_at DEFAULT now()`) from being real entity fields.
  `scraped_at` is application-supplied, not DB-generated, so it belongs on
  `ArticleEntity` like any other writable column.

## Consequences

- `articles` gains a required `scraped_at TIMESTAMPTZ NOT NULL` column with
  no default. Existing local dev DBs need the already-documented
  tear-down/recreate cycle (`docker compose down -v && up -d`, see
  `CLAUDE.md` "Infrastructure" and `docs/database.md` "Migrations") — there
  is no migration tool in this project, `db/init.sql` only runs on first
  volume creation.
- Every `run.log` across the whole codebase (both `ingest` and `scrape`
  entry points, since both import `LOG_FORMAT` from the same module) now
  reports UTC instead of host-local time; a reader must know this convention
  when comparing log timestamps against a host clock.
- `logging.Formatter.converter = time.gmtime` is a **global, process-wide**
  mutation of a stdlib class attribute — it affects every `Formatter`
  instantiated anywhere in the process, not just `RunArtifactWriter`'s own.
  This is intentional (the stdlib-documented way to force UTC formatting)
  and low-risk since the project has no other component that wants
  local-time log output, but it is a side effect worth knowing about before
  importing `commons.observability` for unrelated reasons.
