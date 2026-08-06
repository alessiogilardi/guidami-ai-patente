# Spec 0007: Retrieval Evaluation Harness

| | |
|---|---|
| **Id** | 0007 |
| **Status** | in-progress |
| **Date** | 2026-08-05 |
| **Discussion log** | none — compiled directly from conversation |
| **Supersedes / superseded by** | — |

## Problem & Motivation

The ingestion phase is complete: 770 articles, 3992 commas (3650 embedded, repealed
excluded), and 7099 quiz questions (7098 embedded) are in Postgres with 1536-dim
vectors. Nothing in the codebase reads them back — there is no retrieval code at all,
and therefore no evidence about whether the corpus can actually answer a quiz question.

The next planned feature is hybrid search (pgvector + Postgres FTS fused with Reciprocal
Rank Fusion), motivated by the assumption that dense retrieval misses exact terms.
That assumption has never been measured. Ad-hoc SQL probes run against the live database
show dense retrieval scoring 81.6% on a lexical proxy at k=5 against a ~27% random
baseline (a 3.2x lift), while the worst topic — "alcool, droga e farmaci; primo soccorso"
— collapses to 31.9%, 28 points below the second-worst.

The probes also demonstrate how easily this kind of measurement misleads. A per-keyword
statistic (21–35% of `exact_keywords` match no comma anywhere) initially read as evidence
of a corpus coverage gap. Recomputed per question it inverts: 97.7% of questions have at
least one matching keyword somewhere in the corpus, and the worst topic is 82.3% covered
while scoring 31.9% at k=5. A third pass then found that the apparent validation of that coverage
figure was circular — `hit@k` is itself defined by keyword matching inside retrieved
commas, so a question with no keyword anywhere in the corpus cannot be a hit by
construction. Coverage measured this way is a **lower bound**, not a count: 161 questions
match nothing at all, while a further 901 are covered only by keywords appearing in more
than ten commas each, and the most frequent keyword in the bank matches 2894 of 3650
commas. The true uncovered population plausibly lies between 161 and roughly 1060. It
follows that no claim of the form "the text is present, so this is a ranking failure" is
supported for any individual topic — only the bounds are.

Two lessons are baked into this spec. First, hybrid search must not be funded before
ranking failures and coverage failures are separated, because no fusion algorithm
retrieves a text that was never ingested. Second — learned the hard way, three times over
in this spec's own history — a metric validated against a signal derived from its own
input validates nothing. Every control here is therefore stated together with what it
cannot rule out, and where no judge-free control exists, the spec says so rather than
inventing one.

The headline figures quoted above (81.6% / ~27% / 3.2x) are all **keyword-derived** and
inherit every limitation of `exact_keywords` described in AD-4 and FR-10. They are
recorded as the historical starting point, not as a target to beat.

## Functional Requirements

### FR-1: `ingest evaluate retrieval` command

A new `evaluate retrieval` subcommand of the existing `ingest` CLI runs the full
measurement over the quiz bank and the knowledge corpus already stored in Postgres.

**Acceptance criteria:**
- Given a populated database, when `uv run ingest evaluate retrieval` is run, then the
  command completes and writes a metrics summary plus per-question detail.
- Given `--config configs/ingestor_config.test-data.yaml`, when the command is run, then
  it targets the same Postgres tables with the alternate config, exactly as
  `prepare`/`index` do.
- Given `--dry-run`, when the command is run, then it prints the measurement chain it
  would execute and exits without opening a database connection and without writing to
  the filesystem.
- Given `--plain`, when the command is run, then output is rendered without the live
  dashboard. Note this command does not run a `flowstep` `Flow`, so it is outside the
  existing `_MONITORED_COMMANDS` set; the flag must be given a defined meaning for a
  non-Flow command rather than inherited by analogy.
- Given a completed run, when artifacts are written, then a manifest type for this command
  exists — `logging_setup._build_manifest` raises on an unknown command, so the command
  cannot ship without one.
- Given the run parameters, when the command is invoked, then **seed**, baseline repetition
  count `N`, the `k` values for FR-4, and the reporting thresholds of FR-2 are all supplied
  from configuration (a new evaluation section of `ingestor_config.yaml`), with CLI flags
  overriding where useful. No run parameter is hardcoded in the harness.
- Given `--dry-run` on a command with no `Flow` to derive steps from, when the chain is
  printed, then it is produced from the same declaration the real run executes, not from a
  hand-maintained parallel list.

### FR-2: Corpus coverage metric (primary)

For each quiz question, the harness reports **how strongly** the corpus matches it,
scanning the entire corpus rather than only the retrieved top-k. Coverage is never a
binary label and never a single percentage: a binary needs a threshold nobody can justify
without a judge, and the one binary definition that was tried read 97.7% and discriminated
nothing.

**Acceptance criteria:**
- Given a question, when text coverage is computed, then it is the **maximum `ts_rank`
  achieved by any comma in the corpus** against the tsquery built from the question text —
  a continuous score per question, requiring no `exact_keywords` and no threshold.
