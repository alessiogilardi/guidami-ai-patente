# Spec 0001: Article-level storage with first-class commas

| | |
|---|---|
| **Id** | 0001 |
| **Status** | implemented |
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
a single exception among them. It never reads a fourth body container,
`art-just-text-akn`, so four CdS articles and one CAP article lose their entire content —
including CdS art. 216, 2861 characters of norm in force. It ingests Normattiva's
editorial note markers (`((190))`, `((45))`) as if they were norms. It extracts the legal
comma number from the source HTML and then destroys it by concatenating it into the text,
leaving a positional index that disagrees with the real comma number in 629 of 1502
numbered blocks. It loses the article title for 7 articles whose heading Normattiva emits
in a different element.

Repeal detection is broken at **both** levels, and the article level is the dominant
defect. `repealed` is `bool(soup.find(class_="abrogato")) or "abrogato" in html.lower()`:
the class never appears in the corpus (0 of 266 CdS pages), so only the substring match
survives, and it fires on any page whose editorial notes say `NUMERO ABROGATO` or
`PERIODO ABROGATO`. It flags 29 of 266 CdS articles and 4 of 96 CAP articles as repealed,
among them arts. 2, 3 and 5 — the classification, definitions and general-circulation
articles. Because the per-comma rule inherits that flag, 268 of the 271 CdS blocks it
marks repealed are false positives from the article level, and with `embed_repealed=false`
each of them lands in the table with a null embedding, invisible to retrieval. The
per-comma substring match (`ABROGAT` anywhere in the body) adds three more. Meanwhile the
three articles genuinely repealed — CdS 34-bis, 127 and 130-bis, whose bodies are the
formula `((ARTICOLO ABROGATO DALLA ...))` — are flagged **not** repealed, because that
formula lives in the container the scraper never reads.

None of this is repairable downstream: a data model cannot reconstruct commas the
acquisition layer never emitted. And the file the pipeline actually consumes for the CAP
source, `codice_rca.json`, has no reproducible provenance — no script in the repository
produces it, so a corrected re-scrape would not even reach it.

## Functional Requirements

### FR-1: The legal comma number is captured as a structured field

The scraper records each comma's legal number (`1`, `4-bis`, `12-ter`) as its own field
rather than concatenating it into the comma text. The number is recognised by shape —
digits optionally followed by `-` and a word — never by a whitelist of Latin ordinals.

**Acceptance criteria:**
- Given a `art-comma-div-akn` containing a `comma-num-akn` span, when the article is parsed, then the comma's number field holds the span's value without the trailing dot and the comma's text field does not begin with that number.
- Given a comma div with no `comma-num-akn` span whose text begins with a number followed by a dot (Normattiva omits the span for amended commas, e.g. `((4-bis. L'utilizzo di un veicolo...`), when the article is parsed, then the number field holds `4-bis` and the text field does not begin with `4-bis.`.
- Given CdS art. 142, when the article is parsed, then the parsed comma numbers are exactly the legal numbers present in the source HTML, with no positional renumbering.
- Given the source misspelling `((1-quinques.` (CAP art. 76), when the article is parsed, then the number field holds `1-quinques` verbatim: no ordinal is validated against a known-suffix list, so no unrecognised suffix can be raised on or dropped.

### FR-2: Commas whose body is a list are no longer dropped

A comma div that carries no `art_text_in_comma` span still produces a comma, its text read
from the div itself.

**Acceptance criteria:**
- Given CdS art. 142, whose comma 3 has a `comma-num-akn` span but no `art_text_in_comma` span, when the article is parsed, then a comma numbered `3` is emitted with the text `Le seguenti categorie di veicoli non possono superare le velocità sottoindicate: ...`.
- Given CdS art. 85, whose comma 2 has the same shape, when the article is parsed, then a comma numbered `2` is emitted.
- Given CdS arts. 47, 48, 151 and 225 — which today parse to zero commas because every one of their comma divs lacks the text span — when they are parsed, then each emits at least one comma.
- Given the full CdS raw corpus, when every article is parsed, then the number of emitted commas increases by 104 relative to the pre-change parser and no previously emitted comma disappears.

### FR-3: Unnumbered list-item blocks are merged into the comma that introduces them

A comma div that yields no legal number and is not discarded by FR-4 is appended to the
text of the most recent numbered comma. With no such comma the block is discarded and the
loss is logged.

**Acceptance criteria:**
- Given CdS art. 85, where the divs `a) alla prima violazione...`, `b) alla seconda violazione...`, `c) ...`, `d) ...` follow the comma numbered `4-bis`, when the article is parsed, then no standalone comma is emitted for those four divs and the text of comma `4-bis` contains all four items.
- Given the parsed CdS corpus, when every article is parsed, then no emitted comma's text begins with a bare list marker such as `a)` or `b)`.
- Given an unnumbered block that appears before any numbered comma in an article, when the article is parsed, then parsing does not raise, no comma is emitted for it, and a `warning` records the article number and a truncated preview of the discarded text.

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
- Given the parsed corpus after the change, when article titles are inspected, then CdS arts. 81, 116-bis, 120, 204-bis, 215-bis and CAP arts. 136, 142-ter all have a non-empty title, and the only remaining empty titles are CdS 34-bis, 127 and 130-bis — the three repealed articles, whose pages carry no heading at all.

### FR-6: The RCA subset is produced by a versioned, configuration-driven extraction

`codice_rca.json` is generated from `codice_assicurazioni_private.json` by a repeatable
command that filters the article ranges declared in configuration. A range matches an
article on the **leading numeric part** of its number, so suffixed articles inside the
range are included.

**Acceptance criteria:**
- Given `codice_assicurazioni_private.json` and the configured ranges `118-165` and `278-300`, when the extraction runs, then it writes `codice_rca.json` containing exactly 96 articles — 72 from the first range, 24 from the second.
- Given article `119-bis`, when the range `118-165` is applied, then it is selected: matching is on the leading numeric part, not on string equality.
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
- Given CdS arts. 34-bis, 127 and 130-bis — repealed, no commas, no title — when the source is indexed, then each produces one `articles` row with `is_repealed = TRUE`, an empty-string `title` and zero `article_commas` rows (`title` is `NOT NULL`, which does not mean non-empty).
- Given the schema after the change, when `knowledge_chunks` is queried, then the table does not exist.

### ~~FR-8: Contexts are keyed by the legal comma number and validated~~

**Removed.** Article context enrichment is dropped entirely rather than fixed — see
**FR-16** and **AD-18**. The requirement existed to make the contextualizer's key
semantically checkable; with no contextualizer there is no key to check.

### FR-16: Article context enrichment is removed

The LLM contextualization of corpus articles is deleted, not merely excluded from the
embedding input. It was a sketch, never executed past the `parsed` layer, and nothing
consumes its output.

**Acceptance criteria:**
- Given the repository after the change, when it is searched, then `ContextEnricher`, `ArticleContextualizerAgent`, `ArticleContextualizerRequest`, `ArticleContextualizerResponse`, `ArticleContextualizerMapper`, `configs/agents/article_contextualizer.yaml` and the `article_contextualizer_concurrency` config key are absent, as are their test modules.
- Given the repository after the change, when the knowledge model chain is inspected, then `EnrichedArticleModel` and `ArticleMapper.from_cleaned_to_enriched` are absent: the chain is `ParsedArticleModel → CleanedArticleModel → entity`.
- Given `article_commas`, when its columns are inspected, then there is no `context` column.
- Given `ingest prepare knowledge`, when it runs, then it performs cleaning only, writes **one JSON file per article** into the `cleaned` layer under the existing deterministic `element_id(source, number)` name, and makes no LLM call.
- Given `knowledge_indexing`, when its configuration is read, then `input_layer` is `cleaned` and no `enriched` layer is configured for knowledge; the quiz pipeline's `enriched` layer is untouched.
- Given a re-run of `ingest prepare knowledge` without `--force`, when it runs, then articles whose `cleaned` file already exists are still skipped: the per-element resumability plumbing is retained even though cleaning is now cheap.

