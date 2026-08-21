# Spec 0003: Regolamento di attuazione (DPR 495/1992) in the corpus

| | |
|---|---|
| **Id** | 0003 |
| **Status** | implemented |
| **Date** | 2026-07-31 |
| **Discussion log** | — (compiled from conversation, 2026-07-31) |
| **Supersedes / superseded by** | — |
| **Depends on** | 0001 (article-level storage) — see AD-1 |

## Problem & Motivation

The corpus holds the Codice della Strada and the RCA subset of the Codice delle
Assicurazioni Private. It does **not** hold the Regolamento di esecuzione e di attuazione
del nuovo codice della strada (DPR 16 dicembre 1992, n. 495), and that is where the
normative descriptions of road signs live.

A large share of the quiz bank asks about signs. Of 7106 sub-questions in
`quiz-patente-ab.json`, the recurring form is `Il segnale raffigurato ...` — for example
`Il segnale raffigurato preavvisa confine di Stato con un Paese che fa parte dell'Unione
Europea`. Nothing in the CdS answers that: the CdS delegates the sign catalogue to the
Regolamento, whose art. 116 reads

> `(Segnali di divieto generici) 1. I segnali di divieto relativi alla circolazione di tutti
> i veicoli sono: [...] c) il segnale DIVIETO DI SORPASSO (fig. II.48), che indica il divieto
> di sorpassare i veicoli a motore eccetto i ciclomotori e i motocicli anche se la manovra
> può compiersi entro la semicarreggiata con o senza la striscia continua;`

This is exactly the material the quiz tests, and it is absent. The consequence is not a
weak answer but an unanswerable one: no embedding strategy retrieves a norm that was never
ingested, and a retrieval evaluation run against today's corpus would attribute to the
index a failure that belongs to acquisition. Spec 0001 records this as an explicit
Non-Goal precisely so it would be tracked here.

The text is nowhere in the repository: `data/docs/` holds only the 24 MB quiz PDF, no
`data/{raw,parsed}/reg` exists, and no file, config key or script mentions the Regolamento
or DPR 495. It has to be scraped.

Adding it also exposes a second, smaller problem. The scraper hardcodes one module-level
constant and one entry point per law — `CDS`/`main_cds`, `CAP`/`main_cap`, registered as
`scrape-codice` and `scrape-cap` — so a third source means a third constant, a third
function and a third `[project.scripts]` line. Two laws made that pattern look like a
coincidence; three make it a shape. Its data structures are `TypedDict`s, which are erased
at runtime and validate nothing, and progress goes to `print`, so a scrape leaves no trace
in the per-run log files every `ingest` command writes. That tidy-up was originally scoped
here as this spec's own Phase 2 (FR-6/FR-7); now that Phase 1 is implemented, it has been
split out into `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md` so this spec can close — see
the Changelog.

## Functional Requirements

FR-1…FR-5 ingest the Regolamento; this is this spec's full remaining scope. The
acquisition-layer tidy-up originally scoped here as Phase 2 (FR-6, FR-7) has been split
into `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md` now that this phase is implemented —
see the Changelog and AD-5.

### FR-1: The Regolamento is a third scraper target

`scrapers.normattiva` gains a `REG` law configuration and an entry point, alongside `CDS`
and `CAP`.

**Acceptance criteria:**
- Given the URN `urn:nir:stato:decreto.presidente.repubblica:1992-12-16;495`, when the TOC is fetched and parsed, then 409 article parameter sets are returned, numbered 1 through 408.
- Given the TOC, when it is parsed, then the four annex entries are excluded, as they already are for the other two sources by the `flagTipoArticolo != "0"` filter.
- Given the scrape completes, when the output is inspected, then `data/raw/reg/` holds one HTML file per article and `data/parsed/reg/regolamento_attuazione.json` holds one record per article.
- Given the extraction is registered under `[project.scripts]` as `scrape-regolamento`, when it is invoked, then it runs the same fetch/retry/session-refresh loop as the existing sources with no new politeness policy.

### FR-2: The article title is the leading parenthesised segment

The Regolamento emits no `article-heading-akn`. The title is the parenthesised segment at
the head of the body, which is split off from the comma text rather than left inside it.