- Given a completed run, when text coverage is reported, then it is reported as the
  distribution of that score (median and quartiles) plus the share of questions above each
  of the configured thresholds — a curve, never one number.
- Given a question with `exact_keywords`, when keyword coverage is computed, then it is
  reported as the document-frequency band already defined: questions matching nothing,
  questions covered only by keywords above each configured DF cutoff, questions covered by
  a keyword below the lowest cutoff. Note that a **higher** document frequency means a
  **less** selective keyword.
- Given the keyword band, when it is rendered, then the "matches nothing" figure is
  labelled a **lower bound** on the uncovered population, not a count.
- Given both coverage views, when they are reported, then each is labelled with its
  dependency: text coverage depends only on human-authored text, keyword coverage depends
  on an LLM artifact (FR-10).
- Given a completed run, when the summary is produced, then both views are reported overall
  and broken down by topic, ordered worst-first.
- Given a question with `exact_keywords IS NULL` or empty, when keyword coverage is
  computed, then the question is reported in a separate `not_measurable` bucket, never
  silently counted as covered or uncovered.
- Given the coverage test and the ranking metrics, when either matches text against the
  corpus, then both search exactly the same fields; a run where the two definitions diverge
  is a defect, not a finding.
- Given the coverage metric, when the summary is produced, then it carries an explicit note
  that **no judge-free validity check for coverage exists**: `hit@k` is defined by the same
  matching operation and cannot independently corroborate it, and `exact_keywords` are
  themselves derived from the question text (FR-10), so neither is an outside witness.

### FR-3: Random baseline control

Every run computes the same hit metric against randomly drawn commas, and reports it
alongside the real metric.

**Acceptance criteria:**
- Given a completed run, when the summary is produced, then it contains the random
  baseline hit rate at the same k values as the real metric.
- Given a configured repetition count `N` (default 3, configurable), when the baseline is
  computed, then the random comma draw is repeated `N` times with a different sample each
  time, and the summary reports the mean and the spread across repetitions — never a
  single draw.
- Given the baseline and the real metric, when the lift is reported, then it is reported
  **both** as a ratio and as a difference in percentage points, and the baseline's spread
  is reported in percentage points alongside it — no comparison mixes the two units.
- Given the random draw, when it is sampled, then it draws only from the commas the real
  metric can retrieve (`embedding IS NOT NULL`, 3650 of 3992). A baseline drawn from a
  different population is not a control for the same thing.
- Given the same seed and the same `N`, when the run is repeated, then every baseline
  repetition is reproducible.
- Given `N` repetitions of ~7000 draws each, the between-repetition spread of the mean is
  expected to be a fraction of a percentage point, so the spread **cannot** serve as a
  discrimination threshold against a lift measured in tens of points. The harness therefore
  reports the numbers and does **not** emit an automated `metric_not_discriminating`
  verdict; a control that can never fire is worse than none, because it reads as reassurance.

### FR-4: Ranking metrics, reported over both denominators

The harness reports how well dense retrieval ranks matching commas, against both the
covered subset and the full measurable set — the two answer different questions and are
never collapsed into a single headline number.

**Acceptance criteria:**
- Given a completed run, when the summary is produced, then it reports hit@k for the
  configured `k` values twice: once over the covered subset, once over all measurable
  questions.
- Given the covered subset, when it is defined, then it is defined by the **keyword**
  "matches nothing" bucket of FR-2 — the only binary coverage label this spec has — and is
  labelled as keyword-derived wherever it appears.
- Given both figures, when they are rendered, then each is labelled with what it answers:
  the covered-subset figure isolates ranking quality (ceiling 100%), the full-set figure is
  the end-to-end product figure.
- Given both figures, when they are rendered, then the note accompanying them states that
  because the coverage test and the hit test match identically (FR-2), an uncovered question
  is a miss by construction and the two figures are related by
  `full ≈ covered × coverage_rate`. **The gap between them is an arithmetic identity, not a
  measured cost**, and must not be presented as evidence about the corpus.
- Given a completed run, when the summary is produced, then it reports the same metrics
  broken down by topic and by presence/absence of `image_filename`.
- Given the image/non-image breakdown, when it is rendered, then it carries an explicit
  warning that the two populations are not comparable to each other on this metric,
  because keyword selectivity differs between them.

### FR-5: Lexical adherence score (judge-free)

For each retrieved comma the harness computes a continuous adherence score using
Postgres full-text search with the `italian` configuration, independent of the embedding.

**Acceptance criteria:**
- Given a question and a retrieved comma, when the adherence score is computed, then it is
  `ts_rank` against a tsquery built from the question text, over a corpus-side tsvector
  built with `setweight` (article title `A`, comma text `B`) — one definition, used
  everywhere, never a plain `title || ' ' || text` concatenation.
- Given the question text, when the tsquery is built, then its lexemes are combined with OR
  (`|`), because `plainto_tsquery` combines with AND and was measured to return 0.0000 on
  every row of a sample.
- Given a completed run, when the summary is produced, then it reports the adherence score
  computed on the weighted tsvector and, separately, on title-only and text-only
  tsvectors, so the contribution of each field is visible rather than assumed.
