# Spec 0001: Article-level storage with first-class commas

| | |
|---|---|
| **Id** | 0001 |
| **Status** | draft |
| **Date** | 2026-07-31 |
| **Discussion log** | specs/discussions/article-level-storage.md |
| **Supersedes / superseded by** | — |

## Problem & Motivation

The normative corpus (Codice della Strada + the RCA subset of the Codice delle
Assicurazioni Private) is stored as one row per comma in `knowledge_chunks`. That table
is simultaneously the retrieval index and the serving payload, so every comma duplicates
its article's title, URL and repeal flag, and the comma is forced to be both the unit
searched and the unit returned. A future quiz bot needs the opposite: search at comma
granularity, but hand the LLM the whole article so the explanation reads the norm in
context.

Underneath that modelling problem sits a corpus problem nobody had seen, because the
knowledge pipeline has never run past the `parsed` layer. The scraper silently drops
every comma whose body is a lettered list — 104 of 1893 comma blocks in the CdS, without
a single exception among them. It ingests Normattiva's editorial note markers (`((190))`,
`((45))`) as if they were norms. It extracts the legal comma number from the source HTML
and then destroys it by concatenating it into the text, leaving a positional index that
disagrees with the real comma number in 629 of 1502 numbered blocks. It loses the article
title for 7 articles whose heading Normattiva emits in a different element. Separately,
the per-comma repeal heuristic matches the substring `ABROGAT` anywhere in the body, which
marks Art. 3 of the CdS — the definitions article, 11 277 characters — as repealed and
therefore excludes it from the vector index entirely.

None of this is repairable downstream: a data model cannot reconstruct commas the
acquisition layer never emitted. And the file the pipeline actually consumes for the CAP
source, `codice_rca.json`, has no reproducible provenance — no script in the repository
produces it, so a corrected re-scrape would not even reach it.

## Functional Requirements

### FR-1: The legal comma number is captured as a structured field

The scraper records each comma's legal number (`1`, `4-bis`, `12-ter`) as its own field
rather than concatenating it into the comma text.

**Acceptance criteria:**
- Given a `art-comma-div-akn` containing a `comma-num-akn` span, when the article is parsed, then the comma's number field holds the span's value without the trailing dot and the comma's text field does not begin with that number.
- Given a comma div with no `comma-num-akn` span whose text begins with a number followed by a dot (Normattiva omits the span for amended commas, e.g. `((4-bis. L'utilizzo di un veicolo...`), when the article is parsed, then the number field holds `4-bis`.
- Given CdS art. 142, when the article is parsed, then the parsed comma numbers are exactly the legal numbers present in the source HTML, with no positional renumbering.
- Given an ordinal suffix the implementation does not recognise (the source contains the misspelling `1-quinques` in CAP art. 76), when the article is parsed, then parsing does not raise and the comma is still emitted.

### FR-2: Commas whose body is a list are no longer dropped

A comma div that carries no `art_text_in_comma` span still produces a comma.

**Acceptance criteria:**
- Given CdS art. 142, whose comma 3 has a `comma-num-akn` span but no `art_text_in_comma` span, when the article is parsed, then a comma numbered `3` is emitted with the text `Le seguenti categorie di veicoli non possono superare le velocità sottoindicate: ...`.
- Given CdS art. 85, whose comma 2 has the same shape, when the article is parsed, then a comma numbered `2` is emitted.
- Given the full CdS raw corpus, when every article is parsed, then the number of emitted commas increases by 104 relative to the pre-change parser and no previously emitted comma disappears.

### FR-3: Unnumbered list-item blocks are merged into the comma that introduces them

A comma div that yields no legal number and is not discarded by FR-4 is appended to the
text of the most recent numbered comma.

**Acceptance criteria:**
- Given CdS art. 85, where the divs `a) alla prima violazione...`, `b) alla seconda violazione...`, `c) ...`, `d) ...` follow the comma numbered `4-bis`, when the article is parsed, then no standalone comma is emitted for those four divs and the text of comma `4-bis` contains all four items.
- Given the parsed CdS corpus, when every article is parsed, then no emitted comma's text begins with a bare list marker such as `a)` or `b)`.
- Given an unnumbered block that appears before any numbered comma in an article, when the article is parsed, then parsing does not raise.

### FR-4: Editorial note references and marker-only fragments are discarded

A comma div whose text, after removing the amendment markers `((` and `))`, is empty or
consists only of digits produces no comma.

