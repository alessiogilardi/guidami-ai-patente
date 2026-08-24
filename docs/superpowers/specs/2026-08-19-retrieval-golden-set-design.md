# Spec 0011: Retrieval Golden Set

| | |
|---|---|
| **Id** | 0011 |
| **Status** | in-progress |
| **Date** | 2026-08-19 |
| **Discussion log** | docs/superpowers/specs/discussions/golden-set-retrieval-evaluation.md |
| **Supersedes / superseded by** | — |

## Problem & Motivation

There is no list of right answers against which corpus retrieval can be measured. The
project has two evaluation paths and neither produces one.

The deterministic harness (`ingest evaluate retrieval`, spec 0007) scores a retrieval as
successful when any LLM-generated `exact_keyword` of a quiz question appears as a
case-insensitive substring inside any of the top-k retrieved commas. A quiz about giving
way to pedestrians on a crossing counts as a hit because the word "precedenza" occurs in
one of dozens of unrelated commas, whether or not the comma that actually justifies the
answer was retrieved at all — and counts as a miss when the justifying comma explains the
rule without using that exact word. The harness also cannot finish: at roughly one second
per question per arm it needs about eight hours over the 7099-question bank, and its last
run was killed after two lines.

The LLM judge (`src/retrieval_evaluation/`, ADR 0013) answers a different question — "do
these commas, taken together, make the answer clear?" — a verdict on the pile. Measuring
retrieval requires knowing *which* comma is the right one, not whether the pile is
convincing.

Without per-question ground truth, no retrieval change can be evaluated: neither the move
to hybrid dense + full-text search, nor a different embedding variant, nor a corpus
extension. Every such decision is currently made on a proxy that is known to be wrong in
both directions.

## Functional Requirements

### FR-1: The corpus text-search vectors are materialized and indexed

`articles` and `article_commas` each carry a stored, generated `tsvector` column with a
GIN index over it, so text search no longer recomputes the vector for the whole corpus on
every query.

**Acceptance criteria:**
- Given a fresh database created from `db/init.sql`, when the schema is inspected, then
  `articles.tsv_title` and `article_commas.tsv_text` exist as `GENERATED ALWAYS AS ...
  STORED` columns and each has a GIN index.
- Given an existing database that predates this change, when
  `db/migrations/0011_retrieval_golden_set.sql` is applied, then the same columns and
  indexes exist and no row of `articles` or `article_commas` has changed in any other
  column.
- Given that migration has already been applied, when it is applied a second time, then
  it completes without error and changes nothing.
- Given an article row, when its `title` is updated, then `tsv_title` reflects the new
  title without any application code writing to that column.
- Given a comma row, when its `text` is updated, then `tsv_text` reflects the new text
  without any application code writing to that column.
- Given the populated corpus, when a text search is executed against the indexed columns,
  then the query plan uses a bitmap index scan over at least one of the two GIN indexes
  rather than a sequential scan of `article_commas`.

### FR-2: Full-text retrieval returns a ranked top-k of commas

`CorpusReadRepository` exposes a method that returns the `k` commas ranked highest by
weighted `ts_rank_cd` against a caller-supplied lexeme list, ordered best first and broken
by a deterministic tiebreaker, using the materialized columns from FR-1.

**Acceptance criteria:**
- Given a lexeme list and a `k`, when the method is called, then at most `k` commas are
  returned, ordered by descending text-rank score.
- Given a lexeme list that matches nothing in the corpus, when the method is called, then
  an empty list is returned and no exception is raised.
- Given a comma whose parent article title matches a lexeme and whose own text does not,
  when the method is called, then that comma is eligible for the result (title band A
  participates in matching, not only in scoring).
- Given the same lexeme list and `k` twice against an unchanged corpus, when the method is
  called, then the two results are identical in content and order.
- Given two matching commas with the same text-rank score, when they are ordered, then the
  one with the lower `article_commas.id` precedes the other.
- Given a lexeme list whose matches at rank `k` share their score with further matches
  beyond `k`, when the method is called under two different query plans that return the
  same match set, then the two results are still identical in content and order.

### FR-3: A retrieved comma carries its database identifier

`RetrievedComma` exposes the `article_commas.id` of the row it was read from, on every
retrieval path that produces it.

**Acceptance criteria:**
- Given any comma returned by dense, text, or random retrieval, when it is inspected, then
  its identifier equals the `id` of the `article_commas` row it was read from.
- Given a retrieved comma, when a caller needs the database row it refers to, then the
  identifier is available without issuing a second query to look the comma up by its
  citation.

### FR-4: The text-search query is built from the question's own text, without an LLM

For a quiz question, the lexemes given to FR-2 are extracted by Postgres from the
concatenation of `topic`, `text`, and `image_description`, and are combined disjunctively.

**Acceptance criteria:**
- Given a question with an image description, when its lexeme list is built, then the list
  contains lexemes originating from all three fields.
- Given a question with no image description, when its lexeme list is built, then the list
  is built from `topic` and `text` alone and no error is raised.
- Given a question whose text contains Italian stop words, when its lexeme list is built,
  then those stop words are absent from the list.
- Given a question whose text contains punctuation that the `websearch_to_tsquery` syntax
  would interpret as an operator (a leading hyphen, quotation marks, the token `or`), when
  its lexeme list is built, then no lexeme is negated, grouped, or otherwise removed as a
  result of that punctuation.
- Given a lexeme list of two or more entries, when it is turned into a text-search query,
  then a comma matching only one of the lexemes is still eligible to be returned.
- Given the labeling run configuration, when the lexeme-building strategy is changed, then
  it is changed through configuration and requires no change to the retrieval or labeling
  code.

### FR-5: Candidates are the union of a dense arm and a text arm

For each quiz question, the candidate set submitted for labeling is the deduplicated union
of the top 50 commas from dense retrieval on the `topic_text` variant and the top 50 commas
from FR-2 text retrieval on the FR-4 lexemes.