**Acceptance criteria:**
- Given art. 116, whose body begins `(Segnali di divieto generici) 1. I segnali di divieto...`, when the article is parsed, then the title field holds `Segnali di divieto generici` and the first comma's text begins `I segnali di divieto...`.
- Given the parsed corpus, when article titles are inspected, then no title begins or ends with a parenthesis and no comma text begins with the article's own title.
- Given an article whose body has no leading parenthesised segment, when it is parsed, then the title is empty, the whole body is treated as comma text, and a `warning` records the article number.

### FR-3: The single body block is segmented into commas on inline number markers

The whole article sits in one `art-just-text-akn` block with commas numbered inline. The
block is split on those markers into one comma per number.

**Acceptance criteria:**
- Given art. 79, whose body carries the inline markers `1.`, `2.`, `3.`, when it is parsed, then three commas numbered `1`, `2`, `3` are emitted and their concatenated text reconstructs the body minus the markers and the title.
- Given art. 2, whose first marker is written `((1.` under an amendment, when it is parsed, then the comma number is `1` and the marker characters are not part of its text — the same normalisation spec 0001 FR-1 applies to the CdS.
- Given a body containing `n. 495.`, `art. 2.`, `fig. II.48` or a date such as `16 dicembre 1992, n. 495.`, when it is parsed, then none of these is mistaken for a comma marker.
- Given any article, when its commas are emitted, then their numbers form a contiguous sequence starting at `1`; if they do not, parsing **fails loudly** naming the article and the sequence found.

### FR-4: The Regolamento is a third `source` in the existing tables

No new table: the Regolamento reuses `articles` and `article_commas` with `source = "reg"`.

**Acceptance criteria:**
- Given `IngestorConfig`, when it is loaded, then `sources` contains a `reg` entry and `knowledge_preparation` / `knowledge_indexing` list `reg` alongside `cds` and `cap`.
- Given the source literal on the knowledge models and the article entity, when it is inspected, then it admits `"reg"`.
- Given `cds` and `cap` have been indexed, when `reg` is indexed, then their rows are unchanged and `reg` rows are added under the same per-source full-reload behaviour.
- Given `ingest reset knowledge`, when it runs, then it empties both tables for all three sources, as today.
- Given `ingest status`, when it runs, then it reports `reg` readiness for `prepare` and `index`.

### FR-5: `prepare` and `index` handle the Regolamento with no source-specific branch

The cleaning and indexing flows treat `reg` like any other knowledge source.

**Acceptance criteria:**
- Given `ingest prepare knowledge --source reg`, when it runs, then it writes one JSON file per article into `data/cleaned/reg/` under the same deterministic `element_id(source, number)` name, and makes no LLM call.
- Given `ingest index knowledge --source reg`, when it runs, then it embeds article title + comma text per comma, as for the other sources.
- Given the flows after the change, when they are read, then no branch keys off `source == "reg"`.

### ~~FR-6: One scraper command with `--source`, replacing the per-law entry points~~

**Moved to `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md` FR-1** (2026-08-02), unchanged in
substance — see that spec for the current acceptance criteria.

### ~~FR-7: The scraper's data structures are dataclasses, not `TypedDict`s~~

**Moved to `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md` FR-2** (2026-08-02), unchanged in
substance — see that spec for the current acceptance criteria.

## Non-Goals

