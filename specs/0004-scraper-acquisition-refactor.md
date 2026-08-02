# Spec 0004: Scraper acquisition-layer refactor (unified CLI, dataclasses)

| | |
|---|---|
| **Id** | 0004 |
| **Status** | draft |
| **Date** | 2026-08-02 |
| **Discussion log** | none — split from `specs/0003-regolamento-attuazione-corpus.md` §Phase 2 (FR-6, FR-7), 2026-08-02 |
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
implementer touching this file should be aware of; see Open Questions below. Fixing them
is **not** required by this spec's acceptance criteria, but this refactor is the natural
point to also address them, since the file is already being restructured.

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

## Non-Goals

- **Moving the scraper into the ingestor.** It stays in `src/scrapers/`, which is what `docs/layout.md:128` prescribes for data-acquisition scripts — so this refactor needs no ADR and no `docs/` restructuring. FR-1 only makes the CLI shape match `ingest`, which is the seam that makes an eventual `ingest scrape` a delegation instead of a port.
- **Fixing the Known Issues found during spec 0003 Phase 1** (see Open Questions below). Not required by FR-1/FR-2's acceptance criteria — tracked here because this refactor touches the same file, not because either FR depends on them.
- **Re-tuning the politeness delay or retry/session-refresh policy.** Unchanged from spec 0003: `DELAY_SECONDS = 1.5`, same retry loop, same session-invalidation guard.
- **Bringing `src/parsers/questions_pdf.py` to the same standard** (dataclasses, tests, lifted `C901` exemption). Tracked as an open question below, not decided here.

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

## Constraints

- **No `continue` in loop bodies**, lazy `%s` logging arguments, English docstrings and log messages (`.claude/rules/`).
- **This refactor needs no ADR and no `docs/` restructuring** beyond what it directly touches. The scraper stays in `src/scrapers/` with a `[project.scripts]` entry, which is exactly what `docs/layout.md:128` prescribes; only the CLI shape and the data structures change. `docs/architecture.md:53` and the script table in `CLAUDE.md` need updating for the renamed entry point, nothing more.
- **Must not change the parsed JSON shape.** It is a contract consumed by `ParsedArticleModel`; FR-2 swaps the producing type, not the produced keys.
- **Schema changes, if any turn out to be needed, go into `db/init.sql`** and are applied by recreating the volume; there is no migration tool. None are expected for this refactor.

## Feasibility Evidence

