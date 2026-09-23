# ADR 0035: Gather the vocabulary explanation as a second, independent LLM stage inside the existing explanation endpoint

## Status

Proposed

## Context

`GET /quiz-questions/{number}/explanation` (spec 0017) rendered exactly one LLM
call — the legal explanation, via `ExplanationWriterAgent`, bounded by
`AppConfig.explanation_deadline_s`. Spec 0020 added a second capability: an
answer-blind explanation of the question's own wording and technical terms
(`QuestionExplainerAgent`, grounded on the new `glossary_entries` table via
`GlossaryReadRepository`), meant to render alongside the legal explanation in the
same bot message (three sections: vocabulary prose, legal prose, a glossary block).

The two stages are genuinely independent: the vocabulary stage never needs the
legal stage's result (or the answer at all — it is deliberately answer-blind, AD-4),
and the legal stage never needs the vocabulary stage's result. But a bug in the new,
additive vocabulary stage must never be able to degrade or take down the already-
shipped, already-live legal-explanation path.

## Decision

`ExplanationService._explain` splits into `_legal_outcome` (the unchanged spec-0017
path) and `_vocabulary_outcome` (new), run concurrently via `asyncio.gather(legal,
vocabulary)`, both still bounded by the single existing `explanation_deadline_s`
timeout (`src/guidami_ai_patente/services/explanation_service.py`). Three properties
are load-bearing:

1. **Gathered, not sequenced** — wall-clock latency is `max(legal, vocabulary)`, not
   their sum.
2. **One shared deadline, not two independent budgets** — the endpoint's worst-case
   latency contract to callers is unchanged by adding a second LLM call.
3. **`_vocabulary_outcome` never raises** — its entire body (the DB read via
   `QuizQuestionRepository.find_question_vocabulary_context`, the retrieval call via
   `GlossaryReadRepository.candidates_for`, and the `QuestionExplainerAgent.run` call)
   sits inside one blanket `try/except Exception`, degrading to `(None, ())` and
   logging a `warning` on any failure. This is what makes the vocabulary stage
   additive rather than a new outage surface for the legal stage: `asyncio.gather`
   only cancels its sibling task if one of the awaited coroutines itself raises, and
   this one structurally cannot.

A fourth, related decision: candidates from `GlossaryReadRepository` (RRF-ordered) are
shuffled once (`random.shuffle`, no fixed seed) before being shown to
`QuestionExplainerAgent`, and the same shuffled list object is reused afterward to
resolve `cited_term_numbers` ordinals back into `CitedGlossaryTerm`s — never re-fetched
or independently re-shuffled, or the ordinals would silently resolve to the wrong
terms.

## Alternatives considered

- **A separate new endpoint** (e.g. `GET /quiz-questions/{number}/vocabulary`) instead
  of extending the existing explanation response. Rejected — the bot's own rendering
  wants both sections composed into one message; a separate endpoint would force the
  bot into two round trips with independent timeout/failure handling just to render
  one screen, and would duplicate the answer-lookup plumbing `_explain` already does
  once.
- **Sequence the two stages** (legal, then vocabulary) instead of gathering them.
  Rejected — the two calls share no data dependency, so sequencing would only add
  latency (their sum instead of their max) for no correctness benefit.
- **Give the vocabulary stage its own, independent deadline** (wider or narrower than
  `explanation_deadline_s`) rather than sharing the existing one. Rejected — a second,
  independent timeout would let the endpoint's total worst-case latency grow whenever
  the vocabulary stage's own budget is the looser of the two, silently widening the
  contract every caller of `/explanation` already depends on.
- **Let a vocabulary-stage failure propagate** (matching how a legal-stage failure
  becomes a 503 via `ExplanationUnavailableError`) instead of degrading silently.
  Rejected — the vocabulary stage is additive; a caller that already worked before
  spec 0020 must keep working identically if the new stage misbehaves, so failure
  there degrades the response, it does not fail the request.

## Consequences

Adding a second LLM stage costs no additional worst-case latency budget and cannot
regress the existing legal-explanation guarantee — verified both by task review
(tracing the `try/except` boundary against every call inside `_vocabulary_outcome`)
and by a real-model smoke test showing a legal-stage refusal (`insufficient_knowledge`)
still carrying a real, independently-computed vocabulary explanation.

The cost: the vocabulary stage's own failure mode is invisible to the API response —
a caller cannot distinguish "no glossary term applied to this question" from "the
vocabulary stage crashed" from the response alone; both currently degrade to
`term_explanation: null` only when nothing could be said at all (an empty retrieval
plus nothing to add), while a genuine crash also produces a non-null but generic
`term_explanation` in most cases — both are visible only via the `warning` log line,
never surfaced to the client. If per-cause visibility becomes a real product need
later, that is a new, separate decision (a status field on the response, or similar),
not implied by this one.
