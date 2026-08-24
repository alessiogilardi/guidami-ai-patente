<!--
SPEC — the contract. Durable, git-tracked, never deleted (superseded instead).
The user signs scope; the compiling skill asserts feasibility with codebase evidence.
Downstream plans are extracted from this document and reference FR ids: every
requirement must be individually testable and traceable.
Status lifecycle: draft → ready → in-progress → implemented → superseded.
Every status beyond draft is written by the user alone — skills only propose:
draft → ready at sign-off; ready → in-progress when the first plan is extracted;
in-progress → implemented once the Definition of Done is verified.
-->

# Spec 0012: Quiz flow API (propose → check → explain)

| | |
|---|---|
| **Id** | 0012 |
| **Status** | ready |
| **Date** | 2026-08-24 |
| **Discussion log** | — (brainstormed in-session, 2026-08-24) |
| **Supersedes / superseded by** | Supersedes `docs/superpowers/specs/2026-08-19-quiz-check-endpoint-design.md` (mis-numbered "Spec 0011", never signed off — see AD-17). Amends the golden-set decision AD-6 of `2026-08-19-retrieval-golden-set-design.md` (the real Spec 0011) — see AD-10. |

## Problem & Motivation

The end goal of the project is a quiz bot: a question is proposed, the user answers
true/false, the answer is validated, and — on request — the bot explains *why* that
answer is right or wrong by grounding the explanation in the corpus normativo
(CdS + CAP + Regolamento). The user interface will be a Telegram bot, not yet built.

The FastAPI app (`src/guidami_ai_patente/`) today exposes only `GET /health`. Nothing
lets a client obtain a question, submit an answer, or ask for a justification. The data
and the machinery, however, are almost entirely in place:

- `quiz_questions` holds 7099 ingested true/false questions with `topic`, `text`,
  `image_filename` and `correct_answer`.
- `quiz_question_embeddings` holds **precomputed** query vectors per named variant,
  so no embedding needs to be produced at request time.
- `articles` / `article_commas` hold the corpus with `VECTOR(1536)` embeddings and
  GIN-indexed weighted `tsvector` columns.
- `src/retrieval_evaluation/` already implements two-arm candidate retrieval
  (`CandidateSetService`), lexeme extraction (`QuestionLexemeService`), the
  LLM judge (`CommaLabelerAgent`) and golden-set persistence
  (`GoldenSetWriteRepository`).

This spec defines the three-endpoint flow the bot needs, the one genuinely new AI
component (an explanation writer), the schema changes that turn the golden set from an
offline evaluation artifact into a runtime cache with provenance, and the module
boundary that lets production and the evaluation harness share **one** judge.

## Functional Requirements

### FR-1: Propose a quiz question deterministically from a seed

`GET /quiz-questions/random` selects one question from a reproducible permutation of
the bank derived from a caller-supplied seed, so a client storing a single integer can
walk the bank without repeats.

Query parameters: `seed` (string, required), `index` (integer ≥ 0, required),
`topic` (string, optional).

**Acceptance criteria:**
- Given the bank contains at least two questions, when a client requests
  `?seed=abc&index=0` twice, then both responses carry the same `number`.
- Given the same seed, when a client requests `?seed=abc&index=0` and
  `?seed=abc&index=1`, then the two responses carry different `number` values.
- Given two different seeds, when a client walks `index = 0 … N-1` for each, then the
  two resulting sequences of `number` values are not identical. (Stated over the whole
  sequence rather than a single index: two permutations may legitimately agree at one
  position, so a per-index assertion would be flaky.)
- Given any seed, when a client walks `index = 0 … N-1`, then every question matching
  the filter appears exactly once.
- Given `topic=velocità` is supplied, then every question returned across all
  `index` values has `topic = "velocità"`.
- Given `index` is greater than or equal to the number of questions matching the
  filter, then the response is `404 Not Found`.
- Given any successful response, then the body contains `number`, `topic`, `text` and
  `image_url`, and **contains no `correct_answer` field**.
- Given the question has no `image_filename`, then `image_url` is `null`.
- Given the question has an `image_filename`, then `image_url` is the absolute path of
  the FR-12 endpoint for that file.

**Accepted limitation (AD-18):** the permutation is derived from the current set of
`quiz_questions.id` values, so adding or removing questions shifts it. A client walking
the bank across a re-ingestion may therefore see a question twice or skip one. Bot
sessions last minutes and bank regeneration is a rare, deliberate event, so this is
accepted rather than mitigated.

### FR-2: Fetch a specific question by number

`GET /quiz-questions/{number}` returns the same projection as FR-1 for an explicitly
named question, so a restarted client can recover the question it had proposed.

**Acceptance criteria:**
- Given a `quiz_questions` row exists with `number = "0001"`, when a client requests
  `GET /quiz-questions/0001`, then the response is `200 OK` and the body carries that
  row's `number`, `topic`, `text` and `image_url`, in the same shape as FR-1.
- Given the same row, then the response body **contains no `correct_answer` field**.
- Given no row matches, then the response is `404 Not Found`.

### FR-3: Check a submitted answer against the stored correct answer

`POST /quiz-questions/{number}/check` with body `{"answer": bool}` compares the
submitted boolean against the persisted `correct_answer`.

**Acceptance criteria:**
- Given a row exists with `number = "0001"` and `correct_answer = true`, when the
  client sends `{"answer": true}`, then the response is `200 OK` and `correct` is
  `true`.
- Given the same row, when the client sends `{"answer": false}`, then the response is
  `200 OK` and `correct` is `false`.
- Given no row matches `number`, then the response is `404 Not Found`.

### FR-4: The check response advertises explanation availability

The check response carries `explanation_status`, so the client knows which affordance
to present before requesting an explanation.

`explanation_status` ∈ `cached` | `uncached` | `unavailable`.

The field names the **cache state of the association**, not a latency promise: a
`cached` explanation is still rendered by a live writer call (FR-5 invokes the writer
on every request), so the client's actual choice is between a short wait, a long one,
and no affordance at all (AD-4).

The three cases are evaluated **in this order**; the first match wins. The embedding
check is reached only on a cache miss, because a cache hit needs no retrieval and
therefore no query vector.

**Acceptance criteria:**
- Given the question has a current labeling (FR-8) with `has_supporting_commas = true`,
  then `explanation_status` is `"cached"` — **regardless of whether an embedding row
  exists**.
- Given the question has a current labeling with `has_supporting_commas = false`,
  then `explanation_status` is `"unavailable"`.
- Given the question has no current labeling and has a `quiz_question_embeddings` row
  for the configured variant, then `explanation_status` is `"uncached"`.
- Given the question has no current labeling and no `quiz_question_embeddings` row for
  the configured variant, then `explanation_status` is `"unavailable"` (the
  `not_indexed` case of FR-7).

### FR-5: Explain an answer from a cached comma association

`GET /quiz-questions/{number}/explanation` serves an explanation grounded in the
commas already associated with the question, without re-running retrieval or the judge.

**Acceptance criteria:**
- Given the question has a current labeling with at least one row in
  `quiz_comma_labels`, when a client requests the explanation, then the response is
  `200 OK`, `status` is `"explained"`, `explanation` is a non-empty string, and
  `citations` lists the labeled commas ordered by ascending `judge_rank`.
- Given the same condition, then no candidate retrieval query and no judge LLM call
  are issued for that request.
- Given the same condition, then each citation carries `source`, `article_number`,
  `article_title`, `comma_number`, `text` and `rank`.
- Given the same condition, then `provenance` carries `origin`, `human_validated` and
  `judge_model` of the labeling that was used.

### FR-6: Compute the association live on a cache miss, and persist it

When no current labeling exists, the endpoint retrieves candidates from both arms,
submits them to the judge, and writes the outcome to the golden set before answering.

**Acceptance criteria:**
- Given the question has no current labeling and has an embedding for the configured
  variant, when a client requests the explanation, then a dense arm of `dense_k`
  commas and a text arm of `text_k` commas are retrieved and merged by comma id,
  each carrying its one-based `dense_rank` and/or `text_rank`.
- Given the same request, then the merged candidate set is submitted to the judge in a
  deterministically shuffled order.
- Given the judge returns one or more ordinals, then a `quiz_labelings` row with
  `has_supporting_commas = true` and its `quiz_comma_labels` children are persisted
  before the response is returned.
- Given the judge returns an empty list, then a `quiz_labelings` row with
  `has_supporting_commas = false`, the judge's `rationale`, and **zero**
  `quiz_comma_labels` children is persisted.
- Given a second request for the same question follows with unchanged configuration,
  then it is served as a cache hit per FR-5 and issues no judge call.
- Given the question has no embedding row for the configured variant, then no
  retrieval is attempted and the response is FR-7's `not_indexed` case.
- Given two requests for the same uncached question run concurrently, then both may
  perform retrieval and call the judge, and the losing write is discarded without
  raising: the labeling insert is `ON CONFLICT DO NOTHING` against
  `UNIQUE (run_id, quiz_question_id)`, and both clients receive a well-formed
  explanation (AD-19).
- Given the losing racer's insert conflicts, then its `RETURNING id` yields **no row**
  and the write path returns `None` rather than raising; the caller then re-reads the
  current labeling (FR-8) instead of writing its own `quiz_comma_labels` children.
- Given retrieval or the **judge** raises, then **nothing is written to
  `labeling_runs`, `quiz_labelings` or `quiz_comma_labels`** and the response is
  FR-13's `503` (AD-20).
- Given the judge's verdict has been persisted and the **writer** subsequently fails,
  then the labeling is **not** rolled back — the golden set records the judge's
  verdict, not the writer's success (FR-13, AD-29).

### FR-7: Insufficient knowledge is reported, never fabricated

When the corpus does not justify the answer, the writer agent is not invoked and the
client is told why.

**Acceptance criteria:**
- Given the current labeling has `has_supporting_commas = false`, when a client
  requests the explanation, then the response is `200 OK`, `status` is
  `"insufficient_knowledge"`, `explanation` is `null` and `citations` is `[]`.
- Given the same condition, then the explanation writer agent is **not instantiated
  and not called**.
- Given the labeling is not human-validated, then `reason` is `"no_supporting_norm"`.
- Given the labeling is human-validated (`validated_at` is not null), then `reason` is
  `"no_supporting_norm_confirmed"`.
- Given the question has **no** current labeling and no embedding row for the
  configured variant, then `reason` is `"not_indexed"`. (A current labeling always
  wins: it needs no query vector, so a missing embedding never downgrades a cache hit.)
- Given any `insufficient_knowledge` response, then `judge_rationale` carries the
  stored `quiz_labelings.rationale` when a labeling exists, and `null` for
  `not_indexed`.

### FR-8: Deterministic precedence among competing labelings

Where several labelings exist for one question, exactly one is "current": a
human-validated labeling wins over any other; otherwise the most recent labeling whose
run matches the active configuration wins; otherwise there is no current labeling.

**Acceptance criteria:**
- Given a human-validated labeling from an outdated run and a non-validated labeling
  from a run matching the active configuration, then the human-validated one is
  selected.
- Given two non-validated labelings whose runs both match the active configuration,
  then the one with the greater `created_at` is selected.
- Given the only labelings present come from runs whose `judge_model`,
  `prompt_version`, `candidate_variant`, `dense_k`, `text_k` or `lexeme_fields` differ
  from the active configuration, and none is human-validated, then no labeling is
  selected and the request is treated as a cache miss (FR-6).
- Given two runs whose `lexeme_fields` hold the same field names in a different order,
  then they are **not** distinct configurations: the value is canonicalised by sorting
  on write, so ordering never opens a spurious epoch (AD-8).

### FR-9: One live run per configuration epoch

Live labelings are grouped under a `labeling_runs` row with `origin = 'live'`, created
lazily and reused while the judge configuration is unchanged.

**Acceptance criteria:**
- Given no live run exists for the active configuration, when a live labeling is
  persisted, then exactly one `labeling_runs` row with `origin = 'live'` is created.
- Given a live run already exists for the active configuration, when a further live
  labeling is persisted, then no additional `labeling_runs` row is created.
- Given two concurrent requests both find no live run for the active configuration,
  then exactly one `labeling_runs` row results and both labelings reference it.
- Given the active `judge_model` changes, when a live labeling is persisted, then a
  second `labeling_runs` row with `origin = 'live'` is created alongside the first.
- Given the active `lexeme_fields` changes to a different **set** of fields, when a live
  labeling is persisted, then a second `labeling_runs` row with `origin = 'live'` is
  created; given only the order changes, then no new row is created (FR-8).