- **AD-1** — supported by: `src/scrapers/normattiva.py:41` — `class LawConfig(TypedDict)` is erased at runtime, so a misspelled or missing key produces a silently wrong article URL instead of a construction error (verified 2026-08-02 @ 3cce407)
- **AD-1** — supported by: `src/scrapers/normattiva.py:83` — `class ArticleRecord(TypedDict)` is the shape written to the parsed JSON, the artifact spec 0003 promotes to a contract; a dataclass preserves that shape while giving it a real runtime type (verified 2026-08-02 @ 3cce407)
- **AD-1** — supported by: `src/guidami_ai_patente_ingestor/models/knowledge/parsed_article.py:11` — `ParsedArticleModel` is a Pydantic model loading exactly that JSON, so the validation boundary already exists one layer down and does not need duplicating in the scraper (verified 2026-08-02 @ 3cce407)
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/cli/parser.py:67` — `build_parser(config)` derives `--source` choices from config and attaches `--dry-run` per leaf subparser: the conventions FR-1 mirrors, and the insertion point a future `ingest scrape` would use (verified 2026-08-02 @ 3cce407)
- **AD-2** — supported by: `src/scrapers/normattiva.py:538-550` — `main_cds`/`main_cap`/`main_reg` are three separate entry points for what is one operation parameterised by law (verified 2026-08-02 @ 3cce407)
- **FR-1** — supported by: `pyproject.toml:27-29` — `scrape-codice`, `scrape-cap` and `scrape-regolamento` are three separate `[project.scripts]` entries for what is one operation parameterised by law (verified 2026-08-02 @ 3cce407)
- **FR-1** — supported by: `src/scrapers/normattiva.py:269` — a bare `continue` skips a non-article TOC entry (verified 2026-08-02 @ 3cce407)
- **FR-1** — supported by: `src/scrapers/normattiva.py:275` — a bare `continue` skips a duplicate TOC entry (verified 2026-08-02 @ 3cce407)
- **FR-1** — supported by: `src/scrapers/normattiva.py:498` — a bare `continue` skips a failed fetch, violating `.claude/rules/code-conventions.md` (verified 2026-08-02 @ 3cce407)
- **FR-1** — supported by: `src/scrapers/normattiva.py:510` — a bare `continue` skips a still-invalid session after refresh, same violation (verified 2026-08-02 @ 3cce407)
- **FR-2** — supported by: `src/scrapers/normattiva.py:69` — `class ArticleParams(TypedDict)` carries the nine query parameters that build every article URL, the structure whose silent mistyping is hardest to notice (verified 2026-08-02 @ 3cce407)

## Open Questions

- [ ] **non-blocking** — Should this refactor also bring `src/scrapers/` fully under test and lift its `C901` exemption (`pyproject.toml:72-75`)? Spec 0003 Phase 1 already added substantial unit tests for `_parse_article` and its helpers (`tests/scrapers/test_normattiva.py`, 27 tests) — the previously-blanket "no tests" premise is no longer accurate. What remains untested by design are the network-fetching entry points (`main`, `main_cds`, `main_cap`, `main_reg`); the narrower question is whether `main`'s own control flow (once unified under FR-1) should get tested too, and whether the `C901` exemption should be lifted now that the module is being restructured anyway — owner: user
- [ ] **non-blocking** — Should `src/parsers/questions_pdf.py` get the same treatment as FR-1/FR-2 (dataclasses, CLI shape, tests)? Otherwise the two acquisition modules sit on different footings after this refactor — owner: user
- [ ] **non-blocking** — **(found during spec 0003 Phase 1)** A live 409-article scrape produced 25/407 successfully-parsed articles (6.1%) with no leading-parenthesis title — `_split_leading_title`'s warning fallback path (`src/scrapers/normattiva.py:141-158`) — just over spec 0003's own 5% "design failure" guardrail for that fallback (FR-2/AD-3's open question, now measured). Worth a closer look at which of the 25 are genuinely titleless vs. a heuristic miss the current rules don't yet cover — owner: investigation
- [ ] **non-blocking** — **(found during spec 0003 Phase 1)** Two articles are permanently skipped by the live scrape's parse-error guard: `data/parsed/reg/regolamento_attuazione.json` has 407, not 409, records. Art. 83's comma 10 is a table-like list of symbol/figure-code triples with no sentence punctuation before its `11.` marker — `_is_marker_start`'s boundary rules (`src/scrapers/normattiva.py:180-201`) all assume ordinary prose. Art. 194 fails with `comma base numbers are not contiguous from 1: ['1', '3']`, cause not yet diagnosed. Needs bespoke handling or manual correction if these two articles matter for the quiz corpus — owner: investigation
- [ ] **non-blocking** — **(found during spec 0003 Phase 1)** `article-heading-akn` title cleanup only strips a *leading/trailing* parenthesis: `titolo = heading_tag.get_text(strip=True).strip("().")` (`src/scrapers/normattiva.py:320`, pre-existing since spec 0001) doesn't remove an embedded, non-edge stray `)` when a heading concatenates a cross-reference note with the real title with no separating space (e.g. Regolamento art. 16's title rendered as `Art. 10 Cod. Str.)Provvedimento di autorizzazione`; arts. 393/397/398 hit the same pattern). Not previously observed in CdS/CAP samples; surfaced only by the live Regolamento scrape — owner: investigation
- [ ] **non-blocking** — **(found during spec 0003 Phase 1)** Per-comma repeal detection doesn't recognise all Regolamento wording: `_COMMA_REPEALED_PREFIX = "COMMA ABROGATO"` (`src/guidami_ai_patente_ingestor/mappers/article_mapper.py:10`) misses the `"COMMA SOPPRESSO"` variant the Regolamento also uses (see spec 0003 art. 4, whose duplicate-comma-6 case is literally `((COMMA SOPPRESSO DAL D.P.R. ... N. 610))`) — such a comma is stored with the correct text but never gets `is_repealed=True` — owner: investigation

## Sign-off

- **Scope approved by user:** pending
- **Feasibility asserted:** by review on 2026-08-02, based on Feasibility Evidence above