### FR-9: Per-comma repeal detection is anchored to the repeal formula

A comma is repealed when its article is repealed (per FR-13), or when its text — after
FR-1 has removed the leading comma number and after leading `((` markers and whitespace
are stripped — begins with `COMMA ABROGATO`.

**Acceptance criteria:**
- Given the parsed comma text `COMMA ABROGATO DAL D.LGS. 15 MARZO 2010, N. 66 .` (number `3` held in its own field), when repeal is evaluated, then the comma is repealed.
- Given the parsed comma text `((COMMA ABROGATO DAL D.LGS. 21 MAGGIO 2018, N. 68 )) .` (number `4`), when repeal is evaluated, then the comma is repealed: leading markers are stripped before the prefix test.
- Given CdS art. 3 comma 1 — the definitions comma, which mentions repeal in its body and whose article is no longer falsely flagged repealed under FR-13 — when repeal is evaluated, then the comma is **not** repealed and receives an embedding.
- Given CdS art. 23 comma 13-ter, whose parsed text opens `PERIODO ABROGATO DAL D.LGS. ...` (a repealed sentence, not a repealed comma), when repeal is evaluated, then the comma is **not** repealed.
- Given any comma of a CdS article flagged repealed by the pre-change heuristic but not by FR-13 (arts. 2, 3, 5, 6, 7, 9, 23, 37, 38, 62, 93, 95, 98, 100, 115, 117, 119, 122, 128, 129, 150, 180, 182, 187, 207, 237), when repeal is evaluated, then the comma is not repealed on account of its article.

Note: the discussion's "32 commas repealed, down from 42" cannot be an acceptance
criterion. The 42 baseline omitted the inherited article flag — the pre-change rule
actually marks 271 of 1802 CdS blocks, 268 of them from the article level — and the
post-Phase-1 corpus has 104 more commas with merged list bodies, so no absolute count
measured on today's `parsed` JSON survives. The count is re-measured as a Definition of
Done check (expected order of magnitude: ~30 commas plus the commas of 3 repealed
articles, which have none).

### FR-10: Knowledge indexing writes both tables as a per-source full reload

The indexing flow replaces one source's articles and commas without touching the other's.

**Acceptance criteria:**
- Given `cds` has been indexed, when `cap` is indexed, then the `cds` rows in both tables are unchanged.
- Given `cds` has been indexed, when `cds` is indexed again, then the row counts for `cds` are unchanged and no duplicates exist.
- Given a comma marked repealed and `embed_repealed` is false, when the source is indexed, then the comma row is present with a null embedding.
- Given the embedding input for a comma, when it is built, then it is composed of the article title and the comma's text only, omitting empty parts — nothing LLM-generated enters the vector.
- Given the same article parsed twice from the same raw HTML, when it is indexed twice, then the embedding inputs are byte-identical: the vector is a function of source data only, with no LLM step anywhere upstream of it.

### FR-11: The chunk-based components are removed

The components superseded by the new model are deleted from the repository together with
their tests.

**Acceptance criteria:**
- Given the repository after the change, when it is searched, then `ArticleChunker`, `EmbeddableChunkModel`, `KnowledgeChunk`, `KnowledgeChunkStoreRepository`, `StoreChunksStep` and `RetrievalResult` are absent, as are their test modules. `RetrievalResult` goes with them: it holds a `KnowledgeChunk` field, has no caller, and its replacement is a retrieval decision deferred with the read path.
- Given the repository after the change, when `uv run ruff check src tests` and `uv run pyright` are run, then both pass with no reference to the removed symbols.
- Given the repository after the change, when `uv run pytest` is run, then the suite passes.

### FR-12: The CLI and configuration operate on the new tables

`ingest reset knowledge` and `ingest status --online` target `articles` and
`article_commas`, and the configuration exposes one table-name key per table.

**Acceptance criteria:**
- Given a populated database, when `ingest reset knowledge` runs, then both tables are emptied and `quiz_questions` is untouched.
- Given `ingest reset knowledge --dry-run`, when it runs, then the rendered step chain names both tables and opens no DB connection.
- Given a reachable database, when `ingest status --online` runs, then it reports existence and row count for `articles` and `article_commas` and does not mention `knowledge_chunks`.
- Given an unreachable database, when `ingest status --online` runs, then it exits 0 and reports the database as unreachable.
- Given `IngestorConfig`, when it is loaded, then `knowledge_chunks_table` is gone and `articles_table` / `article_commas_table` are present with matching defaults in `configs/ingestor_config.yaml`.
- Given `IngestorConfig`, when it is loaded, then `knowledge_preparation.output_layer` and `knowledge_indexing.input_layer` are both `cleaned`, and `article_contextualizer_concurrency` is absent.
- Given `ingest status`, when it runs offline, then it still reports a `prepare`/`knowledge` readiness row per source, computed on the `cleaned` directory.

### FR-13: Article-level repeal detection is anchored to the repeal formula

An article is repealed when its `art-just-text-akn` block, after removing the amendment
markers, begins with `ARTICOLO ABROGATO`. The `"abrogato" in html.lower()` substring
match and the never-present `class="abrogato"` lookup are both removed.

**Acceptance criteria:**
- Given CdS art. 127, whose body is `((ARTICOLO ABROGATO DAL D.P.R. 9 MARZO 2000, N. 104 ))`, when the article is parsed, then it is flagged repealed.
- Given CdS arts. 2, 3 and 5 — whose editorial notes contain `NUMERO ABROGATO` or `PERIODO ABROGATO` — when they are parsed, then none is flagged repealed.
- Given the CdS corpus, when every article is parsed, then exactly 3 articles are flagged repealed (34-bis, 127, 130-bis), down from 29.
- Given the CAP RCA subset, when every article is parsed, then no article is flagged repealed, down from 4.
- Given `embed_repealed` is false, when the corpus is indexed, then the commas of arts. 2, 3, 5 and the other 26 falsely flagged CdS articles carry a non-null embedding, whereas under the pre-change flag they would all have been null.

### FR-14: `art-just-text-akn` is read as a body container

An article whose content lives in `art-just-text-akn` rather than in `art-comma-div-akn`
still produces commas. Its text is subject to the same rules: FR-4 discards it if it
reduces to markers or digits, FR-13 consumes it if it is the article-repeal formula, FR-1
extracts an inline number when present.

**Acceptance criteria:**
- Given CdS art. 216, whose 2861-character body sits in `art-just-text-akn` with zero comma divs and no inline number, when the article is parsed, then it emits one comma numbered `1` carrying that text — today the article parses to no text and no commas at all.
- Given CAP art. 121-octies, whose body is `((1. l'IVASS e la CONSOB definiscono attraverso un protocollo d'intesa...`, when the article is parsed, then it emits one comma numbered `1` per FR-1.
- Given CdS arts. 34-bis, 127 and 130-bis, whose `art-just-text-akn` holds only the article-repeal formula, when they are parsed, then no comma is emitted and the article is flagged repealed per FR-13.
- Given the parsed corpus after the change, when articles with zero commas are counted, then they are exactly those 3 CdS articles and no CAP article.

### FR-15: `ArticleCleaner` is reduced to title and residual-markup normalization

Marker merging and note-reference filtering move upstream into the scraper (FR-3, FR-4),
so the cleaner's paragraph pipeline is deleted rather than kept as a second, divergent
copy of the same rules.

**Acceptance criteria:**
- Given the repository after the change, when `ArticleCleaner` is inspected, then `_clean_paragraphs` and `_append_cleaned` are absent and no ordinal-prefix stripping remains — post-FR-1 comma text no longer begins with an ordinal, so the current `if not match: return` would discard every comma.
- Given a title wrapped in parentheses, when it is cleaned, then the parentheses are removed as today.
- Given a comma text containing residual inline `((...))` markup, when it is cleaned, then the markers are removed and the inner text is preserved.
- Given the cleaned corpus, when it is compared to the parsed corpus, then no comma is dropped by the cleaner.

## Non-Goals