- **The annexes.** The four annex entries (figures `II.*`, tables `II.1`–`II.15`) are not scraped, so a reference like `(fig. II.48)` stays an unresolved code in the comma text. Their structure — figures and tables rather than prose — is a second parsing problem, and what Normattiva actually serves as text for them has not been verified. Deliberately deferred: the sign *descriptions* are in the articles, which is what the quiz tests.
- **Bridging quiz image → sign description.** The quiz shows a picture; the corpus names the sign in words. Connecting them is a read-path problem, and the quiz side already carries a road-sign description enricher plus `core_concepts` / `exact_keywords` / `rule_explanation`. Nothing here builds that link.
- **Retrieval, hybrid search, vector indexes.** Unchanged from spec 0001: no read path is built.
- **Restricting to the signage articles only.** All 409 are ingested. Range-filtering (the FR-6 technique of spec 0001) would cut fetches and noise, but the quiz also covers vehicles, licences and inspections, which the Regolamento details elsewhere; and the ranges are not known.
- **Re-verifying the CdS/CAP corpus.** This spec adds a source; it does not revisit spec 0001's findings.
- **Moving the scraper into the ingestor.** It stays in `src/scrapers/`, which is what `docs/layout.md:128` prescribes for data-acquisition scripts. The acquisition-layer CLI/dataclass tidy-up itself is out of scope here entirely — see `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md`.
- **Full test coverage for the scraper, and lifting its `C901` exemption.** Contrary to this spec's original plan, FR-2/FR-3's parsing rules ended up with substantial unit test coverage (`tests/scrapers/test_normattiva.py`, 27 tests covering `_parse_article` and its helpers) — real-world edge cases found by the live scrape made that necessary, not optional. What remains untested by design are the network-fetching entry points (`main`, `main_cds`, `main_cap`, `main_reg`), and the `C901` cyclomatic-complexity exemption (`docs/testing.md:25`) is unchanged. Further coverage is tracked in `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md`'s Open Questions.
- **Bringing `src/parsers/` along.** `parsers/questions_pdf.py` is in the same condition (script, `C901`-exempt, one unit test). This spec touches only the scraper, so the two acquisition modules end up on slightly different footings. Deliberate; tracked as an open question in `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md`.

## Architectural Decisions

### AD-1: This spec is sequenced after 0001, not merged into it and not independent of it
Implementation starts once 0001's Phase 1 is done.
- **Rationale:** with today's parser the Regolamento yields **409 empty records** — every article's content is in `art-just-text-akn`, the container 0001's FR-14 adds. So this work is not merely easier after 0001, it is impossible before it. Merging it into 0001 instead would widen a spec that already spans acquisition and schema, and would put a third corpus behind the same re-scrape gate.
- **Rejected alternatives:** merging into 0001 — one re-scrape instead of two, but 0001 grows a third source and a new parsing rule while it is still unimplemented; implementing independently with a private parser for the Regolamento — unblocks immediately, but forks the acquisition layer into two parsers over the same markup vocabulary, which is the duplication 0001's AD-16 exists to avoid.

### AD-2: Comma segmentation generalises 0001's FR-14 rather than special-casing the Regolamento
The rule "split an `art-just-text-akn` block on inline comma markers" replaces FR-14's
"emit a single comma numbered `1`" for blocks that carry markers, and applies to every
source.
- **Rationale:** 0001's FR-14 could get away with the single-comma rule because its only two in-scope cases were CdS art. 216 (one unnumbered paragraph) and CAP art. 121-octies (one comma `1.`). The Regolamento makes the general case the normal case — sampled articles carry 2 to 12 inline-numbered commas — and the two rules are the same rule at different cardinalities. Keeping one segmentation function means CdS/CAP inherit any correction made here.
- **Rejected alternatives:** a `reg`-only segmenter — no risk of regressing CdS/CAP, but two implementations of one rule; leaving FR-14's single-comma behaviour and storing each Regolamento article as one giant comma — no parsing work, but art. 2 becomes a single 5046-character vector, destroying the comma-level granularity that is the entire point of spec 0001.

### AD-3: Segmentation is validated by the contiguity of comma numbers, and fails loudly
Emitted numbers must run `1, 2, 3, …` with no gap; otherwise the parse aborts for that
article.
- **Rationale:** splitting prose on `N.` is inherently fragile — the corpus is full of `art. 2.`, `n. 495.`, `fig. II.48` and dates that look like markers. Unlike the CdS, where legal numbers are irregular (`4-bis`, `13-ter`) and gaps are legitimate, the Regolamento numbers its commas as a plain contiguous sequence, which hands us a free checksum. A false split shows up as a duplicate or out-of-order number; a missed split as a gap. Spec 0001 exists because silent acquisition defects went unnoticed for months — this is the cheap guard that prevents a repeat.
- **Rejected alternatives:** trusting the regex and reviewing samples by hand — the CdS defects were invisible to exactly that; logging a warning instead of failing — a warning in a 409-article run is a line nobody reads.
- **Assumption to verify during implementation:** contiguity from `1` held on all 7 sampled articles, but the sample is 7 of 409. If legitimate exceptions exist (a `-bis` comma, an unnumbered preamble), the rule relaxes to "no duplicates and no decreasing step" rather than being dropped.

