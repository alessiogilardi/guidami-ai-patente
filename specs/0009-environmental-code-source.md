# Spec 0009: Environmental Code as a Corpus Source

| | |
|---|---|
| **Id** | 0009 |
| **Status** | draft |
| **Date** | 2026-08-05 |
| **Discussion log** | specs/discussions/corpus-missing-sources.md |
| **Supersedes / superseded by** | — |

## Problem & Motivation

The quiz bank asks about waste handling — used engine oil, lead batteries, end-of-life
tyres — under the topic "Limitazione dei consumi; rispetto dell'ambiente; inquinamento".
None of that is in the corpus: a search across all 3992 commas for `olio esaust` returns
zero rows, and the rules live in D.Lgs. 152/2006 (Codice dell'Ambiente), which has never
been scraped. Those questions are currently ungroundable — no retrieval strategy can
surface a text that was never ingested.

This is the one part of the missing-source investigation that needs no new machinery.
Verification against the corpus reclassified almost everything else: the CdS articles on
alcohol, drugs and noise (186, 186-bis, 187, 155) turned out to be **already ingested and
embedded**, so that half of the worst-performing topic is a ranking problem, not a coverage
one; the tread-depth limits live in annexes of D.P.R. 495/1992 whose representation is
still undecided; and clinical, physiological and EU sources were excluded outright because
they have no article/comma structure. D.Lgs. 152/2006 is an ordinary Italian law published
on normattiva, with exactly the shape the existing scraper already handles three times
over.

The law is also far larger than the need: it runs to hundreds of articles across seven
parts, of which only the waste-management provisions are relevant to a driving exam. The
project has already met and solved this shape once, when the Codice delle Assicurazioni was
narrowed to the RCA articles.

## Functional Requirements

### FR-1: Scrape D.Lgs. 152/2006

The Environmental Code becomes a fourth scrapable law, through the existing entry point.

**Acceptance criteria:**
- Given the scraper CLI, when `--source amb` is passed, then D.Lgs. 152/2006 is scraped
  from normattiva into `data/raw/amb/` and `data/parsed/amb/`.
- Given `--source` with no argument, when the CLI shows its choices, then the new source
  appears alongside `cds`, `cap` and `reg` without any of them changing behaviour.
- Given `--dry-run`, when the command is run, then it behaves exactly as the existing
  sources do under that flag.
- Given a completed scrape, when the parsed file is read, then each entry has the same
  shape the other laws produce: `number`, `title`, `commas`, `url`, `scraped_at`,
  `repealed`.

### FR-2: Narrow the law to the relevant articles

Only the provisions that can ground a quiz question are carried forward.

**Acceptance criteria:**
- Given the full parsed law, when the narrowing step runs, then it emits a filtered file
  containing only the articles inside the configured ranges.
- Given the configured ranges, when they are read, then they come from configuration and
  not from code, in the same form the RCA ranges already use.
- Given an article whose number carries a suffix (`177-bis`), when it is matched against a
  range, then it is matched on its leading numeric part, consistently with the existing
  range filter.
- Given the narrowed file, when it is inspected, then it contains the waste provisions
  covering used oil, batteries and end-of-life tyres.

### FR-3: Register the source through the ingestion pipeline

The new source flows through preparation and indexing like any other.

**Acceptance criteria:**
- Given the ingestor configuration, when the new source is registered, then `prepare
  knowledge --source amb` and `index knowledge --source amb` both run without code changes
  to the pipelines.
- Given a completed indexing run, when `articles` is queried, then rows exist with
  `source = 'amb'` and their commas carry embeddings.
- Given `UNIQUE (source, number)`, when the new law's article numbers collide with CdS or
  Regolamento numbers, then no conflict occurs, because `source` disambiguates them.
- Given `ingest status`, when it is run, then the new source is reported alongside the
  existing ones.

### FR-4: The addition is measurable

The corpus change is observable in the retrieval metrics rather than assumed to have
helped.

**Acceptance criteria:**
- Given the spec 0007 harness, when it is run before and after this source is indexed,
  then the coverage figures for the environment topic can be compared across the two runs.
- Given a completed run after indexing, when the corpus is searched, then the concepts that
  returned zero commas before this spec (used engine oil, waste tyres, batteries) return at
  least one.

## Non-Goals

- **Annexes of D.P.R. 495/1992** (tread-depth limits) — category B in the discussion log,
  deferred because how to represent an annex is undecided: its content is largely tables
  and figures, which do not map onto the comma model and may flatten into chunks that
  retrieve badly.
- **Non-normative sources** — IRC/CRI first aid protocols, INAIL and Ministero della Salute
  manuals, ISS physiological tables. Excluded by decision D-1: the corpus model assumes
  legislation, and these have neither articles nor commas.
- **EU legislation** — Regulation 2019/2144, Euro emission directives. Same exclusion:
  different structure and not served by normattiva in the form the scraper expects.
- **Fixing the alcohol/drugs retrieval failure** — that text is already in the corpus.
  It is a ranking problem, addressed by specs 0007 and 0008, and no source will fix it.
- **Changing the article/comma model or the database schema** — this spec adds a value to
  `articles.source`, nothing more.

## Architectural Decisions

### AD-1: A new source is a new `LawConfig`, not new scraper code
- **Rationale:** `LawConfig` carries only `slug`, `toc_url` and `output_name`, and laws are
  dispatched through a single `_SOURCES` dict consulted by the CLI's `--source` choices.
  Adding a law is therefore one dataclass instance and one dict entry; the parsing,
  fetching and output logic is already law-agnostic and was exercised three times. Spec
  0003 added the Regolamento the same way.
- **Rejected alternatives:** A dedicated scraper module for the Environmental Code —
  duplicates law-agnostic logic and breaks the single `scrape --source` entry point
  established by spec 0004.

### AD-2: The law is narrowed by configured article ranges, reusing the RCA pattern
- **Rationale:** D.Lgs. 152/2006 is a multi-part environmental code whose overwhelming
  majority — water, air, soil, environmental assessment — cannot ground a driving-exam
  question. Ingesting it whole would add thousands of irrelevant commas, spend embedding
  budget on them, and enlarge the candidate pool that retrieval must discriminate against,
  which is a direct cost to the metrics specs 0007 and 0008 are trying to improve. The
  project already solved this exact shape for the Codice delle Assicurazioni via
  `IngestorConfig.rca_ranges` and a filter step.
- **Rejected alternatives:** Ingest the whole law — measurable harm to retrieval for no
  benefit. Hardcode the article list in the scraper — the relevant range is a domain
  judgement that will be revised, and belongs in configuration like the RCA one.

### AD-3: The narrowed law is a distinct `source` value, not folded into an existing one
- **Rationale:** `articles` is keyed `UNIQUE (source, number)`, and article numbers collide
  freely across laws — the corpus already contains two different "art. 43", one in the CdS
  and one in the Regolamento, and both surfaced together in a single retrieval probe.
  A separate `source` keeps citations unambiguous, which matters because the eventual quiz
  bot must tell the user *which* law it is quoting.
- **Rejected alternatives:** Appending to `cds` — produces silently wrong citations the
  moment two laws share an article number, which they demonstrably do.

## Data Model

No schema change. `articles.source` gains a fourth value alongside `cds`, `cap` and `reg`;
`articles` and `article_commas` are otherwise untouched, and no migration is required.

New data paths follow the existing convention: `data/raw/<slug>/`, `data/parsed/<slug>/`,
then the standard `cleaned/` layer produced by preparation.

## Constraints

- The scraper must remain a single entry point: no second command, no per-law branch
  outside `_SOURCES`.
- Article ranges live in `configs/ingestor_config.yaml`, not in code, matching `rca_ranges`.
- The narrowed parsed output is committed like the other parsed corpora, as is the enriched
  layer (ADR 0012, superseding ADR 0005).
- Scraping normattiva must respect whatever request pacing the existing scraper already
  applies; this spec introduces no new fetching behaviour.
- The `source` slug must be short and stable, since it appears in directory names, config
  keys, CLI arguments and every stored row.

## Feasibility Evidence

- **AD-1** — supported by: `src/scrapers/normattiva.py:46` — `LawConfig` carries only `slug`, `toc_url` and `output_name`, so a law is pure configuration (verified 2026-08-05 @ 6d96b7d)
- **AD-1** — supported by: `src/scrapers/normattiva.py:672` — `_SOURCES: dict[str, LawConfig] = {"cds": CDS, "cap": CAP, "reg": REG}`, the single registry a new law joins (verified 2026-08-05 @ 6d96b7d)
- **AD-1** — supported by: `src/scrapers/normattiva.py:679` — `--source` derives its choices from `sorted(_SOURCES)`, so the CLI surface updates itself (verified 2026-08-05 @ 6d96b7d)
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/configs/ingestor_config.py:71` — `rca_ranges: list[str]` with default `["118-165", "278-300"]`, the configured-range precedent this reuses (verified 2026-08-06 @ 91c4fe7)
- **AD-2** — supported by: `configs/ingestor_config.yaml:12` — the `cap` source points at `codice_rca.json`, the narrowed output rather than the full law, showing the pattern end to end (verified 2026-08-06 @ 91c4fe7)
- **AD-3** — supported by: `db/init.sql:16` — `UNIQUE (source, number)` on `articles`, which makes a distinct source value sufficient to prevent collisions (verified 2026-08-06 @ 91c4fe7)
- **AD-3** — supported by: `configs/ingestor_config.yaml:23` — `knowledge_preparation.sources: [cds, cap, reg]`, the list the new slug joins (verified 2026-08-06 @ 91c4fe7)
- **FR-3 scope clarification** — supported by: `src/guidami_ai_patente_ingestor/models/knowledge/cleaned_article.py:22`, `src/guidami_ai_patente_ingestor/mappers/article_mapper.py:20`, `src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py:207` — each hardcodes `Literal["cds", "cap", "reg"]` for `source`; each needs `"amb"` added. This is a mechanical typing update (widening an enum of valid values), not new branching pipeline logic, so it doesn't contradict AD-1/AD-3's "no per-law branch" intent, but FR-3's acceptance criteria should be read as "no new pipeline *logic*", not "zero-diff outside config" (verified 2026-08-06 @ aafedf8)

## Open Questions

- [x] **blocking** — Which article ranges of D.Lgs. 152/2006 are in scope? Resolved
  2026-08-06: Parte Quarta, **Titolo III — "Gestione di particolari categorie di
  rifiuti" (artt. 227-237)**. Verified against Brocardi's article-by-article index of
  the Codice dell'Ambiente: art. 228 is *Pneumatici fuori uso* (end-of-life tyres),
  art. 236 is *Consorzio nazionale... oli minerali usati* (used mineral oils), art. 227
  covers *rifiuti di pile e accumulatori* (battery waste; the dedicated lead-battery
  consortium article, 235, is abrogated but stays in-range as a repealed record, same
  handling as any other repealed article in the existing corpus). A single range,
  `["227-237"]`, covers all three concepts named in the Problem & Motivation section.
  — owner: user, resolved by research
- [x] **non-blocking** — What slug? Resolved: `amb`, keeping the 3-letter convention
  shared with `cds`/`cap`/`reg`. — owner: user, resolved by research
- [x] **non-blocking** — Should the narrowing be a separate script like
  `scrapers/rca_extract.py`, or a flag on the scrape itself? Resolved: a separate
  script, `scrapers/amb_extract.py`, mirroring `rca_extract.py`'s shape exactly
  (same CLI-detachment "wart" as the RCA precedent — not fixed here, since fixing it
  is a cross-cutting change to an existing script, out of scope for a spec that adds
  one source). To avoid duplicating the range-filtering algorithm across two nearly
  identical files, the filtering logic itself (`extract_rca`'s body) is lifted into a
  shared function both scripts call; each keeps its own thin `main()` (paths + config
  field) and its own `[project.scripts]` entry, matching the existing precedent of one
  entry point per operation. — owner: user, resolved by research

## Sign-off

- **Scope approved by user:** pending
- **Feasibility asserted:** by write-spec on 2026-08-05, based on Feasibility Evidence above

## Changelog

- **2026-08-06** — All three Open Questions resolved (article ranges = Titolo III,
  artt. 227-237, verified against Brocardi's article index; slug = `amb`; narrowing
  script = `scrapers/amb_extract.py`, sharing its filtering core with
  `rca_extract.py`). Added a Feasibility Evidence entry noting that FR-3's "no code
  changes to the pipelines" claim needs a narrow reading: three `Literal["cds",
  "cap", "reg"]` typing sites (`cleaned_article.py`, `article_mapper.py`,
  `knowledge_flows.py`) do need `"amb"` added — a mechanical enum widening, not new
  branching logic. No requirement or decision is otherwise affected.
- **2026-08-06** — Evidence anchors refreshed to `91c4fe7`. `rca_ranges` moved from
  `ingestor_config.py:69` to `:71` (the file gained `quiz_question_embeddings_table`
  above it), and the `codice_rca.json` reference now points at the `file:` line itself
  (`configs/ingestor_config.yaml:12`) rather than the `cap:` block header. The `db/init.sql`
  and `knowledge_preparation.sources` claims were re-read and hold unchanged. Mechanical
  drift only — no requirement or decision is affected, so the status is unchanged.
- **2026-08-06** — Mechanical drift refresh, status unchanged. A Constraint stated that
  the enriched layer "stays gitignored (ADR 0005)"; it has been committed since
  2026-08-05 and ADR 0005 is now superseded by ADR 0012. The constraint now says the
  enriched layer is committed like the parsed output. No requirement or decision is
  affected — this spec adds a source, it does not choose version-control policy.