- **Implementing retrieval.** No read path is built here: `guidami_ai_patente/` has not started, and the schema is justified by the retrieval shape agreed in the discussion, not by shipping it. That includes the serving shape of AD-1: `k`, `N` and the query-side handling of the quiz↔legalese lexical gap are read-path decisions, verified when there is something to verify them against.
- **Hybrid search — FTS columns, GIN indexes, RRF.** Deferred with `docs/plans/architecture-hybrid-retrieval.md`, which is marked superseded rather than rewritten, because choosing the FTS column is a retrieval decision that should be made when retrieval is implemented.
- **Vector indexes (ivfflat/HNSW).** The corpus stays small enough for an exact scan; unchanged from today.
- **A separate embeddings table allowing several vectors per comma.** Rejected as premature: changing the schema in this project costs a volume recreation and a full reload from JSON.
- **Resolving Normattiva's editorial notes.** Note references are discarded, not stored for later resolution; the notes themselves are not downloaded.
- **Any LLM enrichment of the corpus.** Article contextualization is removed (AD-18) rather than re-specified. If plain-language expansion turns out to help retrieval, it belongs on the query side, where the quiz bank already carries `core_concepts`, `exact_keywords` and `rule_explanation` — and either way it is a read-path experiment, not an ingestion feature.
- **Closing the road-sign coverage gap.** A large share of the 7106 quiz sub-questions asks about road signs, whose normative descriptions live in the Regolamento di attuazione (DPR 495/1992), absent from this corpus. Tracked separately in spec 0003; nothing here can retrieve what was never ingested.
- **Data migration or backfill.** No knowledge data exists in the database or in the `cleaned`/`enriched` layers.
- **Write-through resumability during a run.** Unchanged from today's cross-run behaviour.
- **Auditing the remaining `art-just-text-akn` articles outside the ingested corpus.** 56 CAP articles use that container, 55 of them outside the RCA ranges. FR-14 fixes the parser for all of them; only the 1 in-range article is verified here.

## Architectural Decisions

### AD-1: A hit is an `(article, comma)` pair; serving is the top-k commas plus the whole article of the top N
A vector hit identifies both the comma that matched and the article containing it. The
serving shape the schema must support is: the top-k matching commas, plus the full article
by join for the top **N** of them, with **N = 1** as the starting value.
- **Rationale:** an explanation must be able to cite the norm at comma level, and the comma identity is what makes an embedding traceable back to what was embedded, for debugging and partial regeneration. `N = 1` is what keeps the prompt bounded while the primary hit still reads in context, which matters because **49% of commas (1105 of 2230) contain an internal reference** (`ai sensi del comma 1-bis`, `di cui alla lettera c)`) that is unresolvable without the surrounding article. Both halves of the shape need the two-table model: comma text standalone for the tail, article-by-join for the head.
- **Rejected alternatives:** an embedding row keyed only by article — the matched comma becomes unrecoverable, losing both citation and diagnosis; serving only the matched commas — shorter prompt, but it is today's serving granularity, the thing this change exists to move past, and it leaves those 1105 internal references dangling; serving the whole article for every top-k hit — highest fidelity, but at k=5 the prompt carries five full articles of legalese and the primary hit stops standing out.
- **Not implemented here.** `N` is a read-path parameter and the read path is a Non-Goal; the spec fixes the shape the schema must not preclude, not the tuning.

### AD-2: The comma is a first-class entity carrying its own embedding
Two tables: `articles` for the article header, `article_commas` for each comma with its
text, context, repeal flag and vector. The whole article is served by a join.
- **Rationale:** the per-comma attributes are not just the vector — text, LLM context and repeal status are all per-comma. Modelling them as parallel arrays indexed by position inside the article row is a half-normalisation the database cannot constrain; one row per comma makes the constraint real.
- **Rejected alternatives:** arrays on `articles` plus a pure index table — one join cheaper, but keeps an unconstrained positional convention and scatters per-comma attributes across parallel structures; three tables with a separate embeddings table — would allow several vectors per comma without touching the data, but is premature here.

### AD-3: The legal comma number is fixed at the source, in the scraper
Rather than deriving a comma number downstream, the acquisition layer stops discarding the
one the source already provides.
- **Rationale:** the number is present in the source HTML and is destroyed by the parser. The same function also loses **104 real commas in the CdS** (exact, measured against the 266 raw pages that are the ingested corpus) plus an unmeasured share of the CAP subset, a corpus defect no downstream model can repair. The discussion's aggregate "337 commas" mixes the exact CdS figure with 233 commas measured over the full 610-article CAP code, of which only 96 articles are ingested — see the CAP open question.
- **Rejected alternatives:** a positional index plus a number parsed downstream from the text marker — re-derives with a regex what the HTML marks explicitly, and does not recover the lost commas; a positional index with article-level citation only — leaves the corpus incomplete.

### AD-4: One spec, two phases
Phase 1 corrects acquisition; Phase 2 introduces the schema and rewrites indexing.
- **Rationale:** both phases touch the same chain of models and mappers, so splitting them means doing the same signatures twice. The risk that normally justifies a split — rollout, production data, backfill — is absent.
- **Rejected alternatives:** two sequential specs — cleaner traceability, but a second pass over the same mappers for no risk reduction; deferring the scraper — would judge retrieval quality on a corpus known to be incomplete.

### ~~AD-5: The contextualizer contract is keyed by the legal comma number~~
**Withdrawn.** Superseded by AD-18: the contextualizer is removed, so there is no contract
to key. The defect it addressed — a positional key that could not be validated against
anything and was already misaligned — is resolved by deletion rather than by correction.

### AD-6: Superseded components are deleted, not kept disconnected
The chunk-based components are removed along with their tests and the old table.
- **Rationale:** keeping them does not buy the optionality they would be kept for — the intended refinement axis adds rows or columns to `article_commas` rather than resurrecting the chunk model. Git history remains the restore path.
- **Rejected alternatives:** leaving them in the repository unwired — linting and type checking still cover them, and their tests either stay green over code nobody runs or are deleted leaving untested code behind; deciding file by file — more precise, but scatters micro-decisions a single rule resolves.

### AD-7: The RCA subset comes from a versioned range extraction
The scraper stays a generic downloader; a separate versioned step produces the subset from
configured ranges, matching on the leading numeric part of the article number.
- **Rationale:** the subset turned out to be a mechanical rule — two contiguous blocks — so it belongs in configuration. Domain selection sits in ingestion configuration, not in the scraper, and the full code remains available. Matching on the numeric base is what makes 48 + 23 range positions yield 72 + 24 articles: the suffixed articles (`119-bis`, `120-quinquies`, …) are part of the blocks.
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

### AD-11: Per-comma repeal is anchored to the repeal formula, on top of a corrected article flag
Repeal is article-level repeal (AD-13) or a comma whose post-FR-1 text opens with
`COMMA ABROGATO` once leading markers are stripped.
- **Rationale:** the substring match over the comma body produces three false positives on its own, including CdS art. 23 c. 13-ter where a *sentence* is repealed. But the dominant defect is inherited: 268 of the 271 blocks the current rule marks come from the broken article flag, which is why the anchored comma rule is worthless without AD-13. Merging lists into commas enlarges each comma's text and would make the substring match worse.
- **Rejected alternatives:** article-level flag only — no comma-level false positives, but loses commas repealed inside articles still in force, which was the reason the heuristic existed; leaving the heuristic unchanged — no work, but the false positives grow with AD-8.

### AD-12: The unnumbered pre-comma block is the article title
When the heading element yields nothing, the unnumbered pre-comma block becomes the title;
consequently `articles` has no body column and `comma_number` is not nullable.
- **Rationale:** every unnumbered pre-comma block belongs to an article with an empty title, except one which is a note reference. No genuine normative preamble exists in the corpus, so the case that would justify a nullable comma number never occurs.
- **Rejected alternatives:** leaving it out of scope — seven articles would stay untitled after the re-scrape, and the title is part of every comma's embedding input; keeping it as an article body column — persists a parsing defect instead of correcting it and keeps the comma number nullable with no real case behind it.

