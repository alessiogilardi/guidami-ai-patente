# Spec 0003: Regolamento di attuazione (DPR 495/1992) in the corpus

| | |
|---|---|
| **Id** | 0003 |
| **Status** | draft |
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
in the per-run log files every `ingest` command writes.

## Functional Requirements

Two phases. **Phase 1** (FR-1…FR-5) ingests the Regolamento. **Phase 2** (FR-6, FR-7)
tidies the acquisition layer now that it has three sources. The order is not arbitrary —
see AD-5.

### Phase 1 — Ingest the Regolamento

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

### Phase 2 — Tidy the acquisition layer

### FR-6: One scraper command with `--source`, replacing the per-law entry points

The three entry points collapse into a single CLI whose shape mirrors `ingest`, so that
delegating to it from `ingest scrape` later is a thin call rather than a rewrite.

**Acceptance criteria:**
- Given `pyproject.toml` after the change, when `[project.scripts]` is read, then `scrape-codice` and `scrape-cap` are gone and a single `scrape` entry point is registered.
- Given `scrape --source cds`, `--source cap` and `--source reg`, when each runs, then it scrapes the corresponding law; given an unknown source, then it exits non-zero listing the valid ones, without opening a connection.
- Given `scrape --source reg --dry-run`, when it runs, then it prints what it would fetch and where it would write, and performs **no** HTTP request and no filesystem write — the same guarantee `ingest --dry-run` gives.
- Given a real run, when it completes, then progress and diagnostics go through `logging` at purposeful levels (per-article at `debug`, per-source milestones at `info`, a skipped article or a session refresh at `warning`) with lazy `%s` arguments, and the run is captured in a per-run log file as `ingest` commands are.
- Given `main`, when it is read, then the `continue`-based skips are replaced by positive guards, per `.claude/rules/code-conventions.md`.

### FR-7: The scraper's data structures are dataclasses, not `TypedDict`s

`LawConfig`, `ArticleParams` and the article/comma records become dataclasses.

**Acceptance criteria:**
- Given the scraper module after the change, when it is read, then `LawConfig`, `ArticleParams` and the article record are `@dataclass` declarations and no `TypedDict` remains.
- Given a law configuration, when it is constructed with a missing or misspelled field, then it fails at construction rather than silently producing a wrong URL — the failure mode a `TypedDict` cannot give.
- Given the record dataclass, when the parsed JSON is written, then its shape is unchanged from Phase 1: the same keys, including `commas: list[{number, text}]`.
- Given `ParsedArticleModel`, when it loads that JSON, then validation still happens there: the scraper stays unvalidated-but-typed, and the Pydantic boundary is the ingestor's, unmoved.

## Non-Goals

- **The annexes.** The four annex entries (figures `II.*`, tables `II.1`–`II.15`) are not scraped, so a reference like `(fig. II.48)` stays an unresolved code in the comma text. Their structure — figures and tables rather than prose — is a second parsing problem, and what Normattiva actually serves as text for them has not been verified. Deliberately deferred: the sign *descriptions* are in the articles, which is what the quiz tests.
- **Bridging quiz image → sign description.** The quiz shows a picture; the corpus names the sign in words. Connecting them is a read-path problem, and the quiz side already carries a road-sign description enricher plus `core_concepts` / `exact_keywords` / `rule_explanation`. Nothing here builds that link.
- **Retrieval, hybrid search, vector indexes.** Unchanged from spec 0001: no read path is built.
- **Restricting to the signage articles only.** All 409 are ingested. Range-filtering (the FR-6 technique of spec 0001) would cut fetches and noise, but the quiz also covers vehicles, licences and inspections, which the Regolamento details elsewhere; and the ranges are not known.
- **Re-verifying the CdS/CAP corpus.** This spec adds a source; it does not revisit spec 0001's findings.
- **Moving the scraper into the ingestor.** It stays in `src/scrapers/`, which is what `docs/layout.md:115` prescribes for data-acquisition scripts — so Phase 2 needs no ADR and no `docs/` restructuring. FR-6 only makes the CLI shape match `ingest`, which is the seam that makes an eventual `ingest scrape` a delegation instead of a port.
- **Tests for the scraper, and lifting its `C901` exemption.** `src/scrapers/**` has no tests (`docs/testing.md:44`) and is exempt from cyclomatic-complexity checks as a script entry point (`docs/testing.md:25`); Phase 2 changes neither. The trade-off is named rather than hidden: the parsing logic is exactly where spec 0001 found seven silent defects, and it stays untested. Left out because testing it is a reclassification from script to production code — a decision with its own cascade — not a side effect of renaming a CLI. Tracked as an open question.
- **Bringing `src/parsers/` along.** `parsers/questions_pdf.py` is in the same condition (script, `C901`-exempt, one unit test). Phase 2 touches only the scraper, so the two acquisition modules end up on slightly different footings. Deliberate, and tracked as an open question.

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