**Acceptance criteria:**
- Given CdS art. 85, which contains three divs whose entire text is `((190))`, when the article is parsed, then no comma is emitted for them.
- Given a div whose entire text is `((` or `))`, when the article is parsed, then no comma is emitted for it.
- Given the parsed corpus after the change, when the emitted commas are inspected, then none matches the note-reference shape `((NNN))` — down from 9 in `codice_della_strada.json` and 28 in `codice_rca.json`.

### FR-5: A missing article title falls back to the unnumbered pre-comma block

When `article-heading-akn` yields nothing, the `article-pre-comma-text-akn` block is used
as the title, provided it carries no comma number and is not a note reference.

**Acceptance criteria:**
- Given CdS art. 120, whose heading element is absent and whose pre-comma block reads `Requisiti soggettivi per ottenere il rilascio della patente di guida e disposizioni sull'interdizione alla conduzione di velocipedi a pedalata assistita`, when the article is parsed, then the title field holds that text.
- Given CdS art. 205, whose pre-comma block begins `((1. Contro l'ordinanza-ingiunzione...`, when the article is parsed, then the block is emitted as the comma numbered `1` and is not used as the title.
- Given CAP art. 284, whose heading is present and whose pre-comma block is the note reference `((70))`, when the article is parsed, then the title is unchanged and the block produces neither a title nor a comma.
- Given the parsed corpus after the change, when article titles are inspected, then CdS arts. 81, 116-bis, 120, 204-bis, 215-bis and CAP arts. 136, 142-ter all have a non-empty title.

### FR-6: The RCA subset is produced by a versioned, configuration-driven extraction

`codice_rca.json` is generated from `codice_assicurazioni_private.json` by a repeatable
command that filters the article ranges declared in configuration.

**Acceptance criteria:**
- Given `codice_assicurazioni_private.json` and the configured ranges `118-165` and `278-300`, when the extraction runs, then it writes `codice_rca.json` containing exactly 96 articles.
- Given the extraction has run, when its output is compared to the source file, then every emitted article is byte-identical to its counterpart and the source file's ordering is preserved.
- Given the extraction is registered under `[project.scripts]`, when it is invoked a second time on unchanged input, then it produces an identical file.
- Given an article range that matches nothing, when the extraction runs, then it fails loudly rather than writing a partial file.

### FR-7: The corpus is stored as articles plus first-class commas

`knowledge_chunks` is replaced by `articles` and `article_commas`, the latter carrying the
embedding.

**Acceptance criteria:**
- Given an enriched article with N commas, when it is indexed, then exactly one `articles` row and N `article_commas` rows are written, and every comma row references its article by foreign key.
- Given two commas of the same article, when they are inserted with the same `comma_number`, then the database rejects the second.
- Given an article row is deleted, when the deletion commits, then its comma rows are removed with it.
- Given a stored article, when its commas are read back ordered by `position`, then they appear in source-document order, including `1`, `1-bis`, `2` in that sequence.
- Given the schema after the change, when `knowledge_chunks` is queried, then the table does not exist.

### FR-8: Contexts are keyed by the legal comma number and validated

The contextualizer agent receives commas labelled with their legal number and returns a
map keyed by that number; a mismatch fails the run.

**Acceptance criteria:**
- Given an article whose commas are numbered `1`, `4-bis`, `5`, when the agent request is rendered, then the prompt labels each comma with its legal number and the response schema is a map keyed by those strings.
- Given a response whose keys are exactly the numbers sent, when the response is applied, then each context is attached to the comma bearing that number.
- Given a response containing a key that was not sent, or missing a key that was sent, when the response is applied, then the run fails with an error naming the offending article and the mismatched keys.
- Given an article with commas, when it is contextualized, then exactly one LLM call is made for that article.

### FR-9: Per-comma repeal detection is anchored to the repeal formula

A comma is repealed when its article is repealed, or when its text opens with the
repeal formula, rather than when it mentions repeal anywhere.

