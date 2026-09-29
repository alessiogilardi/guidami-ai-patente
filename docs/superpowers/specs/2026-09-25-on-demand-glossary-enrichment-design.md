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

# Spec 0021: On-demand glossary enrichment for the vocabulary explanation stage

| | |
|---|---|
| **Id** | 0021 |
| **Status** | implemented |
| **Date** | 2026-09-25 |
| **Discussion log** | — (brainstormed inline via `superpowers:brainstorming`; no separate transcript file) |
| **Supersedes / superseded by** | — |
| **Extends** | Spec 0020 (unified "Spiega"): adds a second, independent source of glossary candidates inside the existing `_vocabulary_outcome` stage. Introduces no new endpoint. |
| **Enhanced by** | Spec 0019 (definition glossary): the DB-side candidate source this feature merges with, unchanged. |
| **Reuses** | Spec 0011/0012's live comma-retrieval infrastructure (`CandidateSetService` over `CorpusReadRepository`), read-only, for the on-demand agent's corpus grounding. |
| **Coordinates with** | Spec 0022 (plain-language glossary definitions) — **implemented first**, per that spec's own header/changelog. It already added `GlossaryCandidate.definition_plain: str | None = None`, `GlossaryReadRepository`'s extra column, and `_deduplicated_hints`' `candidate.definition_plain or candidate.definition` fallback (`services/explanation_service.py:250-282`, current). This spec's implementation builds `origin` on top of that already-landed shape (FR-6/FR-8, Data Model) — re-verified feasible against the real, current code on 2026-09-25 (see Changelog). |

## Problem & Motivation

`glossary_entries` (spec 0019) is only as complete as `build-glossary`'s offline
extraction pass has covered so far — it extracts verbatim term/definition pairs from
whichever corpus blocks are configured, one block at a time (ADR 0036, ADR 0038). A
quiz question can legitimately use a legal term the pass has not reached yet, or that
never appears as a standalone defined term in the corpus at all (e.g. "revoca",
"sospensione" — CdS uses both with precise, distinct legal meanings that a candidate
preparing for the exam needs to tell apart).

Today, when `GlossaryReadRepository.candidates_for` returns no good candidate for such
a term, `QuestionExplainerAgent` can still explain it — its own prompt already allows
"a term you explain from your own knowledge, with no matching candidate, in plain prose
without guillemets" — but that explanation gets no `«guillemet»` grounding marker, no
`translation_hints` entry, and therefore no dedicated glossary block (spec 0020, FR-8)
and no per-term Russian pinning on a later "Traduci" tap (spec 0018). The candidate
sees a lesser experience for exactly the terms most likely to be unfamiliar or newly
added to the corpus.

This spec adds a second, independent agent, `GlossaryEnricherAgent`, that generates its
own candidate definitions for a question's terms, live, on every explanation request —
grounded on the same corpus retrieval already used to ground the legal explanation
(answer-blind, no judge involved), falling back to the LLM's own general knowledge only
for a term that retrieval finds nothing for. Its output is merged with the DB-retrieved
candidates — the DB always wins a same-term conflict — before the merged list reaches
`QuestionExplainerAgent`, whose own contract does not change at all. The client can tell
which source grounded which cited term via a new `origin` field.

**Shapes considered and rejected during brainstorming, recorded so a future reader does
not re-propose them:**

- **Gap-detection via a retrieval-score threshold** before deciding whether to invoke
  the on-demand agent — rejected: introduces an arbitrary threshold/config knob on top
  of an already-fused RRF score, and does not remove the need to decide what "gap"
  means. Superseded by always running the on-demand agent and letting merge-with-
  DB-priority absorb the redundant case for free.
- **Gap-detection via an explicit expected-term extraction pass** (a separate step
  that lists the technical terms in the question, then checks each against
  `glossary_entries.term`) — rejected: adds its own LLM/heuristic call and a second
  point of failure *ahead of* the stage's own agent, for a problem the always-run
  approach avoids needing to solve at all.
- **`QuestionExplainerAgent` itself flagging missing terms**, then a follow-up call to
  fill them — rejected: a two-round-trip shape (flag, then generate) costs more
  latency than two independent sources gathered once, concurrently.
- **Write-through of on-demand definitions into `glossary_entries`** (mirroring the
  spec 0017 comma-labeling cache-fill pattern) — rejected: would mix verbatim
  corpus-extracted rows (ADR 0038's mechanical guarantee) with live-generated rows —
  sometimes grounded in a retrieved comma, sometimes from general knowledge — in the
  same table, with no reliable way to tell them apart on a later read. `build-glossary`
  stays the only writer of `glossary_entries`.
- **Reusing `GlossaryExtractorAgent` with its `output_validator` disabled by config**
  — rejected: that validator's verbatim-in-source-chunk contract (ADR 0038) is central
  to the class's identity; toggling it would blur two genuinely different tasks
  (extract-from-a-known-chunk vs. generate-from-live-retrieval-or-general-knowledge)
  into one class with two incompatible behaviors.
- **Conditional invocation** (only call the on-demand agent when DB retrieval looks
  weak) — rejected: reintroduces the gap-detection problem discarded above. Always
  running it in parallel is simpler and consistent with spec 0020's existing tolerance
  for an additional concurrent, best-effort stage.
- **Fuzzy or semantic dedup on merge** (e.g. embedding similarity between "sospensione"
  and "sospensione della patente") — rejected: introduces an arbitrary similarity
  threshold; normalized exact-match (`term.casefold()`) is simple, deterministic, and
  already the dedup key `ExplanationService._deduplicated_hints` uses today for a
  related case (two distinct DB rows sharing a term).
- **A per-question cache for on-demand entries** — not proposed by anyone and not
  considered: it would need the same write-through/provenance problem above just to
  exist, for a stage spec 0020 already established should be generated live and
  symmetrically with its DB-only sibling (spec 0020, AD-2).

## Functional Requirements

### FR-1: A second, independent agent generates glossary candidates, live, every call

`GlossaryEnricherAgent` (`agents/glossary_enricher/`, config
`configs/agents/glossary_enricher.yaml` — Italian output, unsuffixed per
`.claude/rules/agent-config-naming.md`) is invoked on every `GET .../explanation` call,
concurrently with `GlossaryReadRepository.candidates_for` (FR-3), never conditionally.
It receives the question's own `text` and `image_description` (answer-blind, mirroring
`QuestionExplainerRequest` — no `correct_answer`-derived field, structurally) and
returns a list of `{term, definition}` pairs, each written in the same simple Italian
register `question_explainer.yaml` already uses. It does not decide *whether* to run;
`ExplanationService` always calls it, and a genuinely term-free question yields an
empty list, which is a normal, non-error outcome.