**Acceptance criteria:**
- Given a question, when its candidate set is built, then every comma in the top 50 of
  either arm is present in the set exactly once.
- Given a comma returned by both arms, when the candidate set is built, then it appears
  once, not twice.
- Given a question for which one arm returns fewer than 50 commas, when the candidate set
  is built, then the set contains whatever that arm returned plus the other arm's results,
  and no error is raised.
- Given a question, when its candidate set is built, then the set is not truncated to the
  top-k of a fused ranking — its size is that of the full union.
- Given the two arm depths, when they are changed, then they are changed through
  configuration and recorded on the run (FR-11).
- Given a question and an unchanged corpus, when its candidate set is built twice, then the
  two sets contain exactly the same commas — neither arm's cut at its depth may vary
  between runs when scores tie at that depth.

### FR-6: Candidates are shuffled deterministically and presented without scores

The candidate set is ordered by a seeded shuffle before being submitted to the judge, and
neither retrieval scores nor arm membership are included in what the judge sees.

**Acceptance criteria:**
- Given a candidate set and a seed, when the presentation order is computed twice, then the
  two orders are identical.
- Given a candidate set of more than one element and two different seeds, when the
  presentation orders are computed, then they differ.
- Given the prompt submitted to the judge, when it is inspected, then it contains no
  cosine distance, no text-rank score, and no indication of which arm retrieved each
  candidate.
- Given the prompt submitted to the judge, when it is inspected, then each candidate
  carries a distinct ordinal number.

### FR-7: The judge names the justifying commas by number, or names none

For each question, the judge returns the ordinal numbers of at most three candidates that
justify the correct answer, together with a rationale; returning an empty list is a valid,
first-class outcome meaning no comma in the corpus justifies the question.

**Acceptance criteria:**
- Given a question whose answer is justified by a candidate, when the judge responds, then
  the response contains that candidate's ordinal number and a non-empty rationale.
- Given a question no candidate justifies, when the judge responds, then the response
  contains an empty list of numbers and a non-empty rationale, and this is not treated as
  an error or a retry condition.
- Given a judge response naming more than three numbers, when it is validated, then
  validation fails rather than silently truncating.
- Given a judge response naming the same number more than once, when it is validated, then
  validation fails rather than deduplicating, so the model is given the chance to correct
  itself rather than having a repetition silently absorbed.
- Given a judge response naming two or more numbers, when they are recorded, then their
  order is the judge's own ordering, most-justifying first.
- Given a judge response naming a number outside the range of the presented candidates,
  when it is processed, then the run fails for that question with an explicit error rather
  than recording a label.
- Given a judge response, when its numbers are resolved, then each maps to exactly one
  `article_commas.id` via the presented candidate list, with no lookup by citation string.

### FR-8: The golden set is persisted in Postgres across three tables

A labeling run writes one `labeling_runs` row, one `quiz_labelings` row per labeled
question, and one `quiz_comma_labels` row per chosen comma.

**Acceptance criteria:**
- Given a question the judge labeled with two commas, when the tables are queried, then
  one `quiz_labelings` row exists for it with the judge's rationale, and exactly two
  `quiz_comma_labels` rows reference it.
- Given a question the judge labeled with no comma, when the tables are queried, then one
  `quiz_labelings` row exists for it and zero `quiz_comma_labels` rows reference it.
- Given a question that was never submitted, when the tables are queried, then no
  `quiz_labelings` row exists for it — distinguishing it from the preceding case.
- Given a labeled question, when its outcome is determined, then it is determined by
  counting its `quiz_comma_labels` rows, with no outcome column that could contradict them.
- Given a labeling run, when a second run is executed, then the first run's rows remain
  readable and unmodified, and both are retrievable by their run identifier.
- Given the same question labeled twice in one run, when the second insert is attempted,
  then the uniqueness constraint on `(run_id, quiz_question_id)` rejects it.

### FR-9: Each labeled comma records the rank each arm gave it

Every `quiz_comma_labels` row carries the position the comma held in the dense arm and in
the text arm, null where that arm did not retrieve it.

**Acceptance criteria:**
- Given a comma retrieved by both arms, when its label row is inspected, then both rank
  columns hold its one-based position in the respective arm.
- Given a comma retrieved only by the text arm, when its label row is inspected, then the
  dense rank is null and the text rank holds its position.
- Given a comma retrieved only by the dense arm, when its label row is inspected, then the
  text rank is null and the dense rank holds its position.
- Given an attempt to insert a label row with both ranks null, when it is executed, then a
  check constraint rejects it.
- Given a completed run, when the labeled commas are queried, then the count of
  text-arm-only, dense-arm-only, and both-arm labels is obtainable in a single SQL query
  with no retrieval re-execution.

### FR-10: A run labels the entire quiz bank, unless explicitly limited

By default the labeling entry point processes every quiz question that has a `topic_text`
vector, with bounded concurrency, and does not sample. A run may be explicitly restricted to
a subset for a trial pass; when it is, the restriction is recorded on the run so a limited
run is never mistaken for a complete or an interrupted one.

**Acceptance criteria:**
- Given the populated database, when a labeling run completes with no explicit limit, then a
  `quiz_labelings` row exists for every quiz question that has a `topic_text` vector.
- Given a run restricted to `n` questions, when it completes, then it labels at most `n`
  questions and its row records the requested limit; given a run with no restriction, then
  that record is absent.
- Given a restriction and a shuffle seed, when the same restricted run is executed twice
  against an unchanged bank, then both select the same subset of questions.
- Given a run in progress, when the number of concurrent judge calls is observed, then it
  never exceeds the configured concurrency bound.
- Given a run, when it is executed, then it writes a per-run log file under `logs/`
  following the module's existing convention.

### FR-11: Every run records the provenance needed to reproduce it

The `labeling_runs` row carries the judge model, a prompt version derived from the prompt
text itself, the candidate variant, both arm depths, the shuffle seed, any explicit question
limit (FR-10), and the corpus state at run time.