### FR-10: The explanation is grounded in the supplied commas only

The writer receives only the labeled commas and must report which of them it cited;
a citation outside that set is rejected.

**Acceptance criteria:**
- Given a labeling with N commas, when the writer is invoked, then it receives exactly
  those N commas and no other candidate.
- Given the writer returns a `cited_comma_numbers` entry that is not an ordinal of the
  supplied commas, then the response is rejected and the agent is retried.
- Given the writer returns only valid ordinals, then the response is accepted.
- Given the writer is invoked, then it receives the question text, the correct answer,
  the image description when present, and the labeled commas.

### FR-11: The explanation adapts to the answer the user submitted

`GET /quiz-questions/{number}/explanation` accepts an optional `submitted` query
parameter carrying the boolean the user answered, which is passed to the writer.

**Acceptance criteria:**
- Given `?submitted=false` and a question whose `correct_answer` is `true`, when the
  explanation is generated, then the writer receives that the user answered
  incorrectly.
- Given `submitted` is omitted, then the writer receives `None` for it and produces a
  neutral explanation; the request is still served normally (`200 OK`).
- Given `submitted` is present, then it changes neither which labeling is selected
  (FR-8) nor what is written to the golden set — it is an input to the writer only.

### FR-12: Serve the quiz images

`GET /quiz-images/{filename}` returns the image bytes for a quiz question's
`image_filename`, so a client can render sign-based questions.

**Acceptance criteria:**
- Given `data/quiz-images/S0142.png` exists and is referenced by some
  `quiz_questions.image_filename`, when a client requests
  `GET /quiz-images/S0142.png`, then the response is `200 OK` with the image bytes and
  a correct `Content-Type`.
- Given a `filename` that no `quiz_questions.image_filename` references, then the
  response is `404 Not Found`, **even if a file of that name exists on disk**.
- Given a `filename` containing a path separator or a parent-directory segment (e.g.
  `../../.env`), then the response is `404 Not Found` and no filesystem read is
  attempted outside the configured image directory.

### FR-13: Transient failures are reported as such, never as missing knowledge

A failure of the judge, the writer, or the model provider is reported distinctly from
"the corpus does not justify this question". What such a failure leaves behind depends
on **which stage** failed: the golden set records the judge's verdict, not the writer's
success (AD-29).

**Acceptance criteria:**
- Given the judge or the writer raises (timeout, rate limit, unvalidatable response
  after retries), when a client requests the explanation, then the response is
  `503 Service Unavailable`.
- Given the same condition, then the response is **not** `insufficient_knowledge` and
  carries no `reason` from FR-7's vocabulary.
- Given the **judge** raises, then no row is written to any golden-set table, and a
  later request re-runs the live stage from scratch — the failure left no trace that
  would suppress a later attempt.
- Given the judge succeeded and the **writer** raises, then the `quiz_labelings` row and
  its `quiz_comma_labels` children are already persisted and are **not** rolled back,
  and a later request for the same question is served as a cache hit per FR-5.
- Given the writer failed after a successful judge, then a subsequent check reports
  `explanation_status = "cached"` (FR-4): the association exists even though the last
  attempt to render it did not complete.

### FR-14: The API detects a judge it does not share with the batch

At startup the app compares its own resolved `prompt_version` against those already
recorded in `labeling_runs` and warns when it matches none.

**Acceptance criteria:**
- Given `labeling_runs` contains at least one row and none has the app's resolved
  `prompt_version`, then a `warning` is logged naming both the app's version and the
  distinct versions found.
- Given at least one row matches, then no warning is logged.
- Given `labeling_runs` is empty, then no warning is logged (an unpopulated golden set
  is not a divergence).
- Given the check itself fails (database unreachable), then startup is not aborted —
  this is a diagnostic, not a health gate.

### FR-15: The outcome flag and its comma rows cannot disagree

`quiz_labelings.has_supporting_commas` is **derived inside the same statement** that
writes the `quiz_comma_labels` rows it summarises, from the same array of comma ids
(AD-10). No caller supplies it.

**Acceptance criteria:**
- Given a labeling write fails while inserting `quiz_comma_labels`, then no
  `quiz_labelings` row for that attempt is visible afterwards.
- Given any persisted labeling, then `has_supporting_commas = true` if and only if it
  has at least one `quiz_comma_labels` child.
- Given any caller of the write path, then it has **no way to supply**
  `has_supporting_commas`: the field is absent from `QuizLabelingEntity` and the value is
  computed by the statement as `cardinality(...) > 0` over the child array.
- Given `article_commas` rows are deleted by FK cascade (e.g. a corpus reset), then the
  invariant can be broken without any write path observing it; detection — not
  prevention — is `ingest status`'s consistency query (AD-10, AD-28).

### FR-16: List the topics available for filtering

`GET /quiz-questions/topics` returns the distinct `quiz_questions.topic` values with
their question counts, so a client can build a filter menu instead of guessing at
accented Italian strings.

**Acceptance criteria:**
- Given the bank holds questions under two or more topics, then the response is
  `200 OK` and the body lists every distinct `topic` with a `count`.
- Given the response, then the topics are ordered deterministically (by `topic`
  ascending), so the client renders a stable menu.
- Given a topic returned by this endpoint is passed as FR-1's `topic` parameter, then
  `index = 0` resolves to a question rather than a `404`.
- Given the bank is empty, then the response is `200 OK` with an empty list, not a
  `404`.

### FR-17: A corpus reset invalidates labelings and refuses to discard human validation

`ingest reset knowledge` truncates the golden-set tables together with the corpus, and
stops rather than destroying human-validated labelings.

**Acceptance criteria:**
- Given `--apply` and no human-validated labeling exists, then `quiz_comma_labels`,
  `quiz_labelings`, `article_commas` and `articles` are truncated in a **single**
  `TRUNCATE` statement.
- Given `--apply` and at least one `quiz_labelings` row has `validated_at IS NOT NULL`,
  then nothing is truncated, the command exits non-zero, and the message names how many
  validated labelings would have been destroyed and that `--force` overrides.
- Given `--apply --force` in the same situation, then the truncation proceeds.
- Given no `--apply`, then the preview lists all four tables and, when validated
  labelings exist, their count — and opens no DB connection beyond that count query.
- Given the current command (`TRUNCATE article_commas, articles`) is run against a
  schema carrying `quiz_comma_labels`, then it fails on the inbound foreign key: this
  FR fixes a command that is **already broken**, not one this spec breaks.

### FR-18: The batch labeler can be restricted to selected topics

`label-golden-set` accepts a repeatable `--topic`, so the cache can be pre-warmed a
slice at a time and a single topic can be re-labeled after a prompt change (AD-30).

**Acceptance criteria:**
- Given `--topic velocità`, then only questions with that `topic` are labeled.
- Given `--topic` is repeated, then the union of the named topics is labeled.
- Given `--topic` is omitted, then the full bank is labeled, as today.
- Given `--topic` and `--limit` are combined, then the limit applies to the filtered
  set.
- Given any `--topic` value, then it does **not** appear in `labeling_runs` and does not
  participate in the configuration epoch: it selects *which* questions are labeled, not
  *how* they are judged (FR-9).

## Non-Goals

- **User identity, sessions, scoring, answer history.** The API stays stateless; the
  Telegram bot owns the seed and index. A `quiz_answers` table and session endpoints
  are a later increment (AD-1).
- **Anti-repetition enforced server-side.** Covered by FR-1's seeded permutation on the
  client side only.
- **Official exam-sheet composition** (30 questions with per-topic quotas).
- **A persisted explanation cache.** Only the quiz↔comma association is cached; the
  explanation text is generated per request (AD-7).
- **Use of `quiz_questions.rule_explanation`.** The column stays populated but is not
  read by the API (AD-7).
- **Free-form user questions** not drawn from the quiz bank. The live pipeline built by
  FR-6 is the mechanism such a feature would reuse, but no endpoint exposes it here.
- **A human validation UI.** This spec adds the columns (`validated_at`,
  `validated_by`) and honours them on read; the tool that writes them is out of scope.
- **Authentication, rate limiting, async job submission for the ~10s live path.**

## Architectural Decisions

### AD-1: The API is stateless; per-user state is deferred, not designed away
- **Rationale:** The bot owns which question it proposed. No user table, no session
  table, no auth. Chosen so the first usable end-to-end flow ships without designing
  identity, while nothing in the contract forecloses adding sessions later.
- **Rejected alternatives:** Stateful sessions now (`POST /sessions`, scoring, targeted
  review) — materially larger surface for a bot that does not yet exist; an optional
  `user_id` on the check that append-logs answers — collects data for a feature whose
  shape is undecided, and puts a write path on the hottest endpoint for no present
  benefit.

### AD-2: Proposal uses a seeded deterministic permutation, not exclusion lists
- **Rationale:** `?seed=<chat_id>&index=<n>` lets the client store a single integer and
  never repeat, reusing the `md5(id::text || seed)` ordering trick already proven in
  `CorpusReadRepository.random_top_k`. The request payload does not grow with session
  length.
- **Rejected alternatives:** `?exclude=0001,0042,...` — the query string grows without
  bound and needs capping; pure random with repeats allowed — simplest, but the user
  explicitly wants no repeats; server-side exclusion — requires the state AD-1 defers.
- **Known limitation, accepted:** changing `topic` mid-session changes the filtered
  permutation, so `index` continuity is only meaningful within one filter.

### AD-3: `correct_answer` never appears in a proposal or fetch response
- **Rationale:** It is the only structural guarantee that validation is genuinely
  server-side. A client that can read the answer can trivially self-grade, which makes
  FR-3 decorative.
- **Rejected alternatives:** Returning it to let the bot grade locally and save a round
  trip — saves one cheap indexed query at the cost of the endpoint's entire purpose.

### AD-4: The check response carries `explanation_status`, naming the cache state rather than a latency
- **Rationale:** The bot must decide *which affordance to render* before the user asks:
  a "Spiegami", a "Spiegami (una decina di secondi…)", or no button at all. Without
  the field the bot must promise an explanation that may never arrive. It costs one
  additional lookup against the same join FR-8 already performs, not a second pipeline.
- **Vocabulary:** `cached` | `uncached` | `unavailable`. The earlier draft used
  `ready` | `on_demand`, which claimed a latency the endpoint does not deliver: FR-5
  invokes the writer on **every** request, cache hit included, so a `ready` explanation
  still costs a live LLM call. The real distinction is a short wait (writer only, ~2–4s)
  versus a long one (retrieval + judge + writer, ~10s), and the field's job is to let the
  client pick a band and decide whether to offer the button at all. Naming the cache
  state says the true thing and leaves the latency mapping where it belongs, in the
  presentation layer.
- **Rejected alternatives:** Keeping the response to `{"correct": bool}` as the
  superseded spec specified — minimal, but forces the client either to guess or to
  issue a speculative explanation request to find out; a separate
  `GET /quiz-questions/{number}/explanation-status` endpoint — a second round trip for
  information the client needs at exactly the moment it already calls the check.

### AD-5: `insufficient_knowledge` is a `200`, not a `404` or `422`
- **Rationale:** "The corpus does not justify this question" is a successful,
  informative domain answer with a body worth reading (the reason, the judge's
  rationale). A `4xx` says the client did something wrong, which it did not.
- **Rejected alternatives:** `404` — conflates "no such question" (a real client error,
  used by FR-2/FR-3) with "question exists, knowledge does not"; `422` — implies an
  unprocessable request.

### AD-6: The API returns a machine-readable `reason`; the bot renders the user-facing wording
- **Rationale:** The judge's stored `rationale` is written in evaluation meta-language
  ("among the commas presented…") and leaks the existence of a retrieval step the user
  knows nothing about. A closed `reason` vocabulary keeps presentation in the
  presentation layer. Crucially it separates `not_indexed` — a **pipeline gap**, fixed
  by re-running ingestion — from `no_supporting_norm`, a **corpus gap**, which no
  re-run fixes. Collapsing the two would hide pipeline regressions permanently.
  `judge_rationale` is passed through for transparency and debugging; the client
  decides whether to show it.
- **Rejected alternatives:** Returning the raw `rationale` as the user-facing message —
  free, but meta-language aimed at a judging task; generating a friendly refusal with
  the writer agent — directly violates the constraint that the writer is never invoked
  without supporting commas.