**Acceptance criteria:**
- Given the comma text `3. COMMA ABROGATO DAL D.LGS. 15 MARZO 2010, N. 66 .`, when repeal is evaluated, then the comma is repealed.
- Given the comma text `4. ((COMMA ABROGATO DAL D.LGS. 21 MAGGIO 2018, N. 68 )) .`, when repeal is evaluated, then the comma is repealed.
- Given CdS art. 3 comma 1 — the definitions comma, which mentions repeal in its body — when repeal is evaluated, then the comma is **not** repealed and receives an embedding.
- Given CdS art. 23 comma 13-ter, whose text opens `13-ter. PERIODO ABROGATO DAL D.LGS. ...` (a repealed sentence, not a repealed comma), when repeal is evaluated, then the comma is **not** repealed.
- Given the CdS corpus, when repeal is evaluated across all commas, then 32 commas are marked repealed, down from 42.

### FR-10: Knowledge indexing writes both tables as a per-source full reload

The indexing flow replaces one source's articles and commas without touching the other's.

**Acceptance criteria:**
- Given `cds` has been indexed, when `cap` is indexed, then the `cds` rows in both tables are unchanged.
- Given `cds` has been indexed, when `cds` is indexed again, then the row counts for `cds` are unchanged and no duplicates exist.
- Given a comma marked repealed and `embed_repealed` is false, when the source is indexed, then the comma row is present with a null embedding.
- Given the embedding input for a comma, when it is built, then it is composed of the article title, the comma's context and the comma's text, omitting empty parts.

### FR-11: The chunk-based components are removed

The components superseded by the new model are deleted from the repository together with
their tests.

**Acceptance criteria:**
- Given the repository after the change, when it is searched, then `ArticleChunker`, `EmbeddableChunkModel`, `KnowledgeChunk`, `KnowledgeChunkStoreRepository` and `StoreChunksStep` are absent, as are their test modules.
- Given the repository after the change, when `uv run ruff check src tests` and `uv run pyright` are run, then both pass with no reference to the removed symbols.
- Given the repository after the change, when `uv run pytest` is run, then the suite passes.

### FR-12: The CLI operates on the new tables

`ingest reset knowledge` and `ingest status --online` target `articles` and
`article_commas`.

**Acceptance criteria:**
- Given a populated database, when `ingest reset knowledge` runs, then both tables are emptied and `quiz_questions` is untouched.
- Given a reachable database, when `ingest status --online` runs, then it reports existence and row count for `articles` and `article_commas` and does not mention `knowledge_chunks`.
- Given an unreachable database, when `ingest status --online` runs, then it exits 0 and reports the database as unreachable.

## Non-Goals

- **Implementing retrieval.** No read path is built here: `guidami_ai_patente/` has not started, and the schema is justified by the retrieval shape agreed in the discussion, not by shipping it.
- **Hybrid search — FTS columns, GIN indexes, RRF.** Deferred with `docs/plans/architecture-hybrid-retrieval.md`, which is marked superseded rather than rewritten, because choosing the FTS column is a retrieval decision that should be made when retrieval is implemented.
- **Vector indexes (ivfflat/HNSW).** The corpus stays small enough for an exact scan; unchanged from today.
- **A separate embeddings table allowing several vectors per comma.** Rejected as premature: changing the schema in this project costs a volume recreation and a full reload from JSON.
- **Resolving Normattiva's editorial notes.** Note references are discarded, not stored for later resolution; the notes themselves are not downloaded.
- **Data migration or backfill.** No knowledge data exists in the database or in the `cleaned`/`enriched` layers.
- **Write-through resumability during a run.** Unchanged from today's cross-run behaviour.

## Architectural Decisions

### AD-1: Retrieval returns the whole article while the matching comma stays identifiable
A vector hit is an `(article, comma)` pair: the article is what would be served, the comma
is what was matched.
- **Rationale:** an explanation must be able to cite the norm at comma level, and the comma identity is what makes an embedding traceable back to what was embedded, for debugging and partial regeneration.
- **Rejected alternatives:** an embedding row keyed only by article — the matched comma becomes unrecoverable, losing both citation and diagnosis; serving only the comma with the article heading — keeps today's serving granularity, which is what this change exists to move past.

### AD-2: The comma is a first-class entity carrying its own embedding
Two tables: `articles` for the article header, `article_commas` for each comma with its
text, context, repeal flag and vector. The whole article is served by a join.
- **Rationale:** the per-comma attributes are not just the vector — text, LLM context and repeal status are all per-comma. Modelling them as parallel arrays indexed by position inside the article row is a half-normalisation the database cannot constrain; one row per comma makes the constraint real.
- **Rejected alternatives:** arrays on `articles` plus a pure index table — one join cheaper, but keeps an unconstrained positional convention and scatters per-comma attributes across parallel structures; three tables with a separate embeddings table — would allow several vectors per comma without touching the data, but is premature here.