**Acceptance criteria:**
- Given a completed run, when its row is inspected, then the judge model, candidate
  variant, dense depth, text depth, shuffle seed, corpus commit and corpus comma count are
  all present and non-null.
- Given two runs executed with an unmodified prompt, when their rows are compared, then
  their prompt versions are equal.
- Given two runs executed with a modified prompt, when their rows are compared, then their
  prompt versions differ, without any human having edited a version field.
- Given a completed run, when its shuffle seed and arm depths are read, then the candidate
  set and presentation order shown to the judge for any question of that run can be
  reconstructed against the same corpus state.

### FR-12: The labeler is a second entry point of the existing judge module

The labeling run is invoked as a named script that lives in `src/retrieval_evaluation/`,
reusing that module's agent infrastructure, wiring and configuration.

Because FR-7's response shape differs from the existing judge's, the labeler adds its own
agent subpackage alongside `retrieval_judge/` rather than modifying it: "reusing" means
`BaseAgent`, the YAML agent-config loading and the wiring builders — not the
`RetrievalJudgeAgent` class itself, which `BaseAgent` binds to a single `output_type` and
which the last acceptance criterion below requires to keep its current behavior.

**Acceptance criteria:**
- Given the project scripts, when they are listed, then a labeling entry point is
  registered under `[project.scripts]` in `pyproject.toml`.
- Given the labeler's agent, when it is inspected, then it is a distinct `BaseAgent`
  subclass from `RetrievalJudgeAgent`, with its own request/response DTOs and its own
  prompt file.
- Given the labeler, when its imports are inspected, then it does not import any
  underscore-prefixed module from `guidami_ai_patente_ingestor`.
- Given the labeler's write path, when it is inspected, then it issues `INSERT` statements
  only — no `UPDATE`, no upsert, no `DELETE`, no DDL.
- Given the existing `evaluate-retrieval-judge` entry point, when the labeler is added,
  then that entry point still runs and its behavior is unchanged.

## Non-Goals

- **Rewriting the evaluation metrics** (discussion D-4/D-5: dropping `is_hit`/`hit@k`/the
  random baseline/`hit_adherence_association`, adding recall@k, MRR and nDCG, and the
  per-image weighting). Those metrics consume the golden set and cannot be built before it
  exists; they belong to a follow-up spec. The fate of
  `EvaluationArtifactWriter.write_judge_export` (spec 0007 FR-9) is decided there, not here.
- **Measuring judge self-consistency.** Deliberately deferred: AD-5's historization already
  makes it a join between two run identifiers whenever it is wanted, so nothing about this
  spec needs to anticipate it.
- **Any human-validation gate on the labels.** Discussion D-3: the user spot-checks when
  they choose to; no quota, no blocking check. The consequence — an unmeasured judge
  accuracy — is recorded as an open question, not designed away.
- **A human-readable export of the golden set.** Discussion D-17 withdraws the readable
  file D-3 had asked for; spot-checking is done with ad-hoc SQL. The data lives in
  Postgres, so an export remains addable later without touching schema or labeler.
- **Comparing embedding variants.** D-9 freezes the design on `topic_text`; the labels
  describe what the frozen design can reach, and are not a neutral referee between variants.
- **An approximate-nearest-neighbour index on `article_commas.embedding`.** Dense retrieval
  stays exact, so labels carry no approximation noise.
- **Serving retrieval to an end user.** The FR-1 index is required by production later, but
  no query path for the future FastAPI app is built here.

## Architectural Decisions

### AD-1: Labels are attached to commas, not to articles
- **Rationale:** corpus embeddings are per comma, so retrieval returns commas. An
  article-level label would force retrieved commas to be collapsed into articles before
  measuring, and with articles holding up to 32 commas, "the right article was found" is a
  target wide enough to inflate recall without saying anything about retrieval.
- **Rejected alternatives:** article-level labels — larger judge prompt and a more
  permissive metric; judging whole articles but persisting comma-level labels — kept in
  reserve should the judge prove unable to discriminate between neighbouring commas of the
  same article, but not adopted without evidence that it is needed.

### AD-2: Candidates come from one dense variant, `topic_text`
- **Rationale:** the six-variant union of the earlier design existed to keep labels neutral
  in a comparison between variants. This spec freezes the production design (dense
  `topic_text` + FTS fused by RRF), so there is no comparison left to arbitrate; labels
  must instead cover what the chosen design can reach, with margin. Labels drawn at depth
  50 per arm against quality measured at k=10 give a 10x margin.
- **Rejected alternatives:** two variants (`topic_text` + `combined_description`) — measured
  at 0.82 Jaccard overlap on their top-10, so the second adds almost nothing over the first;
  the six-variant union — solves a problem that no longer exists, at five extra queries per
  question.

### AD-3: The candidate set is the union of both arms, never the top-k of an RRF fusion
- **Rationale:** RRF ranks the union; taking its top-k would discard the lower half, which
  consists almost entirely of commas found by a single arm and placed low — precisely the
  cases where fusion errs and which the golden set exists to expose. Labeling from a fused
  top-k lets the ranking under test select its own exam.
- **Rejected alternatives:** dense-only candidates — a comma only FTS can find would never
  be seen by the judge, would be labeled "no justifying comma", and FTS would then be
  scored as an error for doing its job; top-k of the fused list — the circularity above.

### AD-4: Candidates are shuffled with a recorded seed and shown without scores
- **Rationale:** presented in rank order, an LLM judge preferentially picks from the top —
  position bias. The resulting golden set would agree with the ranking it is meant to
  measure, and recall@10 would come out high for reasons unrelated to retrieval quality.
  The seed is stored because without it the candidate ordering the judge saw cannot be
  reconstructed.
- **Rejected alternatives:** presenting in rank order — position bias; presenting scores as
  a hint to the judge — same bias by another route, and the scores are diagnostic data for
  the engineer, not evidence for the judge.