### AD-5: The acquisition tidy-up is Phase 2, after the parsing rules, not alongside them
FR-6 and FR-7 are sequenced after FR-1…FR-5 and after spec 0001.
- **Rationale:** spec 0001 rewrites `_parse_article` almost entirely (structured comma numbers, list-body commas, note discarding, title fallback, two repeal rules, a fourth body container) and this spec's FR-2/FR-3 add two more rules to the same function. Restructuring the module while its central function is being rewritten means writing the same code twice and resolving the collision by hand. Sequencing costs nothing: the tidy-up is not a prerequisite for anything in Phase 1 — the third `LawConfig` constant and entry point of FR-1 are two lines under the existing pattern.
- **Rejected alternatives:** doing the refactor first, so the Regolamento is added to an already-clean module — appealing, but it means restructuring code that spec 0001 is about to rewrite, i.e. the same double work in the other order; interleaving them as one change — fewest passes over the file in theory, but it merges a behavioural rewrite with a structural one, so a regression cannot be attributed to either.
- **Consequence:** Phase 1 adds `REG` as a third hardcoded constant and a third entry point, which FR-6 then removes. That duplication is accepted deliberately and is two lines wide.

### AD-6: Dataclasses inside the scraper; the Pydantic boundary stays in the ingestor
The scraper's structures become dataclasses rather than Pydantic models.
- **Rationale:** the scraper's job is to shape HTML into JSON, and it has no untrusted input to validate — its input is HTML it parses itself and its output is validated one layer down, where `ParsedArticleModel` already loads that JSON. Dataclasses give what `TypedDict` fails to give (a real runtime type, construction-time failure on a wrong field, defaults, `__repr__`) without pulling a validation framework into a module that is deliberately kept light. The global standard permits either: "prefer `dataclasses` or Pydantic over raw dicts". Placing the single validation boundary at the ingestor's edge rather than duplicating it in the scraper keeps one place where a malformed record is rejected.
- **Rejected alternatives:** Pydantic models in the scraper — validation at the point of production catches a bad record earlier, but duplicates the boundary `ParsedArticleModel` already is and makes the scraper heavier for a module with no external input; keeping `TypedDict` and only changing the CLI — smallest diff, but a `TypedDict` is erased at runtime, so a misspelled `LawConfig` field yields a silently wrong URL instead of an error, which is precisely the class of silent defect this pair of specs exists to remove.

### AD-7: The scraper CLI is shaped like `ingest` so a later `ingest scrape` is a delegation
`--source`, `--dry-run`, logging levels and the per-run log file follow the `ingest`
conventions even though the command stays separate.
- **Rationale:** the requested integration is "for the future", so the cheapest thing that buys it is convention rather than code: if the two CLIs already agree on flags, output discipline and dry-run semantics, then adding `ingest scrape` later is a subparser that calls a function, with no behavioural surface left to reconcile. It also pays off immediately — a scrape currently vanishes from the logs while every `ingest` command is captured in `logs/ingest_<command>_<ts>/run.log`.
- **Rejected alternatives:** adding `ingest scrape` now — one CLI instead of two, but it makes the ingestor depend on `src/scrapers/` and puts the network-facing step behind a command whose `--dry-run` contract currently promises no I/O of any kind; leaving three entry points and only fixing the dataclasses — half the ergonomic problem, and the third source is exactly what made it visible.

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
- **Phase 2 needs no ADR and no `docs/` restructuring.** The scraper stays in `src/scrapers/` with a `[project.scripts]` entry, which is exactly what `docs/layout.md:115` prescribes; only the CLI shape and the data structures change. `docs/architecture.md:52` and the `ingest`/`scrape` command table in `CLAUDE.md` need updating for the renamed entry point, nothing more.
- **Phase 2 must not change the parsed JSON shape.** It is a contract fixed by spec 0001 and consumed by `ParsedArticleModel`; FR-7 swaps the producing type, not the produced keys.
- **Schema changes, if any turn out to be needed, go into `db/init.sql`** and are applied by recreating the volume; there is no migration tool.

## Feasibility Evidence

