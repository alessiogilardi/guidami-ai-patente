# ADR 0009: `RunArtifactWriter` generalized onto Pydantic manifests; run artifacts extended to `ingest`

## Status

Proposed

## Context

`scrapers/normattiva.py` already wrote `manifest.json`/`report.md` alongside
`run.log` on every run, via `RunArtifactWriter(RunArtifactWriterConfig)`
(`src/commons/observability/run_artifact_writer/`, ADR 0007's sibling
component). Spec 0004's FR-3 called this component "shared with `ingest`",
but its plan only ever wired the run-directory-naming and log-format pieces
into `ingest` (`cli/logging_setup.py:configure_logging`) — the
manifest/report *writing* stayed scraper-only. `RunArtifactWriter`'s shape
reflected that: it was built entirely around scraper-specific concepts
(`source`/`toc_url`/`output_path`, `found`/`saved`, three named skip
categories) that don't map onto `ingest`'s domain (commands, entities,
flows) at all — every `ingest prepare`/`index`/`reset` run left only
`run.log` behind, with no structured, machine-readable record of what
actually happened.

Separately, reviewing this gap surfaced a live, pre-existing bug:
`cli/main.py:_is_dry_run` had no branch for `status`, so it fell through to
`getattr(args, "dry_run", False)` = `False` — `ingest status` was
unconditionally treated as a real, writing run and created an unwanted
`logs/ingest_status_<timestamp>/run.log` on every invocation, `--online` or
not, even though it performs no other write.

Full requirements/acceptance-criteria detail:
`specs/0005-ingest-run-artifacts.md`.

## Decision

1. **Manifest content is modeled as Pydantic models, one concrete model per
   command, sharing a `RunManifest` base** —
   `src/commons/observability/run_artifact_writer/models/run_manifest.py`
   holds only what every manifest genuinely has (`started_at`/`ended_at`,
   an abstract `to_report_lines() -> list[str]`). `ScrapeManifest` (same
   package) carries the scraper's exact prior fields/behavior unchanged.
   `PrepareManifest`/`IndexManifest`/`ResetManifest` (CLI-local,
   `guidami_ai_patente_ingestor/cli/models/run_artifacts/`, per the CLI
   self-containment rule) carry only the fields meaningful to their
   command — `force` is absent from `IndexManifest`/`ResetManifest`
   (neither `index` nor `reset` define a `--force` flag), `flows` is
   absent from `ResetManifest` (runs no `Flow`). No manifest carries a
   field that is always empty for every run of that command.
2. **`RunArtifactWriter` itself shrinks to domain-agnostic mechanics**:
   `__init__(logs_root, run_id_prefix, manifest: RunManifest)` — the
   run-directory/`FileHandler` lifecycle it always owned, plus writing
   `manifest.json` (`manifest.model_dump_json(exclude_none=True)` — the
   `exclude_none=True` is what makes an absent-for-this-command field
   like `source` on a `quiz` run disappear from the JSON entirely, rather
   than serializing as `null`) and `report.md`
   (`"\n".join(manifest.to_report_lines())`) from whatever manifest it
   holds. `RunArtifactWriterConfig` is removed — its fields moved onto
   `ScrapeManifest` directly, one Pydantic model per instance is enough.
3. **`configure_logging` builds and returns a `RunArtifactWriter | None`**
   (`None` under the same `dry_run` gate as before — no filesystem write
   at all for a preview invocation); `cli/main.py:main()` enters it
   through its existing `contextlib.ExitStack` (the same mechanism
   already entering the live dashboard), so a mid-run crash still
   finalizes `manifest.json`/`report.md` via the `ExitStack`'s exception
   safety — no new plumbing for that guarantee.
4. **`_is_dry_run` gains an explicit `status` branch, returning `True`
   unconditionally** — `status` is always read-only (even `--online` only
   *reads* Postgres), so there is no case where it should ever create a
   run directory or `run.log`.

## Alternatives considered

- **A `ManifestReportBuilder` `Protocol` + per-phase builder service
  classes**, injected into `RunArtifactWriter`: rejected as duplicating
  what Pydantic already gives for free (`model_dump_json()`) and adding a
  behavioral port for what is fundamentally data.
- **One shared `IngestManifest` with optional `force`/`flows` fields**
  covering `prepare`+`index`+`reset`: rejected as exactly the
  always-partially-empty-field shape the project's entity conventions
  already warn against (mirrors `.claude/rules/code-conventions.md`'s
  "Entities — insertable projection of the table row").
- **A static `RunReportMapper`** (one `from_<phase>_manifest_to_report_lines`
  method per phase), matching the project's established `*Mapper`
  convention: rejected for this specific case in favor of each manifest
  implementing `to_report_lines()` directly — the transformation is
  inseparable from the one model it renders, with no cross-model reuse to
  justify a separate static class.
- **Adding a `--dry-run` flag to the `status` subparser**: rejected as a
  pointless opt-in for a command that is unconditionally read-only; the
  fixed branch in `_is_dry_run` expresses that invariant directly.

## Consequences

Positive: every real `ingest prepare`/`index`/`reset` run now leaves a
structured, machine-readable `manifest.json` plus a human-readable
`report.md` behind, matching the scraper's existing guarantee;
`ingest reset`'s irreversible `TRUNCATE` — previously recorded only by a
single `logger.info` line — now has a real audit-trail artifact;
`ingest status`'s incidental `run.log` write is fixed as a side effect of
the same change, with no separate flag needed. `RunArtifactWriter` is
smaller and fully domain-agnostic, reusable by any future run-producing
command without scraper-specific baggage.

Negative/accepted debt: `ScrapeManifest.to_report_lines()` reconstructs its
report title's run-label (`scrape_<source>_<timestamp>`) from its own
`source`/`started_at` fields rather than reading `RunArtifactWriter`'s
actual `run_dir.name`, since the shared `RunManifest` base intentionally
carries no `run_id`/`run_dir_name` field and `to_report_lines()` takes no
parameters. This reconstruction is byte-identical to the real directory
name except in the rare case of two runs starting in the same UTC minute,
where `build_run_dir`'s numeric collision suffix (`_2`, `_3`, ...) is
missing from the reconstructed title — a purely cosmetic gap in the report
title line only, not covered by any test today. `RunArtifactWriter.manifest`
is typed as the base `RunManifest`; callers that need the concrete
`PrepareManifest`/`IndexManifest` type (`cli/main.py`) use `typing.cast`
rather than a generic `RunArtifactWriter[M]`, to keep the writer itself
simple.