### FR-2: Grounding reuses the existing legal-retrieval infrastructure, unchanged

Before generating, `ExplanationService` supplies `GlossaryEnricherAgent` with the same
dense+full-text candidate commas `CandidateSetService`
(`labeling/services/candidate_set_service.py`) already retrieves to ground the legal
explanation, obtained exactly the way `CommaSelectorService._label_live` already does
it:

1. `LiveLabelingStackProvider.quiz.find_with_vector(number, judge_identity.epoch
   .candidate_variant, EMBEDDING_MODEL_COLUMN)` — the identical call, same variant, same
   model column — returns the question's `QuizEvaluationRow`, or `None` if the question
   has no embedding for that variant yet (not indexed).
2. `None` is not a failure: `GlossaryEnricherAgent` still runs, with an empty list of
   candidate commas, and falls back to general knowledge for every term (FR-3) exactly
   as it would for a term no comma addresses. There is nothing special to catch here —
   an empty list is already a valid input.
3. Otherwise, `LiveLabelingStackProvider.candidate_set.execute(row)` — the same
   `CandidateSetService` instance `CommaSelectorService` resolves through the same
   provider — returns the two-arm union of `CandidateComma`s; only the wrapped
   `RetrievedComma` (`.comma`) is forwarded to `GlossaryEnricherRequest`, not the
   `dense_rank`/`text_rank` fields, which exist for a downstream judge this feature
   never runs.

**On `QuizEvaluationRow` carrying `correct_answer`** (resolved during grilling,
2026-09-25): `QuizEvaluationRow` does structurally carry `correct_answer: bool`
(`domain/models/retrieval/quiz_evaluation_row.py:20`), and an earlier draft of this FR
proposed bypassing `CandidateSetService` entirely to avoid that object ever entering
`_vocabulary_outcome`'s scope, mirroring spec 0020 AD-4's structural answer-blindness.
That draft was reconsidered and dropped: spec 0020's FR-2 itself already notes that
answer-blindness stopped being a privacy requirement once "Spiega" became reachable
only *after* the user has submitted and seen their own result — it survives today only
as a prompt-focus/testability convention, and that convention is about what
`GlossaryEnricherRequest` (the DTO actually sent to the LLM) contains, not about what
local variables `ExplanationService` briefly holds during retrieval.
`LabelingConfig.lexeme_fields`/the `LexemeField` enum (`domain/enums/lexeme_field.py`)
confirm `CandidateSetService.execute`'s own lexeme extraction never reads
`correct_answer` in practice either — the enum has no member for it. The guarantee this
spec keeps, and tests, is the same one `QuestionExplainerRequest` already has:
`GlossaryEnricherRequest` has no field derived from the answer, structurally.

### FR-3: General knowledge is a fallback, never a competing source

The agent is instructed to ground a term's definition in the supplied candidate commas
whenever one of them supports it, and to fall back to its own general knowledge only
for a term no supplied comma addresses. This is a prompt-level instruction, mirroring
`question_explainer.yaml`'s own existing "explain from your own knowledge without
quoting" allowance — it is not mechanically enforced by an `output_validator`, the same
way that existing allowance is not.

### FR-4: On-demand entries are ephemeral — never written to `glossary_entries`

`GlossaryEnricherAgent`'s output is used to build the merged candidate list for the
current request only (FR-6) and is discarded afterward. Nothing in this feature ever
inserts a row into `glossary_entries`; the offline `build-glossary` pipeline (spec
0019) remains the table's only writer, keeping ADR 0038's verbatim guarantee meaningful
for every row the table holds.

### FR-5: The merged list is what `QuestionExplainerAgent` sees — its own contract is unchanged

`ExplanationService._vocabulary_outcome` builds one `list[GlossaryCandidate]` from
`GlossaryReadRepository.candidates_for` (unchanged call) and
`GlossaryEnricherAgent`'s output (mapped into `GlossaryCandidate`s, FR-6), shuffles it
exactly as today, and hands it to `QuestionExplainerAgent` inside the existing
`QuestionExplainerRequest.candidates` field. `QuestionExplainerAgent`,
`QuestionExplainerRequest` and `QuestionExplainerResponse` are not modified by this
spec: the agent still just cites ordinals from whatever list it is given.

### FR-6: Merge gives DB-retrieved candidates priority on a normalized-term conflict

A new pure function (`utils/`, per `.claude/rules/utils-package-placement.md` —
standalone, stateless, no injected dependency) merges the two sources:

- Every DB-retrieved `GlossaryCandidate` (`origin=VERBATIM_CORPUS`, the new enum
  default, FR-8) is kept as-is.
- Each on-demand `{term, definition}` pair becomes a `GlossaryCandidate` with
  `origin=AGENT_GENERATED` (FR-8), *unless* its `term.strip().casefold()` already
  matches a DB-retrieved candidate's `term.strip().casefold()`, in which case it is
  dropped — the DB entry, extracted verbatim from the corpus, wins. The `.strip()` is
  load-bearing, not decorative (resolved during grilling, 2026-09-25, second round):
  bare `casefold()` alone does not normalize whitespace, so a term differing only by a
  stray leading/trailing space would otherwise NOT be recognized as the same term — see
  AD-6.
- Two on-demand entries sharing a normalized term (the agent should not produce this,
  but nothing outside this function enforces it) are both kept; the pre-existing
  `_deduplicated_hints` dedup (keyed the same way — `term.strip().casefold()`, also
  updated by this spec, see AD-6 — first-cited order) still applies downstream once
  `QuestionExplainerAgent` decides what to cite, unchanged otherwise.
