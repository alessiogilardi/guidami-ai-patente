<!--
SPEC — the contract. Durable, git-tracked, never deleted (superseded instead).
The user signs scope; the compiling skill asserts feasibility with codebase evidence.
Downstream plans are extracted from this document and reference FR ids: every
requirement must be individually testable and traceable.
Status lifecycle: draft → ready → in-progress → implemented → superseded.
Every status beyond draft is written by the user alone — skills only propose:
draft → ready at sign-off; ready → in-progress when the first plan is extracted;
in-progress → implemented once the Definition of Done is verified.
-->

# Spec 0005: Extend RunArtifactWriter (manifest.json/report.md) to the `ingest` CLI

| | |
|---|---|
| **Id** | 0005 |
| **Status** | in-progress |
| **Date** | 2026-08-05 |
| **Discussion log** | `specs/discussions/ingest-run-artifacts.md` |
| **Supersedes / superseded by** | — |

## Problem & Motivation

Every `ingest` CLI run (`prepare`, `index`, `reset`) currently leaves only a
`run.log` file behind under `logs/<prefix>_<timestamp>/`. There is no structured,
machine-readable record of what a run actually did — which command and entity,
with which flags, which flows executed, when it started and ended — and no
human-readable summary. This is a real, observed gap: a real
`logs/ingest_index_202608041408/` run directory contains only `run.log`.

The scraper (`scrapers/normattiva.py`) does not have this gap: it already writes
`manifest.json` and `report.md` alongside `run.log`, via `RunArtifactWriter`
(`src/commons/observability/run_artifact_writer/`). Spec 0004's FR-3 explicitly
titled this component "shared with `ingest`," but its accompanying plan only ever
wired the run-directory-naming and log-format pieces into `ingest`
(`cli/logging_setup.py:configure_logging`) — the manifest/report *writing* stayed
scraper-only. `RunArtifactWriter`'s current public shape reflects that: it is
built around scraper-specific concepts (`source`/`toc_url`/`output_path`,
`found`/`saved`, three named skip categories) that do not map onto `ingest`'s
domain (commands, entities, flows) at all.

`reset` deserves this most acutely: it performs an irreversible `TRUNCATE`
(full table wipe) with only a single `logger.info` line as a record that it
happened.

While verifying this spec's assumption that `ingest status` performs no
filesystem write, inspection of `cli/main.py:26-31` (`_is_dry_run`) turned up a
pre-existing bug: `status` defines no `--dry-run` flag (`cli/parser.py:163-170`),
so `_is_dry_run` falls through to `getattr(args, "dry_run", False)` = `False`
and treats `status` as a real, writing run. `configure_logging`
(`cli/logging_setup.py:60-63`) then unconditionally creates
`logs/ingest_status_<timestamp>/run.log` for every `status` invocation,
`--online` or not — `status` is not actually the no-write command its own
CLI help/docs imply. This spec fixes that gap (FR-2, AD-8) alongside adding
the manifest/report artifacts, so both halves of "what does `status` write to
`logs/`" (today: an unwanted `run.log`; after: nothing) are addressed together.

This spec extends structured run artifacts to `ingest prepare`/`index`/`reset`,
while preserving the scraper's existing `manifest.json`/`report.md` content and
behavior unchanged.

## Functional Requirements

### FR-1: `ingest prepare`, `index`, and `reset` write `manifest.json` and `report.md`

Every real (non-preview) invocation of `ingest prepare`, `ingest index`, or
`ingest reset` writes a `manifest.json` and a `report.md` into its run directory,
alongside the existing `run.log`, finalized even when the run raises an
unhandled exception.

**Acceptance criteria:**
- Given a real `ingest prepare`/`index`/`reset` invocation, when it completes
  successfully, then its run directory (`logs/ingest_<command>_<timestamp>/`)
  contains `run.log`, `manifest.json`, and `report.md`.
- Given a real `ingest prepare`/`index`/`reset` invocation, when a flow (or, for
  `reset`, the truncation) raises an unhandled exception, then `manifest.json`
  and `report.md` are still written before the exception propagates to the
  caller — it is never suppressed.