### AD-4: One `source` value, not a separate pair of tables
`articles` / `article_commas` gain `reg` as a third `source`.
- **Rationale:** the Regolamento has the same shape as the other two — numbered articles, a title, numbered commas, a URL, a repeal flag — so the tables already fit. `UNIQUE (source, number)` keeps it from colliding with the CdS, whose article numbers overlap heavily. A single set of tables also keeps retrieval a single query over the whole corpus, which is what a quiz answer needs: the CdS states the rule and the Regolamento describes the sign.
- **Rejected alternatives:** dedicated `reg_articles` / `reg_article_commas` — isolates a text with a different internal structure, but the structure differs only in *parsing*, not in the stored shape, and it would force every read to union two table pairs; a `law` column on `articles` distinct from `source` — more precise vocabulary, but `source` already means "which legal text", so it would be two names for one concept.

### ~~AD-5: The acquisition tidy-up is Phase 2, after the parsing rules, not alongside them~~

**Historical record, kept for context.** FR-6 and FR-7 were sequenced after FR-1…FR-5 and
after spec 0001, precisely so restructuring the module wouldn't collide with `_parse_article`
being rewritten by spec 0001 and extended by this spec's FR-2/FR-3 at the same time. That
tidy-up is now `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md`; this decision is why it didn't
happen inside this spec. Original rationale/rejected-alternatives text removed with the move
(2026-08-02) — see spec 0004 for the refactor's own current rationale.

### ~~AD-6: Dataclasses inside the scraper; the Pydantic boundary stays in the ingestor~~

**Moved to `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md` AD-1** (2026-08-02), unchanged in
substance.

### ~~AD-7: The scraper CLI is shaped like `ingest` so a later `ingest scrape` is a delegation~~

**Moved to `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md` AD-2** (2026-08-02), unchanged in
substance.

## Data Model

No schema change. `articles.source` and the corresponding model/entity literals accept
`"reg"` in addition to `"cds"` and `"cap"`.

New filesystem artifacts, following the existing conventions:

```
data/raw/reg/toc.html
data/raw/reg/art_0001_1.html … art_0408_1.html     # 409 files
data/parsed/reg/regolamento_attuazione.json        # single file, one record per article
data/cleaned/reg/<element_id>.json                 # one file per article
```

The parsed record shape is the one spec 0001 fixes: `number`, `title`, `url`,
`scraped_at`, `repealed`, and `commas: list[{number, text}]`.

Expected volume, extrapolated from a 7-article sample (2–12 commas each, bodies of
678–5046 characters): order of 2000–2500 commas, comparable to the CdS. Embedding cost at
that size is a fraction of a cent.

## Constraints

- **0001 must be implemented first** — specifically FR-1 (structured comma number), FR-13/FR-14 (`art-just-text-akn`) and the `commas` parsed shape.
- **Politeness delay** — 409 fetches at `DELAY_SECONDS = 1.5`, roughly 10 minutes plus retries. Normattiva returns HTTP 500 as rate limiting and invalidates sessions; the existing retry and session-refresh loop is reused unchanged, not re-tuned.
- **Session invalidation is real and silent** — during the feasibility check, several article fetches returned a valid-looking 200 page with no `article-num-akn` and no body. The existing guard catches it; any new parsing code must not treat such a page as an empty article.
- **No `continue` in loop bodies**, lazy `%s` logging arguments, English docstrings and log messages (`.claude/rules/`).
- **New repeatable operations are registered under `[project.scripts]`.**
- **Schema changes, if any turn out to be needed, go into `db/init.sql`** and are applied by recreating the volume; there is no migration tool.

## Feasibility Evidence

