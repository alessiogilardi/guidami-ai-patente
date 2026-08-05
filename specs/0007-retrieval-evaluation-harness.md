# Spec 0007: Retrieval Evaluation Harness

| | |
|---|---|
| **Id** | 0007 |
| **Status** | draft |
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
while scoring 31.9% at k=5 — so for that topic the text is present and the ranking fails
to surface it. A third pass then found that the apparent validation of that coverage
figure was circular — `hit@k` is itself defined by keyword matching inside retrieved
commas, so a question with no keyword anywhere in the corpus cannot be a hit by
construction. Coverage measured this way is a **lower bound**, not a count: 161 questions
match nothing at all, while a further 901 are covered only by keywords appearing in more
than ten commas each, and the most frequent keyword in the bank matches 2894 of 3650
commas. The true uncovered population plausibly lies between 161 and roughly 1060.

Two lessons are baked into this spec. First, hybrid search must not be funded before
ranking failures and coverage failures are separated, because no fusion algorithm
retrieves a text that was never ingested. Second, every metric here ships with a
validity control, because the measurement is as capable of producing a confident wrong
answer as the retrieval it measures — and the right control is whether a label predicts
failure, not whether it splits the population evenly.

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
  dashboard, consistent with the other `ingest` subcommands.

### FR-2: Corpus coverage metric (primary)

For each quiz question, the harness reports whether the corpus contains any comma that
matches the question — scanning the **entire** corpus, not only the retrieved top-k.
Coverage is computed from the question's own text, and separately from its
`exact_keywords`, so the primary metric does not depend on an unvalidated LLM artifact.

**Acceptance criteria:**
- Given a question, when primary coverage is computed, then it is based on a full-text
  match of the **question text** against the corpus, requiring no `exact_keywords`.
- Given a question with `exact_keywords`, when secondary coverage is computed, then the
  keyword-based definition is reported alongside the primary one, and the two are
  compared rather than merged.
- Given the two coverage figures, when they disagree for a question, then that question is
  counted in a reported disagreement bucket — divergence between a human-authored text
  signal and an LLM-generated keyword signal is a finding about the keywords.
- Given a question whose `exact_keywords` match at least one comma anywhere in
  `article_commas`, when secondary coverage is computed, then the question is reported as
  covered by the keyword definition.
- Given a question whose `exact_keywords` match no comma anywhere in the corpus, when
  coverage is computed, then the question is reported as uncovered and is excluded from
  the covered-subset denominator of the ranking metrics in FR-4.
- Given a completed run, when the summary is produced, then it reports the coverage band
  overall and broken down by topic, ordered worst-first.
- Given a question with `exact_keywords IS NULL` or empty, when coverage is computed,
  then the question is reported in a separate `not_measurable` bucket, never silently
  counted as covered or uncovered.
- Given a completed run, when coverage is reported, then it is reported as a band across
  keyword document-frequency cutoffs — questions matching nothing, questions covered only
  by keywords above each cutoff, questions covered by a selective keyword — never as a
  single coverage percentage.
- Given the coverage band, when it is rendered, then the "matches nothing" figure is
  labelled a **lower bound** on the uncovered population, not a count.
- Given the coverage test and the ranking metrics, when either matches a keyword against
  corpus text, then both search exactly the same fields; a run where the two definitions
  diverge is a defect, not a finding.
- Given the coverage metric, when the summary is produced, then it carries an explicit
  note that no judge-free validity check for coverage exists, because `hit@k` is defined
  by the same keyword matching and cannot independently corroborate it.

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
- Given the reported spread, when the real metric's lift over the baseline mean is smaller
  than that spread, then the run is flagged as `metric_not_discriminating`: a lift inside
  the baseline's own sampling noise is not a lift.
- Given the same seed and the same `N`, when the run is repeated, then every baseline
  repetition is reproducible.

### FR-4: Ranking metrics, reported over both denominators

The harness reports how well dense retrieval ranks matching commas, against both the
covered subset and the full measurable set — the two answer different questions and are
never collapsed into a single headline number.