### AD-7: Only the quiz↔comma association is cached; the explanation text is generated per request
- **Rationale:** The two artifacts have invalidation cycles an order of magnitude
  apart. The association invalidates only when the corpus or the judge changes — rare,
  deliberate, traceable. The explanation would invalidate on any writer prompt tweak or
  model change — and, since AD-21, it is tailored to the answer the user actually
  submitted, so the same question legitimately has two different explanations. A
  cache that invalidates on every prompt edit is not a cache but stale rows nobody can
  audit. The economics agree: the judge sees ~80–100 candidates (~10–13k input tokens),
  the writer sees 2–3 commas (~750–1000 input tokens) — caching the association
  captures roughly 90% of the cost while leaving the cheap 10% free to evolve. It also
  keeps one source of truth: the explanation is a *rendering* of the association, never
  a second fact that can contradict it.
- **Rejected alternatives:** A dedicated explanation table — introduces a second cache
  with a much faster invalidation cycle and no clear ownership; serving the existing
  `quiz_questions.rule_explanation` column — precomputed, ungrounded in the labeled
  commas, and explicitly rejected by the user.
- **Consequence, accepted:** the wording cannot be human-reviewed before it reaches a
  user. The risk is bounded because the writer may only speak about commas that a human
  can validate (FR-10 + `validated_at`): the *sources* are reviewable, the prose is not.
- **Escape hatch, if per-request cost ever matters:** an in-memory/Redis cache keyed by
  `(number, writer_prompt_version, writer_model)` — no schema, so it does not
  reintroduce the maintainability problem this decision avoids.

### AD-8: `labeling_runs.origin` distinguishes batch from live; a partial unique index defines the live configuration epoch
- **Rationale:** A `labeling_runs` row per HTTP request is wasteful and carries
  batch-only fields (`corpus_commit`, `question_limit`) that a running container cannot
  populate. Instead, one live run per configuration epoch, created lazily and reused.
  A partial unique index on `(judge_model, prompt_version, candidate_variant, dense_k,
  text_k, lexeme_fields) WHERE origin = 'live'` makes that creation race-safe across
  workers via `INSERT … ON CONFLICT DO NOTHING` + `SELECT`, with no application lock. It
  also makes a model or prompt change open a *new* epoch, so **the cache invalidates
  itself without a single `DELETE`**.
- **`lexeme_fields` belongs in the key.** `QuestionLexemeService` is constructed with
  `lexeme_fields: Sequence[LexemeField]`, and that configuration determines the *entire
  text arm* of the candidate set. Omitting it — as the first draft did — lets the judge
  see a materially different candidate set under an identical epoch key, so the cache
  serves labelings produced from candidates the active configuration would never have
  retrieved. That is the exact failure this AD exists to prevent, one field short of
  complete. It is stored as `TEXT[]`, **canonicalised by sorting on write** in the mapper
  that builds `LabelingRunEntity`, so both the batch and live paths agree: the *set* of
  fields changes retrieval, their order does not (the lexemes are OR-ed into one
  `tsquery`), and a cosmetic YAML reordering must not invalidate the bank.
- **Rejected alternatives:** One run row per request — unbounded growth and unpopulated
  batch columns; `origin` on `quiz_labelings` with a single perpetual live run — loses
  the configuration identity that FR-8's precedence rule depends on; folding
  `lexeme_fields` into a broader `judge_config_version` hash — overloads a name that
  today means something precise and independently verifiable (the `sha256` of the prompt
  file).
- **Consequence:** `corpus_commit` becomes nullable (live runs cannot know it).
  `shuffle_seed` stays `NOT NULL`: candidates must be shuffled at runtime too, to deny
  the judge position bias, using a fixed seed so the shuffle stays reproducible.
- **Accepted limitation — corpus identity is deliberately *not* in the epoch key.**
  `corpus_commit` and `corpus_comma_count` are recorded on batch runs but excluded from
  the unique index and from FR-8's precedence, so re-ingesting the corpus does **not**
  invalidate a single cached labeling: a comma whose text changed keeps its association,
  and one that was deleted takes its `quiz_comma_labels` row with it by FK cascade. This
  is a choice, not an oversight — including corpus identity would invalidate the whole
  bank on any re-ingestion, including one that touched an unrelated source. The exposure
  is bounded by AD-28 (a corpus *reset* truncates the labelings outright) and made
  observable by AD-10's consistency query. Revisit if partial re-ingestion becomes
  routine.

### AD-9: Human validation is recorded on `quiz_labelings`, not on `quiz_comma_labels`
- **Rationale:** The verdict most worth having a human confirm is the **empty** one —
  "yes, I confirm the corpus genuinely does not cover this". That verdict has *zero*
  rows in `quiz_comma_labels`, so there is no row on which to hang the flag. A labeling
  always exists, even when empty. A `CHECK ((validated_at IS NULL) = (validated_by IS
  NULL))` forbids the half-filled "validated by nobody" state.
- **Rejected alternatives:** A flag per comma association — matches the intuition that
  "the association" is what gets validated, but cannot express the most valuable
  validation at all; a separate `labeling_validations` table — a full audit trail is
  not needed for a single boolean fact with one timestamp and one actor.