- Given a completed run, when the summary is produced, then it reports the distribution
  of the top-1 adherence score (median and quartiles), not only its mean.

### FR-6: Dense/FTS agreement and distance margin

The harness reports two confidence signals derived from data it already has, with no
extra retrieval cost.

**Acceptance criteria:**
- Given a question, when the agreement signal is computed, then it reports the overlap
  between the top-k set ranked by cosine distance and the top-k set ranked by `ts_rank`.
- Given a question, when the margin signal is computed, then it reports the difference
  between the top-1 cosine distance and the distance at the **largest configured `k`**,
  so the margin is defined against one fixed depth rather than an ambiguous "top-k".
- Given a completed run, when the summary is produced, then it reports the share of
  questions where the two rankings disagree entirely (zero overlap in the top-k).

### FR-7: Run artifacts

Each run produces a small committed summary for cross-run comparison and a full
per-question detail file that stays out of git.

**Acceptance criteria:**
- Given a completed run, when artifacts are written, then a metrics summary is written to a
  committed path under `data/eval/` in a diffable format, with an explicit shape (a
  versioned model, not an ad-hoc dict) so that a diff between two runs is meaningful.
- Given `data/eval/`, when it is introduced, then its version-control status is stated
  explicitly — it is committed, like `data/enriched/` (ADR 0012, superseding ADR 0005) —
  and `.gitignore` is left untouched for that path deliberately rather than by omission.
- Given a completed run, when artifacts are written, then the per-question detail and
  `run.log` are written under `logs/ingest_evaluate_<YYYYMMDDHHMM>/`. That directory will
  also contain the `manifest.json` and `report.md` that `RunArtifactWriter.__exit__` always
  writes — four artifacts, not two.
- Given two runs of the same corpus with the same seed and the same configured parameters,
  when their summaries are diffed, then the diff is empty.
- Given `--dry-run`, when the command is run, then neither artifact path is written.

### FR-8: No network calls at evaluation time

The harness reads only what ingestion already persisted; it never calls an embedding or
LLM endpoint.

**Acceptance criteria:**
- Given a run with `OPENROUTER_API_KEY` unset, when `ingest evaluate retrieval` is run,
  then it completes successfully.
- Given a completed run, when `llm_call_logs` is inspected, then it contains no rows
  attributable to the evaluation run.

### FR-9: Judge-ready export of the undecidable subset

The harness exports the questions its deterministic signals cannot decide, in a form a
future judge can consume without any judge being implemented here.

**Acceptance criteria:**
- Given a completed run, when artifacts are written, then a separate export contains the
  questions matching no keyword and the questions covered only by non-selective keywords,
  with their retrieved top-k commas and all computed signals.
- Given the export, when it is produced, then each record carries the question text, the
  correct answer, and the retrieved commas with `source` and article number, so it is
  self-contained for review.
- Given the export, when it is produced, then no LLM provider, prompt, or judging
  interface is referenced anywhere in the harness — the export is data, not a plugin seam.

### FR-10: Test whether `exact_keywords` carry signal

`exact_keywords` are an LLM artifact that has never been validated. The harness measures
their usefulness instead of assuming it.

**Acceptance criteria:**
- Given a completed run, when the summary is produced, then it reports the share of
  distinct keywords that match no comma anywhere in the corpus, and the distribution of
  keyword document frequency — direct, self-contained measures of keyword quality that
  depend on no second signal.
- Given a completed run, when the summary is produced, then it reports the association
  between keyword-derived hit@k (a per-question binary) and the FR-5 adherence score of the
  same question's top-1 comma, using a named statistic (point-biserial correlation), not an
  unspecified "agreement".
- Given that association, when it is reported, then it is accompanied by the statement that
  it is **not an independence test**: `exact_keywords` are generated by an LLM *from the
  question text*, which is also the input to `ts_rank`, so the two signals share their
  origin and partial agreement is guaranteed. It bounds how badly the keywords diverge from
  their own source; it cannot confirm they are right.
- Given no judge, when the summary is produced, then it states that whether
  `exact_keywords` carry signal about *the corpus* cannot be settled by this harness, and
  is the question FR-9's export exists to hand to a judge.
- Given the keyword-free signals (FR-5, FR-6) and the keyword-derived ones, when results
  are presented, then each is labelled with which of the two it depends on, so a reader
  can discard the latter without discarding the run.

## Non-Goals

- **LLM-as-judge relevance scoring** — deliberately excluded from this spec. The
  deterministic signals cost nothing and run in CI; they indicate which subpopulation a
  judge should later target, making an untargeted judge run wasteful now. That targeting
  is no longer hypothetical: the 901 questions covered only by non-selective keywords are
  precisely where the judge-free metrics cannot decide, and they are the natural first
  batch whenever a judge is funded. FR-9 exports exactly that batch, but deliberately
  stops at data: no `RelevanceJudge` protocol, no provider abstraction, no prompt.
  Designing an interface for a consumer nobody has chosen yet is how the wrong interface
  gets built.