**Acceptance criteria:**
- Given a completed run, when the summary is produced, then it reports hit@1, hit@3,
  hit@5 and hit@10 twice: once over the covered subset (FR-2), once over all measurable
  questions.
- Given both figures, when they are rendered, then each is labelled with what it answers:
  the covered-subset figure isolates ranking quality (ceiling 100%), the full-set figure
  is the end-to-end product figure (ceiling is the coverage rate).
- Given both figures, when they are rendered, then the gap between them is reported
  explicitly as the cost attributable to missing corpus coverage.
- Given a completed run, when the summary is produced, then it reports the same metrics
  broken down by topic and by presence/absence of `image_filename`.
- Given the image/non-image breakdown, when it is rendered, then it carries an explicit
  warning that the two populations are not comparable to each other on this metric,
  because keyword selectivity differs between them.

### FR-5: Lexical adherence score (judge-free)

For each retrieved comma the harness computes a continuous adherence score using
Postgres full-text search with the `italian` configuration, independent of the embedding.

**Acceptance criteria:**
- Given a question and a retrieved comma, when the adherence score is computed, then it
  is `ts_rank` of the comma's `to_tsvector('italian', title || ' ' || text)` against a
  tsquery built from the question text.
- Given a question whose terms are only partially present in a comma, when the tsquery is
  built, then the lexemes are combined with OR (`|`) and the resulting score is non-zero.
- Given the corpus-side tsvector, when it is built, then the article title and the comma
  text are weighted separately via `setweight` (title `A`, comma text `B`) rather than
  concatenated into one undifferentiated document, so a title match and a body match are
  distinguishable.
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
  between the top-1 and top-k cosine distances.
- Given a completed run, when the summary is produced, then it reports the share of
  questions where the two rankings disagree entirely (zero overlap in the top-k).

### FR-7: Run artifacts

Each run produces a small committed summary for cross-run comparison and a full
per-question detail file that stays out of git.

**Acceptance criteria:**
- Given a completed run, when artifacts are written, then a metrics summary is written
  to a committed path under `data/eval/` in a diffable format.
- Given a completed run, when artifacts are written, then the per-question detail and
  `run.log` are written under `logs/ingest_evaluate_<YYYYMMDDHHMM>/`, which is gitignored.
- Given two runs of the same corpus with the same seed, when their summaries are diffed,
  then the diff is empty.
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
- Given a completed run, when the summary is produced, then it reports the agreement
  between the keyword-based hit@k ranking and the `ts_rank` ranking computed from question
  text, which shares no input with the keywords.
- Given a completed run, when the summary is produced, then it reports the share of
  distinct keywords that match no comma anywhere in the corpus, as a direct measure of
  keyword quality.
- Given low agreement between the two signals, when the summary is produced, then every
  keyword-derived metric in the run is marked unreliable rather than reported as fact.
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
- **Implementing hybrid search / RRF** — this spec measures whether that feature is
  justified; it does not build it. The dense/FTS agreement signal in FR-6 is a
  measurement, not a retrieval path.
- **A production retrieval API** (`similarity_search`, FastAPI routes) — belongs to
  `src/guidami_ai_patente/` when that app starts, and is not created here.
- **Schema changes** — no generated `tsvector` column, no GIN or HNSW/IVFFlat index. Any
  of these would require a database reset and full re-ingest under the project's
  `db/init.sql` workflow.
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
  harness, and the measured dense scan over the full 7098-question corpus already
  completes in 2m46s. Adding a generated `tsvector` column plus a GIN index would change
  `db/init.sql`, which under this project's workflow requires wiping the bind mount and
  re-ingesting the whole corpus — an unjustifiable cost for a measurement, and a
  commitment to hybrid search before the measurement says it is warranted.
- **Rejected alternatives:** Persisted `tsvector` column + GIN index — correct for
  production hybrid search, premature here, and forces a full DB reset.