- An on-demand `GlossaryCandidate` leaves `definition_plain` at its field default
  (`None`, added by spec 0022, now implemented) — the merge function never sets it.
  This is correct, not an oversight: spec 0022's `_deduplicated_hints` fallback
  (`candidate.definition_plain or candidate.definition`) then simply resolves to the
  on-demand agent's own `definition` unchanged, exactly like any other
  not-yet-simplified DB row.
- An on-demand `GlossaryCandidate` is built from only `term`/`definition` (the agent's
  output) plus `origin=AGENT_GENERATED` — after `GlossaryCandidate` is narrowed to the
  fields the vocabulary pipeline actually reads (AD-8), there is no DB-row identity
  field left to fake a value for.

### FR-7: A failure of the on-demand source degrades to DB-only candidates — a timeout does not distinguish sides

`_vocabulary_outcome` runs the DB retrieval and the on-demand agent call concurrently
via `asyncio.gather(..., return_exceptions=True)` — not `asyncio.TaskGroup`, so one
side's failure does not cancel the other. If `GlossaryReadRepository.candidates_for`
raises, the whole vocabulary stage degrades to `(None, ())`, exactly as it does today
(unchanged). If only `GlossaryEnricherAgent` raises a non-timeout exception (an agent
error, or `UnexpectedModelBehavior` once its own duplicate-term retry budget is
exhausted, AD-3), that failure is logged at `warning` and treated as an empty on-demand
list — the merge (FR-6) then trivially yields the DB-only candidates, and
`QuestionExplainerAgent` runs exactly as it does today without this feature.

**Resolved during grilling (2026-09-25, second round)**: there is exactly **one**
timeout for the whole stage — the existing inner `asyncio.timeout(vocabulary_deadline_s)`
that already wraps `_vocabulary_outcome`'s body today, unchanged, now wrapping the
`gather` call plus the merge/shuffle/`QuestionExplainerAgent` sequence that follows it.
An earlier draft of this FR implied the on-demand agent carries its own smaller
sub-budget ("its own share of the stage's inner timeout"), so that a slow enricher call
alone could degrade partially without affecting the DB branch. That draft was dropped:
no timeout anywhere else in this codebase (`LabelingService`, `ExplanationService`'s
outer deadline, this same inner one) uses a per-branch sub-budget — every one is a
single budget around a sequential or gathered `await`. When the shared timeout fires,
`asyncio.timeout` cancels *both* gathered branches at once (cancellation reaches the
awaiting task, not just the coroutines that happened to raise), so there is no way to
attribute the expiry to "only the enricher" — a timeout is therefore stage-level and
degrades the whole stage to `(None, ())`, exactly like a `GlossaryReadRepository`
failure. Only a non-timeout exception raised by `GlossaryEnricherAgent` itself is
isolated to its own contribution; a non-timeout exception raised by
`GlossaryReadRepository.candidates_for` still degrades the whole stage, unchanged. This
mirrors spec 0020's own principle (FR-5 there) that the vocabulary stage is additive,
best-effort value, applied one level deeper — narrowed to exception isolation only, not
timeout isolation.

### FR-8: Provenance is surfaced per cited term in the API response

A new enum, `GlossaryTermOrigin` (`enums/`, `StrEnum`, members `VERBATIM_CORPUS` and
`AGENT_GENERATED`, values from `auto()`), is added to:

- `GlossaryCandidate` — new field
  `origin: GlossaryTermOrigin = GlossaryTermOrigin.VERBATIM_CORPUS`. The default means
  `GlossaryReadRepository._row_to_candidate` need not pass `origin` explicitly at all;
  the merge function (FR-6) is the only caller that ever passes `AGENT_GENERATED`. This
  spec's `origin` is unrelated to `GlossaryCandidate.source` (`cds`/`cap`), which AD-8
  removes from the model entirely as part of the same change — the two were never at
  risk of being confused with each other, but `source` is gone regardless, for the
  independent reason AD-8 gives (unread outside the repository).
- `CitedGlossaryTerm` (domain model) and `CitedGlossaryTermResponse` (API schema) —
  both gain `origin: GlossaryTermOrigin`, populated by
  `ExplanationService._deduplicated_hints` from the candidate's own `origin` field
  (`candidate.origin`), alongside the `term`/`term_ru` it already copies and the
  `definition` it already builds via spec 0022's own
  `candidate.definition_plain or candidate.definition` fallback (implemented,
  `services/explanation_service.py:274-282`) — this spec only adds the `origin=`
  keyword to that same, already-landed constructor call, it does not touch the
  `definition` expression itself.

```json
{
  "translation_hints": [
    { "term": "carreggiata", "definition": "…", "term_ru": "…", "origin": "verbatim_corpus" },
    { "term": "revoca", "definition": "…", "term_ru": null, "origin": "agent_generated" }
  ]
}
```

No other part of `QuizExplanationResponse` changes. `origin` naming follows the
existing precedent of `ProvenanceResponse.origin` (comma-association provenance,
spec 0017) rather than reusing `source`.

## Non-Goals

- No new endpoint, no new request parameter on `GET .../explanation`.
- No gap-detection heuristic of any kind (score threshold, expected-term extraction) —
  the on-demand agent always runs (FR-1).
- No write-through of on-demand definitions to `glossary_entries`, ever (FR-4).
- No change to `GlossaryExtractorAgent`, `build-glossary`, or `translate-glossary-terms`.
- No change to `QuestionExplainerAgent`'s request/response contract (FR-5).
- No fuzzy/semantic dedup — normalized exact-match only (FR-6).
- No new retrieval infrastructure — grounding reuses `CandidateSetService`/
  `CorpusReadRepository` exactly as already wired for live comma labeling (FR-2).
- No bot-side (`guidami_ai_patente_bot`) change: the bot already renders
  `translation_hints` generically (spec 0020, FR-8); this spec only adds a field the
  bot is not required to render differently. Whether the bot should visually
  distinguish `agent_generated` hints is left to a future, separate decision.

## Architectural Decisions

### AD-1: Two independently-sourced glossary sets, merged before the writer agent sees them