- **Implementing hybrid search** — fusing a *dense* ranking with a *full-text* ranking into
  a production retrieval path is out of scope; this spec measures whether that feature is
  justified. The dense/FTS agreement signal in FR-6 is a measurement, not a retrieval path.
  This exclusion is deliberately narrower than "RRF": spec 0008 requires this harness to
  fuse several **dense** rankings by RRF as one of its arms, which is a measurement
  technique and is **not** excluded here. Fusion machinery built for that arm may be reused
  later, but reusing it is a separate decision.
- **A production retrieval API** (`similarity_search`, FastAPI routes) — belongs to
  `src/guidami_ai_patente/` when that app starts, and is not created here.
- **Schema changes** — no generated `tsvector` column, no GIN or HNSW/IVFFlat index. All
  full-text work happens at query time, so this spec needs neither a migration nor a reset.
- **Fixing the corpus coverage gap** — this spec quantifies it; deciding whether to
  ingest additional non-CdS material (first aid, vehicle mechanics) is a separate call.

## Architectural Decisions

### AD-1: The harness is an `ingest` CLI feature, not part of `src/guidami_ai_patente/`
- **Rationale:** `docs/layout.md:175` assigns retrieval code to the FastAPI app package,
  but that package is an empty scaffold and the harness is a data-quality instrument, not
  application runtime. It needs the ingestor's config loading, layer resolution, Postgres
  wiring, logging and run-artifact conventions, all of which already exist in the CLI. This
  is a **conscious documented deviation** from `layout.md`, recorded here so the next
  reader does not treat it as an oversight.
- **Rejected alternatives:** Founding `src/guidami_ai_patente/` on the harness — would
  shape the app package around an offline measurement tool rather than around serving,
  and would duplicate the ingestor's CLI infrastructure. A standalone throwaway script —
  loses config, logging and artifact conventions, and cannot run in CI as a regression gate.

### AD-2: Full-text search is computed at query time, with no schema change
- **Rationale:** `to_tsvector`/`ts_rank` over 3650 commas is fast enough for an offline
  harness, and the measured dense scan over the full 7098-question corpus already completes
  in 2m46s. A generated `tsvector` column plus a GIN index would be a schema change — now
  possible without a wipe, via the `db/migrations/` path established by ADR 0010, but still
  a commitment to hybrid search made before the measurement says it is warranted. Keeping
  the harness schema-free also keeps it runnable against any database state, which matters
  while spec 0008's schema is in flight.
- **Rejected alternatives:** Persisted `tsvector` column + GIN index — correct for
  production hybrid search, premature here; cheap to add later precisely because ADR 0010
  removed the reset requirement.

### AD-3: The tsquery is built by OR-joining the question's lexemes
- **Rationale:** `plainto_tsquery('italian', ...)` combines every term with AND. Against a
  long question sentence no single comma contains all terms, so `ts_rank_cd` returns
  0.0000 for every pair — measured directly against the live database, on every row of a
  5-question probe. Rebuilding the query as an OR of the lexemes produced discriminating
  scores on the same probe (0.0634 for the comma verified correct by hand versus
  0.0165–0.0330 for its competitors).
- **Rejected alternatives:** `plainto_tsquery` — measured to return a constant zero here.
  `websearch_to_tsquery` — still defaults to AND for bare terms, same failure.

### AD-4: Coverage is reported as two distributions, and no binary label is derived from text
- **Rationale:** Without a judge, "the corpus contains the rule that justifies this
  question" cannot be determined semantically, so every coverage figure here is a lexical
  proxy — a comma may share vocabulary without justifying the answer. Two proxies are
  reported, and neither is collapsed to a percentage:
  **text coverage** is the best `ts_rank` any comma achieves against the question text,
  reported as a distribution; **keyword coverage** is the document-frequency band over
  `exact_keywords`, whose "matches nothing" bucket (161 questions) is the one binary label
  the spec uses, as a lower bound.
  A binary threshold on text coverage was deliberately **not** introduced: with the
  OR-joined tsquery of AD-3, any shared lexeme produces a match, and Italian quiz text is
  saturated with `veicolo`, `strada`, `conducente` — a binary would read near 100% for
  structural reasons and discriminate less than the 97.7% keyword figure already rejected
  as uninformative. Trading the keywords' precision defect (63% match nothing) for a recall
  degeneracy would be a strictly worse metric wearing a better justification.
- **Rejected alternatives:** A single binary coverage percentage from question text — the
  degeneracy above; it was drafted, then withdrawn. Keyword-based coverage as the *only*
  definition — measured evidence casts doubt on the keywords. Dropping `exact_keywords`
  entirely — discards a signal before establishing it is worthless, and exact-term matching
  is precisely what hybrid search exists to serve. **A single IDF cutoff** calibrated
  against `hit@k` — the 2026-08-05 calibration appeared to show predictive power growing as
  the cutoff loosened, but that trend is an artifact: the loosest cutoff is the closest to
  the tautology, so the apparently "best" cutoff is simply the most circular one. Document
  frequency is kept as a reporting axis, never as a threshold. Using `rule_explanation` as
  a pseudo-reference — it originates from the same LLM call as `vector_search_queries`, so
  it would partly measure the enrichment step's internal consistency.