### AD-3: The legal comma number is fixed at the source, in the scraper
Rather than deriving a comma number downstream, the acquisition layer stops discarding the
one the source already provides.
- **Rationale:** the number is present in the source HTML and is destroyed by the parser. The same function also loses 337 real commas, a corpus defect no downstream model can repair.
- **Rejected alternatives:** a positional index plus a number parsed downstream from the text marker — re-derives with a regex what the HTML marks explicitly, and does not recover the lost commas; a positional index with article-level citation only — leaves the corpus incomplete.

### AD-4: One spec, two phases
Phase 1 corrects acquisition; Phase 2 introduces the schema and rewrites indexing.
- **Rationale:** both phases touch the same chain of models and mappers, so splitting them means doing the same signatures twice. The risk that normally justifies a split — rollout, production data, backfill — is absent.
- **Rejected alternatives:** two sequential specs — cleaner traceability, but a second pass over the same mappers for no risk reduction; deferring the scraper — would judge retrieval quality on a corpus known to be incomplete.

### AD-5: The contextualizer contract is keyed by the legal comma number
The prompt labels commas with their real number and the response is a map keyed by it.
- **Rationale:** it makes the key semantically checkable — the returned keys can be asserted against the numbers sent. The current positional key cannot be validated against anything and is already misaligned.
- **Rejected alternatives:** one call per comma — misalignment becomes structurally impossible, but multiplies calls roughly thirteenfold while still sending the whole article each time; a positional map with a corrected prompt — minimal, but the key stays an internal index disconnected from citation.

### AD-6: Superseded components are deleted, not kept disconnected
The chunk-based components are removed along with their tests and the old table.
- **Rationale:** keeping them does not buy the optionality they would be kept for — the intended refinement axis adds rows or columns to `article_commas` rather than resurrecting the chunk model. Git history remains the restore path.
- **Rejected alternatives:** leaving them in the repository unwired — linting and type checking still cover them, and their tests either stay green over code nobody runs or are deleted leaving untested code behind; deciding file by file — more precise, but scatters micro-decisions a single rule resolves.

### AD-7: The RCA subset comes from a versioned range extraction
The scraper stays a generic downloader; a separate versioned step produces the subset from
configured ranges.
- **Rationale:** the subset turned out to be a mechanical rule — two contiguous blocks — so it belongs in configuration. Domain selection sits in ingestion configuration, not in the scraper, and the full code remains available.
- **Rejected alternatives:** filtering inside the scraper's table of contents — saves fetches but couples the scraper to a domain selection and destroys the full corpus as an artifact; ingesting the whole code — removes the extraction but injects supervisory and intermediary law irrelevant to the driving exam.

### AD-8: Unnumbered list items merge into the comma that introduces them
A block with no legal number is appended to the preceding numbered comma; the same rule
stops discarding blocks that lack the text wrapper.
- **Rationale:** every dropped comma without exception has a list in its body, so the lost commas and the orphan items are one defect seen from two sides. An isolated list item is not an autonomous norm and does not even state what it qualifies.
- **Rejected alternatives:** separate rows inheriting the number — finer embedding granularity, but blocks a uniqueness constraint on the number and embeds fragments stripped of the sentence that introduces them; parent comma plus prefixed child rows — maximum retrieval coverage, but a two-level model to maintain before knowing it is needed.

### AD-9: Note references and marker-only fragments are discarded
A block that reduces to nothing or to bare digits once amendment markers are removed
produces no comma.
- **Rationale:** they are typographic artifacts of the source, not normative content; today they reach the corpus and would be embedded as if they were norms.
- **Rejected alternatives:** keeping the note number as metadata on the preceding comma — only useful for resolving editorial notes that are not even downloaded.

### AD-10: The hybrid-retrieval plan is marked superseded, not rewritten
The existing plan keeps its content and gains a header noting it is superseded.
- **Rationale:** rewriting it requires choosing which column full-text search runs against, which is a retrieval decision worth making when retrieval is actually built.
- **Rejected alternatives:** rewriting it inside this spec — avoids a second volume recreation, but designs the full-text strategy without having seen vector retrieval work; deleting it — consistent with AD-6, but discards still-valid reasoning about the fusion technique.