Mirrors spec 0020's AD-1 shape (two independent producers, gathered concurrently, one
merged input) one level deeper: where spec 0020 gathers the *legal* and *vocabulary*
stages, this spec gathers the vocabulary stage's own two glossary sources *inside*
`_vocabulary_outcome`, before either reaches `QuestionExplainerAgent`. Keeping the
merge here, rather than teaching `QuestionExplainerAgent` about two sources, keeps that
agent's contract exactly what spec 0020 already tested and shipped.

### AD-2: Grounding reuses `LiveLabelingStackProvider.candidate_set` unmodified, fed by `quiz.find_with_vector`

`ExplanationService` gains `Autowired[LiveLabelingStackProvider]` (already a
`@provider` resolvable in this container, `providers/live_labeling_stack_provider.py`)
alongside its existing fields, and reads `.quiz.find_with_vector` then
`.candidate_set.execute` — the exact same two calls, in the exact same order, that
`CommaSelectorService._label_live` already makes for live comma labeling (FR-2). No new
pywire component, no new SQL, no new orchestration logic to reason about: this
feature's only new database interaction is the LLM call itself, and its only new
runtime logic is unwrapping `CandidateComma.comma` and handling `find_with_vector`'s
`None`. This choice trades a small cross-cutting dependency (the vocabulary stage now
touches a labeling-stack provider it did not touch before) for zero new retrieval code
to maintain and test — retrieval correctness for `article_commas` stays proven by
`CandidateSetService`'s and `CorpusReadRepository`'s own existing tests.

Grilling (2026-09-25) considered and rejected re-implementing the two-arm union
directly against `LiveLabelingStackProvider.corpus: CorpusReadRepository`, specifically
to avoid ever fetching a `QuizEvaluationRow` (which carries `correct_answer`) into
`_vocabulary_outcome`. Rejected once traced against spec 0020's own FR-2, which already
demoted answer-blindness from a privacy requirement to a testability convention once
"Spiega" became post-answer-only — see FR-2's "On `QuizEvaluationRow` carrying
`correct_answer`" note for the full reasoning.

### AD-3: `GlossaryEnricherAgent` is a new, distinct agent — not a reconfigured `GlossaryExtractorAgent`

Per the rejected-shapes discussion: `GlossaryExtractorAgent`'s verbatim
`output_validator` (ADR 0038) is not a switch to flip, it is the class's entire reason
to exist. `GlossaryEnricherAgent` gets its own config
(`configs/agents/glossary_enricher.yaml`, unsuffixed — Italian output, the project's
base language), its own request/response DTOs, and its own duplicate-term
`model_validator` (mirroring `QuestionExplainerResponse._reject_repeated_ordinals`'s
*pattern* — raise `ValueError` on a duplicate so pydantic-ai retries — confirmed during
grilling, 2026-09-25 — not conditional) — independent of `GlossaryExtractorAgent` in
every respect except sharing the general "agent extracts/generates term+definition
pairs" shape. Unlike the ordinal check it mirrors (which compares `int`s directly),
this validator's own dedup key is `term.strip().casefold()` (resolved during grilling,
2026-09-25, second round — see AD-6): the same normalization rule used everywhere else
this spec compares terms, applied here to catch the agent producing the same term
twice, once with different casing/whitespace, within one response.

### AD-4: Ephemeral by design — `glossary_entries` keeps one writer

Choosing not to write on-demand entries through to `glossary_entries` (FR-4) is a
direct consequence of ADR 0038: a table whose rows are guaranteed verbatim-extracted
from a known corpus chunk cannot also hold rows generated live, sometimes from general
knowledge, without a provenance column of its own on that table — which would be a
schema change to a table this spec has no reason to touch. Ephemeral generation avoids
that decision entirely; if a future spec wants persistence, it is a separate, explicit
schema change with its own migration, not a side effect of this one.

### AD-5: The new provenance field is named `origin`, after an existing precedent

`GlossaryCandidate.source` meant the corpus source (`cds`/`cap`) before this spec — a
name this spec's own `origin` was deliberately never going to reuse, to avoid silently
overloading it. AD-8 later removes `source` from the model outright (unread outside
`GlossaryReadRepository`), which makes the naming collision moot in the shipped code,
but the naming choice itself stands independently: `origin` (`GlossaryTermOrigin`) is
named after the existing `ProvenanceResponse.origin` precedent (spec 0017), not invented
fresh.

### AD-6: One normalization rule, `term.strip().casefold()`, used in every term comparison in the vocabulary stage

DB priority on conflict (FR-6). **Resolved during grilling (2026-09-25, second
round)**: the rule is `term.strip().casefold()`, not bare `term.casefold()` as an
earlier draft of this spec proposed (and as the pre-existing `_deduplicated_hints` key
already did, pre-dating this spec). Plain `casefold()` normalizes case but not
whitespace — `"sospensione ".casefold() != "sospensione".casefold()` — so a term
differing only by a stray leading/trailing space would not be recognized as a conflict,
contradicting this spec's own Testing section, which explicitly claims whitespace
variants are caught. Rather than scope the fix to only this spec's new merge function
(which would leave two slightly different term-equality rules in the same stage — the
exact duplication this AD originally set out to avoid), `term.strip().casefold()` is
now used in all three places a term is compared anywhere in the vocabulary stage:

- the new merge function (FR-6);
- the pre-existing `ExplanationService._deduplicated_hints` (spec 0020,
  `services/explanation_service.py:250-282`) — its key changes from `term.casefold()`
  to `term.strip().casefold()`, a one-line change to already-shipped code, made here
  specifically to keep this AD's "one rule for the whole stage" premise true rather
  than merely aspirational;
- `GlossaryEnricherResponse`'s own duplicate-term `model_validator` (AD-3).

A reader still only has to learn one term-equality rule for the whole vocabulary stage.

### AD-7: Partial degradation, scoped to exactly the on-demand agent's own failure

`asyncio.gather(..., return_exceptions=True)`, not `TaskGroup`, is a deliberate
departure from spec 0020's `_explain`-level use of `TaskGroup` (which *does* want a
sibling's failure to cancel the other, at that outer level). Here the two gathered
calls are independent value contributors to the *same* final list, and one existing
call (`GlossaryReadRepository.candidates_for`) already has its failure semantics fixed
by spec 0020 (degrade the whole stage) — this spec adds a second call whose *exception*
should degrade only its own contribution, which `TaskGroup`'s all-or-nothing
cancellation cannot express.