### AD-7: Read repositories live in `commons/`, and are scoped per entity, not per table
- **Rationale:** The harness needs the project's first query code — every existing
  repository under `repositories/db/` is write-only bulk insert. The CLI self-containment
  rule would put a CLI-only component in `cli/`, but a corpus reader is not CLI-only: it is
  exactly what `src/guidami_ai_patente/` will need to serve retrieval, and `commons/`
  already hosts a Postgres repository (`LlmCallLogRepository`) for the same reason — more
  than one consumer.
  **Scope is the entity, not the table.** Every knowledge-side read this spec needs is a
  join: a retrieved comma is useless without its article's `source`, `number` and `title`
  (FR-4 and FR-9 both require the citation, and FR-5's weighted tsvector puts the title in
  band `A`). The same holds for the quiz side, where a question is only usable together
  with its query vector. Two repositories follow — one per aggregate, each taking an
  injected `PostgresClient`:
  a **corpus** reader over `articles` + `article_commas`, and a **quiz** reader over
  `quiz_questions` + `quiz_question_embeddings`.
  Note the deliberate asymmetry with the write side, which *is* per table
  (`ArticleStoreRepository`, `ArticleCommaStoreRepository`): an insert targets one table and
  needs the generated id back to satisfy the foreign key, so it cannot be an aggregate
  operation. Reads have no such constraint and are shaped by what the caller needs whole.
- **Rejected alternatives:** One repository per table — the shape this AD originally
  specified, withdrawn because it made every method either a join anyway (leaving the
  "per table" label describing nothing) or forced the join into Python, where the caller
  re-implements what SQL already does and pays an extra round trip. Repositories under
  `cli/` — satisfies the self-containment rule's letter but fails its stated test ("is this
  used by anything other than the CLI?"), and guarantees a move once the FastAPI app
  starts. Ad-hoc SQL inside the evaluation services — no reuse, and it scatters the
  `%s::vector` cast rule across call sites. Founding `src/guidami_ai_patente/` now to host
  them — pre-empts a package decision the app has not yet earned, and AD-1 already
  declined that.

### AD-5: A random baseline is computed on every run, not once
- **Rationale:** The proxy metric's absolute value is uninterpretable on its own — the
  measured 81.6% hit@5 only becomes meaningful next to the ~27% random baseline. The
  baseline is the one control in this spec that is genuinely external to the metric: it
  replaces the *retrieval* with chance while holding the matching definition fixed, so it
  detects the metric degenerating into "how common is this keyword" — a failure mode no
  keyword-derived or text-derived comparison can catch, since both share the metric's own
  inputs.
- **Rejected alternatives:** Computing the baseline once and hardcoding it — it drifts
  with the corpus, and a stale constant would mask exactly the degeneration it exists to
  catch.

### AD-6: Summary committed under `data/eval/`, detail under gitignored `logs/`
- **Rationale:** `logs` is gitignored, so run artifacts alone cannot support comparison
  across commits. A small committed summary makes regressions visible in a diff and in CI,
  matching how `data/parsed/` and `data/cleaned/` are already committed as pinned
  fixtures. The bulky per-question detail stays ephemeral alongside `run.log`, reusing the
  existing `RunArtifactWriter`.
- **Rejected alternatives:** Everything in `logs/` — no cross-commit comparison.
  Everything committed — per-question detail for 7098 questions would add churn to every diff.

## Data Model

No schema change. The harness is read-only against existing tables:

- `articles` — `id`, `source`, `number`, `title` (read; `source` is required in output
  because `number` is not unique across sources: CdS art. 43 "Segnalazioni degli agenti
  del traffico" and Regolamento art. 43 "Deviazioni di itinerario" both appear in
  retrieval results).
- `article_commas` — `article_id`, `comma_number`, `text`, `embedding` (read). Queries
  must filter `embedding IS NOT NULL`: 342 repealed commas are stored without a vector.