- Given `ingest status`, when it runs (with or without `--online`), then no
  run directory, `run.log`, `manifest.json`, or `report.md` is created. This
  is a **behavior change, not a no-op**: today `status` unconditionally
  creates `logs/ingest_status_<timestamp>/run.log` (see FR-2's bug-fix
  bullet and AD-8) even though it never wrote a `manifest.json`/`report.md`.

### FR-2: Preview/dry-run invocations, and `status`, write nothing to `logs/`

Matching the scraper's existing `--dry-run` guarantee, no run directory or
artifact file is created for a preview invocation of any `ingest` command, nor
for `ingest status`.

**Acceptance criteria:**
- Given `ingest prepare --dry-run` or `ingest index --dry-run`, when it runs,
  then no run directory, `run.log`, `manifest.json`, or `report.md` is created.
- Given `ingest reset` invoked *without* `--apply` (its preview-by-default,
  inverted gate), when it runs, then no run directory or artifact file is
  created — same guarantee, expressed through `cli/main.py:_is_dry_run(args)`'s
  existing unification of both gate shapes.
- Given `ingest status` (with or without `--online`), when it runs, then no
  run directory or `run.log` is created — fixing the pre-existing bug (see
  Problem & Motivation) where `_is_dry_run` returned `False` for `status`
  because it defines no `--dry-run` flag, causing an unconditional `run.log`
  write. `_is_dry_run` gains an explicit `status` branch (AD-8) so this
  guarantee holds without adding a `--dry-run` flag to `status` (which is
  always read-only and never needs the opt-in).

### FR-3: Each command's manifest contains only the fields meaningful to it

Manifest content is modeled as one concrete Pydantic model per command
(`PrepareManifest`, `IndexManifest`, `ResetManifest`), plus the scraper's
existing manifest re-expressed as `ScrapeManifest` — no model carries a field
that is always empty/`None` for every run of that command.

**Acceptance criteria:**
- Given an `ingest prepare knowledge --source <cds|cap>` run, when
  `manifest.json` is read, then it contains `entity="knowledge"`,
  `source` (the `cds`/`cap` value), `force` (the `--force` flag's value), and
  `flows=["knowledge_cleaning"]`.
- Given an `ingest prepare quiz` run, when `manifest.json` is read, then it
  contains `entity="quiz"`, no `source` field, `force`, and
  `flows=["quiz_cleaning", "quiz_enrichment"]` (both flows, in the order they
  ran).
- Given an `ingest index knowledge --source <cds|cap>` run, when
  `manifest.json` is read, then it contains `entity="knowledge"`, `source`,
  and `flows=["knowledge_indexing"]` — no `force` field (`index` defines no
  `--force` flag).
- Given an `ingest index quiz` run, when `manifest.json` is read, then it
  contains `entity="quiz"`, no `source` field, and `flows=["quiz_indexing"]`.
- Given an `ingest reset knowledge --apply` or `ingest reset quiz --apply` run,
  when `manifest.json` is read, then it contains `entity` (`"knowledge"` or
  `"quiz"`) only — no `force` field and no `flows` field (`reset` defines no
  `--force` flag and runs no `Flow`).
- Given any of the four manifests, when `manifest.json` is read, then it never
  contains a `dry_run`/`apply`-shaped field, an `outcome` field, or a
  `warnings` field (explicitly out of scope — see Non-Goals).

### FR-4: Flow names are recorded as they start

For `prepare` and `index` (the two commands that run a `Flow`), the manifest's
`flows` list is appended to at the same point `ProgressReporter.begin_flow(name)`
is already called for that flow.

**Acceptance criteria:**
- Given `ingest prepare quiz`, when `quiz_cleaning` begins and later
  `quiz_enrichment` begins, then the manifest's `flows` list reads
  `["quiz_cleaning", "quiz_enrichment"]` immediately after both have started,
  in that order.
- Given `ingest index knowledge --source cds`, when `knowledge_indexing`
  begins, then the manifest's `flows` list reads `["knowledge_indexing"]`.

### FR-5: `report.md` is produced by the manifest's own `to_report_lines()` method

Each concrete manifest model (`ScrapeManifest`, `PrepareManifest`,
`IndexManifest`, `ResetManifest`) implements `to_report_lines() -> list[str]`,
returning the markdown lines `RunArtifactWriter` writes verbatim (newline-joined)
to `report.md`.

**Acceptance criteria:**
- Given any manifest instance, when `RunArtifactWriter.__exit__` runs, then
  `report.md`'s content equals `"\n".join(manifest.to_report_lines())`.
- Given a manifest type whose `to_report_lines()` is not overridden (the shared
  `RunManifest` base), when it is called directly, then it raises
  `NotImplementedError` — every concrete manifest must supply its own
  rendering.

### FR-6: The scraper's existing manifest/report content and behavior are unchanged

Moving the scraper's manifest/report logic onto `ScrapeManifest` (a
`RunManifest` subclass) must not change what `manifest.json`/`report.md`
contain or when they are written, for the scraper.