### AD-11: Per-comma repeal is anchored to the repeal formula
Repeal is article-level repeal, or a comma whose text opens with the repeal formula.
- **Rationale:** the current substring match produces ten false positives in the CdS, including the definitions article, which would sit in the table with a null embedding and be invisible to retrieval. Merging lists into commas enlarges each comma's text and would make this worse.
- **Rejected alternatives:** article-level flag only — no false positives, but loses commas repealed inside articles still in force, which was the reason the heuristic existed; leaving the heuristic unchanged — no work, but the false positives grow.

### AD-12: The unnumbered pre-comma block is the article title
When the heading element yields nothing, the unnumbered pre-comma block becomes the title;
consequently `articles` has no body column and `comma_number` is not nullable.
- **Rationale:** every unnumbered pre-comma block belongs to an article with an empty title, except one which is a note reference. No genuine normative preamble exists in the corpus, so the case that would justify a nullable comma number never occurs.
- **Rejected alternatives:** leaving it out of scope — seven articles would stay untitled after the re-scrape, and the title is part of every comma's embedding input; keeping it as an article body column — persists a parsing defect instead of correcting it and keeps the comma number nullable with no real case behind it.

## Data Model

### Parsed layer

The article model loses its `text` field: an unnumbered pre-comma block becomes the title
(AD-12) and a numbered one becomes a comma (AD-3). `paragraphs: list[str]` becomes an
ordered list of commas, each with a legal number and its text. `source`, stamped at the
parsed→cleaned boundary, and `contexts`, keyed by comma number (AD-5), carry through the
cleaned and enriched layers as today.

### Database

```sql
CREATE TABLE articles (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT NOT NULL,               -- "cds" | "cap"
    number      TEXT NOT NULL,               -- "142", "116-bis"
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    is_repealed BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (source, number)
);

CREATE TABLE article_commas (
    id           BIGSERIAL PRIMARY KEY,
    article_id   BIGINT NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
    comma_number TEXT NOT NULL,              -- "1", "4-bis"
    position     INT NOT NULL,               -- source-document order
    text         TEXT NOT NULL,
    context      TEXT NOT NULL DEFAULT '',   -- LLM-generated, per comma
    is_repealed  BOOLEAN NOT NULL DEFAULT FALSE,
    embedding    VECTOR(1536),
    UNIQUE (article_id, comma_number)
);

CREATE INDEX idx_article_commas_article_id ON article_commas (article_id);
```

`position` exists because comma numbers do not sort: `1-bis` falls between `1` and `2`
under neither lexical nor numeric ordering, so document order needs its own column.
`UNIQUE (article_id, comma_number)` is safe: under the new parsing rules no CdS article
repeats a comma number.

`knowledge_chunks` is dropped. Migration follows the project's existing mechanism —
`db/init.sql` is the single source of schema truth and only runs on volume creation, so
applying this is `docker compose down -v` followed by `up -d`, then a full re-ingestion.
No backfill is required.

## Constraints

- **No migration tool.** Schema changes go into `db/init.sql` and are applied by recreating the volume; introducing Alembic is out of scope.
- **Definition of Done spans the whole chain:** re-scrape both sources, regenerate the RCA subset, then `ingest prepare` and `ingest index` for `cds` and `cap`.
- **Vector parameters require the explicit `%s::vector` cast** (`.claude/rules/code-conventions.md`).
- **Loop bodies must not use `continue`** — the parsing rules replace the current `continue`-based skip in the scraper (`.claude/rules/code-conventions.md`).
- **Logging uses lazy `%s` arguments, never f-strings** (`.claude/rules/logging.md`).
- **Agent response DTO docstrings and field descriptions stay Italian**, being prompt-facing; request DTOs stay English (`.claude/rules/code-conventions.md`).
- **Entities model the insertable projection**: database-generated columns (`id`) are not declared on write entities (`.claude/rules/code-conventions.md`).
- **Injected dependencies come last** in constructor signatures (`.claude/rules/dependency-injection.md`).
- **New repeatable operations are registered under `[project.scripts]`.**
- **The re-scrape is bounded by Normattiva's politeness delay** — roughly 900 article fetches across both sources.

## Feasibility Evidence