This isolation is scoped to exceptions only, not to the shared inner
`asyncio.timeout(vocabulary_deadline_s)` that still wraps the whole `gather` call
unchanged (resolved during grilling, 2026-09-25, second round — see FR-7): that timeout
has no per-branch sub-budget, so its expiry cancels both branches together and degrades
the whole stage, exactly as a `GlossaryReadRepository` failure does. `gather`'s
`return_exceptions=True` is what lets a *raised* exception from `GlossaryEnricherAgent`
be inspected and swallowed into an empty list instead of propagating — it does nothing
to change what a shared timeout cancels.

### AD-8: `GlossaryCandidate` is narrowed to the fields the vocabulary pipeline actually reads

Resolved during grilling (2026-09-25), replacing an earlier draft that gave an
`AGENT_GENERATED` candidate placeholder values (a negative synthetic `id`, sentinel
strings) for `GlossaryCandidate`'s DB-row-identity fields. A repo-wide search confirmed
`id`/`source`/`article_number`/`comma_number` are read nowhere outside
`GlossaryReadRepository` itself — the dense/full-text fusion these fields exist for
happens entirely in SQL (the `fused` CTE), before `_row_to_candidate` ever builds a
`GlossaryCandidate`. `GlossaryCandidate` is therefore trimmed to exactly
`term`/`definition`/`definition_plain`/`term_ru`/`origin` (FR-8) — a vocabulary
candidate, not a `glossary_entries` row projection — and `_row_to_candidate` still reads
all seven SQL columns (the four identity columns remain necessary for the query's own
fusion) but only forwards the five that matter onto the model. An on-demand candidate
then has exactly the same shape as a DB one, with no placeholder value anywhere. This
also updates the class's own docstring (`"One glossary_entries row a hybrid retrieval
returned"` no longer describes it accurately) and requires updating every existing test
that constructs a `GlossaryCandidate` with the four now-removed fields — an expected,
mechanical consequence of narrowing a model to its real readers, not a behavior change.

## Data Model

No new table, no new column on any existing table. All changes are Python-level:

- New `enums/glossary_term_origin.py`: `GlossaryTermOrigin(StrEnum)` — `VERBATIM_CORPUS`,
  `AGENT_GENERATED` (values via `auto()`, i.e. `"verbatim_corpus"`, `"agent_generated"`).
- `models/glossary_candidate.py`: `GlossaryCandidate` is narrowed (AD-8) to
  `term: str`, `definition: str`, `definition_plain: str | None = None` (spec 0022,
  already implemented), `term_ru: str | None`, and this spec's new
  `origin: GlossaryTermOrigin = GlossaryTermOrigin.VERBATIM_CORPUS` — dropping
  `id`/`source`/`article_number`/`comma_number`, confirmed unread outside
  `GlossaryReadRepository`. `origin` says *who produced* the candidate,
  `definition_plain` says *which register* its definition is in — an on-demand
  candidate has `origin=AGENT_GENERATED` and `definition_plain=None` (FR-6).
- `repositories/glossary_read_repository.py`: `_row_to_candidate` keeps reading all
  seven SQL columns (`_COLUMNS` is unchanged — the fusion CTEs still need `id`) but
  only forwards `term`/`definition`/`definition_plain`/`term_ru` onto the narrowed
  `GlossaryCandidate` (`origin` defaults to `VERBATIM_CORPUS`, untouched call site
  otherwise).
- `models/cited_glossary_term.py`: `CitedGlossaryTerm` gains
  `origin: GlossaryTermOrigin` (no default — always resolved explicitly from the
  candidate it was built from).
- `api/schemas/quiz_explanation.py`: `CitedGlossaryTermResponse` gains
  `origin: GlossaryTermOrigin`.
- New `agents/glossary_enricher/` package: `GlossaryEnricherAgent`,
  `GlossaryEnricherRequest` (question `text`, `image_description`, and `commas:
  list[RetrievedComma]` — the unwrapped `.comma` of each `CandidateComma`
  `LiveLabelingStackProvider.candidate_set.execute` returns, FR-2; no rank fields, this
  feature has no judge stage to rank for), `GlossaryEnricherResponse` (a list of
  `{term, definition}` entries, its own `model_validator` rejecting a duplicate
  `term.casefold()` within one response, mirroring
  `QuestionExplainerResponse._reject_repeated_ordinals` — response DTO, Italian
  docstring/`Field(description=...)` per the code-conventions exception for agent
  response DTOs).
- New `configs/agents/glossary_enricher.yaml`.
- New merge function, `utils/glossary/merge_glossary_candidates.py` (exact path/name
  left to implementation, following the precedent of `comma_repeal_detector`/
  `chunking` cited in `.claude/rules/utils-package-placement.md`).
- `services/explanation_service.py`: `ExplanationService` gains
  `enricher: Autowired[GlossaryEnricherAgent]` and
  `labeling_stack: Autowired[LiveLabelingStackProvider]` (AD-2); `_vocabulary_outcome`
  is restructured per FR-2/FR-6/FR-7, keeping its existing single inner
  `asyncio.timeout(vocabulary_deadline_s)` around the whole (now gathered) body,
  unchanged (FR-7). No new retrieval-depth config: the shared `candidate_set`
  instance's own `LabelingConfig.dense_k`/`text_k` apply, unchanged. `_deduplicated_hints`'s
  dedup key changes from `term.casefold()` to `term.strip().casefold()` (AD-6,
  resolved during grilling, 2026-09-25, second round) — its only change from this spec.

`term_ru` is always `None` for an `AGENT_GENERATED` candidate: this feature generates
Italian only, exactly like `GlossaryExtractorAgent` does before
`translate-glossary-terms` runs its own separate pass (spec 0019, AD-11).

## Constraints

- pywire field injection throughout (`.claude/rules/pywire-di.md`): the new agent, and
  `ExplanationService`'s two new `Autowired` fields.
- Router body stays a thin controller: no route changes at all (FR-1's field addition
  is served by the existing route unchanged).
- One class per file; the new enum lives in `enums/`, never in `models/`
  (`.claude/rules/code-conventions.md`); the merge function lives in `utils/`, never
  `services/` (`.claude/rules/utils-package-placement.md`) — it has no injected
  dependency.