**Acceptance criteria:**
- Given the same scrape run (same law, same articles, same skips) as before
  this change, when `manifest.json` is read, then it contains the same keys and
  values as today: `source`, `toc_url`, `output_path`, `started_at`, `ended_at`,
  `found`, `saved`, `skipped` (per-category counts).
- Given the same scrape run, when `report.md` is read, then it contains the
  same three headed sections (Fetch failures / Session-invalid skips / Parse
  errors), each showing `"None"` when empty, unchanged from today.

## Non-Goals

- **Item-level counts** (e.g. articles/questions processed per flow) surfaced
  from `ProgressReporter`/flow steps back to the manifest — `ProgressReporter`
  has no method today that returns a final count to the caller, and plumbing
  one through is a materially larger refactor with no identified consumer yet
  (D-2's rationale).
- **An `outcome` (completed/failed) field** on any manifest — today's
  `RunArtifactWriter.__exit__` does not inspect `exc_type`/`exc`/`tb` at all;
  adding this would be new behavior reaching the scraper's manifest too (via
  the shared `RunManifest` base), decided out of scope (D-9).
- **A `warnings: list[str]` field / `record_warning` method** on any manifest —
  the only candidate producer today (`prepare`'s Postgres-unavailable degrade
  path, a single `logger.warning` call) is not enough of a pattern to justify a
  new accumulator on every manifest (D-9).
- **Any structured run artifact for `ingest status`** — `status` gets no
  `manifest.json`/`report.md`, out of scope for run artifacts entirely (D-1).
  This spec does fix `status`'s incidental `run.log` write (FR-2, AD-8) so the
  "performs no write of any kind" invariant becomes true — that is a bug fix
  bundled with this spec, not new scope on top of D-1's exclusion.
- **Any change to what the scraper's manifest/report contain** — `ScrapeManifest`
  is a like-for-like relocation of the existing logic, not a redesign (D-3, D-7d).

## Architectural Decisions

### AD-1: Manifest content is modeled as Pydantic models — one concrete model per command, plus the scraper's — not a `Protocol`+builder pair

- **Rationale:** the project already models every structured data shape as
  Pydantic (config, entities, DTOs). A per-command `BaseModel` subclass gets
  free JSON serialization (`model_dump_json()`, replacing today's hand-built
  `json.dumps(dict)`), and accumulation methods (`record_skip`, `record_flow`,
  ...) live directly on the concrete model they belong to. `RunArtifactWriter`
  itself shrinks to domain-agnostic mechanics (run directory, `FileHandler`
  lifecycle, write `manifest.json`/`report.md` from whatever model it holds) —
  arguably more faithful to spec 0004 AD-3's original "no `Protocol`/port...
  yet" than a `Protocol`+builder pair would be, since the only thing
  `RunArtifactWriter` needs from the model is `model_dump_json()` (free from
  `BaseModel`) and `to_report_lines()` (AD-2).
- **Rejected alternatives:** a `ManifestReportBuilder` `Protocol` +
  `ScrapeManifestReportBuilder`/`IngestManifestReportBuilder` service classes —
  rejected as duplicating what Pydantic already gives for free and adding a
  behavioral port for what is fundamentally data.

### AD-2: `to_report_lines()` is a method on each manifest model, not a static `RunReportMapper`

- **Rationale:** chosen over the project's established `*Mapper` convention
  (static, `from_X_to_Y`, non-DI) for this specific case, in favor of the
  simpler direct-method shape — the transformation is inseparable from the one
  model it renders, with no cross-model reuse to justify a separate static
  class.
- **Rejected alternatives:** a `RunReportMapper` static class with one
  `from_<phase>_manifest_to_report_lines` method per phase, injected into
  `RunArtifactWriter` as a callable.