- **AD-1** — supported by: `src/scrapers/normattiva.py:325` — the comma loop iterates `art-comma-div-akn`, of which sampled Regolamento articles have **zero**; every article's text is in `art-just-text-akn`, confirmed by the full 409-article scrape (`data/parsed/reg/regolamento_attuazione.json`, 407 records) (verified 2026-08-02 @ 3cce407)
- **AD-1** — supported by: `docs/superpowers/specs/2026-07-31-article-level-storage-design.md:225` — FR-14 of spec 0001 is what makes `art-just-text-akn` a body container, hence the hard dependency (verified 2026-08-02 @ 3cce407)
- **AD-2** — supported by: `src/scrapers/normattiva.py:326` — the parser reads a comma number from `comma-num-akn`; the Regolamento has no such span, so the number comes from the inline marker instead (verified 2026-08-02 @ 3cce407)
- **AD-2** — supported by: `src/scrapers/normattiva.py:296` (`_build_article_url`) — the live scrape confirms multi-comma inline segmentation is the normal case: 1745 commas across 407 articles, several with 15+ commas (e.g. art. 330: 17) (verified 2026-08-02 @ 3cce407)
- **AD-3** — supported by: `src/scrapers/normattiva.py:220-244` (`_validate_contiguous_numbering`) — implemented as the relaxed rule from the start: base numbers must be contiguous from 1, with a `-bis`/`-ter` suffix tolerated immediately after its base — real articles needed exactly this (art. 9's `1, 2, 3, 3-bis`) (verified 2026-08-02 @ 3cce407)
- **AD-3** — supported by: `src/scrapers/normattiva.py:317` — `re.sub(r"^Art\.\s*", "", numero_raw)` shows the codebase already strips `Art.`-style prefixes with plain regexes (verified 2026-08-02 @ 3cce407)
- **AD-3** — supported by: `src/scrapers/normattiva.py:96` — `_MARKER_FALSE_POSITIVE_PREFIXES` extends the same idea to reject `art.`/`n.`/`fig.` as false-positive comma markers (verified 2026-08-02 @ 3cce407)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/models/knowledge/cleaned_article.py:21` — `source: Literal["cds", "cap", "reg"]`, the single place the source vocabulary is declared on the cleaned model (verified 2026-08-02 @ 3cce407)
- **AD-4** — supported by: `configs/ingestor_config.yaml:13` — the `reg` source entry is `dir` + `file`, the same shape as `cds`/`cap` (verified 2026-08-02 @ 3cce407)
- **FR-1** — supported by: `src/scrapers/normattiva.py:49` — `CDS = LawConfig(...)`, `CAP = LawConfig(...)` (line 55) and `REG = LawConfig(...)` (line 61) are declarative law configurations (verified 2026-08-02 @ 3cce407)
- **FR-1** — supported by: `src/scrapers/normattiva.py:548` — `main_reg` mirrors `main_cds`/`main_cap` (verified 2026-08-02 @ 3cce407)
- **FR-1** — supported by: `src/scrapers/normattiva.py:269` — `if flag != "0": continue` excludes non-article TOC entries; the live scrape found exactly 409 articles numbered 1-408, annexes excluded (verified 2026-08-02 @ 3cce407)
- **FR-1** — supported by: `src/scrapers/normattiva.py:292` — the TOC sort is `int(idArticolo)`; the real scrape confirms 409 entries with no non-numeric identifier (verified 2026-08-02 @ 3cce407)
- **FR-2** — supported by: `src/scrapers/normattiva.py:319` — the title comes from `article-heading-akn`, absent from Regolamento articles (verified 2026-08-02 @ 3cce407)
- **FR-2** — supported by: `src/scrapers/normattiva.py:141-158` — `_split_leading_title` splits the leading parenthesised segment instead, loop-stripping consecutive segments and keeping the last as title (found necessary by the live scrape: some articles carry a cross-reference note before the real title) (verified 2026-08-02 @ 3cce407)
- **FR-2** — supported by: `src/guidami_ai_patente_ingestor/services/knowledge/article_cleaner.py:30` — `_clean_title` already strips wrapping parentheses, so the convention was established before this spec (verified 2026-08-02 @ 3cce407)
- **FR-4** — supported by: `db/init.sql:10` — `source TEXT NOT NULL` with `UNIQUE (source, number)`: a third value needed no DDL change and did not collide with overlapping CdS article numbers (verified 2026-08-02 @ 3cce407)
- **FR-5** — supported by: `docs/superpowers/specs/2026-07-31-article-level-storage-design.md:142` — FR-16 of spec 0001 removes the knowledge LLM step, so `prepare` for a third source is deterministic cleaning with no per-source cost or concurrency concern (verified 2026-08-02 @ 3cce407)

## Open Questions

- [x] **non-blocking** — Is the parenthesised-title and contiguous-inline-comma structure uniform across all 409 articles, or only across the 8 sampled? **Resolved by the full 409-article scrape (2026-08-02):** not fully uniform. 25/407 successfully-parsed articles (6.1%) hit FR-2's empty-title fallback — just over the 5% guardrail this question set — and the AD-3 contiguity rule needed its relaxed form (base-contiguous + tolerated `-bis` suffix) for real, not just as a hedge (art. 9's `1, 2, 3, 3-bis`). 2 articles (art. 83, art. 194) fail to parse even after all fixes and are skipped. Follow-up tracked in `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md`'s Open Questions, since fixing them isn't required for this spec's own acceptance criteria — owner: investigation (resolved)
- [x] **non-blocking** — Does the Regolamento carry repealed articles, and in the same `((ARTICOLO ABROGATO ...))` form spec 0001's FR-13 anchors on? **Resolved by the full scrape:** yes — 4 articles (74, 254, 338, 395) came back `repealed: true` with empty `commas`, exactly matching FR-13's existing rule; no new rule was needed. Separately, comma-*level* repeal uses a different wording (`COMMA SOPPRESSO`, not `COMMA ABROGATO`) not recognised by the existing per-comma check — tracked as a new open question in `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md` — owner: investigation (resolved)
- [ ] **non-blocking** — The Regolamento is amended often. Nothing in the project records *when* a source was scraped at corpus level (`scraped_at` is per record and deliberately not stored in `articles`), so there is no signal that a source has gone stale. Out of scope here, but adding a third source makes it more visible — owner: user
- [ ] **non-blocking** — `(fig. II.48)` references remain unresolved codes in the comma text. Whether they should be stripped, kept verbatim, or one day resolved against the annexes is deferred with the annexes themselves — owner: user

## Sign-off

- **Scope approved by user:** scope agreed 2026-07-31 (articles only, no annexes); spec itself pending review
- **Feasibility asserted:** by review on 2026-07-31, based on Feasibility Evidence above — the TOC, the article markup and the title/comma structure were fetched and measured live against Normattiva, not assumed

## Changelog

- **2026-08-02** — Phase 1 (FR-1…FR-5) implemented and verified against a full live scrape (`data/parsed/reg/regolamento_attuazione.json`, 407/409 articles). Phase 2 (`~~FR-6~~`, `~~FR-7~~`, and their supporting `~~AD-5~~`/`~~AD-6~~`/`~~AD-7~~`) split out into `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md` — unchanged in substance, just relocated now that this spec's own scope (FR-1…FR-5) is complete and Phase 2 no longer needs to share this document. Two Open Questions resolved by the live scrape (title/contiguity uniformity, repealed-article detection); Non-Goals, Constraints and Feasibility Evidence updated to drop Phase-2-only content and refresh stale line-number references (evidence previously anchored at `5790d63`, pre-implementation). Reason: close this spec as `implemented` now that its remaining scope is fully built and verified, without waiting on the unrelated acquisition-layer refactor.

### 2026-08-02 — plan executed: plans/0003-regolamento-attuazione-corpus-phase1-plan.md

- **DoD result:** All items verified mechanically. 13/13 per-task tests pass (`uv run pytest` on each `path::name`); full suite 472 passed; `ruff check`/`ruff format --check`/`pyright` all clean. FR-1 AC1/AC3 verified by a real `uv run scrape-regolamento` run (407/409 articles saved to `data/parsed/reg/regolamento_attuazione.json`); FR-1 AC2/AC4, FR-4 AC3/AC4, FR-5 AC3 verified by inspection/grep exactly as the plan specified. "No `continue` in any modified loop body" holds for T-1…T-4's own additions (zero new `continue` statements) — see Deviations for the one exception found outside those tasks' formal scope.
- **Deviations from plan:**
  1. `main()` was modified outside T-1's explicit "do not touch `main`" note, to add a `try`/`except ValueError`/`else` skip around `_parse_article` — the live scrape crashed on two articles (83, 194) the segmentation heuristic can't parse, and producing the corpus required continuing past them rather than aborting the whole 409-article run. This piece's ownership and DoD accounting are reassigned to `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md` FR-1 AC5 (documents it as implemented ahead of that spec) — not counted as this plan's own deliverable, per explicit user decision.
  2. Files touched beyond the plan's per-task Files lists, accepted as expected companions rather than scope creep: `CLAUDE.md` and `docs/{architecture,database,glossary,layout,testing}.md` (Second Brain / script-table updates required by this repo's own pre-commit policy for any code change); `docs/superpowers/specs/2026-07-31-regolamento-attuazione-corpus-design.md` and `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md` (the spec split requested after implementation); `data/parsed/reg/`, `data/raw/reg/` (generated data output from the real scrape, not source code).
  3. 4 real-world parsing bugs were found and fixed during the live scrape that the plan's synthetic test fixtures could not have anticipated: markers immediately after `))`, mid-body `((N.` amendment brackets (not just at an article's start), `((N.))` with no space before the closing bracket, and duplicate-comma-number de-duplication (AD-3's own pre-authorized relaxed-rule fallback, needed for real). 7 regression tests were added to `tests/scrapers/test_normattiva.py` beyond the plan's original 13, pinning each against a minimal reproduction of the real article that exposed it.
- **Learnings:**
  - A plan's synthetic test fixtures, however carefully derived from a spec's sampled evidence, cannot substitute for running the real acquisition target at full scale: every major parsing-heuristic gap here was found only by the live 409-article scrape, not by the 8-article sample spec 0003 was originally written against. Worth treating "run the real thing once before closing" as a standard step for any spec whose feasibility evidence is sample-based.
  - AD-3's "relaxed rule" fallback (base-contiguous + tolerated `-bis` suffix, instead of strict `1,2,3,...`) was pre-authorized in the spec for exactly this situation and used verbatim once evidence justified it (art. 9) — a spec anticipating its own likely failure mode ahead of time paid off directly.
  - The empty-title rate (25/407, 6.1%) and the 2 permanently-skipped articles are real, measured outcomes just over/near the spec's own guardrails — carried forward as `docs/superpowers/specs/2026-08-02-scraper-acquisition-refactor-design.md` Open Questions rather than gating this close, since fixing them isn't required by FR-1…FR-5's acceptance criteria.
- **Status change:** in-progress → implemented — confirmed by user, 2026-08-02

### 2026-08-06 — review: FR-1 description superseded by spec 0004's completion

A full audit of specs 0001–0006 found this spec's FR-1 acceptance criteria and
Feasibility Evidence describing the scraper's shape as it was *before* spec 0004's
acquisition-layer refactor — a refactor that has itself now landed (see spec 0004's own
2026-08-06 review entry) and rewrote exactly the code FR-1 describes. No code change,
no rewrite of FR-1's text — it remains an accurate historical record of what this spec
built and verified on 2026-08-02. Recorded here per the user's request:

- FR-1's acceptance criteria require registration "under `[project.scripts]` as
  `scrape-regolamento`" and cite `main_reg` mirroring `main_cds`/`main_cap`. Spec 0004
  FR-1 collapsed all three into one `scrape` entry point calling a single `main(law,
  ...)`; `main_cds`/`main_cap`/`main_reg` no longer exist.
- The TOC filter this spec describes as `if flag != "0": continue` is now the positive
  guard `if flag == "0" and key not in seen:` (spec 0004 FR-1's no-`continue` rule).
- Most Feasibility Evidence line-number citations into `src/scrapers/normattiva.py`
  have drifted beyond simple renumbering, because spec 0004 FR-4 decomposed
  `_parse_article` into several named helpers (`_extract_numero_and_titolo`,
  `_build_commi_from_comma_divs`, `_apply_pre_comma_block`, `_detect_article_repeal`,
  `_apply_just_text_akn_body`) to bring it under the `max-complexity = 10` threshold.
- **Learning:** same pattern as specs 0001/0002/0004's review entries in this audit —
  when spec B's implementation rewrites code spec A's Feasibility Evidence cites, spec
  A needs a review pass too, even though nothing in spec A's own scope changed. A
  spec's `implemented` status describes what was true at close, not a standing
  guarantee that its evidence stays accurate through later, unrelated work on the same
  files.
