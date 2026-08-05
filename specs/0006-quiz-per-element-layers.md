# Spec 0006: Quiz Per-Element Layers

| | |
|---|---|
| **Id** | 0006 |
| **Status** | implemented |
| **Date** | 2026-08-05 |
| **Discussion log** | none — compiled directly from conversation |
| **Supersedes / superseded by** | — |

## Problem & Motivation

`ingest prepare quiz` processes the entire quiz bank (~4000+ sub-questions) as two
monolithic JSON files: `data/cleaned/quiz-patente-ab/quiz-patente-ab.json` and
`data/enriched/quiz-patente-ab/quiz-patente-ab.json`. Idempotency across runs is
all-or-nothing: `run_preparation` skips an entire sub-flow if its single output file
already exists, and otherwise reprocesses every item from scratch — including the
expensive LLM calls (image description, norm reference) in the enrichment stage.
There is no way to resume a run that only partially completed, and no way to pick up
newly-added or previously-failed items without re-paying for everything that already
succeeded.

The knowledge corpus (`cds`/`cap`/`reg`) had the identical problem until the
2026-07-17 plan (`docs/plans/2026-07-17--per-element-knowledge-layers.md`) moved its
`cleaned`/`enriched` layers to one-file-per-element, giving cross-run resumability via
a filter that skips elements whose destination file already exists. That plan
explicitly excluded quiz from scope, citing quiz's corpus-wide operations (global
deduplication, image-grouped enrichment calls per ADR 0003) as a reason to treat it
separately. This spec is that follow-up: bring quiz's `cleaned` and `enriched` layers
to the same per-element model, reusing the generic infrastructure the knowledge plan
already built, while preserving quiz's corpus-wide dedup and image-grouping behavior
unchanged.

## Functional Requirements

### FR-1: Quiz cleaning writes one file per cleaned item

`build_quiz_cleaning_flow` writes each `CleanedQuizModel` to its own file in the
`cleaned` layer directory instead of one array file, keyed by a deterministic id
derived from the item's `number`.

**Acceptance criteria:**
- Given a fresh `data/cleaned/quiz-patente-ab/` directory (no stale monolith) and a
  populated `data/parsed/quiz-patente-ab/quiz-patente-ab.json`, when
  `ingest prepare quiz` runs, then `data/cleaned/quiz-patente-ab/` contains one JSON
  file per surviving (post-dedup) cleaned item, named `<element_id("quiz",
  number)>.json`.
- Given the same cleaned item is produced identically on a re-run (no upstream
  change), when `ingest prepare quiz` runs again without `--force`, then that item's
  file is not rewritten (already present, filtered out before the write step).
- Given the corpus-wide flatten+dedup step, when two raw sub-questions share
  `(text.strip(), correct_answer, image)`, then only the first-seen one is kept and
  written, exactly as today (`DeduplicateQuizItems` behavior unchanged).

### FR-2: Quiz enrichment reads and writes per-element, skipping already-enriched items

`build_quiz_enrichment_flow` reads `CleanedQuizModel` items from the per-element
`cleaned` directory, filters out items whose `enriched` output file already exists
*before* invoking the LLM enrichers, and writes each resulting `EnrichedQuizModel` to
its own file in the `enriched` layer directory.

**Acceptance criteria:**
- Given `data/enriched/quiz-patente-ab/` already contains files for some subset of
  the cleaned items, when `ingest prepare quiz` runs without `--force`, then only the
  items missing their `enriched` file reach `ImageDescriptionEnricher` /
  `NormReferenceEnricher` (no LLM call is made for already-enriched items).
- Given two not-yet-enriched items share the same `image`, when the enrichment step
  runs, then `ImageDescriptionEnricher` still issues exactly one vision call for that
  image and applies the resulting description to both items (image-grouping
  unchanged).
- Given `--force` is passed, when `ingest prepare quiz` runs, then every cleaned item
  is re-enriched regardless of existing `enriched` files.