### AD-5: Three tables, with labels historized per run
- **Rationale:** the load-bearing assumption of the whole effort — that the judge's
  citation-level labels are accurate enough to serve as ground truth — is unverified and
  ungated. Comparing two judge runs, or two prompt versions, is a join between run
  identifiers when runs coexist and is not expressible at all when the second overwrites
  the first. The cost is a normalized run table and a run predicate on reads.
- **Rejected alternatives:** two tables keyed uniquely by question with provenance
  denormalized onto each row — simpler reads, but duplicates provenance 7099 times and
  destroys the previous labeling on every re-run, removing the only quality control
  available on the load-bearing assumption.

### AD-6: The "no justifying comma" outcome is the absence of child rows, not a column
- **Rationale:** a `quiz_labelings` row records that a question was labeled; its
  `quiz_comma_labels` children record what was chosen. Zero children therefore means "the
  corpus does not justify this question", and is distinct from a missing row, which means
  "never labeled". An explicit outcome column could contradict the children, and the
  constraint spans two tables so no `CHECK` can prevent it.
- **Rejected alternatives:** a sentinel row with a nullable comma reference and a flag — one
  table fewer, but the foreign key becomes nullable and every query must defend against the
  special case; no state row at all — erases the distinction between "the comma exists and
  was not found" (a retrieval problem) and "the comma does not exist" (a corpus problem),
  which have opposite remedies.

### AD-7: Each label stores the rank each arm gave that comma
- **Rationale:** both arm result lists are already in memory when the union is built, so
  capturing the ranks costs nothing; reconstructing them later would mean re-running
  retrieval against a corpus that may have moved, and the rank is a property of the run, not
  of the comma. It makes "does FTS earn its place?" a single SQL query, and yields per-arm
  recall@k and MRR as a filter on the rank.
- **Rejected alternatives:** storing only the fused rank — not decomposable back into arms,
  and it would freeze the RRF constant into the data; storing nothing and re-deriving later
  — conflates retrieval drift with corpus drift.

### AD-8: The tsvector is two generated columns, one per table, not one populated by UPDATE
- **Rationale:** the weighting in use spans two tables (article title in band A, comma text
  in band B) and a generated column can only read its own row, so it cannot be a single
  column. Generated columns update themselves on every insert and update, so the write path
  is untouched and the vector cannot fall behind the text — which with a one-off `UPDATE`
  is a question of when, not whether. `to_tsvector` with an explicit configuration argument
  is `IMMUTABLE`, so `STORED` is legal.
- **Rejected alternatives:** a single column on `articles` populated by `UPDATE` — `articles`
  holds no text, so it would index titles only, and it needs write-path maintenance;
  a materialized view over the join — a third object to refresh, with the same staleness
  problem and no compensating benefit.

### AD-9: Lexemes are extracted with `to_tsvector` and OR-joined, not parsed by `websearch_to_tsquery`
- **Rationale:** `websearch_to_tsquery`, like `plainto_tsquery`, combines terms with AND;
  over a 15-to-25-word question that means near-zero matches, and the repository already
  settled on disjunction. It is also a parser for human input: it reads punctuation as
  operators, so machine-built text can silently negate or group a term. Extracting lexemes
  with `to_tsvector` gets stop-word removal and stemming from the same dictionary while
  leaving the combination explicit and inspectable.
- **Rejected alternatives:** `websearch_to_tsquery`/`plainto_tsquery` — the two defects
  above; hand-rolled tokenisation and stop-word removal in Python — would drift from the
  dictionary the index is built with, which is the one way to make the index return wrong
  results rather than slow ones.

### AD-10: The labeler stays in `src/retrieval_evaluation/` and writes through an insert-only repository
- **Rationale:** the module's name still describes what it does — building ground truth is
  part of evaluating retrieval — so renaming would be churn across imports and an ADR for no
  gain. Because AD-5 historizes, a labeling is never updated, only inserted, so the write
  path needs no upsert base class: a dedicated repository over `PostgresClient` suffices,
  without promoting the ingestor's private upsert base into `commons` and without reaching
  into another package's private module.
- **Rejected alternatives:** a new `ingest label` subcommand — would inherit run artifacts
  and dry-run for free, but drags manifest machinery onto an offline job that runs
  occasionally; a third top-level package — duplicates wiring and configuration for no
  separation; promoting `UpsertStoreRepository` into `commons` — unnecessary once the write
  path is insert-only, and it would make a read-only package writable.

### AD-11: The prompt version is derived from the prompt text, not assigned by hand
- **Rationale:** a manually maintained version field is one nobody updates, and a prompt
  changed under an unchanged version makes two runs silently incomparable — the exact
  failure the field exists to prevent. Deriving it from the text makes equal versions mean
  equal prompts by construction.
- **Rejected alternatives:** a manual string in configuration — readable, but relies on
  discipline for the property that matters; the git commit of the prompt file — changes when
  unrelated files change, and is undefined with a dirty working tree.

### AD-12: The judge addresses candidates by ordinal number, resolved through the in-memory list
- **Rationale:** the presented candidate list is already held in memory with each comma's
  database identifier (FR-3), so a returned number resolves to an identifier by lookup. A
  number outside the range is detectable, which makes a hallucinated citation a hard error
  instead of a silent wrong label.
- **Rejected alternatives:** returning citation strings and searching the corpus for them
  — reconstructs by query a value already in hand, and a malformed or invented citation
  either fails to resolve or, worse, resolves to the wrong comma.

### AD-13: Text matching is a union of two single-relation branches, never a cross-table `OR`
- **Rationale:** a predicate whose two `OR` branches reference different relations cannot be
  pushed into either table's index scan — restricting one table alone would drop rows the
  other branch matches — so PostgreSQL evaluates it as a post-join filter and neither GIN
  index is ever used. Matching each relation separately and unioning the resulting comma ids
  keeps both branches index-driven, and is provably equivalent: the union of "commas whose
  article title matches" and "commas whose own text matches" is exactly the set the `OR`
  returns.
