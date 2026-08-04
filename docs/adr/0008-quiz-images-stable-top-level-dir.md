# ADR 0008: Quiz images live in a stable top-level directory, not nested under parsed/

## Status

Accepted

## Context

Images extracted from the quiz PDF used to live under
`data/parsed/quiz-patente-ab/images/`, nested inside the pipeline-stage
tree (`raw/` → `parsed/` → `cleaned/` → `enriched/`, see
`docs/layout.md`). That tree models transformations applied to the
*structured quiz JSON*; image bytes, once extracted by
`parsers/questions_pdf.py`, never change through those stages — the
enrichment step (`ImageDescriptionEnricher`) only ever derives new
metadata (`image_description`/`image_analysis`) *from* an image, never
back into it. Nesting images under `parsed/` had two consequences:

1. It implied images belong to one disposable pipeline stage rather than
   being a stable, long-lived asset.
2. Any future consumer needing direct file access to quiz images — the
   planned FastAPI quiz-bot app (`src/guidami_ai_patente/`, not started
   yet), which will need to display the road-sign image for a question —
   would have had to reach into the ingestion pipeline's internal
   `parsed/` staging directory, coupling the app to a path it has no
   other reason to know about.

Separately, `_save_image` (in `parsers/questions_pdf.py`) deduplicates by
MD5 hash within a single parse run (the `seen` dict) but never removed
files across runs: whenever the source PDF changed such that a
previously-extracted image was no longer referenced by any question, its
file was silently left behind under `images/` forever — an unbounded,
invisible drift between the JSON's declared image references and what is
actually on disk.

## Decision

1. Move image storage to a new top-level directory, `data/quiz-images/`
   — a sibling of `raw/`/`parsed/`/`cleaned/`/`enriched/`, not nested
   under any of them. `IngestorConfig.quiz_images_dir`
   (`src/guidami_ai_patente_ingestor/configs/ingestor_config.py`) and
   `configs/ingestor_config*.yaml` point here. It is committed to git
   like `parsed/`/`cleaned/` (deterministic, not LLM-derived — unlike
   `data/enriched/`, which stays gitignored per ADR 0005).
2. `main_questions` (`src/parsers/questions_pdf.py`) now prunes orphaned
   images at the end of every parse run: `_referenced_images(questions)`
   collects every non-null `image` filename actually referenced in the
   freshly-parsed output, and `_prune_orphans(images_dir, referenced)`
   deletes anything else under `data/quiz-images/`. Both derive from the
   same in-memory `questions` list used to write the output JSON, so the
   two stay consistent regardless of write order or a mid-run crash.
3. `test_data_sampler/sampler.py`'s existing "copy only referenced
   images" behavior (ADR 0006) is unchanged in logic — only its source
   (`data/quiz-images/`) and destination (`data/test-data/quiz-images/`,
   now a sibling of `data/test-data/parsed/` rather than nested under it)
   moved to match.

## Alternatives considered

- **Keep images under `data/parsed/quiz-patente-ab/images/` and add a
  "promotion"/sync step** that copies referenced images into a separate
  stable folder as part of `ingest prepare quiz`: rejected as
  unnecessary complexity — there is exactly one producer (the parser)
  and images never get transformed at any pipeline stage, so a second
  copy plus a sync step would only add a place for the two copies to
  drift out of sync, with no compensating benefit.
- **A generic `data/assets/` top-level directory** (room for future
  non-quiz binary assets): rejected for now as premature genericity — no
  other source (cds/cap/reg) currently produces any binary asset, and
  renaming `quiz-images/` → `assets/quiz/` later is a one-line config
  change, not a structural one, if that need ever materializes.
- **Leave the orphan-accumulation behavior as-is and only add a CI test**
  asserting no orphans exist (detect drift without preventing it):
  rejected as insufficient on its own — a failing CI test still requires
  someone to notice, investigate, and manually delete the stale files;
  auto-pruning removes the manual step entirely. A referential-integrity
  unit test was still added alongside the prune, as a regression safety
  net (`tests/parsers/test_questions_pdf.py::test_prune_orphans_*`,
  `test_referenced_images_*`).

## Consequences

Positive: the future FastAPI app can read quiz images from a stable,
pipeline-agnostic path without any knowledge of the ingestion pipeline's
internal `parsed/` staging; the images folder never accumulates stale
files across re-parses; `_prune_orphans`/`_referenced_images` make both
dedup and cleanup behavior explicit and directly unit-tested (previously
untested and undocumented).

Negative/accepted debt: this is a one-time breaking path change —
anyone with a stale local checkout of
`data/parsed/quiz-patente-ab/images/` (or
`data/test-data/parsed/quiz-patente-ab/images/`) needs to re-pull or
re-run `sample-test-data`. `quiz_images_dir` remains a standalone config
field independent of `LayerResolver`'s layer/source model (unchanged
from before this ADR) — acceptable since only one source has images
today; a future second image-bearing source would need the same
standalone-field treatment rather than fitting the generic layer
resolver.