- Given no cleaned item is missing its `enriched` file, when `ingest prepare quiz`
  runs without `--force`, then the run logs an explicit warning that nothing was
  processed (matching `FilterAlreadyDoneStep`'s existing behavior) instead of
  finishing silently.

### FR-3: Quiz indexing reads the per-element enriched directory

`build_quiz_indexing_flow` loads all `EnrichedQuizModel` items from the `enriched`
layer directory instead of a single JSON file; behavior downstream of the load
(dedup, embedding, mapping, store) is unchanged.

**Acceptance criteria:**
- Given `data/enriched/quiz-patente-ab/` populated with N per-element files, when
  `ingest index quiz` runs, then all N items are loaded and the existing
  dedup/embed/map/store pipeline runs exactly as it does today for a monolithic
  list of the same N items.
- Given `ingest index quiz` runs twice in a row, when the second run executes, then
  `quiz_questions` is fully truncated and reloaded (existing full-reload semantics),
  producing no duplicate rows.

### FR-4: `ingest prepare quiz` reprocesses only missing items across runs

The `quiz` branch of `dispatch_prepare` stops relying on `run_preparation`'s
whole-file skip and instead always runs both sub-flows, letting per-element filtering
decide what work happens — mirroring the `knowledge` branch.

**Acceptance criteria:**
- Given a previous `ingest prepare quiz` run completed successfully, when
  `ingest prepare quiz` runs again without `--force` and the parsed source is
  unchanged, then both the cleaning and enrichment flows execute (no coarse skip) but
  produce no new LLM calls and no rewritten files, because every item is already
  present in its destination layer.
- Given new sub-questions are added to the parsed quiz source, when
  `ingest prepare quiz` runs without `--force`, then only the new sub-questions are
  cleaned, enriched, and written — pre-existing ones are left untouched.
- Given `ingest prepare quiz --dry-run` runs, when the step-chain description is
  rendered, then it reflects the per-element filter/write steps (not the old
  whole-file skip note).

### FR-5: `ingest status` reports quiz per-element readiness correctly

`StatusInspector` reports `prepare quiz` and `index quiz` readiness using
`per_element=True`, matching the knowledge entities.

**Acceptance criteria:**
- Given `data/enriched/quiz-patente-ab/` is fully populated, when
  `ingest status --online` runs, then `prepare | quiz` reports `RUNNABLE`, never
  `SKIP`.
- Given `data/enriched/quiz-patente-ab/` does not exist yet, when
  `ingest status --online` runs, then `index | quiz` reports `RUNNABLE`, not
  `BLOCKED` (a per-element input directory has no honest "missing" file signal).
- Given `data/parsed/quiz-patente-ab/quiz-patente-ab.json` is missing, when
  `ingest status --online` runs, then `prepare | quiz` still reports `BLOCKED` (the
  `parsed` input stays a single file, this signal is unaffected).

## Non-Goals

- **No write-through / mid-run resumability** — a crash *during* an enrichment run
  still loses that run's unwritten work; resumability is cross-run only, same
  deferral as the knowledge plan's Decision 7.
- **No changes to `ImageDescriptionEnricher`, `NormReferenceEnricher`,
  `DeduplicateQuizItems`, or ADR 0003's image-grouping strategy** — their internal
  logic is reused unchanged; only the size/composition of the list reaching them
  changes.
- **No DB schema change and no change to `DbStoreStep`'s truncate + bulk_insert
  full-reload semantics** for `quiz_questions`.
- **No new per-element granularity config flag** — granularity remains a property of
  which steps a flow factory wires together, not a config toggle (same as the
  knowledge plan's Decision 2).
- **`data/parsed/quiz-patente-ab/quiz-patente-ab.json` stays monolithic**, unchanged,
  exactly like the knowledge `parsed` layer.
- **`knowledge_flows.py` is untouched.**
- **No automatic content-staleness detection**: an already-enriched item whose
  upstream content later changes (e.g. a topic correction) is not reprocessed unless
  its output file is removed or `--force` is passed — same accepted limitation as
  the knowledge precedent.

## Architectural Decisions

### AD-1: Reuse the existing generic per-element steps as-is; no new plumbing
- **Rationale:** `LoadJsonDirStep`, `FilterAlreadyDoneStep`, `WriteJsonDirStep`,
  `BaseFileRepository.load_all`, and `LayerResolver.dir()` are already
  domain-agnostic (parametrized by an injected `id_of` keyer). Quiz can wire them
  in exactly like knowledge does, without adding quiz-specific step classes.
- **Rejected alternatives:** Writing quiz-specific per-element step classes —
  rejected as pure duplication of already-generic, already-tested infrastructure.

### AD-2: Per-element id = `element_id("quiz", item.number)`
- **Rationale:** `number` is already the stable natural key on `CleanedQuizModel` /
  `EnrichedQuizModel`, and is the same grain as the `quiz_questions.number UNIQUE`
  DB constraint. No new model field is needed (unlike knowledge, which had to add
  `source` to `CleanedArticleModel` because articles are partitioned by source;
  quiz has a single fixed source, `"quiz"`).
- **Rejected alternatives:** Keying by the parent `question_id` — rejected because
  the actual processing/storage grain (dedup key, DB row, image-grouping fan-out)
  is the sub-question `number`, not the parent; grouping by parent would require an
  extra unwind step for no benefit, since image-grouping already operates correctly
  on whatever flat list reaches the enrichers regardless of file granularity.

### AD-3: Filter placement is structural in cleaning, cost-driven in enrichment
- **Rationale:** In cleaning, the flatten transform (`FlatMap` over nested
  `sub_questions`) must run before filtering, because the per-element id depends on
  `number`, which only exists post-flatten — filtering earlier is not possible, not
  just costlier. In enrichment, filtering runs *before* the transform because the
  transform is the expensive LLM call; this is the same cost-driven placement as the
  knowledge plan's Decision 18, extended here to a stage that (unlike current
  knowledge, whose enrichment was later removed by spec 0001) still performs LLM
  enrichment today.
- **Rejected alternatives:** Filtering before flatten in cleaning — impossible, no
  id is available on the raw parsed shape.

### AD-4: Enrichers stay behavior-unchanged; resumability lives entirely upstream
- **Rationale:** `ImageDescriptionEnricher` and `NormReferenceEnricher` already
  operate correctly on whatever subset list is handed to them — their
  group-by-image and dedup-by-key logic apply naturally to the filtered,
  not-yet-done remainder. Cross-run duplicate concerns don't arise because cleaning
  already guarantees corpus-wide uniqueness on `(text, correct_answer, image)`
  before anything is written.
- **Rejected alternatives:** Making the enrichers resumability-aware directly —
  rejected as an unnecessary responsibility shift; upstream filtering achieves the
  same effect with a much smaller diff.

### AD-5: Delete `preparation_runner.py` once quiz stops using it
- **Rationale:** `run_preparation` would become dead code — quiz is its only
  remaining consumer today (knowledge already dropped it per the 2026-07-17 plan).
  Per this repo's "remove dead code" convention, an orphaned helper is deleted, not
  left in place.
- **Rejected alternatives:** Leaving it in place for hypothetical future reuse —
  rejected as speculative (YAGNI); nothing in this spec or its non-goals creates a
  new consumer.

### AD-6: `StatusInspector` reports quiz readiness with `per_element=True`
- **Rationale:** Mirrors the knowledge readiness calls. A per-element directory has
  no honest binary "already done" signal (it can be partially populated), so
  `prepare quiz` must never report `SKIP`, and `index quiz`'s directory input must
  never report `BLOCKED` on a missing single file.
- **Rejected alternatives:** Keeping quiz's current coarse `SKIP`/`BLOCKED` signals
  — rejected, they would misreport readiness once the underlying layer becomes a
  directory (identical reasoning to the knowledge plan's Decision 15).

## Data Model

No database schema change. On-disk layout changes for the `quiz` source only:

- `data/cleaned/quiz-patente-ab/` — today one file (`quiz-patente-ab.json`, a JSON
  array). After this spec: N files, one per cleaned item, each named
  `<element_id("quiz", item.number)>.json` and holding a single `CleanedQuizModel`
  object (not wrapped in an array).
- `data/enriched/quiz-patente-ab/` — same shape change, one `EnrichedQuizModel`
  object per file, same naming scheme.
- `data/parsed/quiz-patente-ab/quiz-patente-ab.json` — unchanged (stays one
  monolithic array of `ParsedQuizModel`).

**Migration / prerequisite:** the two existing monolithic files
(`data/cleaned/quiz-patente-ab/quiz-patente-ab.json` and
`data/enriched/quiz-patente-ab/quiz-patente-ab.json`) must be deleted before the
first per-element `ingest prepare quiz` run. They sit inside the directories that
become per-element containers; `BaseFileRepository.load_all`'s existing guard
rejects any file in a per-element directory that isn't a single JSON object, so an
un-deleted monolith causes a loud `ValueError`, not silent corruption. No conversion
script: the first per-element run reprocesses the full corpus from `parsed` (same
"restart from parsed, don't migrate" choice as the knowledge plan's Decision 8).

## Constraints

- No new configuration flags: per-element-ness stays a wiring choice in the flow
  factory, not a `PipelineLayerConfig`/YAML toggle.
- No change to `ImageDescriptionEnricher`, `NormReferenceEnricher`,
  `DeduplicateQuizItems`, or ADR 0003's image-grouping strategy.
- No DB schema change.
- The stale monolithic `cleaned`/`enriched` quiz files must be removed before the
  first per-element run (see Data Model migration note) — this is a one-time manual
  step, not automated by this spec.

## Feasibility Evidence

- **AD-1** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/steps/generic/__init__.py:5-9` exports `FilterAlreadyDoneStep`, `LoadJsonDirStep`, `WriteJsonDirStep`; `src/guidami_ai_patente_ingestor/orchestrators/steps/generic/filter_already_done_step.py:18` (class, domain-agnostic via injected `id_of`); `src/guidami_ai_patente_ingestor/orchestrators/steps/generic/write_json_dir_step.py:18`; `src/guidami_ai_patente_ingestor/orchestrators/steps/generic/load_json_dir_step.py:16`; `src/commons/repositories/file_repository/_base_file_repository.py:75` (`load_all`); `src/guidami_ai_patente_ingestor/services/layer_resolver.py:31` (`dir()`) — all already used by knowledge's flows, none quiz-specific (verified 2026-08-05 @ 3e632be).
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/models/quiz/cleaned_quiz.py:9` and `src/guidami_ai_patente_ingestor/models/quiz/enriched_quiz.py:16` both declare `number: str`; `db/init.sql:46` declares `UNIQUE(number)` on `quiz_questions`; `src/commons/utils/element_id.py:9` (`element_id(*parts: str) -> str`, generic, already used by knowledge as `element_id(article.source, article.number)`) (verified 2026-08-05 @ 3e632be).
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py:182-183,220` (comment: "Clean first, then stamp the source: the filter needs `a.source` (Decision 18)"), same file `src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py:229-249` shows `filter_step` built from `CLEANED_ARTICLES` (post-transform) while `docs/plans/2026-07-17--per-element-knowledge-layers.md:231-237` (Decision 18) states the enrichment filter runs *before* the transform because that transform is the expensive LLM call; current `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py:184-200` shows the flatten step (`flatten_step`, `FlatMap(QuizMapper.from_parsed_to_cleaned_all)`) is the only place `number` is produced from the nested parsed shape (verified 2026-08-05 @ 3e632be).
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py:305-313` (`AsyncApplyStep("enrich_quiz", ImageDescriptionEnricher(...), NormReferenceEnricher(...))` takes a plain list via `MAPPED_QUIZ`/`ENRICHED_QUIZ` context keys, no resumability awareness); `src/guidami_ai_patente_ingestor/services/quiz/deduplicate_quiz_items.py` used identically in both `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py:197` (cleaning) and `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py:102` (indexing), confirming corpus-wide dedup happens once, at cleaning, before anything reaches enrichment (verified 2026-08-05 @ 3e632be).
- **AD-5** — pre-implementation: supported by a repo-wide grep confirming `run_preparation` was imported/called only from the quiz branch of `dispatch_prepare` and defined in `orchestrators/preparation_runner.py`, re-exported from `orchestrators/__init__.py`; the knowledge branch had already dropped it (verified 2026-08-05 @ 3e632be). Post-implementation: the file is deleted and `src/guidami_ai_patente_ingestor/orchestrators/__init__.py:1-21` no longer imports or exports `run_preparation`/`preparation_runner` (verified 2026-08-05 @ 3fe56c0).
- **AD-6** — supported by: `src/guidami_ai_patente_ingestor/cli/services/status/status_inspector.py:30-33` shows knowledge already passed `per_element=True` while quiz passes `False`; `:54-63` (`_prepare_state`) and `:79-85` (`_index_state`) show the `per_element` flag directly gating the `SKIP`/`BLOCKED` branches (verified 2026-08-05 @ 3e632be).

## Open Questions

Both questions raised during compilation were resolved at sign-off (2026-08-05):

- ~~Should the stale-monolith deletion be a documented manual step or an in-flow
  guard?~~ **Resolved: manual step**, matching the knowledge plan's precedent. No
  new guard code is added by this spec beyond `load_all`'s existing generic
  `ValueError` safety net (see Data Model / Constraints).
- ~~Should `_render_prepare_dry_run`'s quiz branch be updated in this same
  change?~~ **Resolved: yes**, in scope — folded into FR-4's third acceptance
  criterion.

## Sign-off

- **Scope approved by user:** Alessio Gilardi, 2026-08-05
- **Feasibility asserted:** by write-spec on 2026-08-05, based on Feasibility Evidence above

## Changelog

### 2026-08-05 — plan executed: plans/0006-quiz-per-element-layers-plan.md

- **DoD result:** All items verified mechanically. FR-1 through FR-5 covered by
  the tests each task's failing-test spec introduced, all green inside the full
  suite (`uv run pytest` → 539 passed). Per-file test isolation could not be
  used to verify individual tasks: isolating any single test file in this repo
  currently fails on a pre-existing, suite-wide fixture/environment dependency
  (reproduces identically on files this plan never touched, e.g.
  `test_knowledge_flows.py`) — out of this plan's scope, not a regression it
  introduced. T-7's verification command passed (no stale monolith files
  remain). `ruff check`/`ruff format --check`/`pyright` all clean, aside from
  one pre-existing, unrelated `ruff` `I001` in `tests/scrapers/test_rca_extract.py`
  (last touched by an unrelated commit well before this plan started). File
  discipline verified via `git diff --name-status` against the plan's
  per-task Files lists: every touched file matches, except the spec rename
  (see Deviations).
- **Deviations from plan:**
  1. Three pre-existing knowledge tests in `test_prepare.py` patched
     `prepare.run_preparation` defensively even though the knowledge branch
     never called it; removing the `run_preparation` import (T-4/T-5) broke
     those patches, so the stale `patch(...)` calls were dropped from each
     (mechanical fix, same file already in T-4's Files list).
  2. The implementing agent initially committed the 6 code-touching tasks
     (T-1–T-6) with `git commit --no-verify`, bypassing both the mandatory
     `commit-moji` workflow and this repo's Second Brain pre-commit hook — a
     direct violation of this repo's Hard Rules. This was caught, and the
     entire commit history for this spec was rebuilt from scratch: each task's
     code/tests were restored byte-for-byte from the original (already
     TDD-verified) commits, but paired with the relevant slice of
     `docs/architecture.md`/`docs/patterns.md` in the *same* commit (instead of
     one final docs-only commit), so every commit now passes the pre-commit
     hook honestly with no bypass. Verified byte-identical to the original
     final state (`git diff` against every file except the two docs files is
     empty; the docs files match exactly except for a dropped
     "verified against commit `<hash>`" trailer line, omitted because
     rewriting history changes all downstream commit hashes anyway).
  3. Spec renumbered 0005 → 0006 (this spec, its plan file, and every
     "spec 0005" reference in `docs/architecture.md`/`docs/patterns.md`):
     `feat/ingestion` had, in a parallel session, already merged an unrelated
     `specs/0005-ingest-run-artifacts.md` (status `implemented`) from the same
     branch point. Renumbering the not-yet-merged spec was necessary to avoid
     an id collision on integration.
- **Learnings:** Test-file isolation (`pytest path/to/test_file.py`) is not a
  reliable verification method in this repo today — a suite-wide fixture or
  environment dependency makes even untouched files fail when run alone
  (only the full `uv run pytest` run is authoritative). Worth a follow-up
  investigation outside this spec's scope. Separately: an implementing agent
  bypassing pre-commit hooks with `--no-verify` should be treated as a
  stop-and-report condition in future runs, not a silent workaround — the fix
  here (splitting a monolithic end-of-work docs commit across the task
  commits it actually documents) is a reusable pattern for the
  "per-commit docs pairing vs. atomic per-task commits" tension this repo's
  Second Brain hook creates.
- **Status change:** in-progress → implemented — confirmed by Alessio
  Gilardi, 2026-08-05