### AD-10: `quiz_labelings.has_supporting_commas` denormalises the outcome, amending the golden-set spec's AD-6
- **Rationale:** The golden-set spec deliberately refused an outcome column ("a second,
  potentially contradicting source of truth for a fact already derivable by counting"),
  and that was right *for a table read by offline analysis scripts*. This spec changes
  the table's role: it becomes the hot cache of a request path, consulted on every
  check (FR-4) and every explanation (FR-5). A denormalised flag is a defensible answer
  to a changed read pattern.
- **The risk AD-6 named is retired by construction, not merely mitigated.** The flag is
  **not** a field of `QuizLabelingEntity` and no caller can supply it. It is computed
  inside `insert_labeling`'s existing single data-modifying CTE as
  `cardinality(%s::bigint[]) > 0`, over the *same* array that feeds the
  `quiz_comma_labels` insert. One statement, one array: the flag and its children cannot
  physically disagree, which is strictly stronger than "written in one transaction".
  This deliberately bends the entity-as-insertable-projection rule
  (`.claude/rules/code-conventions.md`): `has_supporting_commas` is a derived
  denormalisation owned by the write path, and its absence from the entity is the
  enforcement mechanism, not an omission.
- **One hole remains, and it is a detection problem, not a prevention one.**
  `quiz_comma_labels.article_comma_id` is `ON DELETE CASCADE`, so deleting a comma
  removes label rows while the parent flag stays `true` — a path no write path can
  observe. The consistency query surfaced by `ingest status`
  (`has_supporting_commas = true AND NOT EXISTS (child)`) is therefore retained even
  though the write path can no longer produce the state itself, alongside an integration
  test asserting the invariant.
- **Rejected alternatives:** An `outcome` enum column (`supported` /
  `no_supporting_norm`) — same cost, directly reusable as the API's `reason` field, and
  extensible to future outcomes by updating one `CHECK`; **recommended but not chosen —
  the user selected the boolean**. Keeping the derivation (`EXISTS` against the
  `(labeling_id, article_comma_id)` primary key, index-only and cheap) — preserves
  AD-6 intact but leaves the outcome implicit and scattered across queries.
- **Note:** the boolean is sufficient for the current `reason` vocabulary:
  `no_supporting_norm` vs `no_supporting_norm_confirmed` is decided by `validated_at`,
  and `not_indexed` never reaches this table.

### AD-11: Precedence is human-validated, then current-configuration, then miss
- **Rationale:** Human effort must never be silently overwritten by a batch
  regeneration, so a validated labeling wins regardless of its run's configuration.
  Below that, matching the active configuration is what makes a cached judgement
  trustworthy, and it makes a model/prompt change invalidate the cache by itself.
- **Rejected alternatives:** Most recent wins outright — trivial, but a regeneration
  run buries yesterday's human validation and the cache ignores model changes;
  accepting only validated-or-current-configuration and regenerating everything else —
  strictly safer, but after any prompt change the entire bank pays full price until the
  batch is re-run.

### AD-12: The shared labeling machinery is extracted into a new `src/labeling/` module
- **Rationale:** `CommaLabelerAgent`, `CandidateSetService`, `QuestionLexemeService`,
  `GoldenSetWriteRepository` and `CandidateComma` live in `src/retrieval_evaluation/`,
  a module ADR 0013 deliberately kept separate as measurement instrumentation. The
  moment the API calls them to serve a user, that code *is* production and the package
  name misleads. More than naming: cache coherence **requires** that the batch judge
  and the live judge be the same implementation — if they diverge by even one prompt
  sentence, `prompt_version` stops identifying a behaviour and the cache fills with
  rows produced by different judges under one label. `src/retrieval_evaluation/` keeps
  what is genuinely evaluation-only (`retrieval_judge`, `main.py`, the metric
  services). Requires an ADR amending 0013.
- **Rejected alternatives:** Importing `retrieval_evaluation` from the production app
  unchanged — zero refactor, but production depends permanently on a package named
  "evaluation" and the cost of untangling grows with every call site; promoting the
  machinery into `commons/` — one obvious place to look, but `commons/` is deliberately
  generic infrastructure (base agent, embedding, Postgres client) and this is
  domain logic about commas, quizzes and the corpus normativo.

### AD-13: The dense arm reuses the precomputed `topic_text` embedding; nothing is embedded at request time
- **Rationale:** `quiz_question_embeddings` already stores a vector per variant, and
  `topic_text` composes exactly `topic + text + image_description` — the fields the user
  specified. Reading it costs one indexed lookup; recomputing it would add an
  `EmbeddingClient`, an `OPENROUTER_API_KEY` dependency and ~200ms to the request path
  for a byte-identical result. `register_vector` is already called on the connection
  (`PostgresClient.__init__`), so the vector deserialises without bespoke parsing.
- **Rejected alternatives:** `combined_description` (adds `vector_search_queries`) —
  a defensible variant but not the composition the user specified; embedding the
  question live — strictly more expensive for the same vector.
- **Implementation note:** the vector is fetched into Python and passed to the existing
  `CorpusReadRepository.dense_top_k`, rather than joining the quiz and corpus
  aggregates in one SQL statement. The single-statement form would avoid transferring
  1536 floats, but ~12KB over a local socket is negligible and reuse of the existing,
  tested method wins.

### AD-14: The writer reports which commas it cited, making grounding mechanically checkable
- **Rationale:** "Do not invent" enforced by prompt wording alone is unverifiable.
  Requiring `cited_comma_numbers` back turns grounding into a validator: an ordinal
  outside the supplied set fails the response model, and pydantic-ai retries. This is
  the same mechanism `CommaLabelerResponse` already uses to reject repeated ordinals.
- **Rejected alternatives:** Prompt-only instruction — no enforcement point; post-hoc
  string matching of citations in the prose — brittle and locale-dependent.

### AD-15: The explanation endpoint is a `GET` despite its write-through
- **Rationale:** The write is cache fill, not resource mutation; the same input yields
  the same resource, and the route stays cacheable by intermediaries.
- **Rejected alternatives:** `POST` — literal about the side effect, but misrepresents
  a read as a state change and forfeits caching.

### AD-16: New components are pywire-native; providers are reserved for code shared with the pre-pywire world
- **Rationale:** Two rules, applied by ownership rather than by convenience.

  **1. Code this spec introduces is pywire-native.** Every new service, repository and
  agent under `src/guidami_ai_patente/` carries its role decorator
  (`@service`/`@repository`/`@agent`), declares its dependencies as class-level
  `Autowired[T]` fields, and is zero-argument constructible. This includes classes with
  a real constructor body: pywire's instrumented `__init__` sets every `Autowired`
  field *before* calling the class's own `__init__` (ADR 0017), so a zero-argument
  `__init__` can read them. `ExplanationWriterAgent` is the demanding case and still
  qualifies — `BaseAgent.__init__` requires `config: AgentConfig` and
  `provider: OpenRouterProvider`, so the subclass declares
  `config: Autowired[AppConfig]` and `provider: Autowired[OpenRouterProviderComponent]`
  and calls `super().__init__(...)` from its own zero-argument `__init__`. New code is
  *shaped* for the container rather than wrapped.

  **2. Code shared with the pre-pywire world gets a provider.** `commons/` and
  `labeling/` classes are constructed manually by the ingestor and the batch harness,
  and third-party classes are not ours to reshape. Decorating them would push pywire
  outside `src/guidami_ai_patente/` in violation of ADR 0015, and changing their
  constructors would break their existing callers. They are therefore built inside a
  `@client` provider's own `__init__`, exactly as ADR 0017 established for
  `PostgresClient`.

- **Provider consolidation:** rather than one provider per shared class — seven of them
  (`PostgresClient`, `OpenRouterProvider`, `CorpusReadRepository`,
  `QuestionLexemeService`, `CandidateSetService`, `CommaLabelerAgent`,
  `GoldenSetWriteRepository`) — the shared stack is assembled by **two** providers:
  `PostgresClientProvider` (the connection singleton, already specified by ADR 0017)
  and `LabelingStackProvider`, which autowires `AppConfig` plus
  `PostgresClientProvider` and builds the rest through the extracted builder functions,
  exposing each as an attribute. `src/retrieval_evaluation/wiring.py` already contains
  those builders for the batch path; AD-12's extraction moves them into
  `src/labeling/`, where they must be parameterised on the individual values they need
  (table names, `agents_dir`, API key) instead of on a whole `IngestorConfig`, so both
  `IngestorConfig` and `AppConfig` can feed them.
- **Rejected alternatives:** Decorating the `commons`/`labeling` classes with pywire
  decorators — violates ADR 0015's scoping and breaks the batch callers;
  hand-instantiating inside each consumer — opens a Postgres connection per consumer;
  one provider per shared class — mechanically uniform but seven near-identical
  wrappers for a graph the extracted builders already know how to assemble.

### AD-16b: `GoldenSetReadRepository` is app-local and pywire-native, not part of `src/labeling/`
- **Rationale:** The golden set has only ever had a write path; this read path exists
  solely to serve the explanation endpoint. By the self-containment test in
  `.claude/rules/cli-structure.md` ("is this used by anything other than the app? No →
  local"), it belongs in `guidami_ai_patente/repositories/`, where it is a plain
  `@repository` with `Autowired[PostgresClientProvider]` — no provider, no wrapper.
- **Rejected alternatives:** Placing it in `src/labeling/` beside
  `GoldenSetWriteRepository` — conceptually tidy (read and write of one aggregate
  together), but it would make a brand-new class require a provider purely because of
  where it sits, contradicting rule 1 above. Revisit if the batch harness ever needs to
  read the golden set.

### AD-17: This spec supersedes the mis-numbered quiz-check spec and resolves the id collision
- **Rationale:** `2026-08-19-quiz-check-endpoint-design.md` is titled "Spec 0011", an id
  already taken by `2026-08-19-retrieval-golden-set-design.md` (the one referenced as
  "spec 0011" throughout `db/init.sql`). The quiz-check spec is still `draft` with
  sign-off `pending`, and this spec covers its endpoint in full (FR-3, FR-4) while
  extending its response contract (AD-4). Marking it superseded removes the collision
  without discarding its record.
- **Carried forward from it unchanged:** lookup by `number` rather than `id`
  (its AD-2), `POST` for the check (its AD-3), a lean app-local repository rather than
  extending `commons.QuizReadRepository` (its AD-4), domain exception plus global
  handler for 404 with no `try/except` in the router (its AD-7), the
  `GuidamiApiError`/`QuestionNotFoundError` hierarchy (its AD-10), per-endpoint schema
  files (its AD-11), the stateless `evaluate_answer` function keeping
  `QuizAnswerChecker` thin (its AD-9), and the single session-scoped `AppConfig`
  fixture (its AD-8).
- **Rejected alternatives:** Renumbering the quiz-check spec and implementing both —
  two specs covering one endpoint with divergent response contracts.

### AD-18: The seeded permutation's instability across bank changes is accepted, not mitigated
- **Rationale:** `ORDER BY md5(id::text || seed) OFFSET index` presumes a fixed row set;
  adding or removing a question reshuffles it, so a stored `index` may replay or skip a
  question. A bot session lasts minutes and bank regeneration is a rare, deliberate
  operation, so the exposure is small and self-correcting.
- **Rejected alternatives:** Returning a `bank_version` for the client to compare —
  makes the client handle an invalidation case it cannot do anything useful about;
  abandoning `OFFSET` and having the client send every seen `number` — reintroduces the
  unbounded query string AD-2 exists to avoid.
- **Requirement:** stated as an accepted limitation in FR-1, not left implicit.

### AD-19: Concurrent cache misses are allowed to duplicate work; the losing write is discarded
- **Rationale:** Two simultaneous requests for the same uncached question each run
  retrieval and the judge, and the second write hits
  `UNIQUE (run_id, quiz_question_id)`. `ON CONFLICT DO NOTHING` makes the write
  idempotent and lets both clients answer immediately. The waste is an occasional
  duplicated judgement; the alternative charges a real user for it.
- **Signature consequence:** `GoldenSetWriteRepository.insert_labeling` currently ends
  `return int(rows[0][0])`. Under `ON CONFLICT DO NOTHING` the losing racer's `parent`
  CTE returns **zero** rows, so that line raises `IndexError` on a user-facing path. The
  method's return type becomes `int | None`; `None` means "another request won, re-read
  the current labeling (FR-8)" and is never an error. The children CTE needs no branch:
  it cross-joins `parent`, so an empty parent inserts nothing.
- **Rejected alternatives:** `pg_advisory_xact_lock(hash(number))` — serialises the
  duplicates, but turns the second client's 10s request into 20s and introduces a
  distributed lock to reason about at deploy time; ignoring the conflict entirely —
  leaves an unhandled integrity error on a user-facing path.
- **Revisit if:** concentrated traffic shows the duplication is material.

### AD-20: A transient failure is a `503` and writes nothing
- **Rationale:** A provider timeout, a rate limit, or an unvalidatable response after
  retries is the only genuine *error* this endpoint has, and it must stay
  distinguishable from `insufficient_knowledge` (AD-5). Collapsing them tells the user
  "the Codice della Strada does not cover this" when the truth is "OpenRouter was
  down" — a false statement about the law, cached forever if written. Hence the
  companion rule: **a failed judge stage writes nothing**, so a later attempt is not
  suppressed by a row that records an outage as a corpus gap.
- **Scoped to the judge, not the whole live stage (amended).** The first draft said "a
  failed *live stage* writes nothing", which contradicted FR-6's "persisted before the
  response is returned" in the one case that matters most: the ~11k-token judgement
  succeeded and the ~1k-token writer then timed out. Discarding that verdict re-charges
  the judge for a failure it had no part in. What AD-20 actually protects against is
  persisting a **fabricated corpus gap** — and a successful judgement followed by a
  provider hiccup is not one. See AD-29.
- **Rejected alternatives:** A third `status: "temporarily_unavailable"` inside a
  `200` — hides a server-side failure behind a success code, and clients that only
  branch on the HTTP status would treat it as an answer; a bare `500` — correct in
  kind but gives the client nothing to distinguish "retry in a moment" from "this is
  broken".

### AD-21: The explanation endpoint accepts an optional `submitted` answer, passed to the writer
- **Rationale:** An explanation addressed to someone who got it wrong is a different
  text from one addressed to someone who got it right, and the bot always knows which.
  Optional rather than required so a review flow ("go over yesterday's mistakes") can
  request an explanation without replaying an answer. It is an input to the writer
  only: it does not enter the cache key, does not affect FR-8's precedence, and is
  never persisted.
- **Rejected alternatives:** Omitting it and adding it later — backward compatible, so
  nothing was protected by waiting, while every explanation shipped in the meantime is
  needlessly generic; accepting the parameter but ignoring it — documents a behaviour
  the API does not have.
- **Consequence:** this *reinforces* AD-7. The explanation now genuinely varies per
  user, so persisting it was never viable regardless of cost.

### AD-22: `agents_dir` comes from a required environment variable with no default anywhere
- **Rationale (rescoped by AD-27):** `prompt_version` is
  `sha256(system + "\n" + user)[:16]`, so the batch judge and the live judge agree
  **only if they load the same file**. If the ingestor and the app ever resolve
  `agents_dir` differently, the API's precedence query (`r.prompt_version = %s`) matches
  no batch row: a permanent, silent 100% cache miss with no error and no log,
  indistinguishable from an empty cache while billing full price on every request.
- **What this AD still buys, now that AD-27 exists.** AD-27 moves `agents_dir` inside the
  shared `LabelingConfig`, loaded from one file by both roots, which makes divergence
  *within* a deployment structurally impossible — the job this AD was originally doing
  single-handed. Its remaining and narrower job: `agents_dir` is the epoch field most
  likely to be legitimately overridden per deployment (a container path differs from a
  dev checkout), so it is the one most likely to be set *wrongly* per deployment. A
  defaultless `AGENTS_DIR` means a deployment that gets it wrong fails at startup rather
  than silently resolving a **different file** and producing a wrong hash. The
  cross-deployment case it still cannot cover is AD-23's.
- **Implementation requirement:** the value must be removed from **both** the Python
  field default and `configs/ingestor_config.yaml`. Source precedence is
  `init > env/.env > override yaml > base yaml`, so a value left in the base yaml still
  satisfies the field and the fail-fast never triggers.
- **Blast radius — five places, one commit.** Making the field defaultless breaks every
  construction that does not set it. The change is only complete when all of these are
  updated together, or plan 1's first CI run is an unexplained red build:
  1. `IngestorConfig.agents_dir` — remove the `Path("configs/agents")` default.
  2. `configs/ingestor_config.yaml` — remove the `agents_dir` key.
  3. `.env.example` — add `AGENTS_DIR`, with the repo-relative value as the documented
     local answer.
  4. CI workflow environment — add `AGENTS_DIR`.
  5. The session-scoped pytest config fixture — set it, so the suite does not depend on
     the developer's shell.
  A fresh clone that has not copied `.env.example` will now fail loudly on
  `uv run ingest status`. That is the intended behaviour, not a regression.
- **Rejected alternatives:** Shipping `comma_labeler.yaml` as a resource inside
  `src/labeling/` and letting no config name it — makes divergence structurally
  impossible rather than merely detectable, and treats the prompt as part of the
  judge's identity (which its hash literally is); rejected because it breaks the
  uniform `configs/agents/` convention every other agent follows and turns prompt
  tuning into a code change. Trusting convention — the silent-failure mode above.
- **Residual risk, addressed by AD-23:** an environment variable cannot equalise two
  deployments with different `.env` files, which is the realistic divergence. AD-22
  prevents divergence by carelessness, not by deployment.

### AD-23: The app warns at startup when its own `prompt_version` matches no recorded run
- **Rationale:** The residual risk AD-22 leaves open is invisible by construction, so
  it must be made observable. The app already talks to Postgres; asking "has my judge
  ever produced any of what is in this cache?" costs one query at startup and converts
  a silent, expensive failure into a log line. It is a diagnostic, not a gate: a failed
  check never aborts startup, and an empty `labeling_runs` is not a divergence.
- **Rejected alternatives:** Exposing the resolved `prompt_version` on `GET /health`
  and on `ingest status` for manual comparison — useful, and can be added alongside,
  but relies on somebody looking; relying on the in-process test alone — cannot see
  across two deployments, which is exactly where the divergence happens.

### AD-24: Images are served by an endpoint validated against the database, not by a static mount
- **Rationale:** The proposal response is useless for the 427 sign-based questions
  without the image bytes. `GET /quiz-images/{filename}` resolves the name **against
  `quiz_questions.image_filename`** before touching the filesystem, so the route
  exposes exactly the referenced images and nothing else, and path traversal is
  rejected by construction rather than by string sanitising. The response returns
  `image_url` instead of the bare `image_filename` so the client does not have to know
  how to build the path.
- **Rejected alternatives:** Mounting `StaticFiles` on `/quiz-images` — exposes a whole
  directory with no validation of the requested name; leaving images to the client —
  duplicates 427 files and lets them drift from the database; returning only the stored
  textual `description` — a description is a fallback for a model, not a substitute for
  showing the user the sign they are being asked about.
- **Scope note:** this is a functional requirement the design lacked, not a refinement.

### AD-25: The API is async at the LLM boundary; the shared labeling stack stays synchronous behind `asyncio.to_thread`
- **Rationale:** AD-19 specifies behaviour for two concurrent requests, but nothing else
  in the design established that the app *can* serve two at once. `BaseAgent` exposes
  both `run` (async) and `run_sync`; if the routers were `async def` and called
  `run_sync`, a single explanation would freeze the entire event loop — every other
  request included — for the ~10s the judge takes, and AD-19's race could never occur.
  The resolution splits by cost: routers are `async def` and `await BaseAgent.run` for
  the LLM calls, which are ~95% of the wall clock, while the synchronous SQL stages
  (`CandidateSetService`, `CorpusReadRepository`, `GoldenSetWriteRepository`,
  `QuestionLexemeService`) are wrapped in `asyncio.to_thread`.
- **This is what saves AD-12.** Those four classes are the shared half AD-12 extracts
  into `src/labeling/`, and their entire justification is that batch and live run **one**
  implementation — diverge and `prompt_version` stops identifying a behaviour. Making
  them async would break the batch callers; duplicating them in async would destroy the
  cache-coherence argument the module exists for. `to_thread` costs a thread hop on
  millisecond-scale queries and leaves not one shared line changed.
- **Rejected alternatives:** A genuinely async DB layer with AD-12 sharing only the
  agent — pays for an async rewrite of tested code and forfeits the shared retrieval
  path that makes a cached judgement reproducible; plain `def` routes on FastAPI's
  threadpool — works, and is the honest fallback, but leaves the 10s call occupying a
  worker thread and gives up the natural `await` on an already-async agent.

### AD-26: `PostgresClient` becomes pooled, and that change ships in plan 1 gated on the batch suite
- **Rationale:** `PostgresClient.__init__` opens **one** `psycopg.connect(...,
  autocommit=True)` and it is a process-wide pywire singleton. psycopg3 guards a
  connection with an internal lock, so under AD-25 every threaded SQL stage would queue
  behind every other one — the concurrency AD-25 buys at the LLM boundary would be given
  straight back at the database. The connection is replaced by a
  `psycopg_pool.ConnectionPool` with `configure=register_vector`, since the pgvector
  adapter is registered per connection and AD-13 depends on a `VECTOR` column
  deserialising without bespoke parsing.
- **Blast radius, stated because it reaches outside this spec.** `PostgresClient` lives
  in `commons/` and serves the ingestor and the batch harness. `label-golden-set` already
  takes `--concurrency` for in-flight judge calls, whose DB writes today serialise
  *implicitly* behind the single connection; with a pool they become genuinely parallel.
  That is safe here — they are independent `INSERT`s under `autocommit`, guarded by the
  same unique constraints AD-19 relies on — but it is a behaviour change to working code
  that the API does not otherwise touch. It therefore belongs to **plan 1**, with the
  batch test suite passing unchanged as its gate, rather than arriving unannounced inside
  an HTTP plan.
- **Pool size is deployment configuration, not judge identity:** it lives on `AppConfig`
  and `IngestorConfig`, never on `LabelingConfig` (AD-27). Putting it in the epoch key
  would invalidate 7099 cached labelings on a capacity change.
- **Rejected alternatives:** `min=1, max=1` for the batch to preserve today's implicit
  serialisation — freezes an accidental property as if it were a requirement; a separate
  pooled client for the app only — two clients over one database, and the app's would
  drift from the one the shared repositories are tested against.

### AD-27: `LabelingConfig` moves into `src/labeling/` and becomes the single source of the configuration epoch
- **Rationale:** AD-22 goes to real lengths for **one** epoch field — removing a default
  from two places, a required environment variable, a content-hash test, a startup
  warning — because divergence means a silent, permanent, full-price 100% cache miss.
  After AD-8 the epoch key spans six inputs: `judge_model` and `prompt_version` (both
  derived from the agent YAML under `agents_dir`), `candidate_variant`, `dense_k`,
  `text_k`, `lexeme_fields`. Five of them were about to be duplicated across
  `IngestorConfig` and `AppConfig` — two independently-loaded settings classes with
  independent defaults and independent YAML — leaving four more doors onto the identical
  failure mode AD-22 shuts. A single config object holding those inputs, embedded in both
  roots and resolved from **one** file, makes drift *structurally impossible* rather than
  merely observable.
- **The class already exists; this is a move, not a design.**
  `src/guidami_ai_patente_ingestor/configs/labeling_config.py` already holds
  `candidate_variant`, `dense_k`, `text_k`, `lexeme_fields` (plus `shuffle_seed`,
  `concurrency`, `transport_retries`, `retry_backoff_seconds`) with validators, and is
  already nested as `IngestorConfig.labeling`. AD-12 moves the machinery it configures
  into `src/labeling/`; this AD moves the configuration with it, to
  `src/labeling/configs/labeling_config.py`, and adds `agents_dir`. Not `commons/`:
  AD-12's own rejection of that package — "deliberately generic infrastructure … this is
  domain logic about commas, quizzes and the corpus normativo" — applies unchanged to the
  configuration that names the machinery's identity.
- **`agents_dir` moves inside it.** It sits on `IngestorConfig` today
  (`ingestor_config.py:59`), one level above the config that describes the judge, even
  though it is what determines both `prompt_version` and `judge_model`. Moving it in is
  what lets the single-source property cover AD-22's field alongside the other four.
- **The epoch key is a proper subset of this class.** `shuffle_seed`, `concurrency`,
  `transport_retries` and `retry_backoff_seconds` are run mechanics, not judge identity:
  they live here for cohesion but do **not** enter `labeling_runs`' unique index (except
  `shuffle_seed`, which is recorded as provenance without being part of the key). The
  distinction must be explicit in the class docstring, or the next reader will assume
  every field invalidates the cache.
- **Single source is the whole point.** A `labeling:` section duplicated inside both
  `ingestor_config.yaml` and an app YAML would *move* the duplication rather than remove
  it, and this AD would buy nothing. Both roots read one `configs/labeling.yaml`.
- **It also closes a standing open question.** The nine builders in
  `retrieval_evaluation/wiring.py` all take `IngestorConfig` today, and AD-16 needed them
  driven by `AppConfig` too. They take `LabelingConfig`: neither a bare signature change
  nor a bespoke settings protocol, but a class that already exists and already carries
  most of what they read.
- **Rejected alternatives:** Duplicating the fields and relying on FR-14's startup
  warning to detect drift after the fact — precisely the "trusting convention" AD-22
  rejects, applied to four fields instead of one, and detection is not prevention; having
  `AppConfig` read `configs/ingestor_config.yaml` directly — couples the app to the
  ingestor's configuration file, which ADR 0015's package scoping exists to avoid.

### AD-28: A corpus reset invalidates labelings and refuses to discard human validation
- **Rationale:** `quiz_comma_labels.article_comma_id` references `article_commas` with
  `ON DELETE CASCADE`, and Postgres refuses `TRUNCATE` on a table with an inbound foreign
  key unless the referencing table is named in the same command. `ingest reset knowledge`
  today issues `TRUNCATE article_commas, articles` and therefore **already fails**
  against the current schema — this is a repair, not a regression this spec introduces.
  The fix is to truncate all four tables in one statement, which is correct on the
  merits too: a corpus wipe invalidates every labeling by definition, since the commas
  those labelings point at no longer exist.
- **The guard is the non-obvious half.** Truncating `quiz_labelings` destroys every
  `validated_at`, and AD-11's entire rationale is that "human effort must never be
  silently overwritten by a batch regeneration". A corpus reset is the one operation that
  actually can. So the command counts validated labelings first and refuses unless
  `--force`, naming the count — and the `--apply`-gated preview already renders a step
  list, which is the natural place to say so.
- **Rejected alternatives:** Truncating all four unconditionally with a loud message —
  one line cheaper, but a message is not a gate and the work destroyed is unrecoverable;
  marking the command outdated and deferring the fix — acceptable if plan 1 must touch
  nothing outside its scope, but then the breakage must be recorded as a known-broken
  command rather than left to surface as a bare foreign-key error nobody was warned
  about.

### AD-29: The golden set records the judge's verdict, not the writer's success
- **Rationale:** FR-6 ("persisted before the response is returned") and the first draft
  of FR-13 ("given the judge **or the writer** raises … no row is written") were directly
  contradictory in the case that matters most: the expensive judgement completed and the
  cheap rendering then failed. The two stages produce different things — the judge
  produces a *fact about the corpus* worth caching, the writer produces *prose* AD-7
  already declines to cache — so they deserve different failure semantics. A judge
  failure writes nothing (AD-20's real concern: never persist a fabricated corpus gap). A
  writer failure after a successful judge returns `503` over an **already-persisted**
  labeling, so the retry is a cache hit rather than a second ~11k-token judgement.
- **Rejected alternatives:** Holding the write until the writer succeeds, as the first
  draft literally stated — re-charges the judge for an outage it had no part in, on every
  retry, for the most expensive stage in the system; persisting the labeling *and*
  returning a `200` with a null explanation — hides a server-side failure behind a
  success code, which AD-20 rejects for the same reason.
- **Consequence:** after a writer failure, FR-4 reports `cached` for that question. That
  is correct and not a leak: the association genuinely exists, and only the last attempt
  to render it did not complete.

### AD-30: The cache is pre-warmed as a bounded topic slice, not the full bank
- **Rationale:** Measured coverage is 14 labelings against 7099 questions, so the cache
  is effectively empty and plan 3 is not optional. A full batch pre-warm is ~7099 × ~11k
  input tokens ≈ 78M input tokens — a real, one-off, quantifiable spend committed
  *before* the writer has ever run in production and before the `no_supporting_norm` rate
  is known at scale. Labeling the highest-frequency topics first — a few hundred
  questions — makes a demo and the first real sessions feel instant, yields a measured
  cost-per-question and a measured refusal rate, and leaves the long tail to fill from
  traffic. Buying 7099 answers from a judge nobody has validated at scale is the version
  of this decision that cannot be undone.
- **Requires FR-18:** `label-golden-set` exposes `--concurrency`, `--seed` and `--limit`
  but nothing that selects a topic, and `--limit N` takes an arbitrary slice in query
  order. The repeatable `--topic` flag also pays for itself afterwards: re-label one
  topic after a prompt tweak instead of the bank.
- **Rejected alternatives:** Full pre-warm before plan 3 ships — maximal spend at the
  point of minimal information; pure lazy filling — costs nothing up front but
  concentrates a ~10s wait on exactly the early users whose impression matters most.

### AD-31: The available topics are served by an endpoint, not assumed by the client
- **Rationale:** FR-1 accepts `topic` as a free string, and the values are accented
  Italian (`velocità`). A client typo produces a `404` at `index = 0` that is
  indistinguishable from "you have walked the whole filtered bank" — the same status for
  a client error and a legitimate end-of-sequence. Without an endpoint the bot must
  hardcode a topic list that drifts from the database silently. One
  `SELECT topic, count(*) … GROUP BY topic ORDER BY topic` makes the filter genuinely
  usable, needs no new machinery, and lands with the other no-LLM endpoints in plan 2.
- **Rejected alternatives:** Adding a `total` field to FR-1's response so the client can
  at least distinguish "no such topic" from "walked off the end" — a consolation prize
  that diagnoses the mistake instead of preventing it, and still leaves the bot unable to
  render a menu; leaving topic discovery to the client — guarantees drift the moment the
  bank is re-ingested with adjusted topics, which has already happened once
  (`quiz-patente-ab.json` regenerated with fixed topics).

## Data Model

Four schema changes, no new tables. Per ADR 0010, each is written both as an
idempotent script in `db/migrations/` and applied to `db/init.sql` so a fresh volume
and a migrated database converge.

```sql
-- 1. Batch vs live provenance, and the live configuration epoch (AD-8).
ALTER TABLE labeling_runs
    ADD COLUMN origin TEXT NOT NULL DEFAULT 'batch'
        CHECK (origin IN ('batch', 'live'));

-- A live run cannot know the corpus commit, but a batch run still must: `corpus_commit()`
-- deliberately lets `git rev-parse` fail rather than record a placeholder, relying on this
-- column's NOT NULL. The conditional CHECK preserves that guarantee exactly where it
-- applied and relaxes it only where it cannot be honoured (AD-8).
ALTER TABLE labeling_runs ALTER COLUMN corpus_commit DROP NOT NULL;

ALTER TABLE labeling_runs
    ADD CONSTRAINT labeling_runs_batch_has_corpus_commit
        CHECK (origin <> 'batch' OR corpus_commit IS NOT NULL);

-- `lexeme_fields` completes the configuration epoch (AD-8): it determines the entire
-- text arm, so omitting it would let the judge see a different candidate set under an
-- identical epoch key. Stored sorted (canonicalised on write) so a cosmetic reordering
-- of the YAML list cannot invalidate the bank. Backfilled with the value the three
-- existing runs were produced under, which is the current `lexeme_fields` setting —
-- these runs predate the column, and assuming anything else would misreport them.
ALTER TABLE labeling_runs
    ADD COLUMN lexeme_fields TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];

UPDATE labeling_runs
SET lexeme_fields = ARRAY['image_description', 'text', 'topic']
WHERE lexeme_fields = ARRAY[]::TEXT[];

ALTER TABLE labeling_runs ALTER COLUMN lexeme_fields DROP DEFAULT;

CREATE UNIQUE INDEX uq_labeling_runs_live_config
    ON labeling_runs (judge_model, prompt_version, candidate_variant, dense_k, text_k,
                      lexeme_fields)
    WHERE origin = 'live';

-- 2. Human validation of a labeling as a whole (AD-9).
ALTER TABLE quiz_labelings
    ADD COLUMN validated_at TIMESTAMPTZ,
    ADD COLUMN validated_by TEXT,
    ADD CONSTRAINT quiz_labelings_validation_complete
        CHECK ((validated_at IS NULL) = (validated_by IS NULL));

-- 3. Denormalised outcome (AD-10), written transactionally with its children (FR-15).
--    DEFAULT FALSE, then backfilled from the child count. Measured on 2026-08-24, 3 of
--    the 14 existing labelings have zero children: a DEFAULT TRUE would mark them
--    "explainable" and the endpoint would try to explain citing nothing — precisely the
--    impossible state AD-10 undertakes to avoid, present from the first migration.
--    FALSE is also the safe direction if the backfill fails halfway: the error becomes
--    "an explainable question is not explained", never "explained citing nothing".
--    The DEFAULT is kept after the backfill: no caller supplies this column (FR-15), it
--    is computed by the INSERT itself, so the default only ever covers a hand-written row.
ALTER TABLE quiz_labelings
    ADD COLUMN has_supporting_commas BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE quiz_labelings l
SET has_supporting_commas = EXISTS (
    SELECT 1 FROM quiz_comma_labels cl WHERE cl.labeling_id = l.id
);

-- 4. The hot read is by question, which no existing index serves:
--    idx_quiz_labelings_run_id is on run_id, and UNIQUE (run_id, quiz_question_id)
--    is left-anchored on run_id.
CREATE INDEX idx_quiz_labelings_question_recent
    ON quiz_labelings (quiz_question_id, created_at DESC);
```

`quiz_comma_labels` is unchanged: its existing `dense_rank` / `text_rank` columns
already record which arm found each selected comma and at what position, which is the
retrieval trace the flow needs. The full candidate list is deliberately not persisted
(considered and rejected: ~700k rows for the batch bank plus ~100 per live request, to
enable offline analysis this spec does not require).

### Principal queries

**Propose (FR-1)** — reproducible permutation, optional topic filter:

```sql
SELECT number, topic, text, image_filename
FROM quiz_questions
WHERE (%s::text IS NULL OR topic = %s)
ORDER BY md5(id::text || %s), id
OFFSET %s LIMIT 1;
```

**Check (FR-3)** — single indexed lookup on `UNIQUE(number)`:

```sql
SELECT correct_answer FROM quiz_questions WHERE number = %s;
```

**Current labeling (FR-8)** — the precedence rule, literally:

```sql
SELECT l.id, l.rationale, l.has_supporting_commas, r.origin, r.judge_model,
       (l.validated_at IS NOT NULL) AS human_validated
FROM quiz_labelings  l
JOIN labeling_runs   r ON r.id = l.run_id
JOIN quiz_questions  q ON q.id = l.quiz_question_id
WHERE q.number = %s
  AND ( l.validated_at IS NOT NULL
        OR ( r.judge_model = %s AND r.prompt_version = %s AND r.candidate_variant = %s
             AND r.dense_k = %s AND r.text_k = %s AND r.lexeme_fields = %s ) )
ORDER BY (l.validated_at IS NOT NULL) DESC, l.created_at DESC
LIMIT 1;
```

The `lexeme_fields` parameter is the sorted array, matching the canonical form written by
AD-8; comparing arrays is exact and order-sensitive, which is precisely why the write
side canonicalises rather than the read side normalising.

**Available topics (FR-16)**:

```sql
SELECT topic, count(*) AS question_count
FROM quiz_questions
GROUP BY topic
ORDER BY topic;
```

**Labeled commas (FR-5)** — ordered by the judge's own ranking:

```sql
SELECT a.source, a.number, a.title, c.comma_number, c.text, cl.judge_rank
FROM quiz_comma_labels cl
JOIN article_commas    c ON c.id = cl.article_comma_id
JOIN articles          a ON a.id = c.article_id
WHERE cl.labeling_id = %s
ORDER BY cl.judge_rank;
```

**Precomputed query vector (FR-6, AD-13)**:

```sql
SELECT e.embedding_3_small
FROM quiz_question_embeddings e
JOIN quiz_questions q ON q.id = e.quiz_question_id
WHERE q.number = %s AND e.variant = %s;
```

**Live run, race-safe lazy creation (FR-9)**:

```sql
INSERT INTO labeling_runs (judge_model, prompt_version, candidate_variant,
                           dense_k, text_k, lexeme_fields, shuffle_seed,
                           corpus_comma_count, origin)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'live')
ON CONFLICT DO NOTHING;

SELECT id FROM labeling_runs
WHERE origin = 'live' AND judge_model = %s AND prompt_version = %s
  AND candidate_variant = %s AND dense_k = %s AND text_k = %s
  AND lexeme_fields = %s;
```

**Labeling write, idempotent under concurrency (FR-6, AD-19, FR-15)** — the losing
racer's insert is discarded rather than raising, and the outcome flag is computed from
the very array that feeds the children, so the two cannot disagree:

```sql
WITH parent AS (
    INSERT INTO quiz_labelings (run_id, quiz_question_id, rationale,
                                has_supporting_commas)
    VALUES (%s, %s, %s, cardinality(%s::bigint[]) > 0)
    ON CONFLICT (run_id, quiz_question_id) DO NOTHING
    RETURNING id
), children AS (
    INSERT INTO quiz_comma_labels
        (labeling_id, article_comma_id, judge_rank, dense_rank, text_rank)
    SELECT parent.id, c.article_comma_id, c.judge_rank, c.dense_rank, c.text_rank
    FROM parent, unnest(%s::bigint[], %s::int[], %s::int[], %s::int[])
        AS c(article_comma_id, judge_rank, dense_rank, text_rank)
)
SELECT id FROM parent;
```

This is the existing `GoldenSetWriteRepository.insert_labeling` statement with two
additions: the `ON CONFLICT` clause, and `has_supporting_commas` derived from
`cardinality()` over the same comma-id array the `children` CTE unnests. The children
CTE needs no branch for the conflict case — it cross-joins `parent`, so an empty parent
inserts nothing.

An empty `RETURNING` means another request won the race; the caller then re-reads the
current labeling (FR-8) instead of writing its own `quiz_comma_labels` children. The
method's return type therefore becomes `int | None` (AD-19): `return int(rows[0][0])`
would raise `IndexError` on the losing racer, on a user-facing path.

**Validated-labeling guard for `reset knowledge` (FR-17, AD-28)**:

```sql
SELECT count(*) FROM quiz_labelings WHERE validated_at IS NOT NULL;
```

**Image authorisation (FR-12, AD-24)** — the filename is validated against the database
before any filesystem access:

```sql
SELECT EXISTS (SELECT 1 FROM quiz_questions WHERE image_filename = %s);
```

**Startup judge check (FR-14, AD-23)**:

```sql
SELECT DISTINCT prompt_version FROM labeling_runs;
```

The dense and text arms themselves issue no new SQL: they reuse
`CorpusReadRepository.dense_top_k` and `.text_match_top_k` unchanged.

## Component Map

New or changed code, by package.

| Package | Component | Kind | Note |
|---|---|---|---|
| `src/labeling/` | `CommaLabelerAgent`, `CandidateSetService`, `QuestionLexemeService`, `GoldenSetWriteRepository`, `CandidateComma` | moved | extracted from `retrieval_evaluation/` (AD-12); stays manual-DI and **synchronous** (AD-25) |
| `src/labeling/` | builder functions | moved | from `retrieval_evaluation/wiring.py`, reparameterised on `LabelingConfig` (AD-16, AD-27) |
| `src/labeling/configs/` | `LabelingConfig` | moved + extended | from `guidami_ai_patente_ingestor/configs/`; gains `agents_dir`, embedded in both roots from one `configs/labeling.yaml` (AD-27) |
| `commons/clients/` | `PostgresClient` | changed | single connection → `psycopg_pool.ConnectionPool`, `configure=register_vector` (AD-26) |
| `src/labeling/` | `GoldenSetWriteRepository` | changed | `ON CONFLICT DO NOTHING` on both inserts, `insert_labeling() -> int \| None`, `has_supporting_commas` derived in-statement (AD-19, FR-15) |
| `guidami_ai_patente_ingestor/cli/` | `reset knowledge` | changed | truncates the golden-set tables too; refuses on validated labelings without `--force` (FR-17, AD-28) |
| `retrieval_evaluation/` | `label_main` | changed | repeatable `--topic` for sliced pre-warm (FR-18, AD-30) |
| `guidami_ai_patente/clients/` | `PostgresClientProvider`, `OpenRouterProviderComponent`, `LabelingStackProvider` | new `@client` | the only providers — shared/third-party code (AD-16) |
| `guidami_ai_patente/repositories/` | `QuizQuestionRepository`, `GoldenSetReadRepository` | new `@repository` | pywire-native, `Autowired` fields (AD-16, AD-16b) |
| `guidami_ai_patente/services/` | `QuizProposalService`, `QuizAnswerChecker`, `CommaSelector`, `ExplanationService` | new `@service` | pywire-native; `CommaSelector` = cache-hit or live+write-through |
| `guidami_ai_patente/services/` | `evaluate_answer` | new function | stateless, unit-testable without the container |
| `guidami_ai_patente/agents/` | `ExplanationWriterAgent` + DTOs | new `@agent` | pywire-native via zero-arg `__init__` (AD-14, AD-16) |
| `guidami_ai_patente/exceptions/` | `GuidamiApiError`, `QuestionNotFoundError` | new | carried from the superseded spec |
| `guidami_ai_patente/services/` | `QuizImageService` | new `@service` | DB-validated filename → bytes (FR-12) |
| `guidami_ai_patente/services/` | `JudgeCoherenceChecker` | new `@service` | startup `prompt_version` warning (FR-14) |
| `guidami_ai_patente/api/routers/` | `quiz_questions.py`, `quiz_images.py` | new | thin controllers, no `try/except`; `async def`, `await` the agent, `to_thread` the SQL (AD-25) |
| `guidami_ai_patente/api/schemas/` | one file per endpoint | new | carried from the superseded spec |
| `guidami_ai_patente/enums/` | `ExplanationStatus`, `InsufficientKnowledgeReason` | new | `StrEnum` + `auto()` |

## Implementation Sequencing

This spec is deliberately larger than one implementation plan. It decomposes into three
plans with a strict dependency order, each independently shippable and verifiable:

1. **Extraction, schema and infrastructure** (AD-12, AD-26, AD-27, AD-28, Data Model) —
   create `src/labeling/`, move the shared half out of `retrieval_evaluation/`, move and
   extend `LabelingConfig`, reparameterise the builders on it, write the migration
   (including `lexeme_fields`) and the matching `db/init.sql` edit, adapt
   `GoldenSetWriteRepository` (`ON CONFLICT`, `int | None`, in-statement
   `has_supporting_commas`), switch `PostgresClient` to a pool, apply AD-22's
   five-place `AGENTS_DIR` change, and repair `reset knowledge` (FR-15, FR-17).
   Touches no HTTP surface. **The gate is the batch suite passing unchanged** — this
   plan is the only one that edits code the API does not use, and both the pool and the
   write-path changes can regress it.
2. **Quiz endpoints, no LLM** (FR-1, FR-2, FR-3, FR-4, FR-8, FR-12, FR-14, FR-16) —
   propose, fetch, check, list topics, serve images, the `explanation_status`
   advertisement, and the startup judge-coherence warning. Requires
   `GoldenSetReadRepository` and the FR-8 precedence query, but calls no model and opens
   no write path. This is the whole quiz loop minus the explanation: a bot built on it
   can already ask, show the sign, grade, and tell the user whether an explanation will
   be available.
3. **The explanation endpoint** (FR-5, FR-6, FR-7, FR-9, FR-10, FR-11, FR-13, FR-18) —
   the `ExplanationWriterAgent`, cache-served explanations, cache-miss retrieval plus
   judge, write-through, the optional `submitted` answer, `503` handling per AD-29, the
   `async`/`to_thread` boundary of AD-25, and `--topic` for the AD-30 pre-warm. Both the
   cached and the live path need the writer, so they ship together rather than
   splitting it further.

Plan 2 delivers the first end-to-end bot loop (ask → grade), but **measured golden-set
coverage is 14 labelings against 7099 questions** (see Open Questions), so plan 2 will
advertise `on_demand` for essentially the whole bank. Plan 3 is therefore not an
optional later increment: without it the explanation feature does not exist in
practice. Plans 2 and 3 may be merged if shipping the quiz loop early has no
independent value.

## Constraints

- `pywire` stays scoped to `src/guidami_ai_patente/`; `commons/`, `labeling/` and
  `guidami_ai_patente_ingestor/` keep manual constructor injection (ADR 0015).
- Every component this spec introduces under `src/guidami_ai_patente/` is
  pywire-native: role decorator, class-level `Autowired[T]` fields, zero-argument
  constructible. A provider wrapper is permitted **only** for a class shared with the
  pre-pywire packages or owned by a third party (AD-16) — never for new code, which is
  shaped for the container instead.
- Routers contain no `try/except` and no HTTP-status logic; domain exceptions are
  mapped by a global handler registered on the app.
- At most one `AppConfig` is constructed per pytest session, via the shared session
  fixture — pywire's singleton cache makes any second construction silently
  ineffective and can point the suite at the dev database.
- Integration tests target only the ephemeral test stack
  (`docker/docker-compose.test.yml`, port 5433), never the dev database (ADR 0011).
- The batch labeler and the live labeler are the same `CommaLabelerAgent` instance
  type, loading the same prompt; `prompt_version` must therefore be derived from the
  prompt content, as it already is.
- Every schema change ships as both a `db/migrations/` script and an edit to
  `db/init.sql` (ADR 0010).
- `dense_k`, `text_k` and `lexeme_fields` are configuration, not literals, and their
  values participate in the live-run configuration epoch (AD-8). `lexeme_fields` is
  canonicalised by sorting on write, in the mapper that builds `LabelingRunEntity`, so
  the batch and live paths cannot disagree.
- The six epoch inputs are single-sourced through `LabelingConfig`, resolved from one
  `configs/labeling.yaml` and embedded in both `IngestorConfig` and `AppConfig` (AD-27).
  No epoch field may be declared independently on either root.
- Route handlers are `async def`; LLM calls are `await`ed via `BaseAgent.run`, and the
  synchronous `src/labeling/` stack is invoked through `asyncio.to_thread` (AD-25). No
  route calls `run_sync`.
- `src/labeling/` stays synchronous. Making it async would break the batch callers and
  forfeit the single-implementation guarantee AD-12 exists to provide.
- Pool size is deployment configuration on `AppConfig`/`IngestorConfig`, never on
  `LabelingConfig` — it must not enter the epoch key (AD-26).
- `has_supporting_commas` is absent from `QuizLabelingEntity` and computed inside the
  write statement; no caller may supply it (FR-15, AD-10).
- `agents_dir` has **no default** — not in the Python field and not in
  `configs/ingestor_config.yaml`. `AGENTS_DIR` is its single source, and both
  `IngestorConfig` and `AppConfig` read it (AD-22). A test asserts the two configs
  resolve to the same `comma_labeler.yaml` with the same content hash; that test is a
  spec constraint, not optional coverage.
- A failed live stage writes nothing to any golden-set table (AD-20). No partial
  labeling, no run row created speculatively.
- `GET /quiz-images/{filename}` resolves the name against
  `quiz_questions.image_filename` **before** any filesystem access; a name not
  referenced by the database is a 404 regardless of what exists on disk (AD-24).
- Response DTO docstrings and `Field(description=...)` on agent response models are
  written in Italian (prompt-facing text exception in
  `.claude/rules/code-conventions.md`); every other docstring, comment and log message
  is English.

## Feasibility Evidence

- **AD-2** — supported by: `src/commons/repositories/db/corpus_read_repository.py:118-143`
  — `random_top_k` already orders by `md5(c.id::text || %s), c.id`, the exact
  seeded-permutation mechanism FR-1 reuses (verified 2026-08-24 @ 0613545d)
- **AD-3** — supported by: `db/init.sql:46-63` — `correct_answer BOOLEAN NOT NULL` is a
  plain column, so excluding it is a projection choice, not a schema change (verified
  2026-08-24 @ 0613545d)
- **AD-6/FR-7** — supported by:
  `src/retrieval_evaluation/agents/comma_labeler/dto/comma_labeler_response.py:24-40` —
  `rationale` is `min_length=1` and its description mandates an explanation *especially*
  when `comma_numbers` is empty, so the "why not" text is already produced and
  persisted (verified 2026-08-24 @ 0613545d)
- **AD-7** — supported by: sampling 2277 commas from `data/cleaned/` gives a mean of 463
  characters (median 339, p90 836) ≈ 132 tokens per comma, so ~80–100 deduplicated
  candidates ≈ 10–13k input tokens for the judge versus ~750–1000 for a 2–3 comma
  writer call (measured 2026-08-24 @ 0613545d)
- **AD-8** — supported by: `db/init.sql:123-135` — `labeling_runs` carries
  `shuffle_seed`, `corpus_commit`, `corpus_comma_count` and `question_limit`, the
  batch-oriented columns that make a per-request run row impractical (verified
  2026-08-24 @ 0613545d)
- **AD-9** — supported by: `db/init.sql:118-122` and `:154-165` — the schema comment
  states that zero `quiz_comma_labels` children *is* the "corpus does not justify"
  outcome, confirming the empty verdict has no child row to carry a flag (verified
  2026-08-24 @ 0613545d)
- **AD-10** — supported by: `db/init.sql:118-122` — the comment explicitly records the
  prior decision that "No outcome column exists by design", which this AD amends
  (verified 2026-08-24 @ 0613545d)
- **AD-12** — supported by: `src/retrieval_evaluation/` file listing —
  `services/candidate_set_service.py`, `services/question_lexeme_service.py`,
  `services/golden_set_labeling_service.py`, `repositories/golden_set_write_repository.py`,
  `agents/comma_labeler/` and `models/candidate_comma.py` are the shared half;
  `agents/retrieval_judge/`, `main.py` and `services/retrieval_judge_evaluation_service.py`
  are evaluation-only (verified 2026-08-24 @ 0613545d)
- **FR-6 / AD-12** — supported by:
  `src/retrieval_evaluation/services/candidate_set_service.py:30-56` — `build` already
  performs `dense_top_k(row.embedding, dense_k)` plus `text_match_top_k(lexemes, text_k)`
  and merges them by `comma.id` carrying one-based `dense_rank`/`text_rank`, which is
  FR-6's candidate stage verbatim (verified 2026-08-24 @ 0613545d)
- **FR-6 lexemes** — supported by:
  `src/retrieval_evaluation/services/question_lexeme_service.py:1-40` — lexeme source
  fields are already configuration (`LexemeField`) and extraction already delegates to
  `CorpusReadRepository.extract_lexemes`, sharing the `italian` dictionary with the GIN
  indexes (verified 2026-08-24 @ 0613545d)
- **AD-13** — supported by:
  `src/guidami_ai_patente_ingestor/services/quiz/quiz_variant_registry.py:32-39,63-76` —
  the `topic_text` variant composes `topic`, `text`, `image_description`, exactly the
  fields specified; `configs/ingestor_config.yaml:58` lists `topic_text` among the
  ingested variants; `src/commons/clients/postgres_client.py:5,28` — `register_vector`
  is called on the connection, so a `VECTOR` column deserialises without custom parsing;
  a live count against the dev database gives 7099 `quiz_question_embeddings` rows for
  variant `topic_text` against 7099 `quiz_questions` — **complete coverage**, so the
  dense arm never lacks its query vector in practice (measured 2026-08-24 @ 0613545d)
- **AD-14** — supported by:
  `src/retrieval_evaluation/agents/comma_labeler/dto/comma_labeler_response.py:42-47` —
  `_reject_repeated_numbers` is the existing precedent for a `model_validator` that
  makes pydantic-ai retry rather than admitting a bad response (verified 2026-08-24 @
  0613545d)
- **AD-16** — supported by: `docs/second-brain/adr/0017-appconfig-component-and-testable-autowiring.md`
  — establishes the `@client` provider building a constructor-argument dependency inside
  its own `__init__` after `Autowired` fields are set;
  `src/commons/ai/agents/base_agent.py:25-31` — `BaseAgent.__init__` requires
  `config: AgentConfig` and `provider: OpenRouterProvider`, confirming a new agent needs
  a zero-argument `__init__` reading its own `Autowired` fields rather than direct
  autowiring; `src/retrieval_evaluation/wiring.py:17-96` — the nine builder functions
  the `LabelingStackProvider` consolidates, each currently taking `IngestorConfig` and
  therefore needing reparameterisation during the AD-12 extraction (verified 2026-08-24
  @ 0613545d)
- **AD-16b** — supported by: `.claude/rules/cli-structure.md` — the "is this used by
  anything other than the app? No → local" test; `src/retrieval_evaluation/repositories/golden_set_write_repository.py`
  is the only existing golden-set repository, confirming no read path exists to share
  (verified 2026-08-24 @ 0613545d)
- **AD-17** — supported by: `docs/superpowers/specs/2026-08-19-quiz-check-endpoint-design.md:12-20`
  (titled "Spec 0011", Status `draft`, sign-off `pending`) and
  `docs/superpowers/specs/2026-08-19-retrieval-golden-set-design.md` (also "Spec 0011"),
  with `db/init.sql:118,148` referencing "spec 0011" for the golden-set tables — the
  collision and its correct resolution (verified 2026-08-24 @ 0613545d)

- **AD-10 / FR-15 backfill** — supported by: a live count against the dev database
  groups the 14 existing `quiz_labelings` by child count as 0→**3**, 1→3, 2→6, 3→2,
  proving that a `DEFAULT TRUE` would mis-mark three rows as explainable on migration
  day (measured 2026-08-24 @ 0613545d)
- **AD-19** — supported by: `db/init.sql:143` — `UNIQUE (run_id, quiz_question_id)` on
  `quiz_labelings` is the constraint a concurrent second write hits, and the conflict
  target `ON CONFLICT DO NOTHING` names (verified 2026-08-24 @ 0613545d)
- **AD-20** — supported by:
  `src/retrieval_evaluation/agents/comma_labeler/dto/comma_labeler_response.py:42-47` —
  validation failure surfaces as a raised exception after pydantic-ai exhausts
  `config.num_retries`, so the transient-failure path is reachable and distinct from an
  empty `comma_numbers` result (verified 2026-08-24 @ 0613545d)
- **AD-22** — supported by:
  `src/retrieval_evaluation/utils/run_provenance.py:6-12` — `prompt_version` is
  `sha256(f"{system}\n{user}")[:16]`, derived purely from prompt text, so two loaded
  copies diverge iff their content differs;
  `src/guidami_ai_patente_ingestor/configs/ingestor_config.py:59` — `agents_dir` today
  defaults to `Path("configs/agents")`; `configs/ingestor_config.yaml:41` — and is
  *also* set in the base yaml, so both must be removed for the fail-fast to trigger;
  `src/guidami_ai_patente_ingestor/configs/ingestor_config.py:127` — documented
  precedence `init > env/.env > override yaml > base yaml` confirms a base-yaml value
  would still satisfy the field (verified 2026-08-24 @ 0613545d)
- **AD-23** — supported by: `db/init.sql:123-135` — `labeling_runs.prompt_version` is a
  plain `TEXT NOT NULL` column, so `SELECT DISTINCT prompt_version` is a single cheap
  scan of a table holding 3 rows today (verified 2026-08-24 @ 0613545d)
- **AD-24** — supported by: `db/init.sql:90-93` — `quiz_images` is keyed by `filename`
  and `quiz_questions.image_filename` references it, giving the database-side
  authorisation list the endpoint validates against; `quiz_images` holds 427 rows and
  `data/quiz-images/` holds exactly 427 files — a 1:1 match, so no referenced image is
  missing — under a stable top-level directory by ADR 0008, configured as
  `quiz_images_dir` (`configs/ingestor_config.yaml:42`); filenames are content hashes
  (`000b9ec4803628ffc83403efb710b16e.jpeg`) with no path structure, so the traversal
  check is trivially satisfiable; a repo-wide grep for `StaticFiles` in `src/` returns
  no matches, confirming no image route exists today (verified 2026-08-24 @ 0613545d)

- **AD-25** — supported by: `src/commons/ai/agents/base_agent.py:94,111` — `BaseAgent`
  exposes **both** `async def run` and `def run_sync`, so the async boundary needs no new
  agent API; `src/retrieval_evaluation/services/candidate_set_service.py:31`,
  `question_lexeme_service.py:23`, `repositories/golden_set_write_repository.py:63,75` —
  every shared stage is a plain synchronous method, confirming `to_thread` (not an async
  rewrite) is what preserves AD-12 (verified 2026-08-24 @ 0613545d)
- **AD-26** — supported by: `src/commons/clients/postgres_client.py:26` —
  `psycopg.connect(conninfo, autocommit=True)` opens exactly **one** connection, held for
  the object's lifetime, with no pool anywhere in the class; `:27` — `register_vector` is
  called on that connection, so a pool must register it per-connection via `configure=`;
  `src/retrieval_evaluation/label_main.py:41-46` — `--concurrency` already drives
  in-flight judge calls whose DB writes serialise implicitly behind the single
  connection today (verified 2026-08-24 @ 0613545d)
- **AD-27** — supported by:
  `src/guidami_ai_patente_ingestor/configs/labeling_config.py:17-28` — `LabelingConfig`
  already exists and already holds `candidate_variant`, `dense_k`, `text_k` and
  `lexeme_fields` with validators, so this AD is a move plus `agents_dir`, not a new
  design; `ingestor_config.py:90` — it is already nested as `IngestorConfig.labeling`;
  `ingestor_config.py:59` — `agents_dir` sits one level above it, on the root, which is
  the misplacement this AD corrects;
  `src/guidami_ai_patente/configs/app_config.py:22-24` — `AppConfig` today holds only
  `host`, `port` and `postgres`, so every epoch field would otherwise be added to it by
  hand (verified 2026-08-24 @ 0613545d)
- **AD-8 / `lexeme_fields`** — supported by:
  `src/retrieval_evaluation/services/question_lexeme_service.py:17-20,30` —
  `lexeme_fields` is injected configuration read via `getattr(row, field.value)` and
  determines the entire text arm, yet appears in no column of `labeling_runs`
  (`db/init.sql:123-135`); `question_lexeme_service.py:34` — the lexemes are quoted and
  OR-ed into one `tsquery`, so the *set* changes retrieval while the order does not,
  which is what makes sorting the safe canonical form (verified 2026-08-24 @ 0613545d)
- **AD-19 / `int | None`** — supported by:
  `src/retrieval_evaluation/repositories/golden_set_write_repository.py:120-121` —
  `insert_labeling` ends `rows = self._client.fetch(...)` / `return int(rows[0][0])`,
  which raises `IndexError` when `ON CONFLICT DO NOTHING` suppresses the insert; `:30-48`
  — the class docstring states "no upsert/conflict-handling clause" and "A labeling's
  outcome is derived, never stored" as design, both of which this spec amends explicitly
  (verified 2026-08-24 @ 0613545d)
- **AD-28** — supported by: `src/guidami_ai_patente_ingestor/cli/commands/reset.py:52` —
  `postgres_client.truncate(config.article_commas_table, config.articles_table)` names
  only the two corpus tables; `db/init.sql:154-165` —
  `quiz_comma_labels.article_comma_id BIGINT NOT NULL REFERENCES article_commas (id)`
  is an inbound foreign key from a table the statement does not name, which PostgreSQL
  refuses to truncate around regardless of row counts — so the command is already broken
  today (verified 2026-08-24 @ 0613545d)
- **AD-30 / FR-18** — supported by: `src/retrieval_evaluation/label_main.py:41-57` — the
  batch labeler exposes `--concurrency`, `--seed` and `--limit` and **no** topic filter,
  so a sliced pre-warm requires the new flag; `pyproject.toml:39` —
  `label-golden-set = "retrieval_evaluation.label_main:main"` is the entry point that
  gains it (verified 2026-08-24 @ 0613545d)
- **AD-31 / FR-16** — supported by: `db/init.sql:46-63` — `topic` is a plain column on
  `quiz_questions` with no lookup table, so the distinct set is only discoverable by
  aggregation and no client can enumerate it a priori (verified 2026-08-24 @ 0613545d)

## Open Questions

- [x] **resolved 2026-08-24, measured** — Golden-set coverage: `labeling_runs` = 3,
  `quiz_labelings` = **14**, `quiz_comma_labels` = 21, against a bank of 7099. The cache
  is effectively empty (0.2%). `quiz_question_embeddings` for variant `topic_text`, by
  contrast, is **7099/7099 — complete**. Two consequences, both folded into the plan
  above: `not_indexed` is a theoretical branch that will essentially never fire in
  production and must be tested with a synthetic fixture rather than real data; and the
  live pipeline (plan 3) is **not** an optional later increment — without it the
  explanation feature does not exist for 99.8% of questions. See the new open question
  below on pre-warming.
- [x] **resolved 2026-08-24 (AD-30)** — Pre-warm versus lazy fill: **neither extreme.**
  Pre-warm a bounded slice — the highest-frequency topics, a few hundred questions — then
  let traffic fill the tail. A full 78M-input-token run before the writer has ever run in
  production commits maximal spend at the point of minimal information; the slice yields a
  measured cost-per-question and refusal rate first. Requires FR-18's `--topic` flag.
- [x] **resolved 2026-08-24 (AD-27)** — The nine builders in
  `retrieval_evaluation/wiring.py` take `LabelingConfig`, not `IngestorConfig` and not a
  bespoke settings protocol. The class already exists
  (`guidami_ai_patente_ingestor/configs/labeling_config.py`) and already carries most of
  what they read; AD-27 moves it into `src/labeling/configs/` and adds `agents_dir`.
- [ ] **non-blocking** — `LabelingConfig` will hold both epoch fields
  (`candidate_variant`, `dense_k`, `text_k`, `lexeme_fields`, `agents_dir`) and run
  mechanics (`shuffle_seed`, `concurrency`, `transport_retries`,
  `retry_backoff_seconds`). Decide during the AD-27 move whether the two groups are split
  into nested models or merely documented as distinct in the class docstring — owner:
  whoever implements AD-27. The spec requires only that the distinction be explicit.
- [ ] **non-blocking** — `QuizEvaluationRow` (`domain/models/retrieval/`) is the input
  `CandidateSetService` expects, and its name reflects the evaluation origin. Decide
  during the AD-12 extraction whether it is renamed or kept — owner: whoever implements
  the extraction.
- [ ] **non-blocking** — `ADR 0017` is still `Proposed` and still carries the
  constructor-parameter testability exception that the superseded quiz-check spec's
  AD-9 concluded does not work (pywire's patched `__new__` returns the cached singleton,
  so a second construction's keyword is discarded). That item should be removed when
  ADR 0017 is accepted — owner: whoever implements AD-16.
- [ ] **non-blocking** — `quiz_questions.rule_explanation` becomes orphaned at runtime
  (AD-7). Decide separately whether the ingestion still needs to produce it — owner:
  a later ingestion-scope review.
- [ ] **non-blocking** — the live path takes ~10s, near or beyond typical client
  timeouts. AD-25 stops one such request from blocking every other one, but it does not
  make the request itself shorter. If it proves a problem in practice, the answer is a
  `202` + polling contract, deliberately out of scope here — owner: revisit after the bot
  exists.
- [ ] **non-blocking** — `GET /health` is untouched by this spec. Exposing the resolved
  epoch there for on-demand comparison (rather than only in FR-14's startup log) was
  considered and deliberately scoped out — owner: a later observability review.

## Sign-off

- **Scope approved by user:** yes — 2026-08-24, after the second `grilling` pass
- **Feasibility asserted:** by brainstorming on 2026-08-24, based on Feasibility
  Evidence above

## Changelog

- **2026-08-24** — Initial draft.
- **2026-08-24** — Revised after a `grilling` stress-test of the draft. Nine decisions
  taken, three of which fixed defects rather than refining choices:
  **(1)** the migration's `DEFAULT TRUE` on `has_supporting_commas` would have marked as
  explainable the 3 of 14 existing labelings that have zero comma children — the exact
  impossible state AD-10 undertakes to prevent — now `DEFAULT FALSE` plus a backfill
  from the child count; **(2)** dropping `corpus_commit`'s `NOT NULL` silently disarmed
  the guard `corpus_commit()` deliberately relies on, restored as a conditional `CHECK`
  scoped to batch runs; **(3)** no endpoint served the 427 quiz images, leaving every
  sign-based question unusable — added as FR-12/AD-24, a missing capability rather than
  a refinement. Also added: concurrency semantics for simultaneous cache misses
  (FR-6/AD-19), a `503` contract for transient failures that writes nothing
  (FR-13/AD-20), the optional `submitted` answer passed to the writer (FR-11/AD-21),
  `AGENTS_DIR` as the single defaultless source for the judge prompt (AD-22) with a
  startup coherence warning for the cross-deployment case it cannot cover
  (FR-14/AD-23), and the seeded permutation's instability recorded as an accepted
  limitation (AD-18). FR-1's untestable "different seeds" criterion was restated over
  the whole sequence, and the original FR-11 renumbered to FR-15. Material change —
  status stays `draft`, scope needs approval.
- **2026-08-24** — Revised after a second `grilling` pass, run against the code rather
  than the prose. Seventeen decisions; seven of them fixed defects rather than refining
  choices:
  **(1)** FR-6 and FR-13 **contradicted each other** when the judge succeeded and the
  writer then failed — the expensive stage discarded for the cheap one's outage. The
  golden set now records the judge's verdict, not the writer's success (AD-29); AD-20's
  companion rule narrows from "a failed live stage" to "a failed judge stage".
  **(2)** The configuration epoch was **incomplete**: `lexeme_fields` determines the
  entire text arm and appeared in no column of `labeling_runs`, so the cache could serve
  labelings built from candidates the active configuration would never retrieve. Added
  as a sorted `TEXT[]` to the table, the partial unique index and FR-8's precedence
  (AD-8).
  **(3)** `GoldenSetWriteRepository` **forbids in its own docstring** the
  conflict-handling FR-6/FR-9 require, and `insert_labeling`'s `return int(rows[0][0])`
  would raise `IndexError` on the losing racer of AD-19's documented race — on a
  user-facing path. Return type becomes `int | None`; the amendment to the class's
  stated invariants is now explicit (AD-19).
  **(4)** `ingest reset knowledge` is **already broken**: `TRUNCATE article_commas,
  articles` cannot succeed with `quiz_comma_labels`' inbound foreign key outstanding.
  Repaired, and guarded so it cannot silently destroy the human validations AD-11 exists
  to protect (FR-17, AD-28).
  **(5)** AD-22 hardened **one** of six epoch inputs; the other five were about to be
  duplicated across two independently-loaded configs with the identical silent-100%-
  cache-miss failure mode. `LabelingConfig` — which already exists in the ingestor
  package — moves into `src/labeling/`, absorbs `agents_dir`, and single-sources the
  epoch for both roots (AD-27). AD-22 survives, rescoped to the cross-deployment case it
  still uniquely covers, with its five-place blast radius now named.
  **(6)** `explanation_status = "ready"` **never meant ready**: FR-5 invokes the writer
  on every request, cache hit included. Vocabulary changed to `cached` | `uncached` |
  `unavailable` and AD-4's rationale corrected (AD-4).
  **(7)** Async concurrency and AD-12's shared synchronous module were **mutually
  exclusive** as drafted, and `PostgresClient` holds a single connection, so AD-19's race
  could not occur at all. Resolved by awaiting the agent and `to_thread`-ing the SQL,
  keeping `src/labeling/` synchronous and untouched (AD-25), with `PostgresClient`
  pooled (AD-26) — a change that reaches the batch path and is therefore sequenced into
  plan 1 with the batch suite as its gate.
  Also added: `has_supporting_commas` derived inside the write statement from the same
  array that feeds its children, retiring AD-10's risk by construction rather than
  mitigating it (FR-15); `GET /quiz-questions/topics`, without which the `topic` filter
  is unusable and a typo is indistinguishable from an exhausted bank (FR-16, AD-31);
  `--topic` on `label-golden-set` (FR-18) enabling a bounded pre-warm slice instead of a
  78M-token full run (AD-30); and `corpus_commit`'s exclusion from the epoch key recorded
  as an accepted limitation rather than left implicit (AD-8). Three open questions
  closed. `GET /health` deliberately left untouched. Material change — status stays
  `draft`, scope needs approval.