- **AD-1** — supported by: `src/scrapers/normattiva.py:163` — the comma loop iterates `art-comma-div-akn`, of which the sampled Regolamento articles have **zero**; every article's text is in `art-just-text-akn`, so the current parser produces 409 empty records (verified 2026-07-31 @ 5790d63)
- **AD-1** — supported by: `specs/0001-article-level-storage.md:225` — FR-14 of spec 0001 is what makes `art-just-text-akn` a body container, hence the hard dependency (verified 2026-07-31 @ 5790d63)
- **AD-2** — supported by: `src/scrapers/normattiva.py:164` — the parser already reads a comma number from `comma-num-akn`; the Regolamento has no such span, so the number must come from the inline marker, which is 0001 FR-1's second acceptance criterion applied to a whole block instead of one div (verified 2026-07-31 @ 5790d63)
- **AD-2** — supported by: sampling arts. 2, 79, 116, 117, 122, 142, 230 and 360 through `src/scrapers/normattiva.py:133` (`_build_article_url`) — all 8 carry their whole body in `art-just-text-akn` with 2 to 12 inline comma markers and no comma div, so multi-comma segmentation is the normal case, not an exception (verified 2026-07-31 @ 5790d63)
- **AD-3** — supported by: the same sample via `src/scrapers/normattiva.py:133` — inline markers ran contiguously from `1` in all 7 articles that carried them (`1..3`, `1..10`, `1..2`, `1..12`, `1..4`, `1..5`), giving a checksum the CdS numbering cannot provide (verified 2026-07-31 @ 5790d63)
- **AD-3** — supported by: `src/scrapers/normattiva.py:154` — `re.sub(r"^Art\.\s*", "", numero_raw)` shows the codebase already strips `Art.`-style prefixes with plain regexes, and the Regolamento text contains `art. 2.`, `n. 495.` and `fig. II.48`, which a naive marker regex would split on (verified 2026-07-31 @ 5790d63)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/models/knowledge/cleaned_article.py:20` — `source: Literal["cds", "cap"]` is the single place the source vocabulary is declared on the cleaned model, so adding a third value is a literal widening, not a structural change (verified 2026-07-31 @ 5790d63)
- **AD-4** — supported by: `configs/ingestor_config.yaml:10` — the `cap` source entry is `dir` + `file`, the exact shape a `reg` entry needs (verified 2026-07-31 @ 5790d63)
- **FR-1** — supported by: `src/scrapers/normattiva.py:46` — `CDS = LawConfig(...)` and `CAP = LawConfig(...)` are declarative law configurations, so a third is an added constant plus an entry point, mirroring `main_cds` / `main_cap` at `src/scrapers/normattiva.py:288` (verified 2026-07-31 @ 5790d63)
- **FR-1** — supported by: `src/scrapers/normattiva.py:104` — `if flag != "0": continue` already excludes non-article TOC entries; the Regolamento TOC contains exactly four such entries (`flagTipoArticolo` 1–4), which are its annexes (verified 2026-07-31 @ 5790d63)
- **FR-1** — supported by: `src/scrapers/normattiva.py:129` — the TOC sort is `int(idArticolo)`, and the Regolamento TOC parses to 409 entries running 1 to 408 with no non-numeric identifier (verified 2026-07-31 @ 5790d63)
- **FR-2** — supported by: `src/scrapers/normattiva.py:157` — the title comes from `article-heading-akn`, which is absent from every sampled Regolamento article; the title is instead the leading parenthesised segment of the body, present in 7 of 7 sampled articles (verified 2026-07-31 @ 5790d63)
- **FR-2** — supported by: `src/guidami_ai_patente_ingestor/services/knowledge/article_cleaner.py:27` — `_clean_title` already strips wrapping parentheses, so the convention is established; what is new is *splitting* the title off the body rather than unwrapping an already-separate field (verified 2026-07-31 @ 5790d63)
- **FR-4** — supported by: `db/init.sql:10` — `source TEXT NOT NULL` with `UNIQUE (source, article_number, comma_index)` in today's table, carried into spec 0001's `UNIQUE (source, number)`: a third value needs no DDL change and cannot collide with overlapping CdS article numbers (verified 2026-07-31 @ 5790d63)
- **FR-5** — supported by: `specs/0001-article-level-storage.md:142` — FR-16 of spec 0001 removes the knowledge LLM step, so `prepare` for a third source is deterministic cleaning with no per-source cost or concurrency concern (verified 2026-07-31 @ 5790d63)
- **AD-5** — supported by: `src/scrapers/normattiva.py:148` — `_parse_article` is the single function that spec 0001 rewrites across FR-1, FR-2, FR-3, FR-4, FR-5, FR-13 and FR-14 and that this spec extends with FR-2 and FR-3, so restructuring the module around it concurrently would collide with a behavioural rewrite in progress (verified 2026-07-31 @ 5790d63)
- **AD-5** — supported by: `src/scrapers/normattiva.py:46` — `CDS = LawConfig(...)` shows adding `REG` under the existing pattern is a two-line change, so Phase 1 does not need Phase 2 first (verified 2026-07-31 @ 5790d63)
- **AD-6** — supported by: `src/scrapers/normattiva.py:38` — `class LawConfig(TypedDict)` is erased at runtime, so a misspelled or missing key produces a silently wrong article URL instead of a construction error (verified 2026-07-31 @ 5790d63)
- **AD-6** — supported by: `src/scrapers/normattiva.py:73` — `class ArticleRecord(TypedDict)` is the shape written to the parsed JSON, the artifact spec 0001 promotes to a contract; a dataclass preserves that shape while giving it a real runtime type (verified 2026-07-31 @ 5790d63)
- **AD-6** — supported by: `src/guidami_ai_patente_ingestor/models/knowledge/parsed_article.py:4` — `ParsedArticleModel` is a Pydantic model loading exactly that JSON, so the validation boundary already exists one layer down and does not need duplicating in the scraper (verified 2026-07-31 @ 5790d63)
- **AD-7** — supported by: `src/guidami_ai_patente_ingestor/cli/parser.py:49` — `build_parser(config)` derives `--source` choices from config and attaches `--dry-run` per leaf subparser: the conventions FR-6 mirrors, and the insertion point a future `ingest scrape` would use (verified 2026-07-31 @ 5790d63)
- **AD-7** — supported by: `src/scrapers/normattiva.py:288` — `main_cds` is one entry point per law, the pattern a third source turns from coincidence into shape (verified 2026-07-31 @ 5790d63)
- **FR-6** — supported by: `pyproject.toml:27` — `scrape-codice` and `scrape-cap` are two separate `[project.scripts]` entries for what is one operation parameterised by law (verified 2026-07-31 @ 5790d63)
- **FR-6** — supported by: `src/scrapers/normattiva.py:258` — a bare `continue` skips a failed fetch, violating `.claude/rules/code-conventions.md`; the same file's other `continue` uses are already covered by spec 0001 (verified 2026-07-31 @ 5790d63)
- **FR-7** — supported by: `src/scrapers/normattiva.py:59` — `class ArticleParams(TypedDict)` carries the nine query parameters that build every article URL, the structure whose silent mistyping is hardest to notice (verified 2026-07-31 @ 5790d63)

## Open Questions

- [ ] **blocking** — Is the parenthesised-title and contiguous-inline-comma structure uniform across all 409 articles, or only across the 8 sampled? The sample was unanimous, but a full pass over `data/raw/reg/` after the scrape is what settles FR-2 and FR-3 — owner: investigation (resolved by running the scrape, which is the first implementation task)
- [ ] **non-blocking** — Does the Regolamento carry repealed articles, and in the same `((ARTICOLO ABROGATO ...))` form spec 0001's FR-13 anchors on? Not observed in the sample; the article-level flag rule is inherited as-is until measured — owner: investigation
- [ ] **non-blocking** — The Regolamento is amended often. Nothing in the project records *when* a source was scraped at corpus level (`scraped_at` is per record and deliberately not stored in `articles`), so there is no signal that a source has gone stale. Out of scope here, but adding a third source makes it more visible — owner: user
- [ ] **non-blocking** — Should Phase 2 also bring `src/scrapers/` under test and lift its `C901` exemption? It is currently untested by design as a script (`docs/testing.md:25`, `docs/testing.md:44`), yet it is where spec 0001 found seven silent defects. Deliberately excluded from FR-6/FR-7 because it is a reclassification from script to production code, not a CLI change — owner: user
- [ ] **non-blocking** — Should `src/parsers/questions_pdf.py` get the same treatment as FR-6/FR-7? Otherwise the two acquisition modules sit on different footings after Phase 2 — owner: user
- [ ] **non-blocking** — `(fig. II.48)` references remain unresolved codes in the comma text. Whether they should be stripped, kept verbatim, or one day resolved against the annexes is deferred with the annexes themselves — owner: user

## Sign-off

- **Scope approved by user:** scope agreed 2026-07-31 (articles only, no annexes); spec itself pending review
- **Feasibility asserted:** by review on 2026-07-31, based on Feasibility Evidence above — the TOC, the article markup and the title/comma structure were fetched and measured live against Normattiva, not assumed