### AD-3: Four distinct manifest models — `ScrapeManifest`, `PrepareManifest`, `IndexManifest`, `ResetManifest` — sharing a common `RunManifest` base

- **Rationale:** matches the project's "no field that's always/never
  populated" discipline (extended by analogy from the entities convention):
  `force` is meaningless for `index`/`reset` (neither defines a `--force`
  flag); `flows` is meaningless for `reset` (runs no `Flow`). A single shared
  `IngestManifest` would carry dead fields for at least one of its three
  consumers at any given time. The shared `RunManifest(BaseModel)` base holds
  only what every manifest genuinely has: `started_at`/`ended_at` and the
  abstract `to_report_lines()` (AD-2).
- **Rejected alternatives:** one shared `IngestManifest` with optional
  `force`/`flows` fields covering `prepare`+`index`+`reset` — rejected as
  exactly the always-partially-empty shape the codebase's conventions already
  warn against.

### AD-4: `configure_logging` builds and returns a full `RunArtifactWriter`; `main()` enters it via the existing `ExitStack`

- **Rationale:** the scraper already attaches `run.log`'s `FileHandler` via
  `RunArtifactWriter.__enter__`; unifying `ingest` onto the same ownership
  model means one object owns the run directory, the log file, and the
  manifest/report together — no risk of two components disagreeing about
  which run directory a file belongs to. `cli/main.py:main()` already has a
  `contextlib.ExitStack` conditionally entering the live dashboard before
  command dispatch — the writer is entered the same way, so `__exit__`'s
  manifest/report finalization on a crash (FR-1) comes from the `ExitStack`'s
  existing exception-safety, not new plumbing.
- **Rejected alternatives:** two independent objects — today's plain
  `FileHandler` in `configure_logging` plus a second, separate
  `RunArtifactWriter` just for manifest/report — rejected: both would need to
  independently agree on the same run directory, a duplicated-awareness risk
  with no benefit over a single owner.

### AD-5: `RunArtifactWriterConfig` is removed; `RunArtifactWriter.__init__` takes `logs_root`/`run_id_prefix`/`manifest` directly

- **Rationale:** `source`/`toc_url`/`output_path` move onto `ScrapeManifest`
  itself (AD-3); the config's only remaining unique field would have been
  `logs_root`, not worth a one-field wrapper class per the project's
  dependency-injection convention (plain data first, no collaborator to wrap).
- **Rejected alternatives:** keeping a slimmed-down `RunArtifactWriterConfig`
  with just `logs_root` — rejected as pointless indirection for a single field.

### AD-6: Model file placement follows the CLI-self-containment rule