### AD-13: Article-level repeal is anchored to the article-repeal formula
`repealed` becomes "the `art-just-text-akn` block, markers stripped, opens with
`ARTICOLO ABROGATO`", replacing `class="abrogato"` OR `"abrogato" in html.lower()`.
- **Rationale:** the class never occurs (0 of 266 CdS pages), so the substring match is the whole rule, and it fires on editorial notes: 29 CdS and 4 CAP articles are flagged, including arts. 2, 3 and 5. The flag is not merely noisy but close to inverted — the three genuinely repealed CdS articles are flagged *not* repealed, because their formula lives in the container the scraper never read. Two consequences make this blocking rather than cosmetic: with `embed_repealed=false` every comma of a falsely flagged article gets a null embedding and disappears from retrieval, and `ContextEnricher` skips repealed articles, so 33 articles also lose contextualization. Fixing it in the same commit as AD-14 is free: the formula and the missing container are the same element.
- **Rejected alternatives:** deriving article repeal from "all commas repealed" — would work for the three real cases but inverts the dependency (AD-11 already reads the article flag) and says nothing about an article whose body is only the formula; keeping the flag and compensating downstream — the false positives would have to be enumerated by article number, a hardcoded exception list against a source that changes.

### AD-14: `art-just-text-akn` is a fourth body container, not a special case
The scraper reads it with the same rules as the comma divs instead of treating those
articles as empty.
- **Rationale:** four CdS and one CAP-RCA article have zero `art-comma-div-akn` and their entire content there. Three are the repeal formula AD-13 needs; the other two are live norm — CdS art. 216 (2861 characters on accessory sanctions) and CAP art. 121-octies — lost outright today. Treating the container as a body source rather than adding an article-level branch keeps one set of comma rules.
- **Rejected alternatives:** leaving it out of scope — art. 216 stays absent from the corpus and AD-13 has no formula to read, so the article flag cannot be fixed either; a dedicated `articles.text` column for these bodies — resurrects the column AD-12 removed, for two articles that are ordinary single-comma articles.
- **Explicit assumption:** an `art-just-text-akn` body with no inline number is emitted as a single comma numbered `1` (the sole case is CdS art. 216). The source omits the number because the article has one paragraph; the alternative — a nullable `comma_number` for one row — weakens the schema more than the assumption costs. Revisit if a later re-scrape produces a multi-paragraph unnumbered body.

### ~~AD-15: The contextualizer contract violation is a dedicated exception, excluded from the enricher's catch~~
**Withdrawn.** Superseded by AD-18. The exception taxonomy only mattered while
`ContextEnricher` existed; removing the enricher removes both the catch-all that would
have swallowed the error and the error itself.

### AD-16: `ArticleCleaner` loses its paragraph pipeline rather than duplicating the scraper's rules
Marker merging and note filtering live only in the scraper; the cleaner keeps title
normalization and residual inline-markup removal.
- **Rationale:** after FR-3/FR-4 the two implementations of the same rule would have to be kept in sync, which is the defect this spec corrects elsewhere. And the cleaner is not merely redundant but actively wrong post-FR-1: `_append_cleaned` returns early when the text has no ordinal prefix, and after FR-1 no comma text has one — it would discard the entire corpus.
- **Rejected alternatives:** keeping it defensive and idempotent on both layers — survives a re-scrape with an old scraper, but two copies of one rule; deleting the cleaner entirely — the parenthesised-title and residual-markup cases still need a home, and moving them into the scraper mixes acquisition with normalization.

### AD-17: Articles with no commas are stored, not skipped
A repealed article with zero commas produces an `articles` row with `is_repealed = TRUE`
and no children.
- **Rationale:** "art. 127 is repealed" is answerable content for the quiz bot, and only three articles are involved once FR-2 and FR-14 recover the ones that merely looked empty. Skipping them would make a repealed article indistinguishable from a non-existent one.
- **Rejected alternatives:** skipping them in indexing — a cleaner "every article has a comma" invariant, but loses the distinction and adds an explicit discard rule to the store step; synthesising a comma holding the repeal formula — every article gets a child, but invents a comma the source does not have and needs a fictitious `comma_number`.

### AD-18: The corpus carries no LLM-generated content at all; the vector is article title + comma text
Article context enrichment is deleted rather than kept as un-embedded payload:
`ContextEnricher`, the agent, its DTOs, its prompt config, the `contexts` field, the
`context` column and `EnrichedArticleModel` all go, and `embedded_text` becomes
title + comma text.
- **Rationale:** two steps, one direction. Embedding a generated paraphrase would make retrieval quality a function of an unverified LLM output (`gemini-2.5-flash-lite`), and a bad paraphrase corrupts the *vector*, where it is invisible to review — unlike a bad payload, which a human reading the answer would catch. Having established that the context does not belong in the vector, nothing was left consuming it: it was a sketch that never ran past the `parsed` layer, so no data, no cost and no downstream reader would be lost by deleting it. Keeping a column, an agent, a prompt file and a concurrency knob alive for a feature with no consumer contradicts "remove dead code", and the alternative — keeping it as serving payload — pays LLM cost per article for an output whose quality nothing yet measures. The title stays because it is source data, not enrichment, and it is the only thing anchoring the **320 commas that are both under 250 characters and internally referential** to their subject.
- **Rejected alternatives:** title + context + text, i.e. today's formula — the correct *technique* for this corpus, since the 7106 quiz sub-questions are ~100 characters of everyday Italian against commas of 313 median characters of legalese, and document expansion is how that asymmetry is normally closed; dropped because the derived-artifact risk was judged larger and the same expansion can be applied from the query side, where the quiz bank already carries `core_concepts`, `exact_keywords` and `rule_explanation`. Keeping the context as un-embedded payload — preserves a possible serving benefit, but keeps an unmeasured LLM step, a column and an agent in the tree for it. Comma text alone, without the title — maximum purity, but 320 referential short commas and 252 commas under 120 characters lose their only topical anchor. Two embedding columns to compare variants — buys falsifiability, but pointless: reversing this is not a schema change, it is one `ingest index` run and well under a cent of embeddings, and no quiz→comma ground truth exists to compare against yet.
- **Consequence:** the whole knowledge pipeline becomes deterministic — no LLM call anywhere between raw HTML and stored vector. `index` cannot be degraded by `prepare`, and the same raw corpus always yields the same rows.

### AD-19: `prepare knowledge` survives as a cleaning-only step writing one file per article to `cleaned`
The output layer is renamed from `enriched` to `cleaned`, the per-element layout is kept,
and `index` reads from `cleaned`.
- **Rationale:** a layer named `enriched` that enriches nothing is a lie in the schema of the project, and the honest name already exists. The per-element split is kept even though its original justification — making the per-article LLM spend resumable across runs — is gone: one file per article makes a single article's cleaned output diffable and re-processable in isolation, which is worth more now than before, since this spec rebuilds the parser and the first thing anyone will want is to compare one article before and after. The plumbing (`element_id`, `LoadJsonDirStep`, `FilterAlreadyDoneStep`, `WriteJsonDirStep`) is already implemented, so keeping it costs nothing.
- **Rejected alternatives:** folding cleaning into `index` and dropping the command — one command and one artifact fewer, but no way to inspect the cleaned corpus before spending embeddings, and `ingest status` loses its prepare/knowledge dimension; collapsing `cleaned` back to a single JSON per source — simpler I/O, but loses per-article diffing exactly when the parser is being rewritten; leaving the layer named `enriched` — smallest diff, but keeps a misleading name and a per-element layer whose stated rationale no longer holds.
- **Unchanged:** the quiz pipeline keeps its own `enriched` layer and its enrichers (image descriptions, norm references); this decision is scoped to knowledge.

## Data Model

### Parsed layer

The article model loses its `text` field: an unnumbered pre-comma block becomes the title
(AD-12) and a numbered one becomes a comma (AD-3). `paragraphs: list[str]` is replaced by
`commas: list[ParsedComma]`, an ordered list where each item carries `number: str` and
`text: str`; list order is document order and is what becomes `article_commas.position`.
`number`, `title`, `url`, `scraped_at` and `repealed` are unchanged on the record.
`source` is still stamped at the parsed→cleaned boundary. `contexts` disappears with the
enrichment (AD-18), and with it `EnrichedArticleModel`: the chain is
`ParsedArticleModel → CleanedArticleModel → entity`, and `cleaned` — one JSON file per
article, named by `element_id(source, number)` — is the last filesystem layer before the
database (AD-19).