- Agent config file unsuffixed (Italian, base language,
  `.claude/rules/agent-config-naming.md`).
- Response DTO (`GlossaryEnricherResponse`) docstring and `Field(description=...)` in
  Italian, per the agent-response-DTO exception in `.claude/rules/code-conventions.md`;
  its request DTO stays English.
- No `continue` in loops; lazy `%s`/`%r` logging arguments, levels used purposefully
  (`.claude/rules/logging.md`).
- Tests in `tests/` mirroring `src/`, no `__init__.py`, pytest, TDD.

## Testing

- **Agent-level** (`GlossaryEnricherAgent`, mirroring `question_explainer`'s test
  shape): grounds a definition in a supplied candidate comma when one is relevant;
  falls back to general knowledge, still producing an entry, when no supplied comma is
  relevant to a given term, and also when the supplied comma list is empty (FR-2's
  `find_with_vector` → `None` case); a duplicate `term.strip().casefold()` within one
  response (including a case/whitespace-only variant, not just an exact repeat) is
  rejected by `GlossaryEnricherResponse`'s own `model_validator` (AD-3), mirroring
  `test_question_explainer_response_rejects_repeated_ordinal`'s shape.
- **Merge function** (unit, pure, no fakes needed): a DB candidate and an on-demand
  entry sharing a normalized term — the on-demand one is dropped, the DB one keeps
  `origin=VERBATIM_CORPUS`; a non-conflicting on-demand entry is kept with
  `origin=AGENT_GENERATED` and `definition_plain=None`; an empty on-demand list returns
  the DB list unchanged; case *and* whitespace variants of the same term (e.g.
  `"Sospensione"` vs. `" sospensione "`) are still recognized as a conflict
  (`term.strip().casefold()`, AD-6).
- **`ExplanationService._deduplicated_hints`** (regression guard, resolved during
  grilling, 2026-09-25, second round): a whitespace-only variant of an already-seen
  term (not just a case variant) is now also deduplicated, since its key changed to
  `term.strip().casefold()` (AD-6) — add this case alongside the existing case-variant
  test for this method.
- **`ExplanationService._vocabulary_outcome`** (unit, fakes): (a) both sources succeed
  — the merged, shuffled list reaches `QuestionExplainerAgent` and a cited
  `AGENT_GENERATED` term surfaces with the right `origin` in the result; (b) the
  on-demand agent raises a non-timeout exception — the stage still returns a
  non-`None` `term_explanation` built from DB-only candidates, unchanged from spec
  0020's current behavior; (c) `GlossaryReadRepository.candidates_for` raises — the
  whole stage still degrades to `(None, ())`, exactly as today (regression guard: this
  spec must not change this existing behavior); (d)
  `LiveLabelingStackProvider.quiz.find_with_vector` returns `None` (not indexed under
  `candidate_variant`) — `GlossaryEnricherAgent` still runs, with an empty comma list,
  not a degrade (FR-2); (e) the shared inner timeout fires while the on-demand call is
  still running — the whole stage degrades to `(None, ())`, **not** a partial
  DB-only result (regression guard distinguishing this from case (b): a timeout is
  stage-level, an exception is branch-level — FR-7, resolved during grilling,
  2026-09-25, second round).
- **Endpoint** (`api_client`, fake agents): `GET .../explanation` response's
  `translation_hints` entries carry the correct `origin` for a DB-sourced and an
  agent-generated hint in the same response.
- **`GlossaryCandidate` narrowing** (AD-8, regression guard): every existing test
  constructing a `GlossaryCandidate` is updated to the five-field shape
  (`term`/`definition`/`definition_plain`/`term_ru`/`origin`); existing
  `GlossaryReadRepository._row_to_candidate` behavior is otherwise unchanged —
  `origin` defaults to `VERBATIM_CORPUS` without that call site passing it explicitly.
- **`GlossaryEnricherRequest`** (unit): has no field derived from the answer,
  structurally — same assertion shape as
  `test_question_explainer_request_has_no_answer_field` (spec 0020), confirming FR-2's
  guarantee holds regardless of what `ExplanationService` fetches internally to build
  it.

## Feasibility Evidence

Verified 2026-09-25 on branch `feat/backend`.