- **Rejected alternatives:** the cross-table `OR` — measured to produce a join filter under
  every variant tried (forced join methods, post-`ANALYZE`, inlined predicate), which is why
  this AD exists; matching on `c.tsv_text` alone — single-relation and therefore
  index-usable, but it destroys FR-2's requirement that a comma be reachable through its
  article's title, which is the case the text arm exists to cover; denormalising the article
  title onto `article_commas` — a generated column cannot read another table, so this needs a
  trigger or a materialized view, both already rejected under AD-8.

### AD-14: Every ranked retrieval breaks ties on `article_commas.id`
- **Rationale:** `ts_rank_cd` is coarse on this corpus — a representative query yields 444
  matches across only 17 distinct scores, with 39 rows sharing the score at rank 50 — so
  `ORDER BY score DESC LIMIT k` alone leaves the cut to whatever order the plan happens to
  produce. That is not merely a flaky test: FR-5 takes each arm's top rows as the candidate
  set, so an arbitrary cut silently changes which commas the judge is allowed to see, and
  FR-9 records a rank that would be a position inside an arbitrary tie group.
- **Rejected alternatives:** no tiebreaker — the defect above; tie-breaking on `citation` or
  another derived string — same determinism, more work per row, and it collates by locale;
  returning all rows tied at the cut instead of exactly `k` — defensible, and it would make
  the depth honest rather than arbitrary, but it makes the candidate-set size unbounded and
  is a change to FR-5's contract rather than a fix to this defect.

## Data Model

Three new tables plus two generated columns. All of it is delivered as an idempotent,
transactional migration under `db/migrations/0011_retrieval_golden_set.sql`, with
`db/init.sql` updated in the same change (ADR 0010).

**Generated search columns (FR-1, AD-8)**

- `articles.tsv_title` — `tsvector GENERATED ALWAYS AS (setweight(to_tsvector('italian',
  title), 'A')) STORED`, with a GIN index.
- `article_commas.tsv_text` — `tsvector GENERATED ALWAYS AS (setweight(to_tsvector('italian',
  text), 'B')) STORED`, with a GIN index.

Ranking concatenates the two at query time (`a.tsv_title || c.tsv_text`). Matching does
**not** use a cross-table `OR`: see AD-13 — such a predicate is evaluated after the join and
can never become an index condition, so the two branches are matched separately and unioned.

**`labeling_runs`** — one row per run (FR-11, AD-5)

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGSERIAL PK` | |
| `judge_model` | `TEXT NOT NULL` | |
| `prompt_version` | `TEXT NOT NULL` | derived from the prompt text (AD-11) |
| `candidate_variant` | `TEXT NOT NULL` | `topic_text` |
| `dense_k` | `INT NOT NULL` | 50 |
| `text_k` | `INT NOT NULL` | 50 |
| `shuffle_seed` | `BIGINT NOT NULL` | reconstructs presentation order (AD-4) |
| `corpus_commit` | `TEXT NOT NULL` | |
| `corpus_comma_count` | `INT NOT NULL` | |
| `question_limit` | `INT` | the limit **requested** (FR-10); null for a full pass |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

`question_limit` records what was asked for, not what was reached: the number of questions
actually labeled is the count of `quiz_labelings` rows, so storing it too would duplicate a
derivable value (AD-6's principle). Together with `shuffle_seed` it is what reconstructs
which subset a trial run saw.

**`quiz_labelings`** — one row per labeled question (FR-8, AD-6)

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGSERIAL PK` | |
| `run_id` | `BIGINT NOT NULL` | FK `labeling_runs (id) ON DELETE CASCADE` |
| `quiz_question_id` | `BIGINT NOT NULL` | FK `quiz_questions (id) ON DELETE CASCADE` |
| `rationale` | `TEXT NOT NULL` | present for both outcomes |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

`UNIQUE (run_id, quiz_question_id)`. No outcome column: the outcome is the count of
children (AD-6).

**`quiz_comma_labels`** — one row per chosen comma (FR-8, FR-9, AD-7)

| Column | Type | Notes |
|---|---|---|
| `labeling_id` | `BIGINT NOT NULL` | FK `quiz_labelings (id) ON DELETE CASCADE` |
| `article_comma_id` | `BIGINT NOT NULL` | FK `article_commas (id) ON DELETE CASCADE` |
| `judge_rank` | `INT NOT NULL CHECK (judge_rank > 0)` | the judge's own ordering, most-justifying first (FR-7) |
| `dense_rank` | `INT` | null when the dense arm did not retrieve it |
| `text_rank` | `INT` | null when the text arm did not retrieve it |

The three rank columns are deliberately parallel: one per source that had an opinion about
this comma — the dense arm, the text arm, and the judge. Only `judge_rank` is mandatory,
because a labeled comma always has a place in the judge's ordering while it may have been
found by only one arm.

`PRIMARY KEY (labeling_id, article_comma_id)`, plus
`CHECK (dense_rank IS NOT NULL OR text_rank IS NOT NULL)` — a labeled comma that came from
neither arm was not among the candidates, which is a bug or a hallucinated citation, and is
rejected rather than recorded — plus `UNIQUE (labeling_id, judge_rank)`: two commas sharing
a rank is a self-contradictory ordering, and unlike AD-6's cross-table case this constraint
lives inside one table, so the database can actually enforce it.

The three-labels-maximum of FR-7 is deliberately not a database constraint: it is a prompt
policy, enforced on the judge response model, and encoding it in the schema would freeze a
prompt choice into the data.

## Constraints

- Schema changes ship as an idempotent, transactional script under `db/migrations/`, named
  after this spec, with `db/init.sql` updated in the same change (ADR 0010). A wipe-and-
  re-ingest is not acceptable: the database holds paid-for embeddings.