This is a persisted contract: `data/parsed/{cds,cap}/*.json` is the re-scrape artifact and
the input to `ingest prepare`, so the key name `commas` and the item shape are part of the
spec, not an implementation choice.

`scraped_at` stays on the parsed record but is deliberately **not** carried into
`articles`: it is provenance for the JSON artifact, and the DB is a full reload from that
artifact, so a per-row timestamp would record when the reload ran, not when the norm was
fetched.

### Database

```sql
CREATE TABLE articles (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT NOT NULL,               -- "cds" | "cap"
    number      TEXT NOT NULL,               -- "142", "116-bis"
    title       TEXT NOT NULL,               -- NOT NULL, may be '' (3 repealed CdS articles)
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

No index on `articles (source)`: `source` is the leading column of `UNIQUE (source,
number)`, so the per-source delete of FR-10 already has one. `VECTOR(1536)` repeats
`embedding.vector_dim` from `configs/ingestor_config.yaml` — a pre-existing duplication
between DDL and config, carried over unchanged rather than solved here.

`knowledge_chunks` is dropped. Migration follows the project's existing mechanism —
`db/init.sql` is the single source of schema truth and only runs on volume creation, so
applying this is `docker compose down -v` followed by `up -d`, then a full re-ingestion.
No backfill is required.

## Constraints

- **No migration tool.** Schema changes go into `db/init.sql` and are applied by recreating the volume; introducing Alembic is out of scope.
- **Definition of Done spans the whole chain:** re-scrape both sources, regenerate the RCA subset, then `ingest prepare` and `ingest index` for `cds` and `cap`. It also includes re-measuring the repealed-comma count (FR-9) and the CAP dropped-comma count (open question) on the corrected corpus.
- **Vector parameters require the explicit `%s::vector` cast** (`.claude/rules/code-conventions.md`).
- **Loop bodies must not use `continue`** — the parsing rules replace the current `continue`-based skips in the scraper, in `_parse_article` and in `main` (`.claude/rules/code-conventions.md`).
- **Logging uses lazy `%s` arguments, never f-strings** (`.claude/rules/logging.md`), and mixes levels purposefully — the FR-3 discard is a `warning`, not a `debug`.
- **The Italian-DTO exception no longer applies to knowledge** (`.claude/rules/code-conventions.md`): removing the contextualizer removes the only knowledge-side agent response DTO. The rule stays in force for the quiz agents, which are untouched.
- **Entities model the insertable projection**: database-generated columns (`id`) are not declared on write entities (`.claude/rules/code-conventions.md`).
- **Injected dependencies come last** in constructor signatures (`.claude/rules/dependency-injection.md`).
- **New repeatable operations are registered under `[project.scripts]`.**
- **The re-scrape is bounded by Normattiva's politeness delay** — 266 CdS + 610 CAP fetches at 1.5 s, roughly 22 minutes of wall clock plus retries.

## Feasibility Evidence

- **AD-1** — supported by (historical, `src/domain/models/knowledge/retrieval_result.py` was line-9-and-up at the time, since deleted by this plan's own T-15 per FR-11): `RetrievalResult` wrapped a single `KnowledgeChunk` and had no caller, confirming no read path existed yet and the retrieval shape was still free to be defined; deletion confirmed at `specs/0001-article-level-storage.md:560` (verified 2026-08-01 @ c457354)
- **AD-1** — supported by: `src/scrapers/normattiva.py:169` — the comma texts this line emits, measured over both parsed corpora (2230 blocks, median 313 characters), contain an internal reference (`comma`, `lettera`, `presente articolo`) in 1105 cases (49%), of which 320 are also under 250 characters — the population that needs the article served alongside it (verified 2026-07-31 @ 5790d63)
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/mappers/article_mapper.py:60` — `is_repealed` is computed per chunk, not per article, showing repeal is genuinely a per-comma attribute alongside text and context (verified 2026-07-31 @ 5790d63)
- **AD-2** — supported by: `db/init.sql:8` — `knowledge_chunks` repeats `article_title`, `source_url` and `is_repealed` on every comma row under `UNIQUE (source, article_number, comma_index)` (verified 2026-07-31 @ 5790d63)
- **AD-3** — supported by: `src/scrapers/normattiva.py:164` — the parser reads the `comma-num-akn` span and then concatenates it into the comma text as a prefix, discarding the structured number (verified 2026-07-31 @ 5790d63)
- **AD-3** — supported by: `src/scrapers/normattiva.py:272` — every fetched page is written to `data/raw/<slug>/`, so the raw page count is the full-code article count: 266 for CdS (equal to the ingested corpus) but 610 for CAP against the 96 the pipeline reads, which is why the CdS 104-comma figure is exact and the CAP 233 is not (verified 2026-07-31 @ 5790d63)
- **AD-4** — supported by (historical, `src/guidami_ai_patente_ingestor/models/knowledge/enriched_article.py` was line-21-and-up at the time, since deleted): the enriched model carried `contexts: dict[int, str]`, one of the shared shapes both phases had to change, confirming the two phases touched the same chain; deletion confirmed at `specs/0001-article-level-storage.md:555` (verified 2026-08-01 @ c457354)
- **AD-18** — supported by (historical, `configs/agents/article_contextualizer.yaml` was line-9-and-up at the time, since deleted): the prompt rendered the pre-comma text unlabelled and numbered the paragraph block from 1 while instructing the model to return keys starting at 0: the component being deleted was never coherent, not merely unused; deletion confirmed at `specs/0001-article-level-storage.md:553` (verified 2026-08-01 @ c457354)
- **AD-18** — supported by (historical, `src/guidami_ai_patente_ingestor/agents/dto/article_contextualizer/article_contextualizer_request.py` was line-25-and-up at the time, since deleted with its whole `dto/article_contextualizer/` directory): `paragraphs_block` numbered `paragraphs[0]` as `1.`, disagreeing with the chunker's `comma_index` of `1` for the same paragraph; deletion confirmed at `specs/0001-article-level-storage.md:552` (verified 2026-08-01 @ c457354)
- **AD-6** — supported by (historical, `src/guidami_ai_patente_ingestor/services/knowledge/article_chunker.py` was line-13-and-up at the time, since deleted per FR-11): `ArticleChunker` existed solely to expand an article into per-comma chunks, the step the new model removed; deletion confirmed at `specs/0001-article-level-storage.md:557` (verified 2026-08-01 @ c457354)
- **AD-7** — supported by: `configs/ingestor_config.yaml:12` — the `cap` source points at `codice_rca.json`, which `scrapers/normattiva.py` never writes (verified 2026-07-31 @ 5790d63)
- **AD-7** — supported by: `configs/ingestor_config.yaml:12` — the file this key names, `codice_rca.json`, is reproduced exactly by filtering `codice_assicurazioni_private.json` (610 articles) on the leading numeric part with ranges 118-165 and 278-300: 72 + 24 = 96 articles, same numbers, same order (verified 2026-07-31 @ 5790d63)
- **AD-8** — supported by: `src/scrapers/normattiva.py:166` — the `if not text_span: continue` guard is what drops every comma whose body is a list (verified 2026-07-31 @ 5790d63)
- **AD-9** — supported by: `src/scrapers/normattiva.py:162` — the comma loop accepts any div carrying a text span, including the note-reference divs whose whole content is `((190))`; 9 such paragraphs survive into `codice_della_strada.json` and 28 into `codice_rca.json` (verified 2026-07-31 @ 5790d63)
- **AD-10** — supported by: `db/init.sql:8` — `knowledge_chunks` no longer exists as a table (`CREATE TABLE articles` at this line is what replaced it), confirming the hybrid-retrieval plan's fusion query — which selected payload columns directly from `knowledge_chunks` — could not survive unchanged and was correctly marked superseded rather than rewritten (verified 2026-08-06 @ 2d741ac; the original evidence — line 96 of the hybrid-retrieval plan doc under docs/plans/ — was itself deleted as obsolete by commit `0a18903` — see Changelog)
- **AD-11** — supported by: `src/guidami_ai_patente_ingestor/mappers/article_mapper.py:60` — repeal is `model.repealed or "ABROGAT" in raw_text.upper()`, an unanchored substring match over the whole comma body, sitting on top of the article flag (verified 2026-07-31 @ 5790d63)
- **AD-11** — supported by: `src/scrapers/normattiva.py:171` — evaluating both rules over the corpus this flag feeds, the current rule marks 271 of 1802 CdS blocks, 268 of them inherited from `repealed`; the formula-anchored comma rule alone marks ~30 (verified 2026-07-31 @ 5790d63)
- **AD-11** — supported by (historical, `src/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/embed_chunks_step.py` was line-53-and-up at the time, since deleted per FR-11, superseded by `EmbedCommasStep`): repealed chunks were excluded from embedding and retained a null vector, which is how a false positive became invisible to retrieval; deletion confirmed at `specs/0001-article-level-storage.md:559` (verified 2026-08-01 @ c457354)
- **AD-12** — supported by: `src/scrapers/normattiva.py:156` — the title comes solely from `article-heading-akn`, with no fallback when that element is absent (verified 2026-07-31 @ 5790d63)
- **AD-12** — supported by: `src/scrapers/normattiva.py:159` — the pre-comma block is read into `text`, which is where the missing titles currently end up (verified 2026-07-31 @ 5790d63)
- **AD-12** — supported by: `src/scrapers/normattiva.py:157` — this fallback to `""` produces 8 empty titles in CdS and 2 in CAP; FR-5 recovers 5 CdS and both CAP, leaving CdS 34-bis, 127 and 130-bis, which are exactly the 3 articles whose pages carry no heading element at all (verified 2026-07-31 @ 5790d63)
- **AD-13** — supported by: `src/scrapers/normattiva.py:171` — `repealed` is `bool(soup.find(class_="abrogato")) or "abrogato" in html.lower()` (verified 2026-07-31 @ 5790d63)
- **AD-13** — supported by: `src/scrapers/normattiva.py:171` — `class="abrogato"` appears in 0 of the 266 `data/raw/cds/art_*.html` pages, so the `or` branch is the entire rule; it flags 29 CdS and 4 CAP-RCA articles, including arts. 2, 3 and 5, whose only match is `NUMERO ABROGATO` / `PERIODO ABROGATO` inside an editorial note (verified 2026-07-31 @ 5790d63)
- **AD-13** — supported by (historical, `src/guidami_ai_patente_ingestor/services/knowledge/enrichers/context_enricher.py` was line-57-and-up at the time, since deleted per FR-16): `if article.repealed ... return article` skipped the LLM call, so the false positives also suppressed contextualization for those 33 articles; deletion confirmed at `specs/0001-article-level-storage.md:551` (verified 2026-08-01 @ c457354)
- **AD-14** — supported by: `src/scrapers/normattiva.py:163` — this loop and the pre-comma read are the only body sources, and 4 CdS pages (34-bis, 127, 130-bis, 216) plus 1 CAP-RCA page (121-octies) have neither `art-comma-div-akn` nor `article-pre-comma-text-akn`; all five carry their content in `art-just-text-akn`, which `_parse_article` never queries (verified 2026-07-31 @ 5790d63)
- **AD-14** — supported by: `src/scrapers/normattiva.py:160` — `text` is read only from `article-pre-comma-text-akn`, which `data/raw/cds/art_0216_1.html` lacks; its `<span class="art-just-text-akn">` holds 2861 characters beginning `Nell'ipotesi in cui, ai sensi del presente codice, è stabilita la sanzione amministrativa accessoria del ritiro...`, so the parsed record has empty `text` and empty `paragraphs` (verified 2026-07-31 @ 5790d63)
- **AD-14** — supported by: `src/scrapers/normattiva.py:171` — the flag this line computes could instead be read from `art-just-text-akn`, which in arts. 34-bis, 127 and 130-bis holds exactly `((ARTICOLO ABROGATO DAL/DALLA ...))` and nothing else (verified 2026-07-31 @ 5790d63)
- **AD-18** — supported by (historical, `src/guidami_ai_patente_ingestor/services/knowledge/enrichers/context_enricher.py` was line-64-and-up at the time, since deleted per FR-16): `except Exception` logged a warning and returned the article unchanged, so the enricher's failures were silent by construction; deleting it removed the swallow rather than negotiating with it; deletion confirmed at `specs/0001-article-level-storage.md:551` (verified 2026-08-01 @ c457354)
- **AD-19** — supported by: `configs/ingestor_config.yaml:19` and `configs/ingestor_config.yaml:23` — `knowledge_preparation.output_layer` and `knowledge_indexing.input_layer` are both `enriched`, so removing the enrichment makes the layer name false and both keys must move to `cleaned` (verified 2026-07-31 @ 5790d63)
- **AD-19** — supported by: `src/guidami_ai_patente_ingestor/cli/services/status/status_inspector.py:14` — the readiness logic already treats knowledge `cleaned`/`enriched` as per-element directories, so keeping one file per article is the status quo, not new work (verified 2026-07-31 @ 5790d63)
- **AD-19** — supported by: `specs/0006-quiz-per-element-layers.md:6` — `Status: implemented`: `element_id`, `LoadJsonDirStep`, `FilterAlreadyDoneStep` and `WriteJsonDirStep` exist, so retaining the per-article split costs nothing even though its original LLM-resumability rationale is gone (verified 2026-08-06 @ 2d741ac; supersedes the original citation of `docs/plans/2026-07-17--per-element-knowledge-layers.md`, deleted as obsolete by commit `0a18903` — see Changelog)
- **AD-16** — supported by (historical, `src/guidami_ai_patente_ingestor/services/knowledge/article_cleaner.py` was line-95-and-up at the time; the file was rewritten by T-6 and is now 55 lines with no `_append_cleaned`): `_append_cleaned` returned early when `_ORDINAL_PREFIX_PATTERN` did not match, so once FR-1 stripped the ordinal from the comma text every comma would have been discarded; the fix is confirmed at `specs/0001-article-level-storage.md:560` (verified 2026-08-01 @ c457354)
- **AD-16** — supported by (historical, `src/guidami_ai_patente_ingestor/services/knowledge/article_cleaner.py` was line-62-and-up at the time; the file was rewritten by T-6 and is now 55 lines with no `_clean_paragraphs`): `_clean_paragraphs` implemented the `((`/`))` merge and the note-reference filter that FR-3 and FR-4 moved into the scraper; the move is confirmed at `specs/0001-article-level-storage.md:561` (verified 2026-08-01 @ c457354)
- **AD-17** — supported by: `src/scrapers/normattiva.py:166` — this guard is why 8 CdS articles parse to zero content today (34-bis, 47, 48, 127, 130-bis, 151, 216, 225): 47, 48, 151 and 225 have comma divs that merely lack the text span and are recovered by FR-2, 216 is the FR-14 case, leaving exactly 3 genuinely commaless articles (verified 2026-07-31 @ 5790d63)
- **AD-18** — supported by (historical, `src/guidami_ai_patente_ingestor/models/knowledge/embeddable_chunk.py` was line-30-and-up at the time, since deleted per FR-11, superseded by `EmbeddableArticleComma`): `parts = [self.article_title, self.context, self.chunk_text]` was the embedding input then, confirming the LLM-generated context entered the vector and not only the payload; deletion confirmed at `specs/0001-article-level-storage.md:557` (verified 2026-08-01 @ c457354)
- **AD-18** — supported by (historical, `configs/agents/article_contextualizer.yaml` was line-2-and-up at the time, since deleted per FR-16): the context was produced by `openrouter/google/gemini-2.5-flash-lite`, so under the pre-change formula every vector depended on an unverified generated artifact; deletion confirmed at `specs/0001-article-level-storage.md:553` (verified 2026-08-01 @ c457354)
- **AD-18** — supported by: `data/parsed/quiz-patente-ab/quiz-patente-ab.json:1` — 7106 quiz sub-questions averaging ~100 characters of everyday Italian (`Il segnale raffigurato preavvisa confine di Stato...`) against commas of 313 median characters of legalese: the lexical asymmetry the dropped context was covering, now left to the query side (verified 2026-07-31 @ 5790d63)
- **FR-12** — supported by: `src/guidami_ai_patente_ingestor/configs/ingestor_config.py:64` and `src/guidami_ai_patente_ingestor/cli/commands/reset.py:41` — `knowledge_chunks_table` is a single config key consumed by `reset` and by the status wiring, so replacing one table with two is a config-shape change, not only a rename (verified 2026-07-31 @ 5790d63)