### AD-3: The tsquery is built by OR-joining the question's lexemes
- **Rationale:** `plainto_tsquery('italian', ...)` combines every term with AND. Against a
  long question sentence no single comma contains all terms, so `ts_rank_cd` returns
  0.0000 for every pair — measured directly against the live database, on every row of a
  5-question probe. Rebuilding the query as an OR of the lexemes produced discriminating
  scores on the same probe (0.0634 for the comma verified correct by hand versus
  0.0165–0.0330 for its competitors).
- **Rejected alternatives:** `plainto_tsquery` — measured to return a constant zero here.
  `websearch_to_tsquery` — still defaults to AND for bare terms, same failure.

### AD-4b: Primary coverage is computed from question text, not from `exact_keywords`
- **Rationale:** `exact_keywords` are generated by an LLM and have never been validated;
  3685 of 5845 distinct keywords (63%) match no comma anywhere in the corpus, and the most
  frequent one matches 2894 of 3650. Resting the primary metric on that artifact makes
  every downstream conclusion inherit its unknown error. The question text is
  human-authored and always present, so full-text matching it against the corpus yields a
  coverage signal with no LLM dependency. The keyword definition is retained as a
  secondary, comparable signal precisely so FR-10 can measure whether it was worth
  trusting.
- **Rejected alternatives:** Keeping keyword-based coverage as the only definition —
  measured evidence already casts doubt on it. Dropping `exact_keywords` entirely —
  discards a signal before establishing it is worthless, and they may still carry value
  for exact-term matching, which is the case hybrid search exists to serve.

### AD-4: Coverage is a lexical proxy, and is labelled as such
- **Rationale:** Without a judge, "the corpus contains the rule that justifies this
  question" cannot be determined semantically. What can be determined deterministically is
  whether the question's LLM-extracted `exact_keywords` appear anywhere in the corpus.
  ADR 0002 flattened those keywords into first-class columns specifically so they would be
  queryable with plain SQL, so this uses them as intended. The metric measures lexical
  presence, not truth: a comma may share vocabulary without justifying the answer. That
  limitation is stated in the output, not just in this spec. Crucially, the metric cannot
  be validated against `hit@k`: `hit@k` is defined by the same keyword matching, so a
  question covered by nothing cannot be a hit by construction and any apparent correlation
  between the two is circular. Coverage is therefore published as a band bounded below by
  the "matches nothing" count (161 on 2026-08-05), with the fragile middle quantified
  (901 questions covered only by keywords appearing in more than ten commas).
- **Rejected alternatives:** Semantic coverage via a judge — out of scope by decision.
  Using `rule_explanation` as a pseudo-reference — it is the strongest judge-free signal
  available, but it originates from the same LLM call as `vector_search_queries`, which
  produced the query vector; scoring one against the other would partly measure the
  enrichment step's internal consistency rather than adherence to the corpus.
  **A single IDF cutoff** picked by calibration against `hit@k` — the calibration run on
  2026-08-05 appeared to show predictive power growing as the cutoff loosened, but that
  trend is an artifact: the loosest cutoff is the closest to the circularity described
  above, so the apparently "best" cutoff is simply the most tautological one. No cutoff
  can be chosen this way. Document frequency is retained as the axis along which the
  coverage band is reported, rather than as a threshold that decides a binary label.

### AD-5: A random baseline is computed on every run, not once
- **Rationale:** The proxy metric's absolute value is uninterpretable on its own — the
  measured 81.6% hit@5 only becomes meaningful next to the ~27% random baseline. Because
  the query vectors come from `vector_search_queries` while the corpus vectors come from
  article title + comma text, the two sides are generated differently and a control is the
  only way to detect the metric silently degenerating into "how common is this keyword".
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
- `quiz_questions` — `number`, `topic`, `text`, `exact_keywords`, `image_filename`,
  `embedding` (read).

New artifact shapes only: a metrics summary model under `data/eval/`, and a per-question
detail record under `logs/`.

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