- `quiz_questions` — `number`, `topic`, `text`, `exact_keywords`, `image_filename` (read).
- **Quiz query vectors** — `db/init.sql` no longer carries `quiz_questions.embedding`:
  spec 0008's DDL landed in `764440b`, and vectors now live in
  `quiz_question_embeddings (quiz_question_id, variant, embedding_3_small)`. The harness
  must read them from there, keyed by variant. Until spec 0008's write path is implemented
  the table is empty on a fresh volume (see 0008's half-migrated constraint), so the harness
  must fail with a clear message when it finds no vectors rather than reporting zeroes.

A read layer does not exist: every repository under `repositories/db/` is write-only bulk
insert, exposing only `table_exists` and `row_count`. `PostgresClient.fetch` is the
primitive, but the query layer this harness needs must be created — and its home is a live
question, since a corpus reader is also what `src/guidami_ai_patente/` will eventually need
(see AD-1's deviation).

New artifact shapes: a versioned metrics summary model under `data/eval/`, a per-question
detail record under `logs/`, and an `EvaluateManifest` under
`cli/models/run_artifacts/` — `logging_setup._build_manifest` raises on an unknown command,
so the command cannot run without one.

## Constraints

- Read-only against Postgres. The harness issues no `INSERT`, `UPDATE`, `DELETE`,
  `TRUNCATE`, or DDL; temporary tables scoped to the session are permitted.
- No new runtime dependency. Everything needed (psycopg, pgvector, rich) is already in
  `pyproject.toml`; FTS is native Postgres.
- Vector parameters must use the explicit `%s::vector` cast, per
  `.claude/rules/code-conventions.md`.
- CLI-only components live inside `cli/`, per `.claude/rules/cli-structure.md`; the
  command must be registered under `[project.scripts]` conventions already established.
- A full-corpus run must stay within a few minutes; the measured dense-only baseline is
  2m46s for 7098 questions at k=10.
- Integration tests touching Postgres carry `@pytest.mark.integration` and are excluded
  from the default `pytest` invocation.
- Spec 0008 migrates rather than resets, moving `quiz_questions.embedding` into its variant
  table as the `search_queries` arm, so this harness's baseline configuration survives the
  schema change and can be re-measured at any time. Running this harness first is therefore
  preferable but no longer a hard ordering constraint; the committed summary from FR-7
  remains the mechanism for comparing runs across commits.

## Feasibility Evidence

- **AD-1** — supported by: `docs/layout.md:195` — assigns FastAPI/retrieval code to `src/guidami_ai_patente/`, the rule this decision consciously deviates from (verified 2026-08-06 @ 91c4fe7)
- **AD-1** — supported by: `pyproject.toml:31` — `ingest = "guidami_ai_patente_ingestor.cli:main"`, the entry point the new subcommand extends (verified 2026-08-05 @ 6d96b7d)
- **AD-1** — supported by: `src/guidami_ai_patente_ingestor/cli/parser.py:4` — existing subcommand surface (`prepare`/`index`) with the `--config`/`--dry-run`/`--plain` flags FR-1 mirrors (verified 2026-08-06 @ 91c4fe7)
- **AD-2** — supported by: `db/init.sql:26` — `embedding VECTOR(1536)` on `article_commas`; the file declares no `tsvector` column and no full-text or vector index (the six indexes it does declare are plain b-tree) (verified 2026-08-05 @ 46fad9a)
- **AD-3** — supported by: `db/init.sql:24` — `text TEXT NOT NULL`, plain text with no precomputed search vector, so the tsquery must be built at query time (verified 2026-08-05 @ 46fad9a)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/agents/mappers/norm_reference_describer_mapper.py:51` — `exact_keywords` is populated from an LLM agent's output, confirming it is a generated artifact rather than source data (verified 2026-08-05 @ 6d96b7d)
- **AD-4** — supported by: `db/init.sql:38` — `text TEXT NOT NULL` on `quiz_questions`, the always-present human-authored field text coverage uses (verified 2026-08-05 @ 46fad9a)
- **AD-4** — supported by: `db/init.sql:42` — `exact_keywords TEXT[]` as a first-class column, the flattening ADR 0002 performed to make it SQL-queryable (verified 2026-08-05 @ 46fad9a)
- **AD-4** — supported by: `src/domain/entities/quiz/quiz_question.py:20` — `exact_keywords: list[str] | None`, nullable, which is why FR-2 needs a `not_measurable` bucket (verified 2026-08-05 @ 6d96b7d)
- **AD-7** — supported by: `src/commons/ai/observability/repositories/llm_call_log_repository.py:32` — `LlmCallLogRepository`, an existing Postgres repository living in `commons/` because more than one consumer needs it (verified 2026-08-05 @ 46fad9a)
- **AD-7** — supported by: `src/commons/ai/observability/repositories/llm_call_log_repository.py:40` — its `__init__(self, client: PostgresClient)` shape, which the read repositories follow (verified 2026-08-05 @ 46fad9a)
- **AD-7** — supported by: `.claude/rules/cli-structure.md:34` — the deciding test "is this used by anything other than the CLI?", which a corpus reader fails, sending it out of `cli/` (verified 2026-08-05 @ 46fad9a)
- **AD-5** — supported by: `src/guidami_ai_patente_ingestor/models/quiz/quiz_metadata.py:24` — `embedded_text` returns the joined `vector_search_queries`, showing the query vector is generated from different text than the corpus vector (verified 2026-08-05 @ 6d96b7d)
- **AD-5** — supported by: `src/guidami_ai_patente_ingestor/models/knowledge/embeddable_article_comma.py:22` — corpus `embedded_text` is article title + comma text, the other side of that asymmetry (verified 2026-08-05 @ 6d96b7d)
- **AD-6** — supported by: `.gitignore:167` — `logs` is ignored, so run artifacts alone cannot support cross-commit comparison (verified 2026-08-05 @ 6d96b7d)
- **AD-6** — supported by: `src/commons/observability/run_artifact_writer/run_artifact_writer.py:35` — `RunArtifactWriter` already produces `run.log`, `manifest.json` and `report.md` in a timestamped run directory (verified 2026-08-05 @ 6d96b7d)

## Open Questions

- [ ] **non-blocking** — Which document-frequency cutoffs should the FR-2 keyword band
  report, and which `ts_rank` thresholds the text-coverage curve? The 2026-08-05
  calibration used DF cutoffs 1/2/3/5/10/20/50/100/250/500; the informative region was
  1–20, saturating above 50. Observed `ts_rank` values fell in 0.01–0.07 on a small sample,
  which is not enough to fix a threshold set. Both are reporting parameters, so a wrong
  first guess costs a re-run, not a redesign. — owner: user
- [ ] **non-blocking** — Where does the read layer live? Every existing repository is
  write-only, so this spec creates the first query code in the project. AD-1 places the
  harness in `cli/`, but a corpus reader is also what `src/guidami_ai_patente/` will need.
  Putting it in `cli/` risks a later move; putting it in a shared layer pre-empts a
  decision the FastAPI app has not yet earned. — owner: user
- [ ] **non-blocking** — The upper end of the uncovered range (~1060) can only be
  resolved by a judge run over the 901 fragile questions. Worth scheduling once this
  harness has run at least once end to end? — owner: user
- [ ] **non-blocking** — Should the committed summary in FR-7 be checked by CI as a
  regression gate, or only produced for manual inspection? — owner: user
- [ ] **non-blocking** — The one quiz question with `embedding IS NULL` (7098 of 7099) is
  unexplained; it should be identified but does not affect the harness design. —
  owner: investigation

## Sign-off

- **Scope approved by user:** Alessio Gilardi, 2026-08-05
- **Feasibility asserted:** by write-spec on 2026-08-05, based on Feasibility Evidence above

## Changelog

- **2026-08-06** — Evidence anchors refreshed to `91c4fe7`. `docs/layout.md` had shifted,
  moving the FastAPI/retrieval assignment from line 177 to 195; the `cli/parser.py` claim
  was re-read and holds unchanged. Mechanical drift only — no acceptance criterion, AD
  rationale, or constraint is affected, so the status is unchanged.
- **2026-08-06** — Mechanical drift refresh, status unchanged. An FR-7 acceptance
  criterion contrasted `data/eval/` (committed) against `data/enriched/` (gitignored);
  `data/enriched/` has been committed since 2026-08-05 and ADR 0005 is now superseded by
  ADR 0012, so the contrast is restated as a comparison. No acceptance criterion, decision
  rationale, or constraint changes: the criterion still requires `data/eval/`'s
  version-control status to be stated explicitly rather than left implicit.
- **2026-08-05** — FR-4 now reports hit@k over both denominators (covered subset and all
  measurable questions) instead of the covered subset alone, with the gap between them
  reported explicitly. Requested by the user; the two figures answer different questions
  (ranking quality vs end-to-end product coverage) and collapsing them hides the cost of
  missing corpus coverage.
- **2026-08-05** — FR-2 gained selectivity and saturation criteria, and its open question
  was promoted to **blocking**. A question-level coverage measurement run the same day
  returned 97.7% (6937/7098) under the naive "any keyword matches anywhere" definition,
  proving that definition non-discriminating. Problem & Motivation was corrected in the
  same pass: it previously presented a corpus coverage gap as the likely bottleneck,
  which the per-question measurement does not support — the worst topic is 82.3% covered
  yet scores 31.9% at k=5, making it a ranking failure.
- **2026-08-05** — The blocking question above is **resolved and the previous entry's
  conclusion reversed**. IDF weighting was calibrated across nine document-frequency
  cutoffs against actual retrieval outcomes: predictive power degrades monotonically as
  the cutoff tightens, and the unweighted definition is the strongest (uncovered group
  misses 93.8%, covered group 16.7%). The judgement that a 97.7% coverage rate proved the
  definition non-discriminating was wrong — the test of a metric is whether its label
  predicts failure, not whether it splits the population evenly. FR-2's validity criterion
  was rewritten from saturation (`coverage_not_discriminating`) to predictive separation
  (`coverage_not_predictive`), AD-4 records the rejected IDF alternative with its numbers,
  and Problem & Motivation now states the finding this produces: coverage is not the
  bottleneck, ~1160 questions have their answer in the corpus and still fail to retrieve
  it.
- **2026-08-05** — **The validation underpinning both entries above was circular, and the
  claims resting on it are withdrawn.** `hit@k` is defined by keyword matching inside
  retrieved commas, which are a subset of the corpus, so a question matching no keyword
  anywhere cannot be a hit by construction — the "93.8% of uncovered questions are misses"
  figure measured the definition against itself. It read 93.8% rather than 100% only
  because the coverage query searched `article_commas.text` while the hit query searched
  the article title as well; 20 of the 161 match a title, which accounts for the gap.
  Consequences: the IDF calibration is confounded (predictive power grew toward the
  cutoff closest to the tautology, not toward the better metric), so no cutoff can be
  chosen that way; FR-2 now publishes coverage as a band across document-frequency
  cutoffs with the "matches nothing" count labelled a lower bound (161), the fragile
  middle quantified (901 covered only by keywords in more than ten commas), and an
  explicit statement that no judge-free validity check for coverage exists; FR-2 also
  gained a criterion requiring the coverage and ranking queries to search identical
  fields, so the inconsistency that produced this cannot recur. Prompted by the user
  asking how the 161 figure could be trusted.
- **2026-08-05** — Scope extended on user request, keeping this spec measurement-only.
  FR-5 now weights the corpus tsvector with `setweight` (title `A`, comma text `B`) and
  reports per-field adherence instead of scoring one undifferentiated document. New FR-9
  exports the undecidable subset (questions matching nothing, plus those covered only by
  non-selective keywords) as judge-ready data, without introducing any judging interface.
  A constraint was added requiring a committed baseline run before spec 0008 changes the
  schema. The user's related proposals — persisting `vector_search_queries`, three
  alternative quiz embeddings with their columns, and expanding the corpus with missing
  sources — were deliberately routed to specs 0008 and 0009 rather than absorbed here, so
  that this harness stays the instrument those changes are measured with.
- **2026-08-05** — `exact_keywords` demoted from foundation to hypothesis, on the user's
  observation that they may be worthless. FR-2's primary coverage definition no longer
  uses them: it full-text matches the human-authored question text against the corpus,
  with the keyword definition retained as a secondary signal and the disagreement between
  the two reported. New AD-4b records the reasoning and the evidence (63% of distinct
  keywords match nothing in the corpus). New FR-10 measures whether the keywords carry
  signal at all, by checking agreement against the keyword-free `ts_rank` ranking, and
  requires every metric to be labelled with which of the two foundations it rests on.
  This partly reverses the earlier instruction to keep coverage as the primary metric —
  coverage stays primary, but its definition changed, because the original one could not
  survive the doubt cast on its input. FR-3 now repeats the random baseline `N` times
  (default 3, configurable) and reports mean and spread, with the discrimination flag
  keyed to that spread rather than to a fixed lift.
- **2026-08-05** — Amended after an independent adversarial review, which found that several
  amendments above had not been propagated and that new circularity had been introduced.
  Changes, all of them corrections rather than scope moves:
  **FR-2** — the question-text coverage definition added earlier was withdrawn as a binary:
  with the OR-joined tsquery of AD-3 it would have read near 100% for structural reasons,
  making it *less* discriminating than the keyword figure it replaced. Text coverage is now
  a continuous best-`ts_rank` score reported as a distribution; keyword coverage stays the
  DF band; neither is collapsed to a percentage.
  **FR-4** — the "gap between the two denominators is the cost attributable to missing
  coverage" criterion is deleted. Since FR-2 requires both tests to match identically, an
  uncovered question is a miss by construction and `full ≈ covered × coverage_rate` — the
  gap is an arithmetic identity, the same tautology withdrawn two entries above, reintroduced
  in a criterion added one entry above it. The covered-subset denominator is now explicitly
  the keyword "matches nothing" bucket, and labelled keyword-derived.
  **FR-10** — the claim that `ts_rank` "shares no input with the keywords" was false:
  `exact_keywords` are generated by an LLM *from the question text*. The criterion now names
  a statistic (point-biserial), and states that it is not an independence test.
  **FR-3** — the spread-keyed `metric_not_discriminating` flag is removed: with N≈3
  repetitions of ~7000 draws the spread of the mean is a fraction of a point and the flag
  could never fire, while comparing a ratio against a percentage-point spread was
  dimensionally incoherent. The baseline population is now pinned to the retrievable commas.
  **FR-1** — seed, `N`, `k` values and reporting thresholds are now required inputs from
  configuration; a manifest type and a dry-run chain source are named as obligations.
  **AD-4/AD-4b** — merged: two adjacent ADs gave contradictory definitions of the primary
  metric after AD-4b demoted AD-4 without rewriting it.
  **Non-Goals** — the RRF exclusion is narrowed to hybrid (dense+FTS) search, resolving a
  direct contradiction with spec 0008 FR-3, which requires this harness to fuse dense
  rankings by RRF. **Data Model** — rebased onto the post-`764440b` schema: quiz vectors are
  read from `quiz_question_embeddings`, not from the removed `quiz_questions.embedding`; the
  absence of any read layer is recorded. **Evidence** — `docs/layout.md:175`→`:177`, and the
  AD-2 claim "no index declared anywhere in the file" corrected (six b-tree indexes exist;
  the true claim is no FTS or vector index). **Problem & Motivation** — the sentence
  asserting "the text is present and the ranking fails to surface it" is retracted; the
  bounds do not support it.
- **2026-08-05** — AD-7 amended on the user's observation that the evaluation needs joins
  throughout: read repositories are now scoped **per entity**, not per table. Every
  knowledge-side read joins `article_commas` to `articles` (the citation in FR-4/FR-9 and
  the title weighting in FR-5 all require it), and the quiz side joins `quiz_questions` to
  `quiz_question_embeddings`. The original "one repository per table" wording described
  nothing real — the extracted plan had already had to carve out an exception for the
  articles join rather than fix the decision. The rejected-alternatives list records why
  per-table was withdrawn, and the AD now states the deliberate asymmetry with the write
  side, which stays per table because an insert needs its generated id back for the foreign
  key.