- The Italian text-search configuration is used everywhere, and the existing A/B band
  weighting (article title / comma text) is not redefined.
- Dense retrieval stays exact; vector parameters keep the mandatory `%s::vector` cast.
- No LLM call takes part in building the text-search query (FR-4).
- New table names are configuration values on `IngestorConfig`, consistent with the
  existing `*_table` settings, not literals in SQL.
- The labeler runs offline and by hand; it does not enter the `ingest` CLI, and inherits no
  manifest, report, or dry-run machinery.
- Python 3.12+, `uv` for every invocation, `pytest` with `@pytest.mark.integration` for
  anything touching Postgres, tests mirroring `src/` under `tests/` with no `__init__.py`.
- ADR 0013 must be amended or superseded in the same change: its premises — an exploratory
  judge, more expensive than the deterministic harness — are contradicted by this spec,
  which makes the module write a persistent artifact.

## Feasibility Evidence

> Anchors re-verified 2026-08-20 against the working tree at `2dd56724`. Line numbers that
> shifted under phase 1's own edits (`corpus_read_repository.py`, `db/init.sql`,
> `retrieved_comma.py`, `retrieval_judge_evaluation_service.py`, `quiz_question.py`,
> `wiring.py`) were refreshed in place; every underlying claim was re-checked and still
> holds, except AD-12's, which phase 1 has now satisfied rather than contradicted — see its
> entry.