## Open Questions

- [x] **non-blocking** — closed: contextualizer key mismatch (FR-8) is a dedicated contract exception, re-raised through `ContextEnricher`'s catch-all — see AD-15
- [x] **non-blocking** — closed: articles with no commas are stored as an `articles` row with `is_repealed = TRUE` and zero children; the population is 3 CdS articles, not 9, once FR-2 and FR-14 recover the ones that only looked empty — see AD-17
- [ ] **non-blocking** — The CAP drop-rate figure quoted during the discussion (233 of 2780) was measured over the full 610-article code, not the 96 ingested RCA articles. The CdS figure (104 of 1893) is exact. The RCA-specific count is measured as a Definition of Done check once the corrected scraper runs — owner: investigation
- [ ] **non-blocking** — The repealed-comma count after Phase 1 (FR-9) is measured on the corrected corpus rather than asserted, because the pre-change baseline was mis-measured and the corpus itself changes — owner: investigation

## Sign-off

- **Scope approved by user:** confirmed retroactively 2026-08-01, at plan close-out (the plan was
  fully implemented and its Definition of Done verified before this confirmation was formally
  recorded)
- **Feasibility asserted:** by write-spec on 2026-07-31, based on Feasibility Evidence above

## Changelog

### 2026-07-31 — review
Re-verified every FR and AD against the code and the real corpus at `5790d63`. Outcome:

- **Blocking defect found.** The article-level `repealed` heuristic was as broken as the per-comma one and dominated it: 268 of the 271 CdS blocks the old rule marked repealed came from the article flag, so FR-9's rule ("article repealed OR formula") fixed almost nothing and its AC on CdS art. 3 could not have passed. Added **FR-13** / **AD-13**; rewrote **FR-9** and **AD-11**; removed the unmeasurable "32, down from 42" acceptance criterion.
- **Fourth body container found.** `art-just-text-akn` is never read: CdS art. 216 (2861 characters in force) and CAP art. 121-octies were lost outright, and the three genuine `ARTICOLO ABROGATO` formulas AD-13 needs live there. Added **FR-14** / **AD-14**.
- **Downstream blockers added to scope.** `ContextEnricher`'s catch-all would have swallowed the FR-8 contract error (**AD-15**); `ArticleCleaner._append_cleaned` would have discarded every comma once FR-1 strips the ordinal (**FR-15** / **AD-16**); `RetrievalResult` was missing from FR-11's removal list although it holds a `KnowledgeChunk`.
- **Open questions closed.** Contextualizer error taxonomy → AD-15. Commaless articles → AD-17, with the population corrected from 9+1 to 3.
- **Indexing revisited on the user's objection.** FR-10's embedding input was inherited from `embeddable_chunk.py:30`, never decided. It now excludes the LLM-generated context (**AD-18**): the vector is a function of source data only, so it is deterministic and `index` no longer depends on the output of `prepare`. The title stays — it is source data and the only anchor for the 320 commas that are both short and internally referential. The trade-off is recorded rather than hidden: the 7106 quiz sub-questions are ~100 characters of everyday Italian against 313-character legalese commas, and closing that gap now falls to the query side. No hedging second embedding column, because reversing the choice is one `ingest index` run and under a cent of embeddings, not a migration.
- **AD-1 serving shape made explicit.** A hit stays an `(article, comma)` pair, but serving is the top-k commas plus the whole article only for the top **N**, starting at `N = 1`. `k` and `N` are read-path parameters and stay Non-Goals; the schema must merely not preclude the shape — and both halves of it need the two-table model, which strengthens AD-2.
- **Article context enrichment removed outright.** Once the context was out of the vector, nothing consumed it: a sketch that never ran past `parsed`, with no data, no spent cost and no reader. **FR-16** deletes `ContextEnricher`, the agent, its DTOs and mapper, `article_contextualizer.yaml`, the `article_contextualizer_concurrency` key, the `contexts` field, `EnrichedArticleModel`, `from_cleaned_to_enriched` and the `article_commas.context` column. **FR-8**, **AD-5** and **AD-15** are struck through — they only existed to make the contextualizer correct. Net effect: **no LLM call anywhere between raw HTML and stored vector**, so the knowledge pipeline is fully deterministic.
- **`prepare knowledge` kept, layer renamed (AD-19).** Cleaning-only step writing **one JSON file per article** to `cleaned` (per-element plumbing already `Implemented`), with `knowledge_indexing.input_layer` following it. The name `enriched` would otherwise have described a layer that enriches nothing. The quiz pipeline's `enriched` layer and its enrichers are untouched.
- **Road-sign coverage gap recorded as a Non-Goal.** A large share of the quiz asks about signs, described in the Regolamento di attuazione (DPR 495/1992), absent from this corpus — tracked in spec 0003 so a retrieval failure there is not misread as an embedding problem.
- **Grey areas pinned.** FR-1 number recognition by shape, not by ordinal whitelist; FR-3 discard logged as a `warning`; FR-6 range matching on the leading numeric part; FR-12 config keys; the `parsed` JSON shape as a contract; `scraped_at` deliberately absent from `articles`; `title NOT NULL` may be empty; no redundant index on `articles (source)`; AD-3's "337 commas" split into the exact CdS figure and the unmeasured CAP one.

### 2026-08-01 — plan executed: plans/0001-article-level-storage-plan.md