- **AD-1** — supported by: `docs/layout.md:175` — assigns FastAPI/retrieval code to `src/guidami_ai_patente/`, the rule this decision consciously deviates from (verified 2026-08-05 @ 6d96b7d)
- **AD-1** — supported by: `pyproject.toml:31` — `ingest = "guidami_ai_patente_ingestor.cli:main"`, the entry point the new subcommand extends (verified 2026-08-05 @ 6d96b7d)
- **AD-1** — supported by: `src/guidami_ai_patente_ingestor/cli/parser.py:4` — existing subcommand surface (`prepare`/`index`) with the `--config`/`--dry-run`/`--plain` flags FR-1 mirrors (verified 2026-08-05 @ 6d96b7d)
- **AD-2** — supported by: `db/init.sql:26` — `embedding VECTOR(1536)` on `article_commas` with no `tsvector` column and no index declared anywhere in the file (verified 2026-08-05 @ 6d96b7d)
- **AD-3** — supported by: `db/init.sql:24` — `text TEXT NOT NULL`, plain text with no precomputed search vector, so the tsquery must be built at query time (verified 2026-08-05 @ 6d96b7d)
- **AD-4b** — supported by: `src/guidami_ai_patente_ingestor/agents/mappers/norm_reference_describer_mapper.py:51` — `exact_keywords` is populated from an LLM agent's output, confirming it is a generated artifact rather than source data (verified 2026-08-05 @ 6d96b7d)
- **AD-4b** — supported by: `db/init.sql:38` — `text TEXT NOT NULL` on `quiz_questions`, the always-present human-authored field the primary coverage definition uses instead (verified 2026-08-05 @ 6d96b7d)
- **AD-4** — supported by: `db/init.sql:42` — `exact_keywords TEXT[]` as a first-class column, the flattening ADR 0002 performed to make it SQL-queryable (verified 2026-08-05 @ 6d96b7d)
- **AD-4** — supported by: `src/domain/entities/quiz/quiz_question.py:20` — `exact_keywords: list[str] | None`, nullable, which is why FR-2 needs a `not_measurable` bucket (verified 2026-08-05 @ 6d96b7d)
- **AD-5** — supported by: `src/guidami_ai_patente_ingestor/models/quiz/quiz_metadata.py:24` — `embedded_text` returns the joined `vector_search_queries`, showing the query vector is generated from different text than the corpus vector (verified 2026-08-05 @ 6d96b7d)
- **AD-5** — supported by: `src/guidami_ai_patente_ingestor/models/knowledge/embeddable_article_comma.py:22` — corpus `embedded_text` is article title + comma text, the other side of that asymmetry (verified 2026-08-05 @ 6d96b7d)
- **AD-6** — supported by: `.gitignore:167` — `logs` is ignored, so run artifacts alone cannot support cross-commit comparison (verified 2026-08-05 @ 6d96b7d)
- **AD-6** — supported by: `src/commons/observability/run_artifact_writer/run_artifact_writer.py:35` — `RunArtifactWriter` already produces `run.log`, `manifest.json` and `report.md` in a timestamped run directory (verified 2026-08-05 @ 6d96b7d)

## Open Questions

- [ ] **non-blocking** — What minimum lift over the random baseline should trigger the
  `metric_not_discriminating` flag in FR-3? The measured lift is 3.2x; the threshold is a
  calibration choice that does not change the design. — owner: user
- [ ] **non-blocking** — Which document-frequency cutoffs should the FR-2 coverage band
  report? The 2026-08-05 calibration used 1/2/3/5/10/20/50/100/250/500; the informative
  region was 1–20, saturating above 50. — owner: user
- [ ] **non-blocking** — The upper end of the uncovered range (~1060) can only be
  resolved by a judge run over the 901 fragile questions. Worth scheduling once this
  harness has run at least once end to end? — owner: user
- [ ] **non-blocking** — Should the committed summary in FR-7 be checked by CI as a
  regression gate, or only produced for manual inspection? — owner: user
- [ ] **non-blocking** — The one quiz question with `embedding IS NULL` (7098 of 7099) is
  unexplained; it should be identified but does not affect the harness design. —
  owner: investigation

## Sign-off

- **Scope approved by user:** pending
- **Feasibility asserted:** by write-spec on 2026-08-05, based on Feasibility Evidence above

## Changelog

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