- **AD-1** — supported by: `db/init.sql:31` and `db/init.sql:33` — `article_commas` holds both `text` and `embedding VECTOR(1536)` while `articles` holds only `title` (`db/init.sql:12`), so retrieval granularity is the comma (verified 2026-08-20 @ 2dd56724)
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/services/quiz/quiz_variant_registry.py:32` — `_topic_text_spec` composes `topic`, `text` and `image_description`, and is registered as the `topic_text` variant at line 65 (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-3** — supported by: `src/commons/repositories/db/corpus_read_repository.py:97` — `dense_top_k` already provides the dense arm at arbitrary `k`, so the union needs only the text arm of FR-2 (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-4** — supported by: `src/retrieval_evaluation/services/retrieval_judge_evaluation_service.py:66` — the judge request is built from `dense_top_k` output in rank order today, with no shuffle, which is the behavior this decision changes (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-5** — supported by: `db/init.sql:47` — `quiz_questions.id` is the `BIGSERIAL` the new tables reference, and `db/migrations/0008_quiz_query_representations.sql:1` shows the migrations directory already carries a spec-named script (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-6** — supported by: `src/domain/entities/quiz/quiz_question.py:9` — the project's entity convention already refuses fields that are structurally always-absent on the write path; deriving the outcome from child rows applies the same principle to the schema (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-7** — supported by: `src/commons/repositories/db/corpus_read_repository.py:182` — the text arm, like the dense arm, returns an ordered `list[RetrievedComma]`, so each comma's one-based position in its arm is available in memory at union time (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-8** — supported by: `db/init.sql:8` — `articles` has no text column, only `title`, so a single generated column there would index titles alone; the A/B weighting to reproduce is at `src/commons/repositories/db/corpus_read_repository.py:19` (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-9** — supported by: `src/commons/repositories/db/corpus_read_repository.py:25` — `_to_tsquery_param` OR-joins lexemes with the explicit comment "AD-3: OR, never AND", the convention this decision preserves (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-10** — supported by: `src/guidami_ai_patente_ingestor/repositories/db/__init__.py:1` — `UpsertStoreRepository` lives in the underscore-prefixed `_upsert_store_repository.py` and is not re-exported (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-10** — supported by: `src/commons/clients/postgres_client.py:72` — `execute_many_returning` already supports the insert-and-return-id chain the three tables need, over the read-only-declared `src/commons/repositories/db/__init__.py` (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-11** — supported by: `src/retrieval_evaluation/wiring.py:56` — the judge's prompt is loaded from `retrieval_judge.yaml` through `YamlRepository`, so the prompt text is in hand at wiring time and can be hashed without a new source of truth (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-13** — supported by: `db/init.sql:24` and `db/init.sql:43` — the two GIN indexes exist; measured against the populated dev corpus, the cross-table `OR` plan contains no index condition on either while the union form yields `Bitmap Index Scan on idx_articles_tsv_title` and `on idx_article_commas_tsv_text`, both forms returning the identical 444-row match set (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-14** — supported by: `src/commons/repositories/db/corpus_read_repository.py:177` — the existing `text_top_k` orders by score alone with no tiebreaker, the shape this decision forbids for the new method; measured on the dev corpus, one representative query returns 444 matches over 17 distinct scores with 39 rows tied at rank 50 (verified 2026-08-19, re-verified 2026-08-20 @ 2dd56724)
- **AD-12** — supported by: `src/domain/models/retrieval/retrieved_comma.py:13` — `RetrievedComma` now carries `id`, the `article_commas.id` of the row it was read from, alongside the derived `citation` property. At spec time it carried only `citation`, which is why FR-3 added the identifier; phase 1 delivered it, so the in-memory ordinal-to-id resolution this decision relies on is no longer prospective but available (re-verified 2026-08-20 @ 2dd56724)

## Open Questions

- [ ] **non-blocking** — Judge accuracy at citation level is unverified, and this spec adds
      no gate on it (discussion D-3). It is the load-bearing assumption of the whole effort,
      and there is a documented counter-example under the *current* prompt (quiz 19231:
      right verdict, wrong comma cited). AD-2/AD-3/AD-4 all reduce the risk; none measures
      it. Every metric later built on this golden set must carry "unvalidated ground truth"
      in the artifact that reports it. — owner: user
- [x] **non-blocking — answered 2026-08-20** — How many distinct commas the 50+50 union
      actually yields: **median 90**, measured over a 25-question sample during phase 1.
      This supersedes the median of 117 quoted here previously, which came from a different
      construction (six dense variants at depth 50). It moves the cost estimate, not a
      decision. — owner: investigation
- [ ] **non-blocking** — The full-pass cost estimate (~$15, ~70 minutes) is extrapolated
      linearly from a 10-question run at concurrency 8 with a much smaller prompt.
      — owner: investigation
- [ ] **non-blocking** — Whether ADR 0013 is amended or superseded (the Constraints section
      requires one of the two, not which). — owner: user
- [ ] **non-blocking** — Dropping the human-readable export (discussion D-17) raises the
      friction of the only quality control the project has over its load-bearing
      assumption. Recoverable at any time from the tables. — owner: user
- [ ] **non-blocking** — Whether questions with a figure are measurable against this corpus
      at all: the corpus covers sign *classification*, but a sign-recognition question may
      be justified mainly by the image description and by no comma in particular. Affects
      how the follow-up metrics spec reports that population, not this spec's labeling.
      — owner: investigation

## Sign-off

- **Scope approved by user:** Alessio Gilardi, 2026-08-19 (re-approved same day for the AD-13/AD-14 amendment)
- **Feasibility asserted:** by write-spec on 2026-08-19, based on Feasibility Evidence above

## Changelog

### 2026-08-19 — AD-13 and AD-14 added; FR-2/FR-5 acceptance criteria extended

**What changed.** Two architectural decisions were added and the Data Model's description
of the matching predicate was corrected.

- **AD-13** — text matching is a union of two single-relation branches, not a cross-table
  `OR`. The Data Model previously asserted that testing `a.tsv_title @@ q OR c.tsv_text @@ q`
  kept "both indexes usable". That claim is false and has been removed.
- **AD-14** — every ranked retrieval breaks ties on `article_commas.id`. FR-2 gained two
  acceptance criteria (explicit tiebreaker; stability across plans that return the same match
  set) and FR-5 gained one (the candidate cut is identical across runs).

**Why.** Implementation of the phase 1 plan's T-4 stalled on FR-1's acceptance criterion
requiring a bitmap index scan. Investigation against the populated dev corpus established
two independent defects in this spec:

1. A cross-table `OR` cannot become an index condition — restricting either table alone
   would drop rows the other branch matches, so PostgreSQL must evaluate it after the join.
   Measured: the `OR` form produces a join filter and no index condition; the union form
   produces a bitmap index scan on each GIN index; both return the identical 444-row match
   set.
2. `ts_rank_cd` is coarse enough on this corpus (444 matches, 17 distinct scores, 39 rows
   tied at rank 50) that `LIMIT k` without a tiebreaker leaves the cut to the plan. This was
   never a test-only concern: FR-5 turns each arm's cut into the judge's candidate set, and
   FR-9 records a rank inside that cut.

**Correction to the record.** The escalation that surfaced defect 1 also claimed the `OR`
form performs "similarly to not having the GIN indexes at all". Measurement contradicts
that: legacy on-the-fly tsvector 243.7 ms, `OR` form 10.1 ms, union form 7.3 ms. The
generated columns of FR-1 deliver their gain under either shape; the case for AD-13 rests
on FR-1's acceptance criterion and on headroom as the corpus grows, not on present-day
latency. Defect 2 was not part of that escalation.

**Status.** Kept at `ready` rather than dropped to `draft`: the amendment was described in
full to the user before being written, and authorised in the same exchange.

### 2026-08-20 — plan executed: docs/superpowers/plans/2026-08-19-retrieval-golden-set-phase1-plan.md

- **DoD result:** all runnable items verified mechanically. T-1's three test specs and
  T-2's one all exist and pass by name; `uv run pytest` 658 passed; `uv run pytest -m
  integration` 51 passed, 1 skipped; `uv run ruff check src tests` and `uv run pyright`
  both clean. **One item not mechanically verifiable:** file discipline. No work from
  either phase 1 plan is committed, so `git diff HEAD` cannot separate this plan's tasks
  from the pre-regeneration work the plan itself marks `already satisfied` — see
  Deviations.
- **Deviations from plan:** the working tree carries changes beyond T-1/T-2's Files lists
  (`src/commons/repositories/db/corpus_read_repository.py` and its test). All are
  attributable and none is a scope change: (a) `src/domain/models/retrieval/retrieved_comma.py`
  plus the seven test files that construct a `RetrievedComma`, and `db/init.sql` /
  `db/migrations/0011_retrieval_golden_set.sql` — the FR-1/FR-3 work the regenerated plan
  records as `already satisfied`, uncommitted at regeneration time; (b) `docs/architecture.md`,
  `docs/database.md`, `docs/layout.md`, `docs/patterns.md` and the new
  `docs/adr/0015-union-decomposed-cross-relation-text-match.md` — the Second Brain update
  this project's CLAUDE.md mandates for a structural change. Accepted rather than proven:
  a committed baseline would have made this a mechanical check.
- **Learnings:** (1) the 50+50 arm union yields a **median of 90 distinct commas** over a
  25-question sample — the spec's Open Questions still records 117, which was measured over
  a different construction (six dense variants at depth 50); the spec should be corrected at
  its next amendment. (2) Several `path:line` anchors in Feasibility Evidence shifted under
  phase 1's own edits (`corpus_read_repository.py`, `retrieved_comma.py`, `db/init.sql`) —
  mechanical drift only, no acceptance criterion, AD rationale or constraint affected.
  (3) Writing a plan file through a shell heredoc hits the platform's argument-length limit;
  use a file-writing tool for artifacts of this size.
- **Status change:** not flipped to `implemented` — this plan covers only FR-1 … FR-3.
  FR-4 … FR-12 remain, planned in `docs/superpowers/plans/2026-08-19-retrieval-golden-set-phase2-plan.md`. The
  spec was promoted `ready → in-progress`, confirmed by Alessio Gilardi, 2026-08-20.

### 2026-08-20 — Feasibility Evidence anchors refreshed; union-size question answered

**What changed.** Housekeeping only — no requirement, acceptance criterion, architectural
decision or constraint was added, removed or reworded.

- **Feasibility Evidence** — all fifteen anchors re-verified against the working tree.
  Nine `path:line` references had drifted under phase 1's own edits and were refreshed in
  place: AD-1 (`db/init.sql:19` → `:31`/`:33`), AD-3 (`corpus_read_repository.py:48` →
  `:97`), AD-4 (`retrieval_judge_evaluation_service.py:72` → `:66`), AD-5
  (`db/init.sql:33` → `:47`), AD-6 (`quiz_question.py:22` → `:9`), AD-7
  (`corpus_read_repository.py:114` → `:182`), AD-8's weighting anchor (`:18` → `:19`),
  AD-11 (`wiring.py:52` → `:56`), AD-14 (`corpus_read_repository.py:125` → `:177`). The
  six unchanged anchors (AD-2, AD-8's `db/init.sql:8`, AD-9, both AD-10 entries, AD-13)
  were re-checked and re-stamped.
- **AD-12's evidence was rewritten**, not merely renumbered: it asserted that
  `RetrievedComma` "carries no database identifier today … which is why FR-3 adds one".
  Phase 1 implemented FR-3, so the sentence had become false as written. The decision it
  supports is unaffected — the in-memory ordinal-to-id resolution it relies on is now
  available rather than prospective.
- **The union-size Open Question is answered** and marked resolved: median **90** distinct
  commas over a 25-question sample, superseding the median of 117 the entry quoted, which
  was measured over a six-variant construction that no longer applies.

**Why.** The phase 2 extraction's research pass re-verified every anchor and found the
drift. Per the extraction rules this is mechanical drift — no acceptance criterion, AD
rationale or constraint is affected — so it is a Changelog-only amendment.

**Status.** Unchanged at `in-progress`. Nothing here alters the contract, so no
re-approval was required.

### 2026-08-20 — FR-12 clarified: the labeler gets its own agent, not the judge's

**What changed.** FR-12's prose said the labeler reuses "that module's agent, wiring and
configuration". Read literally, that conflicted with FR-7, which requires a response of
ordinal numbers plus a rationale, and with FR-12's own last acceptance criterion, which
requires `evaluate-retrieval-judge` to keep its current behavior. `BaseAgent` binds
`output_type` per class (`src/commons/ai/agents/base_agent.py:22`), so a single agent class
cannot serve both response shapes.

- The prose now reads "reusing that module's agent **infrastructure**", followed by a
  paragraph stating that "reusing" means `BaseAgent`, the YAML agent-config loading and the
  wiring builders — not the `RetrievalJudgeAgent` class.
- **One acceptance criterion was added**: the labeler's agent must be a distinct `BaseAgent`
  subclass from `RetrievalJudgeAgent`, with its own request/response DTOs and its own prompt
  file.

**Why.** The ambiguity was surfaced by the phase 2 extraction, which had to resolve it as a
plan-level decision (PD-7) precisely because the spec left it open. Encoding the resolution
in the spec removes the ambiguity for every later reader instead of leaving it in a
disposable artifact.

**Scope impact.** None. The added criterion makes explicit what the existing criteria
already forced, and matches the phase 2 plan's T-7 as already written — no task gains,
loses, or changes work.

**Status.** Unchanged at `in-progress`. Confirmed by Alessio Gilardi, 2026-08-20 ("non
riusiamo lo stesso agente, ne scriviamo uno nuovo").

### 2026-08-20 — trial-run limit, judge ordering, and duplicate-number rejection

**What changed.** Three amendments, all arising from a grilling pass over the phase 2 plan
whose goal was to remove implementation ambiguity before any code is written.

- **FR-10 reworded** from "processes every quiz question … and does not sample" to a default
  that does exactly that, plus an explicit, recorded restriction for trial passes. The old
  wording forbade the only affordable way to measure this run's real cost: the ~$15/~70-minute
  estimate is extrapolated from a much smaller prompt, and `configs/ingestor_config.test-data.yaml`
  — which the plan had suggested for a cheap trial — retargets *file* layers only and would
  change nothing for a job that reads Postgres. Two acceptance criteria added (the limit is
  recorded; the same limit and seed select the same subset), and the existing criterion is now
  qualified to a run with no limit.
- **`labeling_runs.question_limit INT`** (nullable) added to the Data Model, so a limited run
  is distinguishable from a complete one and from an interrupted one. It records the limit
  *requested*, not reached — the number actually labeled is the count of `quiz_labelings`
  rows, and persisting a derivable value is what AD-6 argues against.
- **`quiz_comma_labels.position` renamed to `judge_rank`**, gaining
  `UNIQUE (labeling_id, judge_rank)`, and FR-7 gained two criteria: the judge's numbers are
  ordered most-justifying first, and a repeated number fails validation instead of being
  deduplicated. `position` recorded an ordering that nothing had asked the judge to produce,
  so a future metric reading "position 1" would have assumed a relevance rank that did not
  exist. The new name also makes the three rank columns parallel — `dense_rank`, `text_rank`,
  `judge_rank`, one per source that had an opinion about the comma.

**Why the duplicate-number criterion is a validation failure rather than an error.** A
repeated number resolves to two labels for one comma and would surface downstream as a
primary-key violation naming neither the quiz nor the judge. Failing validation instead lets
pydantic-ai's existing retry give the model a chance to correct itself — while
deduplicating silently would hide a judge repeating itself, which is precisely the symptom
the unverified-accuracy open question requires us to keep visible.

**Scope impact.** `question_limit` is nullable and `judge_rank` is a rename, so no existing
acceptance criterion is weakened; FR-11's non-null list is unchanged. No architectural
decision was added or revised.

**Status.** Unchanged at `in-progress`. Confirmed by Alessio Gilardi, 2026-08-20, over an
18-question grilling pass on the phase 2 plan.