- **DoD result:** All 16 tasks (T-1…T-16) implemented and verified. Per-task failing-test specs
  passed at the time each task was implemented, verified directly (not taken on the
  implementer's word) via `uv run pytest` + `ruff check` + `ruff format --check` + `pyright`
  after every task. Final state: `uv run pytest -q` → 449 passed; `uv run pytest -m integration
  -o addopts=""` → 20 passed, 1 skipped (pre-existing, needs a real `OPENROUTER_API_KEY`,
  unrelated to this plan); `ruff`/`pyright` clean. Corpus-wide re-scrape executed against the
  live Normattiva site (`scrape-codice`, `scrape-cap`, `extract-rca`) and cross-checked against
  the pre-plan baseline (commit `c457354`): FR-13 CdS repealed 29→3 (34-bis, 127, 130-bis) —
  exact match; FR-14 zero-comma articles are exactly those 3 — exact match; FR-4 note-shaped
  commas 9→0 (CdS) and 28→0 (CAP) — exact match; FR-6 RCA extraction 96 articles (118-165 +
  278-300), `119-bis` included — exact match; FR-13 CAP-RCA repealed 4→0 — exact match; FR-2/FR-3
  spot checks (arts. 47/48/151/225 each ≥1 comma, art. 85's `4-bis` absorbs its list items, no
  leaked list-marker commas) — pass; FR-5 title recovery for arts. 81/116-bis/120/204-bis/215-bis
  — all non-empty, art. 120 matches the spec's literal example text — pass; FR-1 art. 142 comma
  numbers fully structured including `6-bis`/`9-bis`/`12-bis`/`12-ter`/`12-quater` — pass. **Not
  executed**, by explicit user choice (to avoid live embedding-API cost/time): the full
  `ingest prepare knowledge`/`ingest index knowledge` re-ingestion into Postgres called out in the
  plan's own Definition of Done — this remains a genuine, acknowledged gap, not silently skipped.
  **FR-16's deletion inventory confirmed absent** (grep-verified against `src/` and `tests/`):
  `ContextEnricher` (`services/knowledge/enrichers/context_enricher.py`), `ArticleContextualizerAgent`,
  its request/response DTOs and `ArticleContextualizerMapper`, `configs/agents/article_contextualizer.yaml`,
  the `article_contextualizer_concurrency` config key, `EnrichedArticleModel`
  (`models/knowledge/enriched_article.py`), and `ArticleMapper.from_cleaned_to_enriched`.
  **FR-11's deletion inventory confirmed absent**: `ArticleChunker`
  (`services/knowledge/article_chunker.py`), `EmbeddableChunkModel`
  (`models/knowledge/embeddable_chunk.py`), `KnowledgeChunk` (entity), `KnowledgeChunkStoreRepository`,
  `EmbedChunksStep` (`orchestrators/steps/knowledge/embed_chunks_step.py`), `StoreChunksStep`,
  and `RetrievalResult`. The old `ArticleCleaner._append_cleaned`/`_clean_paragraphs` (the
  paragraph-shaped cleaning logic FR-15/AD-16 replaced) are likewise gone — `article_cleaner.py`
  is now 55 lines, operating on `commas` only.
- **Deviations from plan:** (1) New Design Decision **PD-13** added mid-implementation:
  `PostgresClient.truncate()` widened from `truncate(table_name: str)` to
  `truncate(*table_names: str)`, emitting one combined `TRUNCATE TABLE t1, t2` statement —
  PD-11's premise (two sequential single-table `TRUNCATE` calls suffice) was factually wrong,
  verified against a live Postgres: it unconditionally refuses to empty a table referenced by a
  live FK unless the referencing table is named in the same statement. (2) **T-13 was
  implemented out of the plan's document order**, immediately after T-5/T-6 rather than after
  T-7…T-12, to unblock a real breakage: T-5's `CleanedArticleModel` shape change broke
  `ArticleMapper.from_cleaned_to_enriched` → `EnrichedArticleModel`, and T-13 (which deletes that
  code path entirely, per FR-16) was the actual fix, not a workaround — T-13 only depends on
  T-6, so this reordering did not violate any dependency. (3) `EnrichedArticleModel` was **not**
  deleted by T-13 despite being on its file list — it was kept alive because
  `ArticleChunker`/`ArticleMapper.from_enriched_to_embeddable_chunk` (out of T-13's scope) still
  referenced it; deleted in T-15 once those were also removed. This exposed a genuine plan gap:
  no task's file list ever named `enriched_article.py` for deletion — resolved by treating it as
  part of T-15's inventory once confirmed dead. (4) **T-15's actual deletion inventory grew
  beyond its stated file list**: `EnrichedArticleModel` + its test, `test_embeddable_chunk.py`,
  `context_keys.py`'s three now-dead constants (`ENRICHED_ARTICLES`/`EMBEDDABLE_CHUNKS`/
  `CHUNK_ENTITIES`), the `StoreRepository` protocol's stale docstring, and — discovered only
  after the rest of T-15 landed, via a full clean `pytest` run rather than the grep sweep alone —
  two out-of-inventory test files (`test_json_repository.py`, `test_embedding_service.py`) whose
  fixtures needed porting from the deleted `EnrichedArticleModel`/`EmbeddableChunkModel` onto
  `CleanedArticleModel`/`EmbeddableArticleComma`. All confirmed dead/necessary and applied with
  explicit reasoning, never silently. (5) **T-16's first implementation matched the plan's
  literal (pre-PD-13) `reset.py` text** — two separate `ArticleCommaStoreRepository`/
  `ArticleStoreRepository.truncate()` calls — which crashes against a live Postgres for the same
  FK reason PD-13 fixed elsewhere; corrected to call `postgres_client.truncate(...)` directly
  with both table names in one statement, and the corresponding test rewritten to assert the
  combined-call shape instead of the two-separate-calls shape. (6) A small number of files
  outside their originating task's declared list needed edits as direct, unavoidable
  consequences of symbol removal: `tests/.../test_subagents_from_yaml_injection.py` (T-13),
  `cli/rendering/status_renderer.py` and `orchestrators/knowledge_flows.py`'s one
  `config.knowledge_chunks_table` reference (T-16) — none introduced new behavior.
- **Learnings:** Postgres's `TRUNCATE` restriction on FK-referenced tables is unconditional and
  statement-scoped (not row-count- or ordering-dependent) — worth remembering for any future
  schema with FK relationships and a truncate-based reset path. A spec's predicted corpus-wide
  counts (e.g. "+104 commas") are order-of-magnitude sanity checks, not exact contracts — the
  real re-scrape measured +48, a real but non-alarming divergence (same order of magnitude),
  most likely because the spec's figure and the plan's net-aggregate-delta measurement used
  different counting methodologies (per-article recovered comma vs. net total, which also nets
  out list-item merges). A large, mechanical file-deletion task (T-15) benefits from a
  pre-verified inventory pass before implementation, but even a thorough grep sweep missed 4
  real references that only surfaced when the full test suite was run clean (without
  `--continue-on-collection-errors`) — no sweep substitutes for that final full-suite check.
  Background TDD-writing subagents intermittently ran out of turns on larger multi-file tasks
  (T-9/T-10, T-14, T-15) and returned truncated handoffs without finishing the requested tests;
  the orchestrating session had to detect this via direct `pytest` verification and complete the
  test-writing itself in those cases — worth budgeting for on any future plan with comparably
  large tasks.
- **Status change:** in-progress → implemented — confirmed by Alessio Gilardi, 2026-08-01.

### 2026-08-06 — review: two post-close drifts recorded

A full audit of specs 0001–0006 found two legitimate, already-merged changes that
landed after this spec's Changelog closed on 2026-08-01, neither ever folded back into
the spec text. Recorded here per the user's request; no Data Model/AD text rewrite —
the spec's prose above is left as the historical record of what was decided and why,
and this entry is the record of what has since changed.

Separately, two Feasibility Evidence citations (AD-10, AD-19) pointed into
`docs/plans/`, which no longer exists (commit `0a18903`, "Remove obsolete docs/plans
directory") — a repo-wide cleanup unrelated to this spec. Both were mechanically
repaired (not content changes): AD-10 now cites `db/init.sql:8` (confirming
`knowledge_chunks` no longer exists, the fact the deleted plan's evidence was making);
AD-19 now cites `specs/0006-quiz-per-element-layers.md:6` (the same "per-element layers
already implemented" claim the deleted plan doc made, now made by a spec instead).

- **AD-12/Data Model reversed: `scraped_at` is back on `articles`.** This spec states
  "`scraped_at` stays on the parsed record but is deliberately **not** carried into
  `articles`" and its DDL block has no such column. Commit `75556a1` ("Persist
  scraped_at from scraper through to articles table", 2026-08-04) reintroduced it:
  `db/init.sql:14` (`scraped_at TIMESTAMPTZ NOT NULL`), `domain/entities/knowledge/article.py:13`,
  populated by `mappers/article_mapper.py:44`. Documented correctly in the Second Brain
  (`docs/database.md:238-242`, citing ADR 0007's UTC-timestamp convention) but never
  reflected back here.
- **FR-9's per-comma repeal rule extended beyond its stated acceptance criteria.**
  FR-9 only specifies a `COMMA ABROGATO` prefix check. Commit `abe1335` relocated this
  logic into `services/knowledge/comma_repeal_detector.py`, which also now recognizes
  `COMMA SOPPRESSO` (spec 0004 FR-7) and treats an empty/whitespace-only comma text as
  repealed (commit `e503c94`, 2026-08-04) — a legitimate, documented extension, but one
  FR-9's acceptance criteria don't describe or cover.
- **Learning:** same pattern as specs 0002/0004's review entries — an `implemented`
  spec's Changelog closes at the moment its own plan finishes, but later, unrelated
  commits can still touch the exact code it describes without ever being checked
  against it. Worth a periodic re-audit rather than assuming `implemented` means
  frozen-and-accurate indefinitely.