- **AD-1** — supported by: `src/domain/models/knowledge/retrieval_result.py:9` — `RetrievalResult` wraps a single `KnowledgeChunk` and has no caller, confirming no read path exists yet and the retrieval shape is still free to be defined (verified 2026-07-31 @ 9c66eb5)
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/mappers/article_mapper.py:60` — `is_repealed` is computed per chunk, not per article, showing repeal is genuinely a per-comma attribute alongside text and context (verified 2026-07-31 @ 9c66eb5)
- **AD-2** — supported by: `db/init.sql:8` — `knowledge_chunks` repeats `article_title`, `source_url` and `is_repealed` on every comma row under `UNIQUE (source, article_number, comma_index)` (verified 2026-07-31 @ 9c66eb5)
- **AD-3** — supported by: `src/scrapers/normattiva.py:164` — the parser reads the `comma-num-akn` span and then concatenates it into the comma text as a prefix, discarding the structured number (verified 2026-07-31 @ 9c66eb5)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/models/knowledge/enriched_article.py:21` — the enriched model carries `contexts: dict[int, str]`, one of the shared shapes both phases must change, confirming the two phases touch the same chain (verified 2026-07-31 @ 9c66eb5)
- **AD-5** — supported by: `configs/agents/article_contextualizer.yaml:5` — the prompt renders the pre-comma text unlabelled and numbers the paragraph block from 1, while instructing the model to return keys starting at 0 (verified 2026-07-31 @ 9c66eb5)
- **AD-5** — supported by: `src/guidami_ai_patente_ingestor/agents/dto/article_contextualizer/article_contextualizer_request.py:25` — `paragraphs_block` numbers `paragraphs[0]` as `1.`, disagreeing with the chunker's `comma_index` of `1` for the same paragraph (verified 2026-07-31 @ 9c66eb5)
- **AD-6** — supported by: `src/guidami_ai_patente_ingestor/services/knowledge/article_chunker.py:13` — `ArticleChunker` exists solely to expand an article into per-comma chunks, the step the new model removes (verified 2026-07-31 @ 9c66eb5)
- **AD-7** — supported by: `configs/ingestor_config.yaml:12` — the `cap` source points at `codice_rca.json`, which `scrapers/normattiva.py` never writes (verified 2026-07-31 @ 9c66eb5)
- **AD-8** — supported by: `src/scrapers/normattiva.py:166` — the `if not text_span: continue` guard is what drops every comma whose body is a list (verified 2026-07-31 @ 9c66eb5)
- **AD-9** — supported by: `src/scrapers/normattiva.py:162` — the comma loop accepts any div carrying a text span, including the note-reference divs whose whole content is `((190))` (verified 2026-07-31 @ 9c66eb5)
- **AD-10** — supported by: `docs/plans/architecture-hybrid-retrieval.md:96` — the planned fusion query selects payload columns directly from `knowledge_chunks`, so it cannot survive the table's removal unchanged (verified 2026-07-31 @ 9c66eb5)
- **AD-11** — supported by: `src/guidami_ai_patente_ingestor/mappers/article_mapper.py:60` — repeal is `model.repealed or "ABROGAT" in raw_text.upper()`, an unanchored substring match over the whole comma body (verified 2026-07-31 @ 9c66eb5)
- **AD-11** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/embed_chunks_step.py:53` — repealed chunks are excluded from embedding and retain a null vector, which is how a false positive becomes invisible to retrieval (verified 2026-07-31 @ 9c66eb5)
- **AD-12** — supported by: `src/scrapers/normattiva.py:156` — the title comes solely from `article-heading-akn`, with no fallback when that element is absent (verified 2026-07-31 @ 9c66eb5)
- **AD-12** — supported by: `src/scrapers/normattiva.py:159` — the pre-comma block is read into `text`, which is where the missing titles currently end up (verified 2026-07-31 @ 9c66eb5)

## Open Questions

- [ ] **non-blocking** — Should the mismatch between contextualizer keys and sent comma numbers (FR-8) raise a dedicated exception type or a generic error? The behaviour is specified; only the exception taxonomy is open — owner: user
- [ ] **non-blocking** — The CAP drop-rate figures quoted during the discussion (233 of 2780) were measured over the full 610-article code, not the 96 ingested RCA articles. The CdS figure (104 of 1893) is exact. The RCA-specific count should be measured once the corrected scraper runs — owner: investigation
- [ ] **non-blocking** — Nine CdS articles and one CAP article have neither text nor commas and will produce an article row with no comma rows. Whether these should be skipped, or kept as empty shells, was not decided — owner: user

## Sign-off

- **Scope approved by user:** pending
- **Feasibility asserted:** by write-spec on 2026-07-31, based on Feasibility Evidence above