- **Rationale:** `RunManifest` and `ScrapeManifest` live in
  `commons/observability/run_artifact_writer/models/` — the scraper is not
  part of the `ingest` CLI, and the base type is genuinely shared
  infrastructure. `PrepareManifest`, `IndexManifest`, and `ResetManifest` live
  in `guidami_ai_patente_ingestor/cli/models/`, since they exist only to serve
  the `ingest` CLI (`.claude/rules/cli-structure.md`'s self-containment rule).
- **Rejected alternatives:** all four (plus the base) in
  `commons/observability/run_artifact_writer/models/` — rejected, would place
  CLI-only concerns in shared infrastructure against the project's own
  documented convention.

### AD-7: `scrapers/normattiva.py`'s `_process_article` receives `manifest: ScrapeManifest`, not `writer: RunArtifactWriter`

- **Rationale:** `_process_article` never used `writer.log_file` — only
  `record_skip` — so it only ever needed the manifest, not the writer. `main()`
  keeps `writer` for `.log_file` logging and constructs/holds the
  `ScrapeManifest` separately, passing the manifest (not the writer) down to
  `_process_article`. This is a type-level, mechanical change with no behavior
  change (FR-6).
- **Rejected alternatives:** keeping `_process_article`'s parameter as
  `writer: RunArtifactWriter` and having it reach through a `.manifest`
  property — rejected as an unnecessary indirection once the manifest is the
  only thing the function actually uses.

### AD-8: `_is_dry_run` gains an explicit `status` branch, returning `True` unconditionally

- **Rationale:** fixes the pre-existing bug (Problem & Motivation, FR-2) where
  `status` fell through `_is_dry_run`'s `getattr(args, "dry_run", False)`
  default to `False`, causing `configure_logging` to treat every `status`
  invocation as a real, writing run and create an unwanted
  `logs/ingest_status_<timestamp>/run.log`. `status` is always read-only
  (`status.run_status` performs no `Flow`, no DB write, not even with
  `--online`, which only *reads* Postgres), so there is no case where it should
  ever be treated as anything but dry-run.
- **Rejected alternatives:** adding a `--dry-run` flag to the `status`
  subparser and requiring/defaulting it — rejected as a pointless opt-in for a
  command that is unconditionally read-only; a fixed branch in `_is_dry_run`
  expresses that invariant directly instead of asking every caller to pass a
  flag that can only ever have one meaningful value.

## Constraints

- **Zero content/behavior change to the scraper's existing `manifest.json`/
  `report.md`** — `ScrapeManifest` must reproduce the current `_write_manifest`/
  `_write_report` output exactly (FR-6); this is a relocation, not a redesign.
- **Manifest models are not frozen.** The project's Pydantic convention requires
  `model_config = ConfigDict(frozen=True)` for classes under `configs/`
  specifically — manifests are mutated throughout a run (`record_skip`,
  `record_flow`, `ended_at`) and are not configuration, so they are exempt from
  that rule and must remain mutable.
- **No new dependency.** Everything needed (Pydantic, `logging.FileHandler`,
  `contextlib.ExitStack`) is already in use in the touched files.

## Feasibility Evidence

- **AD-1** — supported by: `src/commons/observability/run_artifact_writer/run_artifact_writer.py:107` — today's `_write_manifest`/`_write_report` hand-build a `dict`/list of strings from private instance state (`self._source`, `self._skips`, ...), the exact logic AD-1 moves onto `ScrapeManifest` fields/methods (verified 2026-08-04 @ 3e632be)
- **AD-1** — supported by: `src/commons/observability/run_artifact_writer/run_artifact_writer.py:100` — `__exit__` calls `_write_manifest()`/`_write_report()` unconditionally, the finalization behavior `RunArtifactWriter` must keep after the refactor (verified 2026-08-04 @ 3e632be)
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/mappers/article_mapper.py:11` — the project's existing static `*Mapper` convention (`class ArticleMapper` with `from_parsed_to_cleaned`/`from_cleaned_to_article_entity`/... methods), the rejected alternative AD-2 deliberately does not replicate for this case (verified 2026-08-04 @ 3e632be)
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/cli/parser.py:111` — `prepare knowledge` requires `--source` and defines `--force` (verified 2026-08-04 @ 3e632be)
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/cli/parser.py:127` — `prepare quiz` defines `--force` but no `--source` (verified 2026-08-04 @ 3e632be)
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/cli/parser.py:141` — neither `index knowledge` nor `index quiz` (line 151) defines a `--force` flag (verified 2026-08-04 @ 3e632be)
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/cli/parser.py:156` — `reset`'s subparsers (`knowledge` at line 158, `quiz` at line 160) define `--apply` only, no `--force` (verified 2026-08-04 @ 3e632be)
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/cli/commands/reset.py:35` — `run_reset` runs no `Flow`, just a `TRUNCATE` per entity (verified 2026-08-04 @ 3e632be)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/cli/main.py:92` — the `contextlib.ExitStack` conditionally entering the dashboard before command dispatch, the same mechanism the writer is entered through (verified 2026-08-04 @ 3e632be)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/cli/logging_setup.py:63` — `handlers.append(logging.FileHandler(log_file))`, `configure_logging`'s plain `FileHandler` construction independent of `RunArtifactWriter`, the code path AD-4 unifies (verified 2026-08-04 @ 3e632be)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/cli/main.py:26` — `_is_dry_run(args)`, the existing single gate (`not args.apply` for `reset`, `getattr(args, "dry_run", False)` otherwise) that already unifies "is this a real, writing run" across all three commands, reused to decide whether `configure_logging` constructs a writer at all (verified 2026-08-04 @ 3e632be)
- **AD-5** — supported by: `src/commons/observability/run_artifact_writer/run_artifact_writer_config.py:8` — `RunArtifactWriterConfig`'s current four fields (`logs_root`, `source`, `toc_url`, `output_path`), three of which move onto `ScrapeManifest` (verified 2026-08-04 @ 3e632be)
- **AD-6** — supported by: `.claude/rules/cli-structure.md:22` — the CLI self-containment rule ("a new service, model, or other component introduced for a CLI feature and used only by the CLI goes under `cli/services/`, `cli/models/`, etc.") (verified 2026-08-04 @ 3e632be)
- **AD-7** — supported by: `src/scrapers/normattiva.py:569` — `_process_article`'s `writer: RunArtifactWriter` parameter (verified 2026-08-04 @ 3e632be)
- **AD-7** — supported by: `src/scrapers/normattiva.py:584` — `writer.record_skip(...)`, the only method `_process_article` calls on it (verified 2026-08-04 @ 3e632be)
- **AD-7** — supported by: `src/scrapers/normattiva.py:643` — `logger.info("Logging to %s", writer.log_file)` in `main()`, the `.log_file` use that must stay on `writer`, not move to the manifest (verified 2026-08-04 @ 3e632be)
- **FR-4** — supported by: `src/guidami_ai_patente_ingestor/cli/commands/prepare.py:79` — `progress.begin_flow("knowledge_cleaning")`, one of the existing call sites where a matching `manifest.record_flow(name)` is added (verified 2026-08-04 @ 3e632be)
- **FR-4** — supported by: `src/guidami_ai_patente_ingestor/cli/commands/index.py:71` — `progress.begin_flow("knowledge_indexing")`, the equivalent call site in `run_index` (verified 2026-08-04 @ 3e632be)
- **FR-6** — supported by: `src/commons/observability/run_artifact_writer/run_artifact_writer.py:108` — the exact manifest keys (`source`, `toc_url`, `output_path`, `started_at`, `ended_at`, `found`, `saved`, `skipped`) `ScrapeManifest` must reproduce unchanged (verified 2026-08-04 @ 3e632be)
- **FR-6** — supported by: `src/commons/observability/run_artifact_writer/run_artifact_writer.py:122` — the report structure (three headed sections via `_REPORT_HEADINGS`, `"None"` when empty) `ScrapeManifest.to_report_lines()` must reproduce unchanged (verified 2026-08-04 @ 3e632be)
- **AD-8** — supported by: `src/guidami_ai_patente_ingestor/cli/main.py:26` — `_is_dry_run`'s current body: a `reset`-only branch (`not args.apply`), else `getattr(args, "dry_run", False)`, with no `status` case — the gap AD-8 closes (verified 2026-08-05 @ 3e632be)
- **AD-8** — supported by: `src/guidami_ai_patente_ingestor/cli/parser.py:163` — the `status` subparser (`status_p`), which defines only `--online`, no `--dry-run` (verified 2026-08-05 @ 3e632be)
- **AD-8** — supported by: `src/guidami_ai_patente_ingestor/cli/logging_setup.py:60` — `if not dry_run:` unconditionally builds the run dir and attaches a `FileHandler`, the code path that fires for `status` today because `_is_dry_run` returns `False` for it (verified 2026-08-05 @ 3e632be)
- **AD-8** — supported by: `src/guidami_ai_patente_ingestor/cli/commands/status.py:20` — `run_status`'s full body: `StatusInspector.evaluate_readiness()`, an optional `--online` Postgres read via `TableHealthChecker.check()`, then `render(...)` — no `Flow` execution and no write anywhere, confirming `status` is safely always-dry-run (verified 2026-08-05 @ 3e632be)

## Open Questions

- [ ] **non-blocking** — Exact `RunArtifactWriter`/`configure_logging`/`main()`
  signatures (how `configure_logging` learns `entity`/`force` to build the
  right manifest, how the manifest reaches `dispatch_prepare`/`run_index` for
  `record_flow`) are implementation-level detail, left for `/write-plan` to
  decide against this spec's acceptance criteria — owner: write-plan

## Sign-off

- **Scope approved by user:** Alessio Gilardi, 2026-08-04; AD-8/FR-2 `status`
  bug-fix addition approved 2026-08-05
- **Feasibility asserted:** by write-spec on 2026-08-04 (AD-1 through AD-7,
  FR-1 through FR-6); AD-8 evidence added and verified 2026-08-05, based on
  Feasibility Evidence above