- **FR-1/FR-5/AD-1** — `agents/question_explainer/question_explainer_agent.py:1-66`,
  `agents/question_explainer/dto/question_explainer_request.py:1-51`,
  `agents/question_explainer/dto/question_explainer_response.py:1-38` (the unchanged
  contract this spec's merged candidate list feeds into).
- **FR-2/AD-2** — `services/comma_selector_service.py:56-127` (`CommaSelectorService
  ._label_live`'s exact `find_with_vector` → `candidate_set.execute` sequence, the call
  order this spec's `ExplanationService` addition mirrors verbatim);
  `providers/live_labeling_stack_provider.py:55-96` (`.corpus: CorpusReadRepository`,
  `.candidate_set: CandidateSetService`, `.quiz: QuizReadRepository`, all built once in
  `__init__`); `commons/repositories/db/quiz_read_repository.py:57-88`
  (`find_with_vector`'s signature and its `None` semantics — "no such question" and
  "no vector for this variant/model" both collapse to `None`, confirmed the caller must
  treat that as "not indexed", not an error); `domain/models/retrieval/
  quiz_evaluation_row.py:1-24` (confirmed `QuizEvaluationRow.correct_answer: bool` is
  present structurally — the fact this spec's FR-2 note and AD-2 discuss); `domain/
  enums/lexeme_field.py` (confirmed `LexemeField` has no member for `correct_answer`/
  `rule_explanation`/`core_concepts` — `topic`/`text`/`image_description` only,
  `configs/labeling.yaml:11`); `labeling/services/candidate_set_service.py:1-51`
  (`CandidateSetService.execute`, dense+text union, no `correct_answer` anywhere in its
  signature or body); `commons/repositories/db/corpus_read_repository.py:103-144,225-252`
  (`dense_top_k`, `text_match_top_k`, `extract_lexemes` — confirmed answer-blind,
  parameterized only by embedding/lexemes/`k`); `db/init.sql:33,78,249` (`article_commas
  .embedding`, `quiz_question_embeddings.embedding_3_small`, `glossary_entries
  .embedding_3_small` all `VECTOR(1536)` — confirmed the same embedding space, relevant
  only to the rejected bypass draft, kept for the record).
- **FR-4/AD-3/AD-4** — glossary extraction verbatim contract, quoted from
  `docs/second-brain/adr/0038-glossary-extraction-mechanical-verbatim-and-chunking.md:38-45`
  via the `second-brain:second-brain-reader` subagent this session dispatched; ADR 0036
  ("glossary is a new, independently-owned derived table") from the same dispatch.
- **FR-6/AD-6** — `services/explanation_service.py:250-282`
  (`_deduplicated_hints`, the existing `term.casefold()` dedup key and first-cited-order
  behavior this spec's merge step is written to stay consistent with; current version,
  post spec 0022, already builds `definition=candidate.definition_plain or
  candidate.definition` at line 278 — this spec adds `origin=` to that same call, per
  the Coordinates-with note in the header).
- **FR-7/AD-7** — `services/explanation_service.py:192-248` (`_vocabulary_outcome`'s
  current single-`try` shape, the one inner `asyncio.timeout`, and the class docstring
  at `services/explanation_service.py:80-97` explaining why `TaskGroup` is used one
  level up in `_explain` but not appropriate for this spec's two independent,
  same-stage calls).
- **FR-8/AD-5** — `models/glossary_candidate.py:1-24` (confirmed `source` (pre-AD-8)
  means CdS/CAP, not provenance, and that `definition_plain: str | None = None` — spec
  0022, implemented — already sits alongside it); `api/schemas/quiz_explanation.py:25-53`
  (`ProvenanceResponse.origin`, the naming precedent this spec's new field follows;
  `CitedGlossaryTermResponse`'s current shape, still `term`/`definition`/`term_ru` only
  — spec 0022 confirmed to add no field there, per its own Non-Goals).
- **AD-8 (grilling, 2026-09-25)** — a repo-wide `Grep` for `candidate.id`/`candidate
  .source`/`candidate.article_number`/`candidate.comma_number` across `src/` returned no
  matches: confirmed these four `GlossaryCandidate` fields are read nowhere outside
  `glossary_read_repository.py` itself, which is what makes narrowing the model safe.
  `repositories/glossary_read_repository.py:13-16,88-109` (`_COLUMNS`, `_row_to_candidate`
  — confirmed the SQL fusion needs `g.id` in the query, not on the returned Python
  object).
- **Spec 0022 (re-verification pass, 2026-09-25)** — confirmed implemented and merged
  (`git log`: `30d122c7`…`769aab21`, spec status `ready`/sign-off recorded). Read the
  real, current `models/glossary_candidate.py`, `repositories/glossary_read_repository.py`
  (`_COLUMNS`/`_row_to_candidate`, now at lines 13-16/88-109) and
  `services/explanation_service.py:250-282` to confirm none of this spec's decisions
  (FR-1 through FR-8, AD-1 through AD-7) are invalidated by spec 0022's landed changes —
  only line-number citations and the FR-6/FR-8/Data Model text above needed updating to
  describe the current, post-0022 shape of `GlossaryCandidate` and `_deduplicated_hints`.
  `CitedGlossaryTerm`/`CitedGlossaryTermResponse` confirmed still exactly as this spec
  originally described (spec 0022 added no field to either).
- **Constraints** — `.claude/rules/pywire-di.md` (`@provider`/`Autowired` conventions);
  `.claude/rules/agent-config-naming.md` (unsuffixed = Italian/base language);
  `.claude/rules/utils-package-placement.md` (merge function's placement);
  `.claude/rules/code-conventions.md` (enums in `enums/`; response-DTO Italian
  exception).
- **Spec 0020 precedent** —
  `docs/superpowers/specs/2026-09-21-question-explanation-design.md` (AD-1, AD-8,
  FR-5, the shapes this spec's AD-1/AD-7/FR-7 explicitly mirror or deliberately
  depart from, with the departure justified in each case).

## Open Questions

Every previously-open question about the grounding-retrieval integration, the
candidate placeholder scheme, the duplicate-term validator and retrieval depths was
resolved during the 2026-09-25 grilling round — see AD-2, AD-3, AD-8, FR-2 and the
Changelog. What remains genuinely deferrable to implementation:

- [ ] **non-blocking** — Exact prompt text for `GlossaryEnricherAgent` (how many terms
  to surface per question, how strongly to prefer corpus grounding, register) and its
  model/config (proposed: same `openrouter/google/gemini-2.5-flash` as its siblings) —
  left to implementation, tuned on real output.
- [ ] **non-blocking** — Whether the bot should visually distinguish an
  `agent_generated` hint from a `verbatim_corpus` one in the rendered glossary block
  (spec 0020, FR-8) — out of this spec's scope (Non-Goals); left to a future, separate
  decision if the plain-text distinction ever matters to a user.
- [ ] **non-blocking** — No cap on the merged candidate list's total size beyond
  `GlossaryReadRepository`'s existing `max_candidates` on its own DB-side arm
  (confirmed during grilling: the on-demand agent typically surfaces only the handful
  of terms the DB missed, not an exhaustive extraction, so practical overflow is
  expected to be rare) — revisit only if `QuestionExplainerAgent`'s prompt cost proves
  to be a real problem in practice.

## Follow-ups after implementation

- Run `second-brain:update` (`architecture.md`, `patterns.md`) to record: the
  two-source merge-with-priority pattern for a live LLM stage combined with a
  precomputed table, and `ExplanationService`'s new dependency on
  `LiveLabelingStackProvider` for read-only retrieval reuse outside the labeling flow
  itself.
- Record an ADR (`second-brain:adr`) for: generating supplementary glossary candidates
  live and merging them with DB priority instead of gap-detection-then-fill, and for
  keeping them ephemeral rather than write-through, given `glossary_entries`' verbatim
  contract (ADR 0038). Fold in the AD-2/FR-2 finding from the grilling round while
  writing it: spec 0020's vocabulary-stage answer-blindness is a testability
  convention, not a privacy boundary, now that "Spiega" is post-answer-only — worth
  recording once so a future feature in this stage doesn't re-derive it from scratch.
- Update the `CLAUDE.md` API endpoints table's description of `GET
  /{number}/explanation` to mention `translation_hints[].origin`.

## Sign-off

- **Scope approved by user:** yes, 2026-09-25 — spec written 2026-09-25 from an
  interactive `superpowers:brainstorming` session, then stress-tested via
  `mattpocock-skills:grilling` across two separate rounds the same day; the user
  confirmed shared understanding at the end of both, then asked to proceed to
  `writing-plans` directly, taken as sign-off. Per the status lifecycle note above,
  `Status` itself (draft → ready) is left for the user to update explicitly rather than
  changed by this skill.
- **Feasibility asserted:** by the assistant on 2026-09-25, re-verified three times the
  same day — once after spec 0022 landed, once during the first grilling round's own
  investigation (AD-2, AD-8), once during the second grilling round (FR-7 timeout
  structure, AD-6 whitespace normalization) — based on the Feasibility Evidence above
  (direct source reads plus one `second-brain:second-brain-reader` dispatch for
  glossary-system ADRs).
- **Definition of Done verified:** not yet — pending implementation.

## Changelog

- **2026-09-25 (grilling, second round)** — Stress-tested again via
  `mattpocock-skills:grilling`, one question at a time. Resolved: (1) FR-7's "own share
  of the stage's inner timeout" language for the on-demand agent was a design gap, not
  an implementation detail — no timeout anywhere else in this codebase carries a
  per-branch sub-budget, and a single shared `asyncio.timeout` wrapping
  `asyncio.gather(...)` cancels both branches together on expiry, so it cannot be
  attributed to "only the enricher" as originally worded. Resolved to: one shared inner
  timeout (unchanged from today), whose expiry degrades the whole stage exactly like a
  `GlossaryReadRepository` failure; only a *non-timeout* exception from
  `GlossaryEnricherAgent` is isolated to its own contribution. (2) The stated dedup
  guarantee ("case/whitespace variants... recognized as a conflict") was not actually
  achieved by bare `term.casefold()`, which normalizes case but not whitespace — fixed
  by using `term.strip().casefold()` everywhere a term is compared in the vocabulary
  stage: the new merge function (FR-6), the pre-existing `_deduplicated_hints` (a
  one-line change to already-shipped spec-0020 code, AD-6), and
  `GlossaryEnricherResponse`'s own duplicate-term `model_validator` (AD-3). Updated:
  FR-6, FR-7 (rewritten), AD-3, AD-6 (rewritten), AD-7, Data Model
  (`explanation_service.py` bullet), Testing (new/split cases for the timeout-vs-
  exception distinction and the whitespace regression guard), Sign-off.
- **2026-09-25 (grilling)** — Stress-tested via `mattpocock-skills:grilling`, one
  question at a time per this project's CLAUDE.md override. Resolved: (1) grounding
  retrieval reuses `CandidateSetService` exactly as originally planned in AD-2 (an
  intermediate draft proposed bypassing it to avoid `QuizEvaluationRow`'s
  `correct_answer` field entirely; reconsidered and dropped once traced against spec
  0020's own FR-2, which already demoted answer-blindness from a privacy requirement to
  a testability convention — see FR-2's new note and AD-2); (2) the embedding variant
  for that retrieval is `judge_identity.epoch.candidate_variant`, the same one grounding
  the legal explanation, not `"text"`; (3) `find_with_vector` returning `None`
  (not-indexed) yields an empty comma list and the agent still runs, not a degrade;
  (4) no new retrieval-depth config — the shared `candidate_set` instance's own depths
  apply; (5) `GlossaryCandidate` is narrowed to
  `term`/`definition`/`definition_plain`/`term_ru`/`origin` (new AD-8), dropping
  `id`/`source`/`article_number`/`comma_number` after a repo-wide search confirmed they
  are read nowhere outside `GlossaryReadRepository` — replaces the earlier
  placeholder-value draft entirely, no sentinel scheme needed; (6) `GlossaryEnricherResponse`
  gets its own duplicate-term `model_validator`, confirmed, not conditional; (7) no cap
  on the merged candidate list's total size, for now. Updated: FR-2 (rewritten with the
  concrete integration and the answer-blindness note), FR-6, AD-2/AD-3 (rewritten), new
  AD-8, Data Model (`GlossaryCandidate` narrowing, `GlossaryEnricherRequest`'s `commas:
  list[RetrievedComma]` shape), Testing (new cases), Feasibility Evidence (new citations:
  `quiz_read_repository.py`, `quiz_evaluation_row.py`, `lexeme_field.py`,
  `configs/labeling.yaml`, `db/init.sql`'s embedding columns), Open Questions (four
  items resolved and removed), Follow-ups (one ADR item added).
- **2026-09-25 (later)** — Re-verified feasible after spec 0022 (plain-language
  glossary definitions) landed and was merged, since both specs touch
  `GlossaryCandidate`, `CitedGlossaryTerm`/`CitedGlossaryTermResponse` and
  `ExplanationService._deduplicated_hints`. Outcome: **still fully implementable, no
  design change** — spec 0022 added `GlossaryCandidate.definition_plain` (defaulted
  `None`) and a `definition_plain or definition` fallback inside the very constructor
  call this spec's FR-8 adds `origin=` to; the two fields are independent and compose
  without conflict (FR-6). Updated: header (new "Coordinates with" row), FR-6 (on-demand
  candidates leave `definition_plain` at its spec-0022 default), FR-8/Data Model (the
  `origin=` addition now described against the real, current constructor and model
  shape), and every Feasibility Evidence line-number citation that had shifted because
  of spec 0022's edits to the same files. `CitedGlossaryTerm`/`CitedGlossaryTermResponse`
  confirmed unchanged by spec 0022, exactly as it promised in its own Non-Goals.
- **2026-09-25** — Initial draft, from an interactive `superpowers:brainstorming`
  session (detection-mechanism, grounding, trigger, write-through, new-agent,
  dedup-key, retrieval-reuse and provenance-granularity decisions all made
  conversationally, one question at a time, per this project's CLAUDE.md override of
  brainstorming's default batching).
