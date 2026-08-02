# Spec 0004: Scraper acquisition-layer refactor (unified CLI, dataclasses)

| | |
|---|---|
| **Id** | 0004 |
| **Status** | draft |
| **Date** | 2026-08-02 |
| **Discussion log** | `specs/discussions/scraper-acquisition-refactor.md` (split from `specs/0003-regolamento-attuazione-corpus.md` §Phase 2 originally; FR-3 through FR-7 compiled from the discussion log's 2 sessions) |
| **Supersedes / superseded by** | — (split from spec 0003; see spec 0003's Changelog) |

## Problem & Motivation

The scraper hardcodes one module-level constant and one entry point per law —
`CDS`/`main_cds`, `CAP`/`main_cap`, and (since spec 0003 Phase 1) `REG`/`main_reg` —
registered as `scrape-codice`, `scrape-cap` and `scrape-regolamento`, so every new
source means a new constant, a new function and a new `[project.scripts]` line. Three
laws turned this from a coincidence into a shape. Its data structures (`LawConfig`,
`ArticleParams`, `ArticleRecord`) are `TypedDict`s, which are erased at runtime and
validate nothing: a misspelled or missing `LawConfig` field produces a silently wrong
article URL, not a construction error. Progress goes to `print`, and four separate
`continue` statements skip a duplicate TOC entry, an excluded annex, a failed fetch and
an invalid session — so a real scrape leaves no trace in the per-run log files every
`ingest` command writes, and a loop-skip has no visible signal that it happened.

Spec 0003 originally scoped this tidy-up as its own Phase 2 (FR-6/FR-7), deliberately
sequenced after its own Phase 1 parsing rewrite (0003 AD-5) to avoid restructuring a
module mid-rewrite. Phase 1 is now implemented, so spec 0003 has been closed with
FR-6/FR-7 struck through and split into this spec — 0003 AD-5's rationale still explains
why this work didn't happen inside 0003 itself.

Running the real 409-article scrape that Phase 1 enabled also surfaced concrete
data-quality and robustness gaps that weren't visible from the 8-article sample spec
0003 was originally written against — not architectural, but real problems an
implementer touching this file should be aware of. A follow-up discussion (see the
Discussion log above) investigated each one against the real data and HTML rather than
deciding blind, found that three of them collapse into one root cause (a `((...))`
amendment bracket that both title-extraction paths strip naively instead of
bracket-aware, FR-5), and closed all of them as in-scope for this spec: FR-5, FR-6 and
FR-7 below. The same discussion also added a new requirement not originally envisioned
by spec 0003's split — structured per-run artifacts (FR-3) — and settled the two
Non-Goals that were previously left as open questions (test coverage, `questions_pdf.py`).

Separately, the scraper's `logs/` output has been invisible relative to `ingest`'s: every
`ingest` command captures console output to a per-run log file, while a scrape currently
leaves no trace beyond whatever the terminal scrolled past, and there is no structured
record of which articles were skipped and why. FR-3 closes this gap with the same
per-run-log-file convention `ingest` uses, extended with two new artifact types.

## Functional Requirements

### FR-1: One scraper command with `--source`, replacing the per-law entry points

The three entry points collapse into a single CLI whose shape mirrors `ingest`, so that
delegating to it from `ingest scrape` later is a thin call rather than a rewrite.

**Acceptance criteria:**
- Given `pyproject.toml` after the change, when `[project.scripts]` is read, then `scrape-codice`, `scrape-cap` and `scrape-regolamento` are gone and a single `scrape` entry point is registered.
- Given `scrape --source cds`, `--source cap` and `--source reg`, when each runs, then it scrapes the corresponding law; given an unknown source, then it exits non-zero listing the valid ones, without opening a connection.
- Given `scrape --source reg --dry-run`, when it runs, then it prints what it would fetch and where it would write, and performs **no** HTTP request and no filesystem write — the same guarantee `ingest --dry-run` gives.
- Given a real run, when it completes, then progress and diagnostics go through `logging` at purposeful levels (per-article at `debug`, per-source milestones at `info`, a skipped article or a session refresh at `warning`) with lazy `%s` arguments, and the run is captured in a per-run log file as `ingest` commands are.
- Given `main`, when it is read, then the `continue`-based skips (the TOC flag-filter skip, the TOC dedup skip, the fetch-failure skip, the session-invalid skip) are replaced by positive guards, per `.claude/rules/code-conventions.md`. **Already implemented, ahead of this spec:** the parse-error skip (`try`/`except ValueError`/`else` around `_parse_article`, `src/scrapers/normattiva.py:514-522`) was added on 2026-08-02 as a pragmatic necessity — spec 0003's live scrape needed it to complete past two unparseable articles rather than abort the whole 409-article run — and already avoids `continue`. It is real, working code today, not a plan for this spec to build; this spec's job is only to preserve that shape through the restructuring, not reintroduce a `continue` in its place. Ownership of this piece (and its DoD accounting) belongs here, not to spec 0003, even though it landed in that spec's implementation window — see spec 0003's Changelog.

### FR-2: The scraper's data structures are dataclasses, not `TypedDict`s

`LawConfig`, `ArticleParams` and the article/comma records become dataclasses.

**Acceptance criteria:**
- Given the scraper module after the change, when it is read, then `LawConfig`, `ArticleParams` and the article record are `@dataclass` declarations and no `TypedDict` remains.
- Given a law configuration, when it is constructed with a missing or misspelled field, then it fails at construction rather than silently producing a wrong URL — the failure mode a `TypedDict` cannot give.
- Given the record dataclass, when the parsed JSON is written, then its shape is unchanged: the same keys, including `commas: list[{number, text}]`.
- Given `ParsedArticleModel`, when it loads that JSON, then validation still happens there: the scraper stays unvalidated-but-typed, and the Pydantic boundary is the ingestor's, unmoved.

### FR-3: Structured per-run artifacts (`logs/<run_id>/{run.log, manifest.json, report.md}`), shared with `ingest`

Every real (non-`--dry-run`) scrape run writes a `run_id` folder under `logs/`, mirroring
and extending `ingest`'s existing per-run log-file convention with two artifact types
that don't exist anywhere in the codebase today: `manifest.json` (run parameters and
outcome counts) and `report.md` (a curated summary of skipped articles, grouped by
cause). Both the scraper and `ingest` share one implementation (see AD-3) rather than
duplicating run-directory logic.

**Acceptance criteria:**
- Given a real `scrape --source <cds|cap|reg>` run, when it starts, then a `logs/scrape_<source>_<YYYYMMDDHHMM>/` directory is created, with the same numeric-suffix fallback (`_2`, `_3`, ...) on a same-minute collision that `ingest`'s `logs/ingest_<command>_<YYYYMMDDHHMM>/` convention already uses.
- Given that run directory, when the run completes — whether it finishes normally or raises an unhandled exception — then it contains `run.log` (as today), `manifest.json`, and `report.md`; all three are finalized even on a crash.
- Given `manifest.json`, when it is read, then it contains the run's parameters (source/law slug, `toc_url`, output paths), start/end timestamps, and outcome counts: articles found in the TOC, articles saved, and each skip reason counted separately (fetch failed, session invalid after refresh, parse error).
- Given `report.md`, when it is read, then it is always present, even for a clean run with zero skips, and groups skipped articles into three markdown subsections — Fetch failures, Session-invalid skips, Parse errors — each showing category-specific detail (e.g. the `ValueError` message for a parse error, the article label and URL for a fetch failure); a category with zero entries shows "None" rather than being omitted.
- Given `main()`'s three existing skip sites (fetch failure, session invalid after refresh, parse error), when an article is skipped, then `main()` calls the shared writer's `record_skip(category, article, detail)` at that point, replacing the current ad-hoc `skipped_parse_errors` list; the writer owns all accumulation and grouping, not `main()`.
- Given `scrape --source <...> --dry-run`, when it runs, then nothing is written to `logs/` at all — no run directory, no `run.log`, no `manifest.json`, no `report.md` — consistent with FR-1's existing "no filesystem write" guarantee for `--dry-run`.
- Given `ingest`'s existing commands, when they run after this change, then they produce the same `logs/ingest_<command>_<YYYYMMDDHHMM>/run.log` path and format as before — `cli/logging_setup.py` becomes a thin wrapper delegating to the shared writer, with no `ingest`-visible behavior change.

### FR-4: `main()`'s control flow is tested and the `C901` exemption is lifted for `src/scrapers/`

`_parse_article` and its helpers already have unit-test coverage (27 tests); `main()`
itself — the piece FR-1 restructures into positive guards — was the only untested-by-design
part of the module. Since the module is already being restructured, `main()` gets test
coverage in the same pass, and the module's `C901` (cyclomatic complexity) exemption is
lifted now that its most complex function is being cleaned up and made testable.

**Acceptance criteria:**
- Given the refactored `main()`, when its control flow is exercised in tests (each of the three skip categories from FR-3, the TOC flag-filter skip, the TOC dedup skip, and a clean run), then each path is covered by a test that mocks the HTTP client rather than hitting the network.
- Given `pyproject.toml`'s `[tool.ruff.lint.per-file-ignores]` after this change, then `"src/scrapers/**" = ["C901"]` is removed and `main()` (split into smaller functions if needed) is at or under the project's `max-complexity = 10`; `"src/parsers/**" = ["C901"]` is unaffected — `questions_pdf.py` is out of scope for this spec (see Non-Goals).

### FR-5: Title extraction strips a wrapping `((...))` amendment bracket, bracket-aware, instead of naive edge-character stripping

Both title-extraction paths — the `heading_tag` path's `.strip("().")` and the
`just_text_tag` path's `_split_leading_title` — fail when the real `(Title)` is wrapped
in an outer amendment bracket `((...))`. Investigation traced this to one root cause
producing three distinct symptoms: an empty title (21 Regolamento articles, where
`_split_leading_title`'s loop explicitly excludes a leading `((` from being recognized as
a title start and falls through to its no-title warning path), a leading cross-reference
note glued to the real title with no separating space (5 Regolamento articles, e.g.
`"Art. 10 Cod. Str.)Provvedimento di autorizzazione"`), and un-stripped bracket/whitespace
debris left in the title (284 records across cds/cap/reg — `.strip("().")` only trims
characters sitting at the string's very edges, so it either leaves outer-bracket remnants
attached or eats through into the real title's own closing punctuation, depending on
whether whitespace happens to separate the two). A single bracket-aware stripping step,
applied before either extraction path runs, addresses all three symptoms.

**Acceptance criteria:**
- Given a `just_text_tag` article body wrapped in a leading `((...))` amendment bracket around its `(Title)` (e.g. Regolamento art. 6), when `_split_leading_title` runs, then it recognizes and strips the wrapping bracket before extracting the title, instead of falling through to the no-title warning path.
- Given a `just_text_tag` article body with a leading cross-reference note glued to the real title inside the amendment bracket with no separating space (e.g. Regolamento art. 16), when title extraction runs, then the cross-reference note is stripped and only the real title remains, consistent with how multiple leading title segments are already handled.
- Given a `heading_tag` wrapped in a leading `((...))` amendment bracket (e.g. CdS art. 9-bis, CAP art. 3), when title extraction runs, then no bracket/whitespace debris (a leading space, a trailing `"). "`, or a truncated closing paren) remains in the extracted title.
- Given the full corpus (cds, cap, reg) re-scraped after the fix, when titles are inspected, then none of the 284 previously-identified records (18 cds, 247 cap, 19 reg) exhibit the leading-space or trailing-space/`.`/`)` symptom, and the 4 genuinely-titleless, fully-repealed articles (Regolamento 74, 254, 338, 395) remain correctly titleless.

### FR-6: `_is_marker_start` recognizes additional comma-boundary contexts, recovering articles 83 and 194

`_is_marker_start` only accepts `.` or `)` as the character immediately preceding a new
comma-number marker, which misses two real boundary contexts in the Regolamento corpus:
a table-like list row ending in a bare word with no punctuation at all (art. 83, comma
10 → 11) and a semicolon-terminated lettered sub-list item (art. 194, comma 1 → 2). Both
articles are currently permanently skipped by the parse-error guard, leaving
`data/parsed/reg/regolamento_attuazione.json` with 407 records instead of 409.

**Acceptance criteria:**
- Given Regolamento art. 83's raw HTML, when it is parsed, then comma 11 is recognized as a separate comma from comma 10, and the article parses successfully instead of raising `ValueError`.
- Given Regolamento art. 194's raw HTML, when it is parsed, then comma 2 is recognized as a separate comma from comma 1, and the article parses successfully instead of raising `ValueError`.
- Given the widened accepted-punctuation set, when the full existing 27-test suite (`tests/scrapers/test_normattiva.py`) is run, then all tests still pass — no new false-positive comma boundary is introduced elsewhere in the corpus.
- Given a live re-scrape of the Regolamento source after the fix, when `data/parsed/reg/regolamento_attuazione.json` is inspected, then it contains 409 records, recovering the two previously-skipped articles.

### FR-7: Per-comma repeal detection recognizes both `COMMA ABROGATO` and `COMMA SOPPRESSO`

`_COMMA_REPEALED_PREFIX` in `article_mapper.py` only matches `"COMMA ABROGATO"`, missing
the `"COMMA SOPPRESSO"` wording used across all three sources (cds: 6, cap: 2, reg: 12 —
20 commas total), which are stored with correct text but never flagged `is_repealed=True`.
This is not Regolamento-exclusive, contrary to how the issue was originally reported —
CdS alone already has 6 silently-mis-flagged commas in production data today.

**Acceptance criteria:**
- Given a comma whose text (after the existing `lstrip("(").strip().upper()` normalization) starts with `"COMMA SOPPRESSO"`, when `ArticleMapper.from_cleaned_to_embeddable_commas` runs, then `is_repealed` is `True`, the same as for `"COMMA ABROGATO"`.
- Given the existing `"COMMA ABROGATO"` behavior, when this change is applied, then it is unaffected — both prefixes are recognized, neither is removed.
- Given the full corpus re-ingested after the fix, when the commas table is inspected, then all 20 previously-identified `COMMA SOPPRESSO` commas across cds/cap/reg are flagged `is_repealed=True`.

## Non-Goals

- **Moving the scraper into the ingestor.** It stays in `src/scrapers/`, which is what `docs/layout.md:128` prescribes for data-acquisition scripts — so this refactor needs no ADR and no `docs/` restructuring. FR-1 only makes the CLI shape match `ingest`, which is the seam that makes an eventual `ingest scrape` a delegation instead of a port.
- ~~**Fixing the Known Issues found during spec 0003 Phase 1.**~~ Reversed by amendment (2026-08-02): investigation showed one of the four issues is actually three symptoms of a single root cause, and all four are now in scope as FR-5, FR-6 and FR-7.
- **Re-tuning the politeness delay or retry/session-refresh policy.** Unchanged from spec 0003: `DELAY_SECONDS = 1.5`, same retry loop, same session-invalidation guard.
- **Bringing `src/parsers/questions_pdf.py` to the same standard** (dataclasses, tests, lifted `C901` exemption). Decided by amendment (2026-08-02): deferred to a follow-up spec — `questions_pdf.py` is a different module (PDF parsing, not HTML scraping) unrelated to `normattiva.py`'s actual diff, and this spec is already substantial (dataclasses, CLI unification, run artifacts, test coverage, four data-quality fixes).

## Architectural Decisions

### AD-1: Dataclasses inside the scraper; the Pydantic boundary stays in the ingestor
The scraper's structures become dataclasses rather than Pydantic models.
- **Rationale:** the scraper's job is to shape HTML into JSON, and it has no untrusted input to validate — its input is HTML it parses itself and its output is validated one layer down, where `ParsedArticleModel` already loads that JSON. Dataclasses give what `TypedDict` fails to give (a real runtime type, construction-time failure on a wrong field, defaults, `__repr__`) without pulling a validation framework into a module that is deliberately kept light. The global standard permits either: "prefer `dataclasses` or Pydantic over raw dicts". Placing the single validation boundary at the ingestor's edge rather than duplicating it in the scraper keeps one place where a malformed record is rejected.
- **Rejected alternatives:** Pydantic models in the scraper — validation at the point of production catches a bad record earlier, but duplicates the boundary `ParsedArticleModel` already is and makes the scraper heavier for a module with no external input; keeping `TypedDict` and only changing the CLI — smallest diff, but a `TypedDict` is erased at runtime, so a misspelled `LawConfig` field yields a silently wrong URL instead of an error, which is precisely the class of silent defect this refactor exists to remove.

### AD-2: The scraper CLI is shaped like `ingest` so a later `ingest scrape` is a delegation
`--source`, `--dry-run`, logging levels and the per-run log file follow the `ingest`
conventions even though the command stays separate.
- **Rationale:** the requested integration is "for the future", so the cheapest thing that buys it is convention rather than code: if the two CLIs already agree on flags, output discipline and dry-run semantics, then adding `ingest scrape` later is a subparser that calls a function, with no behavioural surface left to reconcile. It also pays off immediately — a scrape currently vanishes from the logs while every `ingest` command is captured in `logs/ingest_<command>_<ts>/run.log`.
- **Rejected alternatives:** adding `ingest scrape` now — one CLI instead of two, but it makes the ingestor depend on `src/scrapers/` and puts the network-facing step behind a command whose `--dry-run` contract currently promises no I/O of any kind; leaving three entry points and only fixing the dataclasses — half the ergonomic problem, and having three real sources today (not two-plus-one-planned) is exactly what makes it visible.

### AD-3: `RunArtifactWriter` is a single concrete class (no `Protocol`/port) in `src/commons/observability/`, shared by the scraper and `ingest`

A new `RunArtifactWriter` is added to `src/commons/observability/`, absorbing the
run-directory-with-collision-suffix logic currently living only in `ingest`'s
`cli/logging_setup.py`, plus the new `manifest.json`/`report.md` responsibilities FR-3
introduces. Both the scraper and `ingest` depend on this one shared component instead of
maintaining parallel implementations. It is a plain class, not a `Protocol` + service
pairing.

- **Rationale:** `docs/layout.md:121-126` already designates `src/commons/` as the home for genuinely generic, domain-agnostic infrastructure, and the run-dir logic in `cli/logging_setup.py` is exactly that — no knowledge of ingestion/scraping content. A single implementation avoids two parallel run-dir/collision-suffix codepaths. `src/commons/observability/` already exists and holds a conceptually adjacent component (`ProgressReporter`), so this is the natural package, not a new top-level concern. No `Protocol`/port: unlike `ProgressReporter`, which genuinely swaps between a `LiveDashboard` implementation and a null/console one, there is no second real implementation on the table for `RunArtifactWriter` — `--dry-run` skips constructing the writer entirely rather than swapping in a no-op, so a port has no second caller to justify it yet (YAGNI; can be introduced later, pull-based, if one emerges).
- **Rejected alternatives:** a scraper-local module — smallest diff and keeps this spec's blast radius minimal, but locks in duplicate run-dir logic; importing `cli/logging_setup.py` directly from `src/scrapers/` — wrong dependency direction, the scraper would depend on the ingestor's self-contained CLI package, backwards from AD-2 and `.claude/rules/cli-structure.md`'s boundary; a `Protocol` + service pairing mirroring `ProgressReporter` — explicitly considered and rejected as overengineered for a component with only one real implementation today.

## Constraints

- **No `continue` in loop bodies**, lazy `%s` logging arguments, English docstrings and log messages (`.claude/rules/`).
- **This refactor needs no ADR and no `docs/` restructuring** beyond what it directly touches. The scraper stays in `src/scrapers/` with a `[project.scripts]` entry, which is exactly what `docs/layout.md:128` prescribes; only the CLI shape and the data structures change. `docs/architecture.md:53` and the script table in `CLAUDE.md` need updating for the renamed entry point, nothing more.
- **Must not change the parsed JSON shape.** It is a contract consumed by `ParsedArticleModel`; FR-2 swaps the producing type, not the produced keys.
- **Schema changes, if any turn out to be needed, go into `db/init.sql`** and are applied by recreating the volume; there is no migration tool. None are expected for this refactor.

## Feasibility Evidence

- **AD-1** — supported by: `src/scrapers/normattiva.py:41` — `class LawConfig(TypedDict)` is erased at runtime, so a misspelled or missing key produces a silently wrong article URL instead of a construction error (verified 2026-08-02 @ 008d5ae)
- **AD-1** — supported by: `src/scrapers/normattiva.py:83` — `class ArticleRecord(TypedDict)` is the shape written to the parsed JSON, the artifact spec 0003 promotes to a contract; a dataclass preserves that shape while giving it a real runtime type (verified 2026-08-02 @ 008d5ae)
- **AD-1** — supported by: `src/guidami_ai_patente_ingestor/models/knowledge/parsed_article.py:11` — `ParsedArticleModel` is a Pydantic model loading exactly that JSON, so the validation boundary already exists one layer down and does not need duplicating in the scraper (verified 2026-08-02 @ 008d5ae)
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/cli/parser.py:67` — `build_parser(config)` derives `--source` choices from config and attaches `--dry-run` per leaf subparser: the conventions FR-1 mirrors, and the insertion point a future `ingest scrape` would use (verified 2026-08-02 @ 008d5ae)
- **AD-2** — supported by: `src/scrapers/normattiva.py:540-556` — `main_cds`/`main_cap`/`main_reg` are three separate entry points for what is one operation parameterised by law (verified 2026-08-02 @ 008d5ae; mechanical drift only — same content, line numbers shifted from the original `538-550` anchor)
- **AD-3** — supported by: `src/commons/observability/protocols/progress_reporter.py:1-51` — `ProgressReporter`, the existing `Protocol`+service pattern in the same package family that AD-3 deliberately does *not* replicate (verified 2026-08-02 @ 008d5ae)
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/cli/logging_setup.py:10-27` — the run-dir-with-collision-suffix logic `RunArtifactWriter` absorbs (verified 2026-08-02 @ 008d5ae)
- **AD-3** — supported by: `docs/layout.md:121-126` — `src/commons/` as the designated home for shared, domain-agnostic infrastructure (verified 2026-08-02 @ 008d5ae)
- **FR-1** — supported by: `pyproject.toml:27-29` — `scrape-codice`, `scrape-cap` and `scrape-regolamento` are three separate `[project.scripts]` entries for what is one operation parameterised by law (verified 2026-08-02 @ 008d5ae)
- **FR-1** — supported by: `src/scrapers/normattiva.py:269` — a bare `continue` skips a non-article TOC entry (verified 2026-08-02 @ 008d5ae)
- **FR-1** — supported by: `src/scrapers/normattiva.py:275` — a bare `continue` skips a duplicate TOC entry (verified 2026-08-02 @ 008d5ae)
- **FR-1** — supported by: `src/scrapers/normattiva.py:498` — a bare `continue` skips a failed fetch, violating `.claude/rules/code-conventions.md` (verified 2026-08-02 @ 008d5ae)
- **FR-1** — supported by: `src/scrapers/normattiva.py:510` — a bare `continue` skips a still-invalid session after refresh, same violation (verified 2026-08-02 @ 008d5ae)
- **FR-2** — supported by: `src/scrapers/normattiva.py:69` — `class ArticleParams(TypedDict)` carries the nine query parameters that build every article URL, the structure whose silent mistyping is hardest to notice (verified 2026-08-02 @ 008d5ae)
- **FR-3** — supported by: `src/guidami_ai_patente_ingestor/cli/logging_setup.py:10-27` — the existing `run_id` naming and dry-run-skip behavior FR-3 mirrors and extends (verified 2026-08-02 @ 008d5ae)
- **FR-3** — supported by: `src/scrapers/normattiva.py:485-520` — the three existing skip sites where `record_skip` is called (verified 2026-08-02 @ 008d5ae)
- **FR-4** — supported by: `pyproject.toml:75-76` — `"src/scrapers/**" = ["C901"]` (line 75, to be removed) and `"src/parsers/**" = ["C901"]` (line 76, unaffected) (verified 2026-08-02 @ 008d5ae)
- **FR-4** — supported by: `tests/scrapers/test_normattiva.py:25-571` — 27 existing tests for `_parse_article` and its helpers, confirming `main()` is the only untested-by-design piece of the module (verified 2026-08-02 @ 008d5ae)
- **FR-5** — supported by: `src/scrapers/normattiva.py:152` — `_split_leading_title`'s loop explicitly excludes a leading `((` from title-start recognition (verified 2026-08-02 @ 008d5ae)
- **FR-5** — supported by: `src/scrapers/normattiva.py:320` — the `heading_tag` path's naive `.strip("().")` (verified 2026-08-02 @ 008d5ae)
- **FR-6** — supported by: `src/scrapers/normattiva.py:174-201` — `_is_marker_start`'s accepted preceding-punctuation set, reproduced live against `data/raw/reg/art_0083_1.html` and `art_0194_1.html` to raise the exact `ValueError`s this spec quotes (verified 2026-08-02 @ 008d5ae)
- **FR-7** — supported by: `src/guidami_ai_patente_ingestor/mappers/article_mapper.py:1-104` — `_COMMA_REPEALED_PREFIX`'s single-value check at line 10, applied at line 76 (verified 2026-08-02 @ 008d5ae)

## Open Questions

- [ ] **non-blocking** — Exact `RunArtifactWriter` constructor signature and method names beyond `record_skip` (e.g. what starts the run / writes the initial manifest, what finalizes it on completion or crash) are implementation-level detail, left for `/write-plan` to decide against this spec's acceptance criteria — owner: write-plan
- [ ] **non-blocking** — Whether `src/commons/observability/` needs a sub-package split (e.g. a `run_artifacts/` directory alongside the existing `protocols/`/`services/` split) or a single new file is enough — left for `/write-plan` — owner: write-plan
- [ ] **non-blocking** — Exact bracket-aware stripping logic for FR-5's unified fix (e.g. a shared helper that strips a wrapping `((...))` pair before either the `heading_tag` or `just_text_tag`/`_split_leading_title` path runs) is not designed yet — root cause and blast radius (284 records) are confirmed, but the fix's exact shape is `/write-plan` work — owner: write-plan
- [ ] **non-blocking** — FR-6's widened punctuation set needs the full 27-test suite plus a live re-scrape to confirm no new false-positive comma splits across the corpus before merging — a verification step for implementation, not a design question — owner: write-plan

## Sign-off

- **Scope approved by user:** Alessio Gilardi, 2026-08-02
- **Feasibility asserted:** by review on 2026-08-02, based on Feasibility Evidence above

## Changelog

### 2026-08-02 — amendment: run artifacts + Open Questions closed
Compiled from `specs/discussions/scraper-acquisition-refactor.md` (2 sessions). Added
FR-3 (structured per-run artifacts: `logs/<run_id>/{run.log, manifest.json, report.md}`,
shared with `ingest` via a new `RunArtifactWriter`) and AD-3 (its architectural
placement: a portless concrete class in `src/commons/observability/`). Closed all six
of the spec's original Open Questions with a disposition each: FR-4 (test `main()`,
lift the `C901` exemption), FR-5 (unify three title-extraction defects — empty titles,
glued cross-references, bracket debris — into one bracket-aware fix, revised scope from
a handful of records to 284 across cds/cap/reg), FR-6 (widen `_is_marker_start`'s
punctuation set, recovering articles 83 and 194), FR-7 (recognize `COMMA SOPPRESSO`
alongside `COMMA ABROGATO`, revealed as affecting all three sources, not
Regolamento-only). Non-Goals updated: the "fix Known Issues" non-goal is struck through
(reversed — now in scope as FR-5/6/7); the `questions_pdf.py` non-goal is confirmed
deferred to a follow-up spec rather than left an open question. No FRs renumbered or
removed. Reason: the discussion log converged on all of the above and the user asked to
compile it.
